"""W1 知识库构建流水线 (分类/抽取/关联/质检).

multi-agent 设计: 规则 → LLM 两级兜底, Vision 由 MinerU (配置可用时) 处理扫描件。
每个文件产出 0..N 张实体卡片 (is_audited=false), 全部进人审队列。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

from services.models import (
    KbFile, KbBuildTask, KbCertificate, KbPersonnel,
    KbPersonnelCertificate, KbAchievement, KbFinancial, KbCredit,
    KbEdge,
)
from services.kb.extractors import classify_category, extract_by_category

TEXT_PARSABLE_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".rtf", ".xlsx", ".pptx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# ============ 1. 文本提取 (文本 → MinerU OCR 兜底) ============


def extract_file_text(file_path: str, ext: str) -> tuple[str, str, int]:
    """提取文件全文。返回 (text, method, page_count)。
    method: text=普通解析, vision=MinerU OCR, empty=无可用方法。"""
    ext = ext.lower()
    try:
        if ext in TEXT_PARSABLE_EXTS:
            from core.doc_engine import get_parser
            parser = get_parser(ext)
            parsed = parser.parse(file_path)
            text = parsed.text or ""
            page_count = parsed.metadata.get("page_count") if parsed.metadata else 0
            return text, "text", page_count or 0

        # 图片: MinerU OCR
        if ext in IMAGE_EXTS:
            text = _ocr_with_mineru(file_path)
            return text, "vision", 1

        # 其他扩展名尝试默认文本解析
        try:
            from core.doc_engine import get_parser
            parsed = get_parser(ext).parse(file_path)
            return (parsed.text or ""), "text", 0
        except Exception:
            return "", "empty", 0
    except Exception as e:
        logger.warning(f"文本解析失败 {file_path}: {e}")
        return "", "empty", 0


async def _ocr_with_mineru(file_path: str) -> str:
    """MinerU OCR (cloud 或 self_hosted)。失败静默返回空。"""
    try:
        from core.ocr.mineru_client import get_mineru_client
        settings = None
        try:
            from core.settings import get_settings
            settings = get_settings()
        except Exception:
            pass
        if settings and not (settings.mineru_api_key or settings.mineru_mode == "self_hosted"):
            return ""
        client = get_mineru_client()
        result = await client.extract(file_path)
        # result 结构: {markdown/文本字段}
        text = (
            result.get("markdown")
            or result.get("text")
            or result.get("content")
            or ""
        )
        return str(text)
    except Exception as e:
        logger.warning(f"MinerU OCR 失败: {e}")
        return ""


# ========================================================== 3. LLM 兜底结构化

_LLM_STRUCTURE_PROMPT = """你是投标资质库的字段抽取助手。请从提供的证件/文档文本中抽取结构化字段。

【约束】
- 只输出 JSON, 不要输出其他文字
- 只填写文本中**明确存在**的字段, 找不到的字段必须给空字符串或 0
- 禁止编造: 文本没有的编号/日期/金额一律留空
- 关键字段缺失时, 在 not_found 数组里说明缺什么 (如 "有效期", "证书编号")

【子库: {category}】请输出 schema:
{category_schema}

【文档文本】(可截断)
{text}
"""

_CAT_SCHEMA = {
    "certificate": """{
  "name": "证书名称",
  "number": "证书编号",
  "category": "enterprise | personnel | financial",
  "level": "等级",
  "scope": "覆盖范围/业务范围",
  "holder": "持证主体",
  "issue_date": "颁发日期 YYYY-MM-DD",
  "expiry_date": "有效期至 YYYY-MM-DD (空=长期)",
  "issuing_authority": "发证机关",
  "not_found": ["缺失字段清单"]
}""",
    "achievement": """{
  "project_name": "项目名称",
  "client_name": "业主/甲方",
  "contract_no": "合同编号",
  "contract_amount": "合同金额(统一万元, 数字)",
  "sign_date": "签订日期 YYYY-MM-DD",
  "completion_date": "验收/完工日期 YYYY-MM-DD",
  "project_scope": "项目内容 50字内",
  "project_type": "项目类型",
  "not_found": ["缺失字段清单"]
}""",
    "personnel": """{
  "name": "姓名",
  "gender": "男/女",
  "title": "职称",
  "role": "拟派岗位",
  "id_number": "身份证号",
  "dept": "部门",
  "not_found": ["缺失字段清单"]
}""",
    "financial": """{
  "report_type": "audit_report | financial_statement | tax",
  "period_start": "期初 YYYY-MM-DD",
  "period_end": "期末 YYYY-MM-DD",
  "year": 2025,
  "total_assets": "资产总额(万元, 数字)",
  "revenue": "营业收入(万元, 数字)",
  "net_profit": "净利润(万元, 数字)",
  "debt_ratio": "资产负债率(%, 数字)",
  "audit_agency": "审计机构",
  "not_found": ["缺失字段清单"]
}""",
    "credit": """{
  "credit_type": "aaa_certificate | award | no_violation | credit_check_snapshot",
  "title": "证书/报告名称",
  "check_date": "查询/报告日期 YYYY-MM-DD",
  "result": "结果",
  "not_found": ["缺失字段清单"]
}""",
}


class KbPipeline:
    """单次构建流水线: 对一个公司的若干未解析文件做 提取→分类→结构化→入库。"""

    def __init__(self, db, company_id: str, task: KbBuildTask, llm=None):
        self.db = db
        self.company_id = company_id
        self.task = task
        self.llm = llm
        self.edge_count = 0

    def _add_edge(self, src_type, src_id, edge_type, dst_type, dst_id,
                  confidence=0.5, audited=False):
        self.db.add(KbEdge(
            company_id=self.company_id,
            src_type=src_type, src_id=src_id, edge_type=edge_type,
            dst_type=dst_type, dst_id=dst_id,
            confidence=confidence, source="agent_inferred", is_audited=audited,
        ))
        self.edge_count += 1

    async def run(self, file_ids: list[str]) -> dict:
        from sqlalchemy import select
        result = await self.db.execute(
            select(KbFile).where(KbFile.id.in_(file_ids), KbFile.company_id == self.company_id)
        )
        files = result.scalars().all()
        self.task.total_files = len(files)
        self.task.status = "running"
        self.task.started_at = datetime.utcnow()
        await self.db.flush()

        created_entities = 0
        processed = 0

        for kb_file in files:
            # 回滚后 ORM 对象会被 expire, 先取出只读属性避免异步惰性加载
            filename = kb_file.filename
            try:
                if kb_file.parse_status == "parsed":
                    # 已解析过的文件跳过, 保证任务重跑幂等 (不重复建卡)
                    processed += 1
                    self.task.processed_files = processed
                    continue
                # 单文件用 SAVEPOINT 隔离: 任一 flush 失败只回滚本文件,
                # 否则整个 Session 变 pending-rollback, 后续文件与任务状态更新全部失效
                async with self.db.begin_nested():
                    created_entities += await self._process_file(kb_file)
                processed += 1
                self.task.processed_files = processed
            except Exception as e:
                logger.exception(f"处理文件失败 {filename}: {e}")
                kb_file.parse_status = "failed"
                kb_file.error = str(e)[:500]
                await self.db.flush()

        self.task.processed_files = processed
        self.task.created_entities = created_entities
        self.task.created_edges = self.edge_count
        self.task.finished_at = datetime.utcnow()
        self.task.status = "done"
        await self.db.flush()
        return {
            "task_id": str(self.task.id),
            "total": len(files),
            "processed": processed,
            "created_entities": created_entities,
            "created_edges": self.edge_count,
        }

    async def _process_file(self, kb_file: KbFile) -> int:
        """处理单个文件: 提取→分类→结构化→建卡片。返回创建的卡片数。"""
        from services.llm_factory import get_llm_gateway

        kb_file.parse_status = "parsing"
        await self.db.flush()

        path = kb_file.stored_path
        if not Path(path).exists():
            kb_file.parse_status = "failed"
            kb_file.error = "文件不存在于磁盘"
            return 0

        ext = (kb_file.ext or Path(kb_file.filename).suffix or "").lower()

        # 1) 文本提取
        text, method, pages = extract_file_text(path, ext)
        kb_file.extracted_text = text[:200000]  # 防止超大文本入库
        kb_file.parse_method = method
        kb_file.page_count = pages

        if not text.strip():
            kb_file.parse_status = "parsed"  # 无文本, 待人工上传可读件/填 OCR
            kb_file.category = "unknown"
            kb_file.page_count = pages
            await self.db.flush()
            return 1  # 保留文件行 (标注未解析), 人审时处理

        # 2) 分类 (规则)
        category = classify_category(kb_file.filename, text[:4000])
        kb_file.category = category

        # 3) 结构化抽取 (规则 → LLM 兜底)
        extracted = None
        try:
            extracted = extract_by_category(category, text, kb_file.filename)
        except Exception:
            extracted = None

        use_llm = not extracted and self.llm is not None
        if use_llm:
            extracted = await self._llm_extract(category, text)

        if not extracted:
            # 占位: 建一个空卡片打进人审队列, 标记待补全
            await self._create_placeholder_card(kb_file, category, text)
            kb_file.parse_status = "parsed"
            await self.db.flush()
            return 1

        payload, confidence = extracted
        # 规则抽取返回 {子库: 字段dict}, LLM 已解包; 统一取内层扁平字段
        if isinstance(payload, dict) and isinstance(payload.get(category), dict):
            payload = payload[category]
        created = await self._create_card(kb_file, category, payload, confidence)
        kb_file.parse_status = "parsed"
        await self.db.flush()
        return created

    async def _llm_extract(self, category: str, text: str):
        prompt = _LLM_STRUCTURE_PROMPT.format(
            category=category,
            category_schema=_CAT_SCHEMA.get(category, ""),
            text=text[:6000],
        )
        try:
            data = await self.llm.collect_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            if not isinstance(data, dict):
                return None
            # 以子库名为 key 兜底
            inner = data.get(category) or data
            return (inner, 0.4)  # LLM 抽取置信度默认 0.4
        except Exception as e:
            logger.warning(f"LLM 抽取失败 {category}: {e}")
            return None

    async def _create_placeholder_card(self, kb_file, category, text) -> None:
        """无法抽取时建占位卡片, scope 标注待人工补全原因。"""
        if category == "certificate":
            self.db.add(KbCertificate(
                company_id=self.company_id, file_id=kb_file.id,
                name=kb_file.filename.rsplit(".", 1)[0][:300],
                status="needs_completion", is_audited=False,
                extra={"need_reason": "文本太少或结构不清晰", "text_head": text[:200]},
            ))
        elif category == "achievement":
            self.db.add(KbAchievement(
                company_id=self.company_id, file_ids=[str(kb_file.id)],
                project_name=kb_file.filename.rsplit(".", 1)[0][:500],
                is_audited=False, extra={"need_reason": "文本太少或结构不清晰"}))
        elif category == "personnel":
            self.db.add(KbPersonnel(
                company_id=self.company_id, file_id=kb_file.id,
                name="待补全", is_audited=False,
                extra={"need_reason": "无法从文档确认人员信息", "text": text[:200]}))
        elif category == "financial":
            self.db.add(KbFinancial(
                company_id=self.company_id, file_id=kb_file.id,
                report_type="need_review", is_audited=False,
                extra={"need_reason": "文本不足以抽取财务字段", "text": text[:200]}))
        elif category == "credit":
            self.db.add(KbCredit(
                company_id=self.company_id, file_id=kb_file.id,
                credit_type="need_review", is_audited=False,
                extra={"need_reason": "文本不足以抽取信用字段", "text": text[:200]}))

    async def _create_card(self, kb_file, category, payload, confidence, audited=False) -> int:
        """把抽取结果写入实体表。返回写入行数。"""
        src = "ocr" if kb_file.parse_method == "vision" else "manual"
        if category == "certificate":
            self.db.add(KbCertificate(
                id=str(uuid.uuid4()), company_id=self.company_id, file_id=kb_file.id,
                name=payload.get("name") or kb_file.filename.rsplit(".", 1)[0][:300],
                number=payload.get("number", ""),
                category=payload.get("category", "enterprise"),
                level=payload.get("level", ""),
                scope=payload.get("scope", ""),
                holder=payload.get("holder", ""),
                issue_date=payload.get("issue_date", ""),
                expiry_date=payload.get("expiry_date", ""),
                issuing_authority=payload.get("issuing_authority", ""),
                status=_compute_status(payload.get("expiry_date")),
                raw_text=kb_file.extracted_text[:20000] if kb_file.extracted_text else None,
                is_audited=audited,
                source=src,
                confidence=confidence,
            ))
            return 1
        elif category == "achievement":
            self.db.add(KbAchievement(
                id=str(uuid.uuid4()), company_id=self.company_id, file_ids=[str(kb_file.id)],
                project_name=payload.get("project_name") or kb_file.filename.rsplit(".", 1)[0][:500],
                client_name=payload.get("client_name", ""),
                contract_no=payload.get("contract_no", ""),
                contract_amount=float(payload.get("contract_amount") or 0),
                sign_date=payload.get("sign_date", ""),
                completion_date=payload.get("completion_date", ""),
                year=int(payload.get("year") or 0),
                project_scope=payload.get("project_scope", ""),
                project_type=payload.get("project_type", ""),
                is_audited=audited, source=src,
                confidence=confidence,
            ))
            return 1
        elif category == "personnel":
            personnel = KbPersonnel(
                id=str(uuid.uuid4()), company_id=self.company_id, file_id=kb_file.id,
                name=payload.get("name") or "未命名",
                id_number_enc=payload.get("id_number", ""),
                gender=payload.get("gender", ""),
                title=payload.get("title", ""),
                role=payload.get("role", ""),
                dept=payload.get("dept", ""),
                is_audited=audited, source=src,
                confidence=confidence,
            )
            self.db.add(personnel)

            # 人员资质/证书: 同一文档常含软考证书, 一并抽出 (团队优化器数据源)
            created = 1
            from services.kb.extractors import extract_personnel_certs
            for c in extract_personnel_certs(kb_file.extracted_text or ""):
                person_cert = KbPersonnelCertificate(
                    id=str(uuid.uuid4()),
                    company_id=self.company_id,
                    personnel_id=personnel.id,
                    cert_type=c["cert_type"],
                    cert_type_code=c["cert_type_code"],
                    level=c["level"], cert_no=c["cert_no"],
                    issue_date=c["issue_date"], expiry_date=c["expiry_date"],
                    status=_compute_status(c["expiry_date"]),
                    file_id=kb_file.id, is_audited=audited, source=src,
                    confidence=0.5,
                )
                self.db.add(person_cert)
                self._add_edge("personnel", personnel.id, "holds",
                               "personnel_certificate", person_cert.id,
                               audited=audited)
                created += 1
            return created
        elif category == "financial":
            self.db.add(KbFinancial(
                id=str(uuid.uuid4()), company_id=self.company_id, file_id=kb_file.id,
                report_type=payload.get("report_type", "financial_statement"),
                period_start=payload.get("period_start", ""),
                period_end=payload.get("period_end", ""),
                year=int(payload.get("year") or 0),
                total_assets=float(payload.get("total_assets") or 0),
                revenue=float(payload.get("revenue") or 0),
                net_profit=float(payload.get("net_profit") or 0),
                debt_ratio=float(payload.get("debt_ratio") or 0),
                audit_agency=payload.get("audit_agency", ""),
                is_audited=audited, source=src,
                confidence=confidence,
            ))
            return 1
        elif category == "credit":
            self.db.add(KbCredit(
                id=str(uuid.uuid4()), company_id=self.company_id, file_id=kb_file.id,
                credit_type=payload.get("credit_type", "credit_check_snapshot"),
                title=payload.get("title", ""),
                check_date=payload.get("check_date", ""),
                result=payload.get("result", ""),
                is_audited=audited, source=src,
                confidence=confidence,
            ))
            return 1
        return 0


def _compute_status(expiry: str) -> str:
    """按有效期计算 status: valid/expiring(≤90天)/expired。空=valid。"""
    if not expiry:
        return "valid"
    try:
        d = datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date()
    except ValueError:
        return "valid"
    td = (d - date.today()).days
    if td < 0:
        return "expired"
    if td <= 90:
        return "expiring"
    return "valid"