"""商机聚合服务 — 供 HTTP 接口与 Celery 定时任务共用

职责: 枚举数据源 → 并发抓取 → 去重/行业分类/价值评分 → 写库
避免路由和定时任务各自实现一套抓取逻辑 (此前 celery 空转的根源)。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def run_aggregation(
    db,
    source_codes: Optional[list[str]] = None,
    industry_code: Optional[str] = None,
    company_profile: Optional[dict] = None,
    is_hot_threshold: float = 60.0,
    persist: bool = True,
) -> dict:
    """执行一轮聚合: 选源 → 抓取 → 去重/分类/评分 → 入库。

    - source_codes 非空: 抓取指定源
    - 否则 industry_code 非空: 抓取该行业源
    - 否则: 抓取 DB 中所有 enabled 源 (定时任务默认路径)
    返回与 HTTP /aggregate 兼容的结构。
    """
    from sqlalchemy import select

    from services.news.source_registry import (
        get_sources_by_codes,
        get_sources_by_industry,
    )
    from services.news.fetchers import get_fetcher
    from services.news.skills.hotspot_aggregate_skill import HotspotAggregateSkill
    from services.models import NewsSourceRegistry
    from services.llm_factory import get_llm_gateway
    from core.skill_engine.base import SkillContext

    # 1) 选择数据源 (优先显式 codes → industry → enabled 全部)
    if source_codes:
        yaml_sources = get_sources_by_codes(source_codes)
    elif industry_code:
        yaml_sources = get_sources_by_industry(industry_code)
    else:
        yaml_sources = []
        enabled_rows = (await db.execute(
            select(NewsSourceRegistry).where(NewsSourceRegistry.enabled == True)
        )).scalars().all()
        for r in enabled_rows:
            yaml_sources.append({
                "name": r.name,
                "code": r.code,
                "type": r.type,
                "url": r.url,
                "industry": r.industry_code,
                "weight": r.weight,
                "config": r.extra_config or {},
            })

    # 1.5) 以 DB enabled 为准: 过滤掉在 DB 中被禁用的源
    codes = [s.get("code") for s in yaml_sources if s.get("code")]
    if codes:
        disabled_codes = set((await db.execute(
            select(NewsSourceRegistry.code).where(
                NewsSourceRegistry.code.in_(codes),
                NewsSourceRegistry.enabled == False,
            )
        )).scalars().all())
        if disabled_codes:
            yaml_sources = [s for s in yaml_sources if s.get("code") not in disabled_codes]

    if not yaml_sources:
        return {"success": True, "total": 0, "saved": 0, "items": [], "message": "无可用数据源"}

    # 2) 并发抓取 (限并发 4)
    all_items: list[dict] = []
    errors: list[dict] = []
    sem = asyncio.Semaphore(4)

    async def _one(src: dict) -> list[dict]:
        async with sem:
            try:
                fetcher = get_fetcher(src.get("type", "rss"))
                items = await fetcher.fetch(src)
                return [it.to_dict() for it in items]
            except Exception as e:
                logger.warning(f"抓取失败 {src.get('code')}: {e}")
                errors.append({"code": src.get("code", ""), "error": str(e)})
                return []

    results = await asyncio.gather(*[_one(s) for s in yaml_sources])
    for r in results:
        all_items.extend(r)

    # 3) 聚合 Skill (去重 + 分类 + 评分 + 入库)
    gateway = get_llm_gateway()
    skill = HotspotAggregateSkill()
    ctx = SkillContext(
        project_id="",
        db=db,
        llm=gateway,
        parameters={
            "items": all_items,
            "company_profile": company_profile or {},
            "is_hot_threshold": is_hot_threshold,
            "persist": persist,
        },
    )
    skill_result = await skill.safe_execute(ctx)
    data = skill_result.data or {}
    return {
        "success": skill_result.success,
        "total": data.get("total", 0),
        "saved": data.get("saved", 0),
        "items": data.get("items", []),
        "errors": errors,
        "error": skill_result.error,
    }