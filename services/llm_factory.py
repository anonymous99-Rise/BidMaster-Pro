from __future__ import annotations

from core.llm_gateway.gateway import LLMGateway
from core.settings import get_settings

_gateway: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        settings = get_settings()
        _gateway = LLMGateway({
            "providers": [
                {
                    "api_key": settings.llm_api_key,
                    "api_base": settings.llm_api_base,
                }
            ],
            "default_model": settings.llm_default_model,
            "fallback_models": [m.strip() for m in settings.llm_fallback_modes.split(",") if m.strip()],
            "max_retries": settings.llm_max_retries,
        })
    return _gateway


def set_llm_gateway_from_provider(provider: dict | None) -> None:
    """用数据库中的默认供应商配置重建运行时网关；provider 为 None 时回退到环境变量。"""
    global _gateway
    # api_key 为空时必须回退环境变量,否则网关会拿 "sk-placeholder" 兜底导致 401
    if not provider or not str(provider.get("api_key") or "").strip():
        _gateway = None
        return
    settings = get_settings()
    _gateway = LLMGateway({
        "providers": [
            {
                "api_key": provider.get("api_key") or "",
                "api_base": provider.get("api_base") or "",
            }
        ],
        "default_model": provider.get("default_model") or settings.llm_default_model,
        "fallback_models": [m.strip() for m in settings.llm_fallback_modes.split(",") if m.strip()],
        "max_retries": settings.llm_max_retries,
    })


def reset_llm_gateway():
    global _gateway
    _gateway = None
