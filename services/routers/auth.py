from __future__ import annotations

import hashlib
import secrets
import time

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.database import get_db
from services.models import User, RBACUserRole, RBACRole
from services.session_store import (
    SESSION_TTL,
    cleanup_expired as _cleanup_sessions,
    delete_session,
    get_session,
    save_session,
)

router = APIRouter()

# 登录限速 (进程内存级): 同一邮箱连续失败达阈值后锁定一段时间
_LOGIN_FAILS: dict[str, tuple[int, float]] = {}
_LOGIN_MAX_FAILS = 5
_LOGIN_LOCK_SECONDS = 900


def _check_login_locked(key: str) -> bool:
    rec = _LOGIN_FAILS.get(key)
    if not rec:
        return False
    count, first_ts = rec
    if time.time() - first_ts > _LOGIN_LOCK_SECONDS:
        _LOGIN_FAILS.pop(key, None)
        return False
    return count >= _LOGIN_MAX_FAILS


def _record_login_fail(key: str) -> None:
    now = time.time()
    rec = _LOGIN_FAILS.get(key)
    if rec and now - rec[1] <= _LOGIN_LOCK_SECONDS:
        _LOGIN_FAILS[key] = (rec[0] + 1, rec[1])
    else:
        _LOGIN_FAILS[key] = (1, now)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenInfo(BaseModel):
    token: str
    user_id: str
    email: str
    name: str
    role: str
    avatar: str | None = None


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Fallback for legacy SHA256 hashes
        return hashed == hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_token(token: str) -> dict | None:
    _cleanup_sessions()
    return get_session(token)


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    fail_key = data.email.strip().lower()
    if _check_login_locked(fail_key):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 15 分钟后重试")

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        _record_login_fail(fail_key)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user.password_hash:
        raise HTTPException(status_code=401, detail="该账户未设置密码，请联系管理员")

    if not _verify_password(data.password, user.password_hash):
        _record_login_fail(fail_key)
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    _LOGIN_FAILS.pop(fail_key, None)

    # 兼容历史无盐 SHA256 口令: 登录成功后升级为 bcrypt
    if not user.password_hash.startswith("$2"):
        user.password_hash = _hash_password(data.password)
        await db.flush()

    token = secrets.token_hex(32)
    _cleanup_sessions()
    save_session(token, {
        "user_id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "created_at": time.time(),
    })

    ur_result = await db.execute(
        select(RBACUserRole.role_id).where(RBACUserRole.user_id == user.id)
    )
    role_ids = [row[0] for row in ur_result.all()]

    roles = []
    if role_ids:
        role_result = await db.execute(
            select(RBACRole).where(RBACRole.id.in_(role_ids))
        )
        roles = [{"id": str(r.id), "name": r.name, "display_name": r.display_name} for r in role_result.scalars().all()]

    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "avatar": user.avatar,
            "roles": roles,
        },
    }


@router.get("/me")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from services.middleware.rbac_middleware import get_current_user
    user = await get_current_user(request, db)

    ur_result = await db.execute(
        select(RBACUserRole.role_id).where(RBACUserRole.user_id == user.id)
    )
    role_ids = [row[0] for row in ur_result.all()]

    roles = []
    if role_ids:
        role_result = await db.execute(
            select(RBACRole).where(RBACRole.id.in_(role_ids))
        )
        roles = [{"id": str(r.id), "name": r.name, "display_name": r.display_name} for r in role_result.scalars().all()]

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "avatar": user.avatar,
        "roles": roles,
    }


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    from services.middleware.rbac_middleware import get_current_user
    await get_current_user(request, db)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            delete_session(token)
    return {"success": True}


class ChangePasswordRequest(BaseModel):
    new_password: str


@router.put("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    # 密码走 body 传输, 避免 query 参数明文落入访问日志
    from services.middleware.rbac_middleware import get_current_user
    user = await get_current_user(request, db)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = auth_header[7:].strip()
    session = verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    if not body.new_password or len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")

    user.password_hash = _hash_password(body.new_password)
    await db.flush()

    delete_session(token)

    return {"success": True, "message": "密码已修改，请重新登录"}
