"""知识库 (KB) 路由 — 工作空间 / 子库 / 上传构建 / 人审队列 / 证书字典 / 到期提醒。

设计: 公司=多租户空间 (company_id 贯穿); 一切 agent 产出先进人审队列
(is_audited=false); 人工确认后 is_audited=true 才进自动勾对池。
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.database import get_db
from services.middleware.api_key import require_any_auth, AuthPrincipal
from services.models import (
    KbAchievement,
    KbAnalysisReport,
    KbBuildTask,
    KbCertificate,
    KbCertType,
    KbCollectTask,
    KbCompany,
    KbCredit,
    KbEdge,
    KbFile,
    KbFinancial,
    KbPersonnel,
    KbPersonnelCertificate,
    KbScreeningCorrection,
    KbScreeningResult,
    HotspotItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_any_auth)])

ALLOWED_EXTS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".rtf",
    ".xlsx", ".pptx", ".jpg", ".jpeg", ".png", ".webp", ".bmp",
    ".tif", ".tiff",
}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50MB

# 存储根: 可被 BMP_KB_FILES_ROOT 覆盖
# 默认 ./uploads/kb —— 落在 compose 共享卷 uploads 内, 保证 api 上传的文件 celery-worker 可读
KB_ROOT = os.environ.get("BMP_KB_FILES_ROOT", "./uploads/kb")

# 子库 → 卡片模型
_CARD_MODELS = {
    "certificate": KbCertificate,
    "personnel": KbPersonnel,
    "achievement": KbAchievement,
    "financial": KbFinancial,
    "credit": KbCredit,
}

# 子库 → 可展示字段
_CARD_FIELDS = {
    "certificate": ["id", "name", "number", "category", "level", "scope",
                    "holder", "issue_date", "expiry_date", "issuing_authority",
                    "status", "is_audited", "confidence", "source"],
    "personnel": ["id", "name", "gender", "title", "role", "dept", "phone",
                  "is_audited", "confidence", "source"],
    "achievement": ["id", "project_name", "client_name", "contract_no",
                    "contract_amount", "sign_date", "completion_date", "year",
                    "project_scope", "project_type", "bid_result", "winner_name",
                    "source_url", "announce_date", "is_audited", "confidence", "source"],
    "financial": ["id", "report_type", "period_start", "period_end", "year",
                  "total_assets", "revenue", "net_profit", "debt_ratio",
                  "audit_agency", "is_audited", "confidence", "source"],
    "credit": ["id", "credit_type", "title", "holder", "check_date",
               "result", "is_audited", "confidence", "source"],
}


# ================= 工具函数 =================

def _iso(v) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _uuid_hex() -> str:
    return uuid.uuid4().hex[:12]


def _company_dir(company_id: str) -> Path:
    return Path(KB_ROOT) / str(company_id)


async def _get_company(company_id: str, db: AsyncSession) -> KbCompany:
    row = (await db.execute(
        select(KbCompany).where(KbCompany.id == company_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    return row


def _company_c(c: KbCompany) -> dict:
    return {
        "id": str(c.id), "name": c.name, "short_name": c.short_name,
        "unified_social_code": c.unified_social_code,
        "legal_person": c.legal_person, "industry_code": c.industry_code,
        "region": c.region, "contact": c.contact, "description": c.description,
        "is_default": c.is_default,
        "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at),
    }


def _save_bytes(company_id: str, filename: str, data: bytes, rel_dir: str = "") -> Path:
    """落盘到 ./kb_files/{company_id}/{rel_dir}/{filename}, 重名加后缀。"""
    target_dir = Path(KB_ROOT) / str(company_id)
    if rel_dir:
        target_dir = target_dir / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    target = target_dir / safe_name
    if target.exists():
        target = target_dir / f"{target.stem}_{_uuid_hex()}{target.suffix}"
    target.write_bytes(data)
    return target


# ================= 工作空间 CRUD =================

class CompanyCreate(BaseModel):
    name: str
    short_name: str = ""
    unified_social_code: str = ""
    legal_person: str = ""
    industry_code: str = ""
    region: str = ""
    contact: str = ""
    description: str = ""


class CompanyUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    unified_social_code: str | None = None
    legal_person: str | None = None
    industry_code: str | None = None
    region: str | None = None
    contact: str | None = None
    description: str | None = None


@router.get("/companies")
async def list_companies(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(KbCompany).order_by(KbCompany.created_at.desc())
    )).scalars().all()
    return {"companies": [_company_c(c) for c in rows]}


@router.post("/companies")
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    principal: AuthPrincipal = Depends(require_any_auth),
):
    exists = (await db.execute(
        select(KbCompany).where(KbCompany.name == payload.name)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="工作空间已存在(同名)")

    first = (await db.execute(select(func.count(KbCompany.id)))).scalar() or 0
    company = KbCompany(
        name=payload.name, short_name=payload.short_name,
        unified_social_code=payload.unified_social_code,
        legal_person=payload.legal_person,
        industry_code=payload.industry_code or "12",
        region=payload.region, contact=payload.contact,
        description=payload.description,
        created_by=principal.identifier,
    )
    db.add(company)
    await db.flush()
    _company_dir(str(company.id)).mkdir(parents=True, exist_ok=True)
    return _company_c(company)


@router.get("/companies/{company_id}")
async def get_company(company_id: str, db: AsyncSession = Depends(get_db)):
    return _company_c(await _get_company(company_id, db))


@router.patch("/companies/{company_id}")
async def update_company(
    company_id: str,
    payload: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
):
    c = await _get_company(company_id, db)
    for field in ("name", "short_name", "unified_social_code", "legal_person",
                  "industry_code", "region", "contact", "description"):
        val = getattr(payload, field, None)
        if val is not None:
            setattr(c, field, val)
    await db.flush()
    return _company_c(c)


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str, db: AsyncSession = Depends(get_db)):
    c = await _get_company(company_id, db)
    # 级联清理: 先子后父 (FK 指向 kb_companies.id), 再删来源文件与磁盘
    for model in (
        KbEdge, KbPersonnelCertificate, KbPersonnel, KbCertificate,
        KbAchievement, KbFinancial, KbCredit, KbFile, KbBuildTask,
    ):
        await db.execute(delete(model).where(model.company_id == company_id))
    await db.delete(c)
    await db.flush()
    company_dir = _company_dir(company_id)
    if company_dir.exists():
        import shutil
        shutil.rmtree(company_dir, ignore_errors=True)
    return {"success": True}


# ================= 子库卡片读取 =================

@router.get("/companies/{company_id}/cards")
async def list_cards(
    company_id: str,
    category: str = "certificate",
    audit: str = "all",          # all/unaudited/audited
    status: str = "",
    q: str = "",
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    await _get_company(company_id, db)
    model = _CARD_MODELS.get(category)
    if not model:
        raise HTTPException(status_code=400, detail=f"未知子库: {category}")

    stmt = select(model).where(model.company_id == company_id)
    if audit == "unaudited":
        stmt = stmt.where(model.is_audited == False)  # noqa: E712
    elif audit == "audited":
        stmt = stmt.where(model.is_audited == True)   # noqa: E712
    if status and category in ("certificate", "personnel") and hasattr(model, "status"):
        stmt = stmt.where(model.status == status)
    if q:
        like = f"%{q}%"
        cols = [col for col in (
            getattr(model, "name", None),
            getattr(model, "project_name", None),
            getattr(model, "number", None),
            getattr(model, "cert_no", None),
        ) if col is not None]
        if cols:
            stmt = stmt.where(or_(*[col.ilike(like) for col in cols]))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(model.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    return {
        "category": category, "total": total, "limit": limit, "offset": offset,
        "cards": [{f: getattr(r, f, None) for f in _CARD_FIELDS[category]} for r in rows],
    }


# ================= 图谱视图 =================

def _graph_label(cat: str, r) -> tuple[str, str]:
    """卡片 → (主标签, 副标签), 用于图谱节点显示。"""
    if cat == "certificate":
        return (r.name or "证书", " · ".join(x for x in [r.number, r.level] if x))
    if cat == "personnel":
        return (r.name or "人员", " · ".join(x for x in [r.title, r.role] if x))
    if cat == "achievement":
        return (r.project_name or "业绩", r.client_name or "")
    if cat == "financial":
        return (f"{r.year} 财务报表" if r.year else (r.report_type or "财务"), r.report_type or "")
    if cat == "credit":
        return (r.title or r.credit_type or "信用", r.check_date or "")
    return ("卡片", "")


@router.get("/companies/{company_id}/graph")
async def get_graph(
    company_id: str,
    audit: str = "all",          # all/audited
    db: AsyncSession = Depends(get_db),
):
    """公司资质全景图谱: 节点=实体卡片(按子库), 边=关系(kb_edges)。"""
    await _get_company(company_id, db)

    def _nid(t: str, i: str) -> str:
        return f"{t}:{i}"

    nodes: list[dict] = []
    node_ids: set[str] = set()

    # 5 子库主卡片
    for cat, model in _CARD_MODELS.items():
        stmt = select(model).where(model.company_id == company_id)
        if audit == "audited":
            stmt = stmt.where(model.is_audited == True)  # noqa: E712
        for r in (await db.execute(stmt)).scalars().all():
            label, sub = _graph_label(cat, r)
            nid = _nid(cat, str(r.id))
            nodes.append({
                "id": nid, "type": cat, "label": label, "sub": sub,
                "audited": bool(r.is_audited),
                "status": getattr(r, "status", "") or "",
            })
            node_ids.add(nid)

    # 人员证书 (人员簇叶子节点, 供 holds 边落点)
    pcert_stmt = select(KbPersonnelCertificate).where(
        KbPersonnelCertificate.company_id == company_id)
    if audit == "audited":
        pcert_stmt = pcert_stmt.where(KbPersonnelCertificate.is_audited == True)  # noqa: E712
    for r in (await db.execute(pcert_stmt)).scalars().all():
        nid = _nid("personnel_certificate", str(r.id))
        nodes.append({
            "id": nid, "type": "personnel_certificate",
            "label": r.cert_type or "人员证书", "sub": r.cert_no or "",
            "audited": bool(r.is_audited), "status": r.status or "",
        })
        node_ids.add(nid)

    # 关系边 (仅两端节点都可见时)
    edges = []
    for e in (await db.execute(
        select(KbEdge).where(KbEdge.company_id == company_id)
    )).scalars().all():
        s, d = _nid(e.src_type, str(e.src_id)), _nid(e.dst_type, str(e.dst_id))
        if s in node_ids and d in node_ids:
            edges.append({
                "id": str(e.id), "src": s, "dst": d,
                "edge_type": e.edge_type, "audited": bool(e.is_audited),
            })

    stats = {cat: sum(1 for n in nodes if n["type"] == cat) for cat in _CARD_MODELS}
    stats["personnel_certificate"] = sum(1 for n in nodes if n["type"] == "personnel_certificate")
    return {"nodes": nodes, "edges": edges, "stats": stats}


# ================= 上传 + 构建任务 =================

@router.post("/companies/{company_id}/upload")
async def upload_files(
    company_id: str,
    file: UploadFile = File(...),
    auto_build: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    """单文件上传 → 建 KbFile + 触发 W1 构建流水线。"""
    await _get_company(company_id, db)
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {MAX_FILE_BYTES // 1024 // 1024}MB")

    filename = Path(file.filename or "unnamed").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    sha = _sha256(content)
    dup = (await db.execute(
        select(KbFile).where(
            KbFile.company_id == company_id, KbFile.sha256 == sha
        )
    )).scalar_one_or_none()
    if dup:
        # 同一文件已入库: 去重返回已有记录
        return {"success": True, "file_id": str(dup.id), "task_id": None, "duplicated": True}

    saved = _save_bytes(company_id, filename, content, rel_dir="")
    kb_file = KbFile(
        company_id=company_id, filename=filename, rel_dir="",
        stored_path=str(saved), file_size=len(content), ext=ext,
        sha256=sha, parse_status="pending",
    )
    db.add(kb_file)
    await db.flush()

    task_id = await _trigger_build(db, company_id, [str(kb_file.id)]) if auto_build else None
    return {"success": True, "file_id": str(kb_file.id), "task_id": task_id}


@router.post("/companies/{company_id}/upload-folder")
async def upload_folder(
    company_id: str,
    file: UploadFile = File(...),           # .zip 整包
    auto_build: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    """ZIP 整包上传: 保留目录结构(Obsidian 式), 逐文件建 KbFile + 触发 W1。"""
    await _get_company(company_id, db)
    content = await file.read()
    if len(content) > MAX_FILE_BYTES * 2:
        raise HTTPException(status_code=413, detail="ZIP 超过 100MB 上限")

    file_ids: list[str] = []
    existing_shas: set[str] = set((await db.execute(
        select(KbFile.sha256).where(KbFile.company_id == company_id)
    )).scalars().all())
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for member in zf.namelist():
                member_name = member.replace("\\", "/")
                if member_name.startswith("/") or ".." in member_name.split("/"):
                    continue  # 防 zip slip
                if member.endswith("/"):
                    continue
                filename = Path(member_name).name
                ext = Path(filename).suffix.lower()
                if not filename or ext not in ALLOWED_EXTS:
                    continue
                data = zf.read(member)
                if len(data) > MAX_FILE_BYTES:
                    continue
                sha = _sha256(data)
                if sha in existing_shas:
                    continue  # 已入库去重
                parent = Path(member_name).parent
                parent_rel = "" if str(parent) == "." else str(parent)
                saved = _save_bytes(company_id, filename, data, rel_dir=parent_rel)
                kb_file = KbFile(
                    company_id=company_id, filename=filename, rel_dir=parent_rel,
                    stored_path=str(saved), file_size=len(data), ext=ext,
                    sha256=sha, parse_status="pending",
                )
                db.add(kb_file)
                await db.flush()
                file_ids.append(str(kb_file.id))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="上传文件不是有效的 ZIP")

    if not file_ids:
        if existing_shas:
            # 包内文件均已入库 (按 sha256 去重)
            return {"success": True, "file_count": 0, "file_ids": [], "task_id": None,
                    "duplicated": True}
        raise HTTPException(
            status_code=400,
            detail="ZIP 内没有支持的文件 (支持: " + ", ".join(sorted(ALLOWED_EXTS)) + ")",
        )

    task_id = await _trigger_build(db, company_id, file_ids) if auto_build else None
    return {"success": True, "file_count": len(file_ids), "file_ids": file_ids, "task_id": task_id}


async def _trigger_build(db, company_id: str, file_ids: list[str]) -> str:
    """创建构建任务并投递 celery。投递失败不影响主流程 (可手动重试)。"""
    task = KbBuildTask(
        company_id=company_id, status="pending",
        total_files=len(file_ids), params={"file_ids": file_ids},
    )
    db.add(task)
    await db.flush()
    task_id = str(task.id)
    # 必须先提交再投递: worker 抢跑会在任务行可见前查库, 命中"构建任务不存在"
    await db.commit()
    try:
        from services.celery_app import run_kb_pipeline
        run_kb_pipeline.delay(task_id)
        await db.execute(update(KbBuildTask).where(KbBuildTask.id == task_id).values(status="queued"))
    except Exception as e:
        logger.warning(f"KB 构建任务投递失败 (可稍后重试): {e}")
        await db.execute(update(KbBuildTask).where(KbBuildTask.id == task_id).values(status="pending"))
    await db.commit()
    return task_id


@router.get("/build-tasks")
async def list_build_tasks(
    company_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(KbBuildTask).order_by(KbBuildTask.created_at.desc()).limit(limit)
    if company_id:
        stmt = stmt.where(KbBuildTask.company_id == company_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"tasks": [
        {
            "id": str(t.id), "company_id": str(t.company_id),
            "status": t.status, "total_files": t.total_files,
            "processed_files": t.processed_files,
            "created_entities": t.created_entities,
            "created_edges": t.created_edges, "error": t.error,
            "created_at": _iso(t.created_at),
        }
        for t in rows
    ]}


@router.post("/build-tasks/{task_id}/retry")
async def retry_build_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(
        select(KbBuildTask).where(KbBuildTask.id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="构建任务不存在")
    if task.status == "running":
        raise HTTPException(status_code=400, detail="任务正在运行中")
    if not (task.params.get("file_ids") or []):
        raise HTTPException(status_code=400, detail="任务没有关联文件")
    # 先提交 queued 状态再投递, 避免 worker 抢跑查不到任务行
    await db.execute(update(KbBuildTask).where(KbBuildTask.id == task_id).values(status="queued", error=""))
    await db.commit()
    try:
        from services.celery_app import run_kb_pipeline
        run_kb_pipeline.delay(task_id)
    except Exception as e:
        await db.execute(update(KbBuildTask).where(KbBuildTask.id == task_id).values(status="pending"))
        await db.commit()
        raise HTTPException(status_code=500, detail=f"投递失败: {e}")
    return {"success": True, "task_id": task_id}


# ================= 人审队列 =================

@router.get("/review-queue")
async def list_review_queue(
    company_id: str | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """聚合所有子库中 is_audited=false 的卡片 (人审门禁)。"""
    items = []
    for cat, model in _CARD_MODELS.items():
        stmt = select(model).where(model.is_audited == False)  # noqa: E712
        if company_id:
            stmt = stmt.where(model.company_id == company_id)
        rows = (await db.execute(stmt.limit(limit))).scalars().all()
        for r in rows:
            items.append({
                "entity_type": cat,
                "id": str(r.id),
                "company_id": str(r.company_id),
                "fields": {f: getattr(r, f, None) for f in _CARD_FIELDS[cat]},
            })
    return {"items": items, "count": len(items)}


@router.post("/review-queue/{entity_type}/{card_id}/approve")
async def approve_card(entity_type: str, card_id: str, db: AsyncSession = Depends(get_db)):
    """人工确认卡片入池 (is_audited=true)。"""
    model = _CARD_MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=400, detail=f"未知实体类型: {entity_type}")
    row = (await db.execute(select(model).where(model.id == card_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡片不存在")
    row.is_audited = True
    await db.flush()
    # 人员证书无独立审核入口, 随所属人员一并入池
    if entity_type == "personnel":
        await db.execute(update(KbPersonnelCertificate).where(
            KbPersonnelCertificate.personnel_id == card_id
        ).values(is_audited=True))
    # 关系边随卡片入池同时生效 (设计: 确认后边生效)
    await db.execute(update(KbEdge).where(
        or_(
            (KbEdge.src_type == entity_type) & (KbEdge.src_id == card_id),
            (KbEdge.dst_type == entity_type) & (KbEdge.dst_id == card_id),
        )
    ).values(is_audited=True))
    return {"success": True, "entity_type": entity_type, "id": card_id}


@router.post("/review-queue/{entity_type}/{card_id}/reject")
async def reject_card(entity_type: str, card_id: str, db: AsyncSession = Depends(get_db)):
    """拒掉这张卡片 (删除), 并清理关联的人员证书与关系边避免悬挂。"""
    model = _CARD_MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=400, detail=f"未知实体类型: {entity_type}")
    row = (await db.execute(select(model).where(model.id == card_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="卡片不存在")
    # 人员被拒: 一并删除其人员证书及边 (证书无独立审核入口, 不会自行入池)
    if entity_type == "personnel":
        pcert_ids = (await db.execute(select(KbPersonnelCertificate.id).where(
            KbPersonnelCertificate.personnel_id == card_id))).scalars().all()
        for pid in pcert_ids:
            await db.execute(delete(KbEdge).where(or_(
                (KbEdge.src_type == "personnel_certificate") & (KbEdge.src_id == pid),
                (KbEdge.dst_type == "personnel_certificate") & (KbEdge.dst_id == pid),
            )))
        await db.execute(delete(KbPersonnelCertificate).where(
            KbPersonnelCertificate.personnel_id == card_id))
    await db.execute(delete(KbEdge).where(or_(
        (KbEdge.src_type == entity_type) & (KbEdge.src_id == card_id),
        (KbEdge.dst_type == entity_type) & (KbEdge.dst_id == card_id),
    )))
    await db.delete(row)
    await db.flush()
    return {"success": True, "id": card_id}


# ================= 证书类型字典 =================

class CertTypeCreate(BaseModel):
    code: str
    name: str
    category: str = "enterprise"
    default_valid_months: int = 0
    scope_hint: str = ""


@router.get("/cert-types")
async def list_cert_types(category: str = "", db: AsyncSession = Depends(get_db)):
    stmt = select(KbCertType).where(KbCertType.enabled == True).order_by(  # noqa: E712
        KbCertType.sort_order, KbCertType.created_at)
    if category:
        stmt = stmt.where(KbCertType.category == category)
    rows = (await db.execute(stmt)).scalars().all()
    return {"cert_types": [
        {
            "id": str(c.id), "code": c.code, "name": c.name,
            "category": c.category, "default_valid_months": c.default_valid_months,
            "scope_hint": c.scope_hint, "is_builtin": c.is_builtin,
        }
        for c in rows
    ]}


@router.post("/cert-types")
async def create_cert_type(payload: CertTypeCreate, db: AsyncSession = Depends(get_db)):
    exists = (await db.execute(
        select(KbCertType).where(KbCertType.code == payload.code)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail=f"证书类型 code 已存在: {payload.code}")
    row = KbCertType(
        code=payload.code, name=payload.name, category=payload.category,
        default_valid_months=payload.default_valid_months,
        scope_hint=payload.scope_hint, is_builtin=False,
    )
    db.add(row)
    await db.flush()
    return {"success": True, "id": str(row.id)}


@router.delete("/cert-types/{cert_type_id}")
async def delete_cert_type(cert_type_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(KbCertType).where(KbCertType.id == cert_type_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="证书类型不存在")
    if row.is_builtin:
        raise HTTPException(status_code=400, detail="内置证书类型仅可禁用, 不可删除")
    await db.delete(row)
    await db.flush()
    return {"success": True}


# ================= 到期提醒 =================

@router.get("/expiry-alerts")
async def list_expiry_alerts(
    company_id: str | None = None,
    days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """列出有效期 <=days 天 或已过期的证书/人员证书 (仅已入池)。"""
    today = datetime.now().date()
    alerts = []
    for model, kind, name_of in (
        (KbCertificate, "certificate", lambda r: r.name),
        (KbPersonnelCertificate, "personnel_certificate",
         lambda r: f"{r.cert_type or ''} {r.cert_no or ''}".strip()),
    ):
        stmt = select(model).where(
            model.is_audited == True,  # noqa: E712
            model.status.in_(["expiring", "expired"]),
        )
        if company_id:
            stmt = stmt.where(model.company_id == company_id)
        rows = (await db.execute(stmt)).scalars().all()
        for r in rows:
            expiry = getattr(r, "expiry_date", "") or ""
            remain = -1
            if expiry:
                try:
                    remain = (datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date() - today).days
                except ValueError:
                    pass
            if remain <= days:
                alerts.append({
                    "entity_type": kind, "id": str(r.id),
                    "company_id": str(r.company_id), "name": name_of(r),
                    "expiry_date": expiry, "status": r.status, "days_left": remain,
                })
    alerts.sort(key=lambda a: a["days_left"])
    return {"alerts": alerts, "count": len(alerts)}


# ================= 来源文件 =================

@router.get("/companies/{company_id}/files")
async def list_files(
    company_id: str,
    parse_status: str = "",
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    await _get_company(company_id, db)
    stmt = select(KbFile).where(KbFile.company_id == company_id)
    if parse_status:
        stmt = stmt.where(KbFile.parse_status == parse_status)
    rows = (await db.execute(
        stmt.order_by(KbFile.created_at.desc()).limit(limit)
    )).scalars().all()
    return {"files": [
        {
            "id": str(f.id), "filename": f.filename, "rel_dir": f.rel_dir,
            "ext": f.ext, "file_size": f.file_size, "parse_status": f.parse_status,
            "parse_method": f.parse_method, "category": f.category,
            "page_count": f.page_count, "error": f.error,
            "created_at": _iso(f.created_at),
        }
        for f in rows
    ]}


# ================= 公开采集 (W2) =================

class CollectCreate(BaseModel):
    keyword: str = ""                    # 搜索企业名, 留空用公司全称
    source_codes: list[str] = []         # 指定源, 留空用全部启用的 epoint 源
    max_per_source: int = 30


@router.post("/companies/{company_id}/collect")
async def start_collect(
    company_id: str,
    payload: CollectCreate | None = None,
    db: AsyncSession = Depends(get_db),
):
    """手动触发公开采集: 按企业名搜中标公告 → 预填业绩人审队列。"""
    payload = payload or CollectCreate()
    company = await _get_company(company_id, db)
    keyword = (payload.keyword or "").strip() or company.name
    task = KbCollectTask(
        company_id=company_id, status="pending", keyword=keyword,
        params={"source_codes": payload.source_codes or None,
                "max_per_source": payload.max_per_source},
    )
    db.add(task)
    await db.flush()
    task_id = str(task.id)
    # 先提交再投递: worker 抢跑会在任务行可见前查库
    await db.commit()
    try:
        from services.celery_app import run_kb_collect
        run_kb_collect.delay(task_id)
        await db.execute(update(KbCollectTask).where(
            KbCollectTask.id == task_id).values(status="queued"))
    except Exception as e:
        logger.warning(f"公开采集任务投递失败 (可稍后重试): {e}")
        await db.execute(update(KbCollectTask).where(
            KbCollectTask.id == task_id).values(
            status="failed", error=f"投递失败: {e}"[:500]))
    await db.commit()
    return {"success": True, "task_id": task_id, "keyword": keyword}


@router.get("/collect-tasks")
async def list_collect_tasks(
    company_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(KbCollectTask).order_by(KbCollectTask.created_at.desc()).limit(limit)
    if company_id:
        stmt = stmt.where(KbCollectTask.company_id == company_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"tasks": [
        {
            "id": str(t.id), "company_id": str(t.company_id), "status": t.status,
            "keyword": t.keyword, "source_codes": t.source_codes or [],
            "total_found": t.total_found, "parsed": t.parsed,
            "created_entities": t.created_entities, "duplicated": t.duplicated,
            "error": t.error, "created_at": _iso(t.created_at),
        }
        for t in rows
    ]}


@router.post("/collect-tasks/{task_id}/retry")
async def retry_collect_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = (await db.execute(
        select(KbCollectTask).where(KbCollectTask.id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="采集任务不存在")
    if task.status == "running":
        raise HTTPException(status_code=400, detail="任务正在运行中")
    await db.execute(update(KbCollectTask).where(
        KbCollectTask.id == task_id).values(status="queued", error=""))
    await db.commit()
    try:
        from services.celery_app import run_kb_collect
        run_kb_collect.delay(task_id)
    except Exception as e:
        await db.execute(update(KbCollectTask).where(
            KbCollectTask.id == task_id).values(
            status="failed", error=f"投递失败: {e}"[:500]))
        await db.commit()
        raise HTTPException(status_code=500, detail=f"投递失败: {e}")
    return {"success": True, "task_id": task_id}


# ================= 商机分析 (KB-M4) =================

class OpportunityStageUpdate(BaseModel):
    stage: str  # candidate / analysis / tender


@router.get("/companies/{company_id}/opportunities")
async def list_opportunities(
    company_id: str,
    stage: str = Query("", description="阶段: 空=全部, candidate/analysis/tender"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """商机分析: 按阶段列出该公司的备选库/分析库/投标库。"""
    await _get_company(company_id, db)
    conditions = [HotspotItem.company_id == company_id]
    if stage:
        conditions.append(HotspotItem.stage == stage)
    where_clause = and_(*conditions)
    total = (await db.execute(
        select(func.count(HotspotItem.id)).where(where_clause)
    )).scalar() or 0
    q = (select(HotspotItem)
         .where(where_clause)
         .order_by(HotspotItem.score_total.desc(), HotspotItem.created_at.desc())
         .limit(limit).offset(offset))
    rows = (await db.execute(q)).scalars().all()
    return {
        "stage": stage,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_opportunity_dict(r) for r in rows],
    }


@router.post("/opportunities/{opportunity_id}/stage")
async def update_opportunity_stage(
    opportunity_id: str,
    body: OpportunityStageUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新单个商机的阶段 (candidate → analysis → tender)。"""
    if body.stage not in ("", "candidate", "analysis", "tender"):
        raise HTTPException(status_code=400, detail="无效的阶段值")
    row = (await db.execute(
        select(HotspotItem).where(HotspotItem.id == opportunity_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="商机不存在")
    row.stage = body.stage
    await db.commit()
    return {"success": True, "id": opportunity_id, "stage": row.stage}


@router.post("/companies/{company_id}/opportunities/from-hotspot")
async def add_opportunity_from_hotspot(
    company_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """从资讯热点落库为该公司的备选商机 (stage=candidate)。

    body: {hotspot_id: str, stage?: str}  —— 复制已聚合的 hotspot 到该公司名下。
    """
    await _get_company(company_id, db)
    hotspot_id = (body or {}).get("hotspot_id", "")
    target_stage = (body or {}).get("stage", "candidate")
    if target_stage not in ("", "candidate", "analysis", "tender"):
        raise HTTPException(status_code=400, detail="无效的阶段值")
    src = (await db.execute(
        select(HotspotItem).where(HotspotItem.id == hotspot_id)
    )).scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="资讯热点不存在")
    # 同一公司+同一指纹已存在则不重复落库
    if src.fingerprint:
        exist = (await db.execute(select(HotspotItem.id).where(
            HotspotItem.company_id == company_id,
            HotspotItem.fingerprint == src.fingerprint,
        ))).first()
        if exist:
            return {"success": True, "id": str(exist[0]), "duplicated": True,
                    "stage": target_stage}
    new_row = HotspotItem(
        id=str(uuid.uuid4()),
        title=src.title, url=src.url, source=src.source, sources=src.sources,
        pub_date=src.pub_date, content=src.content, source_code=src.source_code,
        industry_code=src.industry_code, region=src.region, amount=src.amount,
        bid_deadline=src.bid_deadline, owner_org=src.owner_org,
        project_code=src.project_code, announce_type=src.announce_type,
        fingerprint=src.fingerprint, extra=src.extra,
        score_total=src.score_total, score_urgency=src.score_urgency,
        score_match=src.score_match, score_amount=src.score_amount,
        score_region=src.score_region, score_freshness=src.score_freshness,
        is_hot=src.is_hot, is_converted=src.is_converted,
        converted_project_id=src.converted_project_id,
        stage=target_stage, company_id=company_id,
    )
    db.add(new_row)
    await db.commit()
    return {"success": True, "id": str(new_row.id), "duplicated": False,
            "stage": target_stage}


def _opportunity_dict(r: HotspotItem) -> dict:
    return {
        "id": str(r.id),
        "title": r.title,
        "url": r.url,
        "source": r.source,
        "sources": r.sources or [],
        "pub_date": r.pub_date,
        "industry_code": r.industry_code,
        "region": r.region,
        "amount": r.amount,
        "bid_deadline": r.bid_deadline,
        "owner_org": r.owner_org,
        "project_code": r.project_code,
        "announce_type": r.announce_type,
        "score_total": r.score_total,
        "is_hot": r.is_hot,
        "stage": r.stage,
        "company_id": r.company_id or "",
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ================================================================
# W3 商机初筛 (KB-M6): 资格条件逐条勾对 → 三态 + 三大产物
# ================================================================

class ScreenRequest(BaseModel):
    """发起初筛: requirements 为资格条款列表(通常来自解读 qualification_table)。"""
    requirements: list[dict]            # [{"id": "B1-1", "text": "..."}]
    opportunity_id: str = ""
    use_llm_fallback: bool = False
    interpret_json: dict | None = None  # 解读产物(用于红线清单提取), 可选


async def _load_kb_cards(db: AsyncSession, company_id: str) -> list[dict]:
    """勾对证据池: 该公司已人审的 证书/财务/信用 卡片。"""
    cards: list[dict] = []
    certs = (await db.execute(
        select(KbCertificate).where(
            KbCertificate.company_id == company_id,
            KbCertificate.is_audited == True,  # noqa: E712
        ))).scalars().all()
    for c in certs:
        cards.append({"id": str(c.id), "kind": "certificate",
                      "name": c.name, "holder": c.holder,
                      "expiry_date": c.expiry_date, "status": c.status,
                      "is_audited": c.is_audited})
    credits = (await db.execute(
        select(KbCredit).where(
            KbCredit.company_id == company_id,
            KbCredit.is_audited == True,  # noqa: E712
        ))).scalars().all()
    for c in credits:
        cards.append({"id": str(c.id), "kind": "credit",
                      "name": c.title or c.credit_type, "holder": c.holder,
                      "expiry_date": "", "status": "",
                      "is_audited": c.is_audited})
    return cards


@router.post("/companies/{company_id}/screen")
async def run_screening(company_id: str, body: ScreenRequest, db: AsyncSession = Depends(get_db)):
    """对一组资格条件做初筛, 结果落库并返回三态+三大产物。"""
    from services.kb.screening import (
        screen_requirements, build_response_table, extract_redlines,
        collect_company_values,
    )
    if not body.requirements:
        raise HTTPException(status_code=400, detail="requirements 不能为空")

    company = (await db.execute(
        select(KbCompany).where(KbCompany.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")

    # 修正回流映射: 条款指纹 → 人工修正结论
    corr_rows = (await db.execute(
        select(KbScreeningCorrection).where(
            KbScreeningCorrection.company_id == company_id)
    )).scalars().all()
    corrections = {c.fingerprint: c.corrected_verdict for c in corr_rows}

    kb_cards = await _load_kb_cards(db, company_id)
    company_values = await collect_company_values(db, company_id)

    result = screen_requirements(body.requirements, kb_cards, company_values, corrections)

    # LLM 兜底: needs_review 且未走修正的模糊条款
    if body.use_llm_fallback:
        from services.kb.screening import llm_fallback_clause
        from services.llm_factory import get_llm_gateway
        try:
            llm = get_llm_gateway()
        except Exception:
            llm = None
        if llm is not None:
            for item in result["items"]:
                if item.get("verdict") == "needs_review" and item.get("source") == "evidence":
                    fb = await llm_fallback_clause(llm, item.get("text", ""))
                    if fb:
                        item["llm_fallback"] = fb
                        if fb["verdict"] in ("matched", "failed"):
                            item["verdict"] = fb["verdict"]
                            item["source"] = "llm"
            result["stats"] = {
                "total": len(result["items"]),
                "matched": sum(1 for r in result["items"] if r["verdict"] == "matched"),
                "failed": sum(1 for r in result["items"] if r["verdict"] == "failed"),
                "needs_review": sum(1 for r in result["items"] if r["verdict"] == "needs_review"),
            }
            ok = all(r["verdict"] == "matched" for r in result["items"])
            bad = any(r["verdict"] == "failed" for r in result["items"])
            result["overall"] = "passed" if ok else ("failed" if bad else "needs_review")

    response_table = build_response_table(body.requirements, result)
    redlines = extract_redlines(body.interpret_json) if body.interpret_json else []

    row = KbScreeningResult(
        company_id=company_id,
        opportunity_id=body.opportunity_id or None,
        status="done", overall=result["overall"],
        requirements=body.requirements, summary=result["stats"],
        items=result["items"], redlines=redlines, response_table=response_table,
    )
    db.add(row)
    await db.commit()
    return {"success": True, "screening_id": str(row.id), "overall": result["overall"],
            "summary": result["stats"], "items": result["items"],
            "redlines": redlines, "response_table": response_table}


@router.get("/companies/{company_id}/screenings")
async def list_screenings(company_id: str, db: AsyncSession = Depends(get_db),
                          opportunity_id: str = Query("")):
    """历史初筛结果列表。"""
    q = select(KbScreeningResult).where(KbScreeningResult.company_id == company_id)
    if opportunity_id:
        q = q.where(KbScreeningResult.opportunity_id == opportunity_id)
    q = q.order_by(KbScreeningResult.created_at.desc()).limit(50)
    rows = (await db.execute(q)).scalars().all()
    return [{"id": str(r.id), "opportunity_id": r.opportunity_id or "",
             "overall": r.overall, "summary": r.summary,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/screenings/{screening_id}")
async def get_screening(screening_id: str, db: AsyncSession = Depends(get_db)):
    """单条初筛结果详情 (含逐条结论/红线/响应表)。"""
    r = (await db.execute(
        select(KbScreeningResult).where(KbScreeningResult.id == screening_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="初筛结果不存在")
    return {"id": str(r.id), "company_id": r.company_id,
            "opportunity_id": r.opportunity_id or "", "overall": r.overall,
            "summary": r.summary, "items": r.items, "redlines": r.redlines,
            "response_table": r.response_table,
            "created_at": r.created_at.isoformat() if r.created_at else None}


class CorrectionRequest(BaseModel):
    """人工修正回流: 改判某条款, 后续同条款直接沿用。"""
    clause_text: str
    original_verdict: str = ""
    corrected_verdict: str          # matched/failed
    reason: str = ""


@router.post("/screenings/{screening_id}/correct")
async def correct_screening(screening_id: str, body: CorrectionRequest,
                            db: AsyncSession = Depends(get_db)):
    """人工改判初筛结论 → 落修正表回流 (产物指纹按条款文本)。"""
    import uuid as _uuid
    from services.kb.screening import _RULE_PATTERNS  # noqa: F401
    if body.corrected_verdict not in ("matched", "failed"):
        raise HTTPException(status_code=400, detail="corrected_verdict 只能是 matched/failed")
    r = (await db.execute(
        select(KbScreeningResult).where(KbScreeningResult.id == screening_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="初筛结果不存在")
    fp = str(_uuid.uuid5(_uuid.NAMESPACE_URL, body.clause_text))[:32]
    corr = KbScreeningCorrection(
        company_id=r.company_id, fingerprint=fp,
        clause_text=body.clause_text[:2000],
        original_verdict=body.original_verdict,
        corrected_verdict=body.corrected_verdict, reason=body.reason,
    )
    db.add(corr)
    await db.commit()
    return {"success": True, "fingerprint": fp}


# ================================================================
# W4 深度分析 (KB-M7): 团队优化器 + 业绩算分 → 评分报告
# ================================================================

class AnalyzeRequest(BaseModel):
    """发起深度分析。similar_keywords 用于业绩匹配 (为空=全部类似)。"""
    opportunity_id: str = ""
    similar_keywords: list[str] = []
    performance_years: int = 3


@router.post("/companies/{company_id}/analyze")
async def run_deep_analysis(company_id: str, body: AnalyzeRequest,
                            db: AsyncSession = Depends(get_db)):
    """同步执行深度分析 (纯规则秒级): 团队优化器+业绩算分 → 报告行落库。

    数据源: 该公司 personnel/personnel_certificates/achievements 已人审卡。
    """
    from services.kb.scoring import optimize_team, score_performance
    from datetime import datetime as _dt

    company = (await db.execute(
        select(KbCompany).where(KbCompany.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")

    personnel_rows = (await db.execute(
        select(KbPersonnel).where(
            KbPersonnel.company_id == company_id,
            KbPersonnel.is_audited == True,  # noqa: E712
        ))).scalars().all()
    certs_rows = (await db.execute(
        select(KbPersonnelCertificate).where(
            KbPersonnelCertificate.company_id == company_id,
            KbPersonnelCertificate.is_audited == True,  # noqa: E712
        ))).scalars().all()
    certs_by_person: dict = {}
    for c in certs_rows:
        certs_by_person.setdefault(str(c.personnel_id), []).append({
            "cert_type": c.cert_type, "level": c.level,
            "valid_until": c.expiry_date or "",
        })
    personnel = [{"id": str(p.id), "name": p.name} for p in personnel_rows]
    team = optimize_team(personnel, certs_by_person)

    ach_rows = (await db.execute(
        select(KbAchievement).where(
            KbAchievement.company_id == company_id,
            KbAchievement.is_audited == True,  # noqa: E712
        ))).scalars().all()
    achievements = [{
        "project_name": a.project_name, "client_name": a.client_name,
        "contract_amount": a.contract_amount, "sign_date": a.sign_date,
        "announce_date": a.announce_date, "bid_result": a.bid_result,
    } for a in ach_rows]
    perf = score_performance(achievements,
                             tuple(body.similar_keywords),
                             years=body.performance_years)

    # 汇总与结论: 团队+业绩为规则可算部分, 满分 20 (15+5)
    team_score = team.get("max_total", 0.0)
    perf_score = perf.get("score", 0.0)
    suggestion = ("建议投" if (team_score + perf_score) >= 13
                  else "谨慎" if (team_score + perf_score) >= 7 else "放弃")
    report = KbAnalysisReport(
        company_id=company_id, opportunity_id=body.opportunity_id or None,
        status="done", team=team, performance=perf,
        scoring_summary={
            "team_score": team_score, "team_cap": team.get("cap"),
            "performance_score": perf_score, "performance_cap": perf.get("cap"),
            "total": team_score + perf_score,
            "suggestion": suggestion,
            "gaps": team.get("gaps", []) + ([perf.get("gap")] if perf.get("gap") else []),
        },
        started_at=_dt.utcnow(), finished_at=_dt.utcnow(),
    )
    db.add(report)
    await db.commit()
    return {"success": True, "report_id": str(report.id),
            "team": team, "performance": perf, "scoring_summary": report.scoring_summary}


@router.get("/companies/{company_id}/analysis-reports")
async def list_analysis_reports(company_id: str, db: AsyncSession = Depends(get_db)):
    """历史分析报告列表。"""
    rows = (await db.execute(
        select(KbAnalysisReport)
        .where(KbAnalysisReport.company_id == company_id)
        .order_by(KbAnalysisReport.created_at.desc()).limit(50)
    )).scalars().all()
    return [{"id": str(r.id), "opportunity_id": r.opportunity_id or "",
             "status": r.status, "scoring_summary": r.scoring_summary,
             "report_path": r.report_path,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/analysis-reports/{report_id}")
async def get_analysis_report(report_id: str, db: AsyncSession = Depends(get_db)):
    """单条分析报告详情。"""
    r = (await db.execute(
        select(KbAnalysisReport).where(KbAnalysisReport.id == report_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"id": str(r.id), "company_id": r.company_id,
            "opportunity_id": r.opportunity_id or "", "status": r.status,
            "team": r.team, "performance": r.performance,
            "scoring_summary": r.scoring_summary, "report_path": r.report_path,
            "created_at": r.created_at.isoformat() if r.created_at else None}


# ================================================================
# 商务文函自动化 (KB-M7 第三关落点): 响应表/承诺函/声明函 docx 下载
# ================================================================

def _docx_response_table(screening: KbScreeningResult, company_name: str) -> bytes:
    """产物③落地: 商务要求响应表 docx。"""
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading(f"{company_name} — 商务要求响应表", level=1)
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(["序号", "招标文件要求", "投标响应", "偏离情况"]):
        hdr[i].text = h
        for p in hdr[i].paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.size = Pt(10.5)
    for i, row in enumerate(screening.response_table or [], 1):
        cells = table.add_row().cells
        cells[0].text = str(i)
        cells[1].text = row.get("clause", "")
        cells[2].text = row.get("response", "")
        cells[3].text = row.get("deviation", "")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_commitment_letter(company: KbCompany, requirements: list[dict]) -> bytes:
    """资格承诺函 docx: 逐条承诺满足资格审查要求。"""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("资格承诺函")
    run.font.size = Pt(18)
    run.font.bold = True
    doc.add_paragraph(
        f"致:招标人\n\n我方 {company.name} 参加本项目投标, 郑重承诺满足下列资格要求:")
    for i, req in enumerate(requirements, 1):
        text = req.get("text") or req.get("clause") or ""
        doc.add_paragraph(f"{i}. {text}")
    doc.add_paragraph(
        "\n如经查实我方存在虚假承诺, 自愿接受取消投标资格、没收投标保证金等处理。")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run(f"\n投标人: {company.name}\n日期: ____年____月____日")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_sme_declaration(company: KbCompany) -> bytes:
    """中小企业声明函 docx (自动按企业规模留空待填, 附占位说明)。"""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("中小企业声明函")
    run.font.size = Pt(18)
    run.font.bold = True
    doc.add_paragraph(
        f"本公司 {company.name} 郑重声明, 根据《政府采购促进中小企业发展管理办法》"
        "(财库〔2020〕46号)的规定, 本公司参加本项目采购活动, 属于_____行业,"
        "从业人员____人, 营业收入____万元, 资产总额____万元, 属于(中型企业/小型企业/微型企业)。"
        "\n本公司对上述声明内容的真实性负责。如有虚假, 依法承担相应责任。")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.add_run(f"\n企业名称(盖章): {company.name}\n日期: ____年____月____日")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@router.get("/screenings/{screening_id}/docs/response-table")
async def download_response_table(screening_id: str, db: AsyncSession = Depends(get_db)):
    """下载商务要求响应表 docx。"""
    from fastapi.responses import Response
    r = (await db.execute(
        select(KbScreeningResult).where(KbScreeningResult.id == screening_id)
    )).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="初筛结果不存在")
    company = (await db.execute(
        select(KbCompany).where(KbCompany.id == r.company_id)
    )).scalar_one_or_none()
    data = _docx_response_table(r, company.name if company else "")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f"attachment; filename=response_table_{screening_id[:8]}.docx"},
    )


@router.get("/companies/{company_id}/docs/commitment-letter")
async def download_commitment_letter(company_id: str, db: AsyncSession = Depends(get_db),
                                     screening_id: str = Query("")):
    """下载资格承诺函 docx (有初筛结果按其条款, 否则取最近一次)。"""
    from fastapi.responses import Response
    company = (await db.execute(
        select(KbCompany).where(KbCompany.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")
    requirements: list[dict] = []
    if screening_id:
        r = (await db.execute(
            select(KbScreeningResult).where(KbScreeningResult.id == screening_id)
        )).scalar_one_or_none()
        if r:
            requirements = r.requirements or []
    if not requirements:
        latest = (await db.execute(
            select(KbScreeningResult)
            .where(KbScreeningResult.company_id == company_id)
            .order_by(KbScreeningResult.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        requirements = (latest.requirements if latest else []) or []
    data = _docx_commitment_letter(company, requirements)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=commitment_letter.docx"},
    )


@router.get("/companies/{company_id}/docs/sme-declaration")
async def download_sme_declaration(company_id: str, db: AsyncSession = Depends(get_db)):
    """下载中小企业声明函 docx。"""
    from fastapi.responses import Response
    company = (await db.execute(
        select(KbCompany).where(KbCompany.id == company_id)
    )).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")
    data = _docx_sme_declaration(company)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=sme_declaration.docx"},
    )