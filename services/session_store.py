"""会话存储:Redis 优先(重启不掉线),Redis 不可用时回退进程内存。"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

logger = logging.getLogger("auth")

SESSION_TTL = 86400 * 7

_memory_sessions: dict[str, dict] = {}
_redis = None
_redis_broken = False

_KEY_PREFIX = "bmp:session:"


def _get_redis():
    global _redis, _redis_broken
    if _redis is not None:
        return _redis
    if _redis_broken:
        return None
    try:
        import redis
        from core.settings import get_settings
        _redis = redis.Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        _redis.ping()
        return _redis
    except Exception as e:
        logger.warning(f"[auth] Redis 不可用,会话回退进程内存: {e}")
        _redis_broken = True
        return None


def save_session(token: str, session: dict) -> None:
    r = _get_redis()
    if r is not None:
        try:
            r.setex(_KEY_PREFIX + token, SESSION_TTL, json.dumps(session))
            return
        except Exception as e:
            logger.warning(f"[auth] Redis 写入会话失败,回退内存: {e}")
    _memory_sessions[token] = session


def get_session(token: str) -> Optional[dict]:
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(_KEY_PREFIX + token)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"[auth] Redis 读取会话失败: {e}")
    session = _memory_sessions.get(token)
    if session and time.time() - session["created_at"] > SESSION_TTL:
        delete_session(token)
        return None
    return session


def delete_session(token: str) -> None:
    _memory_sessions.pop(token, None)
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_KEY_PREFIX + token)
        except Exception:
            pass


def cleanup_expired() -> None:
    now = time.time()
    expired = [k for k, v in _memory_sessions.items() if now - v["created_at"] > SESSION_TTL]
    for k in expired:
        delete_session(k)
