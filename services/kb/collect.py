"""W2 公开采集: 按企业名搜索已接公告源 → 解析中标/未中标记录 → 去重 → 业绩预填人审队列。

设计 (2026-10-10 实测):
- Epoint WebBuilder 平台的 ES 检索接口支持按关键词全文检索公告正文:
  fields="content" + noWd=false + wd=企业名。noWd 默认 true 会忽略 wd (实测踩坑),
  必须显式置 false 才生效。
- 企业名不在标题里而在正文, 所以必须搜 content 而非 title。
- 正文含中标候选人/报价/招标人 → 结构化解析后**判定我方角色** (中标/未中标/仅提及),
  不能"命中即中标": 招标代理机构也常出现在正文。
- 政采多标段公告: 表头 "中标（成交）金额(元)" 后跟多行供应商, 我方可能不在第一行,
  必须逐行判定 (实测六盘山高中/唐徕中学等公告踩坑)。
- 未中标记录 (参与未中标/废标) 同样采集, 用于复盘 (设计文档要求)。
- 全部记录进人审队列 (is_audited=false), 人工确认后入业绩库。
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

import httpx

from services.news.dedup import NewsDeduplicator
from services.news.field_extractor import extract_region, extract_project_code

logger = logging.getLogger(__name__)

_WS = re.compile(r"[\s ]+")
# 机构名: 以常见机构后缀结尾, 允许括号/字母数字
_ORG = (r"[一-龥A-Za-z0-9（）()]{2,40}?(?:公司|局|处|院|校|大学|学院|中学|小学|幼儿园|"
        r"中心|集团|厂|站|所|社|部|银行|队|政府|办|厅|委|署|会)")

# 公告标题后缀 (从项目名剥离)
_TITLE_SUFFIX_RE = re.compile(r"(中标候选人)?(中标|成交|结果|废标|流标)?(公示|公告|通知书|结果公告|候选人公示)$")

# 中标人抽取模式 (按优先级)
# 1) 政府采购中标公告: "三、中标（成交）信息 / 供应商名称 供应商地址 供应商联系电话 中标（成交）金额(元)" 后紧跟中标供应商行
_GOV_WINNER_RE = re.compile(
    r"中标.{0,4}金额[^一-龥]{0,3}[（(]元[)）]\s*(" + _ORG + r")\s+(\S+)\s+(\S+)\s+([\d,，.]+)")
# 政采中标公告表头 (用于定位中标供应商表, 支持 "中标（成交）金额(元)" / "中标金额(元)")
_GOV_HEADER_RE = re.compile(r"中标\s*(?:[（(]\s*成交\s*[)）])?\s*金额\s*[（(]\s*元\s*[)）]")
# 2) 候选人公示: "第一中标候选人  单位名  金额元"
_WINNER_TABLE_RE = re.compile(r"第一中标候选人\s+(" + _ORG + r")\s+([\d,，.]+)\s*元")
# 3) 文字型: "中标人：xxx / 中标供应商 xxx"
_WINNER_PATTERNS = [
    re.compile(r"(?:第一中标候选人|第一成交候选人|中标人|中标供应商|成交供应商|中标单位)\s*(?:名称)?\s*[:：]?\s*(" + _ORG + ")"),
    re.compile(r"(?:中标人|中标供应商|成交供应商|中标单位)\s*(?:名称)?\s*[:：]\s*(" + _ORG + ")"),
    # 单供应商政采公告 / 单一来源: "供应商名称：X" / "拟定供应商信息 名称：X"
    re.compile(r"(?:拟定)?供应商\s*(?:信息)?\s*名称\s*[:：]\s*(" + _ORG + ")"),
]
# 评分/排名表: 提取第一名 (用于判定我方是否"参与未中标")
_RANK_WINNER_RES = [
    re.compile(r"排名第[一1]\s*(" + _ORG + ")"),
    re.compile(r"(" + _ORG + r")\s+[\d.]+\s+排名第[一1]"),
]
_OWNER_RE = re.compile(r"受\s*(" + _ORG + r")\s*的?委托")
# 政府采购公告尾部: "采购人信息 名 称： X"
_OWNER_INFO_RE = re.compile(r"采购人信息\s*名\s*称\s*[:：]\s*(" + _ORG + ")")
_OWNER_KW_RE = re.compile(r"(?:招\s*标\s*人|采\s*购\s*人|业主单位|采购单位)\s*[:：]\s*(" + _ORG + ")")
_AMOUNT_RE = re.compile(
    r"(?:中标金额|成交金额|中标价|成交价|投标报价|中标\s*[（(]\s*成交\s*[)）]\s*金额)"
    r"\s*[:：]?\s*([\d,，.]+)\s*(万元|元)")
_DATE_RE = re.compile(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})")
_PUBDATE_RE = re.compile(r"发布日期\s*[:：]\s*(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})")
# 未中标/废标信号
_REJECT_RE = re.compile(r"(符合性审查[^。]{0,30}(不通过|未通过)|作无效投标|无效投标处理|被否决|否决投标|废标)")
# 中标结果类公告标题 (我方出现即"参与未中标", 采集用于复盘)
_AWARD_TITLE_RE = re.compile(r"中标|成交|结果|废标|流标")


def _norm(t: str) -> str:
    return _WS.sub(" ", (t or "").replace("&nbsp;", " ")).strip()


def _to_wan(num: str, unit: str) -> Optional[float]:
    try:
        v = float(num.replace(",", "").replace("，", ""))
    except ValueError:
        return None
    return round(v if unit == "万元" else v / 10000.0, 4)


def _mentioned_in_reject(text: str, company: str) -> bool:
    """判断我方名是否出现在"符合性审查不通过/无效投标/否决"语境附近 (未中标信号)。"""
    for m in _REJECT_RE.finditer(text):
        seg = text[max(0, m.start() - 60): m.end() + 60]
        if company in seg:
            return True
    return False


def _is_scored_bidder(text: str, company: str) -> bool:
    """公司名后紧跟评分(如 "公司名 76.42") → 评标表里的投标人 (参与未中标)。"""
    return bool(re.search(re.escape(company) + r"\s+\d{1,3}\.\d{1,2}(?=\s|$)", text))


# 政采中标公告表体行: "供应商名 地址 电话 金额" (多标段时表头后跟多行)
# 地址常含空格("宁安南街 490 号 IBI 育成中心"), 故用电话号(7+位数字/连字符)作分隔锚点
_GOV_ROW_RE = re.compile(r"(" + _ORG + r")\s+(.*?)\s+([\d\-]{7,})\s+([\d,，.]+)")
# 中文编号小节 (用于限定表体范围, 如 "四、主要标的信息")
_SECTION_RE = re.compile(r"[一二三四五六七八九十]+、")


def _gov_winner_amount(text: str, company: str) -> Optional[float]:
    """政采中标公告: 判断我方是否在"中标供应商"表中, 命中返回我方中标金额(万元)。

    表头 "中标（成交）金额(元)" 后跟多行 "供应商名 地址 电话 金额"; 多标段时
    我方可能在第 2/3 行, 只看第一行会漏采 (实测六盘山高中等公告)。
    用中文编号小节限定表体范围, 避免把"主要标的信息/评审专家"里的名字误判。
    """
    mh = _GOV_HEADER_RE.search(text)
    if not mh:
        return None
    seg = text[mh.end(): mh.end() + 2000]
    ms = _SECTION_RE.search(seg)
    if ms:
        seg = seg[:ms.start()]
    for m in _GOV_ROW_RE.finditer(seg):
        if m.group(1) == company:
            v = _to_wan(m.group(4), "元")
            return v if v is not None else 0.0
    return None


def parse_award(content: str, title: str, url: str, company_name: str,
                webdate: str = "") -> Optional[dict]:
    """从公告正文判定我方角色并抽取业绩字段。

    返回 None 表示正文未出现该公司名 (非相关公告, 丢弃)。
    role: winner(中标)/owner(招标代理)/rejected(废标)/candidate_other(他人中标)/
          participated(参与未中标)/mentioned(纯提及, 如监督方)
    """
    t = _norm(content)
    if not company_name or company_name not in t:
        return None

    winner = ""
    amount: Optional[float] = None

    m = _GOV_WINNER_RE.search(t)
    if m:
        winner = m.group(1)
        amount = _to_wan(m.group(4), "元")
    if not winner:
        m2 = _WINNER_TABLE_RE.search(t)
        if m2:
            winner = m2.group(1)
            amount = _to_wan(m2.group(2), "元")
    if not winner:
        for pat in _WINNER_PATTERNS:
            mm = pat.search(t)
            if mm:
                winner = mm.group(1)
                break
    if not winner:
        # 评分/排名表: 第一名即中标人 (用于判定我方是否参与未中标)
        for pat in _RANK_WINNER_RES:
            mm = pat.search(t)
            if mm:
                winner = mm.group(1)
                break
    if amount is None:
        ma = _AMOUNT_RE.search(t)
        if ma:
            amount = _to_wan(ma.group(1), ma.group(2))

    owner = ""
    mo = _OWNER_RE.search(t) or _OWNER_INFO_RE.search(t) or _OWNER_KW_RE.search(t)
    if mo:
        owner = mo.group(1)

    # 公告日期: 优先"发布日期", 其次正文首个日期, 最后 webdate 兜底
    date = ""
    md = _PUBDATE_RE.search(t) or _DATE_RE.search(t)
    if md:
        date = f"{md.group(1)}-{int(md.group(2)):02d}-{int(md.group(3)):02d}"
    elif webdate:
        date = str(webdate)[:10]

    project_name = _TITLE_SUFFIX_RE.sub("", title or "").strip() or title

    # 政采中标供应商表: 我方可能不在第一行, 逐行判定 (命中即 winner, 并取我方金额)
    gov_amount = _gov_winner_amount(t, company_name)
    if gov_amount is not None:
        winner = company_name
        amount = gov_amount

    # 角色判定
    c = company_name
    role = "mentioned"
    if c == winner:
        role = "winner"
    elif c == owner:
        role = "owner"
    elif _mentioned_in_reject(t, c):
        role = "rejected"
    elif "中标候选人" in t and winner and c != winner:
        role = "candidate_other"
    elif _AWARD_TITLE_RE.search(title or "") and winner and c != winner:
        # 中标结果类公告 + 已识别出他人中标 → 我方参与但未中标 (复盘用)
        role = "participated"
    elif _is_scored_bidder(t, c):
        # 评标得分表里的投标人 (有分无名次) → 我方参与未中标
        role = "participated"

    bid_result = "win" if role == "winner" else (
        "loss" if role in ("rejected", "candidate_other", "participated") else "")

    return {
        "project_name": project_name[:500],
        "client_name": owner[:300],
        "contract_amount": amount or 0.0,
        "winner_name": winner[:300],
        "source_url": url,
        "announce_date": date,
        "project_scope": "",
        "project_type": "",
        "region": extract_region(t),
        "bid_result": bid_result,
        "role": role,
        "year": int(date[:4]) if date else 0,
    }


async def search_epoint(page_url: str, api_path: str, keyword: str,
                        max_items: int = 30, timeout: int = 25) -> list[dict]:
    """Epoint ES 检索接口按关键词全文检索公告正文, 自动翻页拉取直到拿满或达上限。

    max_items 为总上限 (跨页累计); 单页最多 30 条, 逐页累加。
    """
    if not page_url or not api_path or not keyword:
        return []
    base = "/".join(page_url.split("/", 3)[:3])  # scheme://host
    api_url = base + api_path
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
        "Origin": base,
        "Referer": page_url,
    }
    page_size = min(30, max_items)
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False, headers=headers) as client:
            pn = 0
            while len(out) < max_items:
                payload = {
                    "token": "", "pn": pn, "rn": page_size, "sdt": "", "edt": "",
                    "wd": keyword, "inc_wd": "", "exc_wd": "",
                    "fields": "content",       # 企业名在正文, 必须搜 content
                    "cnum": "",
                    "sort": '{"webdate":"0"}',
                    "ssort": "", "cl": 20000, "terminal": "",
                    "condition": [], "time": None, "highlights": "",
                    "statistics": None, "unionCondition": None,
                    "accuracy": "", "noParticiple": "0",
                    "searchRange": None,
                    "noWd": False,             # 关键: 默认 true 会忽略 wd
                    "isBusiness": "1",
                }
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result") or {}
                records = result.get("records") or []
                if not records:
                    break
                out.extend(records)
                total = int(result.get("totalcount") or 0)
                pn += page_size
                if len(out) >= total:
                    break
    except Exception as e:
        logger.warning(f"Epoint 关键词检索失败 {api_url}: {e}")
    return out[:max_items]


def _load_epoint_sources(source_codes: Optional[list[str]] = None) -> list[dict]:
    """取启用的 epoint 类源 (支持关键词检索的已接源)。

    source_codes 为空/None → 全部 enabled 的 epoint 源; 指定 → 仅这些 code。
    """
    from services.news.source_registry import get_all_sources
    codes = source_codes or None
    out = []
    for s in get_all_sources():
        if (s.get("type") or "").lower() != "epoint":
            continue
        if codes is None:
            if not s.get("enabled", True):
                continue
        elif s.get("code") not in codes:
            continue
        if not (s.get("config") or {}).get("api_path"):
            continue
        out.append(s)
    return out


class KbCollectPipeline:
    """W2 公开采集流水线: 搜企业名 → 解析 → 去重 → 建业绩卡片(待审)。"""

    def __init__(self, db, company_id: str, task, company_name: str,
                 source_codes: Optional[list[str]] = None, max_per_source: int = 30):
        self.db = db
        self.company_id = company_id
        self.task = task
        self.company_name = company_name
        self.source_codes = source_codes
        self.max_per_source = max_per_source

    async def run(self) -> dict:
        from datetime import datetime
        from sqlalchemy import select
        from services.models import KbAchievement

        self.task.status = "running"
        self.task.started_at = datetime.utcnow()
        await self.db.flush()

        sources = _load_epoint_sources(self.source_codes)
        if not sources:
            self.task.status = "failed"
            self.task.error = "没有可用的关键词检索源 (epoint)"
            await self.db.flush()
            return {"error": self.task.error}

        # 已入库指纹 (公司内) —— 跨源/跨次去重
        existing_fps = set((await self.db.execute(
            select(KbAchievement.fingerprint).where(
                KbAchievement.company_id == self.company_id,
                KbAchievement.fingerprint != "",
            )
        )).scalars().all())

        total_found = 0
        parsed = 0
        created = 0
        dup = 0
        seen_fps: set[str] = set()
        used_codes: list[str] = []

        for src in sources:
            code = src.get("code", "")
            cfg = src.get("config") or {}
            records = await search_epoint(
                src.get("url", ""), cfg.get("api_path", ""),
                self.company_name, self.max_per_source,
            )
            if not records:
                continue
            used_codes.append(code)
            total_found += len(records)
            src_name = src.get("name", "")

            for rec in records:
                title = str(rec.get("title") or "").strip()
                content = str(rec.get("content") or "")
                link = str(rec.get("linkurl") or "").strip()
                from urllib.parse import urljoin
                url = urljoin(src.get("url", ""), link) if link else ""

                item = parse_award(content, title, url, self.company_name,
                                   webdate=str(rec.get("webdate") or ""))
                if not item:
                    continue
                parsed += 1

                # 指纹去重: 复用资讯指纹策略 (项目编号 > 标题+业主 > URL)
                fp = NewsDeduplicator.compute_fingerprint({
                    "project_code": extract_project_code(content),
                    "title": item["project_name"],
                    "owner_org": item["client_name"],
                    "url": url,
                })
                if fp in seen_fps or fp in existing_fps:
                    dup += 1
                    continue
                seen_fps.add(fp)

                # 只入"我方相关"记录: 中标/未中标/参与未中标 都算参与证据 (复盘用);
                # 招标代理(owner) 与纯提及(mentioned, 如监督方/评分表列名) 不算业绩, 跳过
                if item["role"] in ("owner", "mentioned"):
                    continue

                # 未中标记录无我方合同金额, 清空避免污染业绩算分
                if item["role"] != "winner":
                    item["contract_amount"] = 0.0

                self.db.add(KbAchievement(
                    id=str(uuid.uuid4()),
                    company_id=self.company_id,
                    project_name=item["project_name"],
                    client_name=item["client_name"],
                    contract_amount=item["contract_amount"],
                    winner_name=item["winner_name"],
                    source_url=item["source_url"],
                    announce_date=item["announce_date"],
                    region=item["region"],
                    year=item["year"],
                    bid_result="win" if item["role"] == "winner" else "loss",
                    fingerprint=fp,
                    is_audited=False,
                    source="public_agent",
                    confidence=0.6 if item["role"] == "winner" else 0.35,
                    extra={"role": item["role"], "collected_from": src_name,
                           "source_code": code},
                ))
                created += 1
            await self.db.flush()

        self.task.total_found = total_found
        self.task.parsed = parsed
        self.task.created_entities = created
        self.task.duplicated = dup
        self.task.source_codes = used_codes
        self.task.status = "done"
        self.task.finished_at = datetime.utcnow()
        await self.db.flush()
        return {
            "task_id": str(self.task.id),
            "sources": used_codes,
            "total_found": total_found,
            "parsed": parsed,
            "created": created,
            "duplicated": dup,
        }
