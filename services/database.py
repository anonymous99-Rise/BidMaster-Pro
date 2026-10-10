from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event, text
from core.settings import get_settings

logger = logging.getLogger(__name__)

_engine = None
_async_session_factory = None
_db_ready = False


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = settings.get_database_url()
        logger.info(f"数据库类型: {settings.db_type}, 连接串: {database_url.split('@')[-1] if '@' in database_url else database_url}")
        engine_kwargs = {
            "echo": settings.debug,
            "pool_size": 20,
            "max_overflow": 10,
            "pool_pre_ping": True,
        }
        if settings.db_type == "mysql":
            engine_kwargs["pool_recycle"] = 3600
            engine_kwargs["connect_args"] = {"charset": "utf8mb4"}
        _engine = create_async_engine(database_url, **engine_kwargs)
    return _engine


def async_session() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db() -> AsyncSession:
    if not _db_ready:
        raise HTTPException(status_code=503, detail="数据库暂不可用，请检查数据库服务是否已启动")
    session_factory = async_session()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def is_db_ready() -> bool:
    return _db_ready


# 已有表的新增列 (create_all 只建新表, 不会给已存在的表加列, 需手动幂等补齐)
_SCHEMA_EXTRA_COLUMNS = {
    "hotspot_items": [
        ("announce_type", "VARCHAR(20) DEFAULT 'tender'"),
    ],
    # KB-M3 公开采集: 业绩卡片补采集溯源字段
    "kb_achievements": [
        ("winner_name", "VARCHAR(300) DEFAULT ''"),
        ("source_url", "VARCHAR(1000) DEFAULT ''"),
        ("announce_date", "VARCHAR(20) DEFAULT ''"),
        ("fingerprint", "VARCHAR(64) DEFAULT ''"),
    ],
}


async def init_db():
    global _db_ready
    from services.models import Base
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # 幂等补齐旧表新增列 (PostgreSQL / MySQL 均支持 ADD COLUMN IF NOT EXISTS)
            for table, cols in _SCHEMA_EXTRA_COLUMNS.items():
                for col_name, col_type in cols:
                    ddl = f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}'
                    try:
                        await conn.execute(text(ddl))
                    except Exception as e:
                        logger.warning(f"补充列 {table}.{col_name} 失败 (忽略): {e}")
        _db_ready = True
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.warning(f"数据库不可用，应用将以降级模式启动: {e}")
        _db_ready = False


async def close_db():
    global _engine, _async_session_factory, _db_ready
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception as e:
            logger.warning(f"关闭数据库引擎时出错: {e}")
        finally:
            _engine = None
    _async_session_factory = None
    _db_ready = False
    logger.info("数据库资源已释放")
