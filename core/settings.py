from __future__ import annotations

from pydantic_settings import BaseSettings
from pathlib import Path
from urllib.parse import quote_plus


class Settings(BaseSettings):
    app_name: str = "智能招投标平台"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    db_type: str = "postgresql"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bidmaster"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "root"
    mysql_database: str = "bidmaster"

    redis_url: str = "redis://localhost:6379/0"
    chroma_dir: str = "./chroma_db"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "bidmaster"
    projects_root: str = "./projects"

    llm_default_model: str = "deepseek/deepseek-chat"
    llm_api_key: str = ""
    llm_api_base: str = "https://api.deepseek.com"
    llm_fallback_modes: str = "ollama/qwen2.5"
    llm_max_retries: int = 3

    embedding_mode: str = "api"
    embedding_model: str = "text-embedding-v3"
    embedding_api_key: str = ""
    embedding_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    mineru_mode: str = "cloud"
    mineru_api_key: str = ""
    mineru_endpoint: str = "https://mineru.net/api/v4"
    mineru_timeout: int = 180
    mineru_model_version: str = "vlm"
    mineru_poll_interval: int = 5
    mineru_max_polls: int = 60

    tender_text_max_chars: int = 32000

    model_config = {"env_file": ".env", "env_prefix": "BMP_", "extra": "ignore"}

    def get_database_url(self) -> str:
        if self.db_type == "mysql":
            return (
                f"mysql+aiomysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
                f"?charset=utf8mb4"
            )
        return self.database_url


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _backfill_empty_from_env_file(_settings)
    return _settings


def _backfill_empty_from_env_file(s: Settings) -> None:
    """docker-compose 显式注入的空字符串 env(如容器创建时 .env 尚未恢复)会覆盖 .env 文件值，
    这里对密钥类字段补读 .env 文件把空值填回去。"""
    envp = Path(".env")
    if not envp.exists():
        return
    vals: dict[str, str] = {}
    for line in envp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("BMP_") and "=" in line:
            k, v = line.split("=", 1)
            vals[k[4:].lower()] = v.strip().strip('"').strip("'")
    for field in ("llm_api_key", "embedding_api_key", "mineru_api_key"):
        if not getattr(s, field, "") and vals.get(field):
            setattr(s, field, vals[field])
