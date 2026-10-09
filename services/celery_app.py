from __future__ import annotations

import os

from celery import Celery

celery_app = Celery(
    "bidmaster",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    # redis broker 下 acks_late 任务依赖 visibility_timeout 归还未确认消息,
    # 默认 1h 小于长任务耗时会导致重复投递
    broker_transport_options={"visibility_timeout": 3600 * 12},
    result_backend_transport_options={"visibility_timeout": 3600 * 12},
    visibility_timeout=3600 * 12,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "news-monitor": {
            "task": "services.celery_app.run_news_monitor",
            "schedule": 3600,
        },
        "kb-expiry-scan": {
            "task": "services.celery_app.run_kb_expiry_scan",
            "schedule": 86400,  # 每日
        },
    },
)


def _run_task(coro_factory):
    """celery 任务公共执行器: 每任务独立 event loop, 结束后 dispose 全局 engine

    asyncpg 连接绑定创建时的 event loop, 而 celery 每个任务都跑在新 loop 里,
    复用全局 engine 的连接池会跨 loop 报错 —— 任务结束后统一 dispose,
    下个任务自动重建全新 engine。
    """
    import asyncio

    async def _runner():
        from services.database import close_db
        try:
            return await coro_factory()
        finally:
            await close_db()

    return asyncio.run(_runner())


@celery_app.task(name="services.celery_app.run_news_monitor", bind=True)
def run_news_monitor(self):
    """定时聚合采集: 每小时抓取所有 enabled 数据源并入库

    此前该任务只遍历任务列表并返回 "processed",不抓任何数据,
    导致"今日热点/推荐"完全依赖手动点击。现改为真实执行聚合。
    """
    async def _run():
        from sqlalchemy import select
        from services.database import async_session
        from services.models import CompanyProfile

        async with async_session()() as db:
            from services.news.aggregate_service import run_aggregation

            # 定时采集自动带上已保存的公司画像, 让评分贴合企业业务偏好
            prof_result = await db.execute(
                select(CompanyProfile).where(CompanyProfile.name == "default")
            )
            prof_row = prof_result.scalar_one_or_none()
            company_profile = prof_row.profile_data if prof_row and prof_row.profile_data else None

            result = await run_aggregation(
                db,
                source_codes=None,     # 全部 enabled 源
                industry_code=None,
                company_profile=company_profile,
                persist=True,
            )
            await db.commit()
            return result

    return _run_task(_run)


@celery_app.task(name="services.celery_app.run_full_check", bind=True)
def run_full_check(self, project_id: str):
    async def _run():
        from services.routers.check import _get_tender_and_bid_text
        from services.database import async_session
        from services.llm_factory import get_llm_gateway
        from core.skill_engine.base import SkillContext
        from services.check.skills.selfcheck_list_skill import SelfcheckListSkill

        async with async_session()() as db:
            _, tender_text, bid_text = await _get_tender_and_bid_text(project_id, db)
            if not tender_text or not bid_text:
                return {"error": "招标文件或投标文件内容为空"}

            gateway = get_llm_gateway()
            skill = SelfcheckListSkill()
            ctx = SkillContext(
                project_id=project_id, db=db, llm=gateway,
                parameters={"tender_text": tender_text, "bid_text": bid_text},
            )
            result = await skill.safe_execute(ctx)
            return {"success": result.success, "data": result.data}

    return _run_task(_run)


@celery_app.task(name="services.celery_app.run_batch_format", bind=True)
def run_batch_format(self, file_paths: list[str], template: str = "default"):
    async def _run():
        from services.format.skills.docx_format_skill import DocxFormatSkill
        from services.llm_factory import get_llm_gateway
        from core.skill_engine.base import SkillContext

        gateway = get_llm_gateway()
        skill = DocxFormatSkill()
        results = []
        for fp in file_paths:
            ctx = SkillContext(
                project_id="", db=None, llm=gateway,
                parameters={"file_path": fp, "template": template},
            )
            result = await skill.safe_execute(ctx)
            results.append({"file": fp, "success": result.success, "output": result.data.get("output_path") if result.success else result.error})
        return results

    return _run_task(_run)


@celery_app.task(name="services.celery_app.run_kb_pipeline", bind=True)
def run_kb_pipeline(self, task_id: str):
    """W1 知识库构建流水线: 对指定构建任务的文件做 提取→分类→结构化→入池。"""
    async def _run():
        from sqlalchemy import select
        from services.database import async_session
        from services.models import KbBuildTask
        from services.kb.pipeline import KbPipeline
        from services.llm_factory import get_llm_gateway

        async with async_session()() as db:
            task_row = (await db.execute(
                select(KbBuildTask).where(KbBuildTask.id == task_id)
            )).scalar_one_or_none()
            if not task_row:
                return {"error": "构建任务不存在"}
            if task_row.status == "running":
                return {"error": "任务仍在运行中", "task_id": task_id}
            # 重跑: 重置为 pending, 让 pipeline 跳过已解析文件而非重复建卡
            if task_row.status == "done":
                task_row.status = "pending"

            gateway = get_llm_gateway()
            file_ids = task_row.params.get("file_ids", []) or []
            pipeline = KbPipeline(
                db=db, company_id=task_row.company_id,
                task=task_row, llm=gateway,
            )
            try:
                result = await pipeline.run(file_ids)
            except Exception as e:
                # 任务级异常: 置 failed, 避免 status 卡死 running 导致无法 retry
                task_row.status = "failed"
                task_row.error = f"流水线异常: {e}"[:500]
                await db.commit()
                return {"error": task_row.error, "task_id": task_id}
            await db.commit()
            return result

    return _run_task(_run)


@celery_app.task(name="services.celery_app.run_kb_expiry_scan", bind=True)
def run_kb_expiry_scan(self):
    """每日重算证书/人员证书 status (valid/expiring/expired)。

    到期清单由前端按 status 查询, 此处只做状态重算。
    """
    async def _run():
        from datetime import datetime, date
        from sqlalchemy import select
        from services.database import async_session
        from services.models import KbCertificate, KbPersonnelCertificate

        today = date.today()
        updated = 0
        expiring = 0
        async with async_session()() as db:
            for model in (KbCertificate, KbPersonnelCertificate):
                rows = (await db.execute(select(model))).scalars().all()
                for row in rows:
                    expiry = getattr(row, "expiry_date", "") or ""
                    new_status = "valid"
                    if expiry:
                        try:
                            d = datetime.strptime(str(expiry)[:10], "%Y-%m-%d").date()
                        except ValueError:
                            d = None
                        if d:
                            td = (d - today).days
                            new_status = "expired" if td < 0 else ("expiring" if td <= 90 else "valid")
                    if row.status != new_status:
                        row.status = new_status
                        updated += 1
                    if new_status in ("expiring", "expired"):
                        expiring += 1
            await db.commit()
        return {"updated": updated, "expiring_or_expired": expiring}

    return _run_task(_run)
