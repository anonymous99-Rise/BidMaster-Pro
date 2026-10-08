from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.settings import get_settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# 降低 SQLAlchemy 引擎日志级别（太多 INFO 日志）
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
from core.exceptions import (
    LLMGatewayError,
    JsonRepairError,
    SkillNotFoundError,
    UnsupportedFormatError,
    GateNotPassedException,
    ProjectNotFoundError,
)
from services.database import init_db, close_db, is_db_ready
from services.routers import projects, interpret, generate, check, format_doc, skills, llm_config, news, knowledge, rbac, ai_image, auth, agent_runtime, mineru_config, api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    # compose 会注入空字符串环境变量(如 BMP_MINERU_API_KEY=""),而 pydantic
    # 环境变量优先于 .env 文件,导致设置页写入 /app/.env 的配置被空值覆盖。
    # 此处仅用 .env 值回填"为空"的环境变量,非空环境变量(部署显式配置)保持优先。
    import os
    from pathlib import Path
    _env_file = Path(os.getcwd()) / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            if _k and not os.environ.get(_k):
                os.environ[_k] = _v
    from services.skill_bootstrap import register_builtin_skills
    from core.task_manager import TaskManager
    from services.database import async_session
    register_builtin_skills()
    await init_db()

    # 启动时用数据库中的默认 LLM 供应商重建运行时网关,
    # 否则重启后回退到环境变量(通常为空),网关会用占位符 key 导致 401
    try:
        from sqlalchemy import select
        from services.models import LLMProviderConfig
        from services.llm_factory import set_llm_gateway_from_provider
        async with async_session()() as _ldb:
            _row = (await _ldb.execute(
                select(LLMProviderConfig)
                .where(LLMProviderConfig.enabled == True, LLMProviderConfig.is_default == True)
                .order_by(LLMProviderConfig.updated_at.desc())
            )).scalars().first()
            if _row:
                set_llm_gateway_from_provider({
                    "api_key": _row.api_key,
                    "api_base": _row.api_base,
                    "default_model": _row.default_model,
                })
                logging.getLogger("llm").info(
                    f"[llm] 启动已从数据库加载默认供应商配置: {_row.provider_id}/{_row.default_model}"
                )
    except Exception as _e:
        logging.getLogger("llm").warning(f"[llm] 启动加载 LLM 配置失败 (回退环境变量): {_e}")

    # 同步预置数据源 (YAML -> DB),仅做幂等写入,不抛错
    try:
        from services.news.source_registry import sync_sources_to_db
        async with async_session()() as _sdb:
            synced = await sync_sources_to_db(_sdb)
            await _sdb.commit()
            if synced:
                logging.getLogger("news").info(f"已同步 {synced} 个新数据源到注册表")
    except Exception as _e:
        logging.getLogger("news").warning(f"同步数据源失败 (可忽略): {_e}")

    # Periodic TaskManager cleanup
    async def _periodic_cleanup():
        tm = TaskManager.instance()
        while True:
            await asyncio.sleep(tm._cleanup_interval)
            tm.cleanup_old_tasks()

    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_db()


app = FastAPI(
    title="智能招投标平台 API",
    description="全流程智能招投标平台",
    version="0.1.0",
    lifespan=lifespan,
)

import os

_electron_origins = [
    "http://localhost:15168",     # Vite dev (项目定制端口)
    "http://127.0.0.1:15168",
    "http://localhost:5173",      # Vite dev (默认端口，兼容)
    "http://127.0.0.1:5173",
    "http://localhost:4173",      # Vite preview
    "http://127.0.0.1:4173",
    "app://.",                    # Electron file protocol
    "file://",
]
_extra_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _extra_origins:
    _electron_origins.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_electron_origins,
    # file:// 页面发起跨域请求时 Origin 为 "null"，桌面客户端依赖此正则放行
    allow_origin_regex=r"^(https?://.*|null|file://|app://\..*)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "User-Agent", "X-Requested-With", "X-API-Key"],
    max_age=600,
)


@app.exception_handler(LLMGatewayError)
async def llm_gateway_error_handler(request: Request, exc: LLMGatewayError):
    return JSONResponse(status_code=502, content={"detail": f"LLM网关错误: {str(exc)}"})


@app.exception_handler(JsonRepairError)
async def json_repair_error_handler(request: Request, exc: JsonRepairError):
    return JSONResponse(status_code=422, content={"detail": f"JSON修复失败: {str(exc)}"})


@app.exception_handler(SkillNotFoundError)
async def skill_not_found_handler(request: Request, exc: SkillNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(UnsupportedFormatError)
async def unsupported_format_handler(request: Request, exc: UnsupportedFormatError):
    return JSONResponse(status_code=415, content={"detail": str(exc)})


@app.exception_handler(GateNotPassedException)
async def gate_not_passed_handler(request: Request, exc: GateNotPassedException):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ProjectNotFoundError)
async def project_not_found_handler(request: Request, exc: ProjectNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误",
            "error": str(exc),
            "traceback": tb if get_settings().debug else None,
        },
    )


app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(projects.router, prefix="/api/projects", tags=["项目管理"])
app.include_router(interpret.router, prefix="/api/interpret", tags=["招标解读"])
app.include_router(generate.router, prefix="/api/generate", tags=["投标生成"])
app.include_router(check.router, prefix="/api/check", tags=["投标检查"])
app.include_router(format_doc.router, prefix="/api/format", tags=["文档输出"])
app.include_router(skills.router, prefix="/api/skills", tags=["Skill管理"])
app.include_router(llm_config.router, prefix="/api/llm", tags=["LLM配置"])
app.include_router(news.router, prefix="/api/news", tags=["资讯中心"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])
app.include_router(rbac.router, prefix="/api/rbac", tags=["权限管理"])
app.include_router(ai_image.router, prefix="/api/ai-image", tags=["AI配图"])
app.include_router(agent_runtime.router, prefix="/api/agent", tags=["多Agent编排"])
app.include_router(mineru_config.router, prefix="/api/mineru", tags=["MinerU OCR"])
app.include_router(api_key.router, prefix="/api/api-keys", tags=["API Key 管理"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "智能招投标平台", "version": "0.1.0", "db_ready": is_db_ready()}


@app.get("/api/stats")
async def get_stats():
    from core.skill_engine.registry import SkillRegistry
    from services.llm_factory import get_llm_gateway
    registry = SkillRegistry.instance()
    try:
        gateway = get_llm_gateway()
        token_usage = gateway.get_token_summary()
    except Exception:
        token_usage = {}
    return {
        "skills_count": len(registry._skills),
        "skills": registry.list_all(),
        "token_usage": token_usage,
        "db_ready": is_db_ready(),
    }
