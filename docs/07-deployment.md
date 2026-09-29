# 07 部署与配置

## 方式一：Docker Compose（推荐）

`docker/docker-compose.yml`，两种 profile：

- **基础 profile**：postgres(5432) + redis(6379) + minio(9000/9001) —— 本地开发只起基础设施
- **完整 profile**：+ api(FastAPI 8000) + celery-worker + celery-beat + web(nginx)

构建文件：`docker/Dockerfile.api`、`docker/Dockerfile.web`、`docker/entrypoint.sh`、`docker/nginx.conf`。

```bash
cp .env.example .env      # 填写 BMP_LLM_API_KEY 等
docker compose --profile full up -d
# API 文档 http://localhost:8000/docs，MinIO 控制台 http://localhost:9001
```

### 国内源（默认启用）

| 项 | 镜像源 | 覆盖方式 |
|----|--------|----------|
| Docker Hub 基础镜像 | `docker.m.daocloud.io`（DaoCloud 代理） | 环境变量 `DOCKER_REGISTRY=docker.io` 还原官方源；Dockerfile 构建用 `--build-arg REGISTRY=` |
| apt（Debian） | 清华 TUNA | Dockerfile 内置 |
| pip | 清华 PyPI | Dockerfile 内置（`PIP_INDEX_URL`） |
| npm | npmmirror | Dockerfile.web 内置（`NPM_CONFIG_REGISTRY`） |

## 桌面端打包与发布（Electron）

- **日常构建**：`.github/workflows/desktop-client-ci.yml`（改 `packages/desktop/**` 时自动触发）→ 三平台打包出构件上传 Artifact，**不发布**（`--publish=never`）
- **发布 Release**：`.github/workflows/desktop-client-release.yml`，两种触发：
  1. 推版本 tag：`git tag v0.1.0 && git push origin v0.1.0`（tag 与 `packages/desktop/package.json` 的 `version` 一致）
  2. Actions 页手动 Run workflow
  
  三平台构建后经 electron-builder 自动发布到 GitHub Releases（Windows NSIS 安装包 / macOS DMG / Linux AppImage + 自动更新 latest.yml）。发新版本前先 bump `packages/desktop/package.json` 的 `version`。
- **本地打包**：`cd packages/desktop && npm run electron:build -- --publish=never`

## 方式二：本地开发

```bash
# 1. 基础设施
docker compose up -d postgres redis minio
# 2. 后端
pip install -e .
alembic upgrade head        # 注：迁移目录缺失，实际靠启动时 init_db() create_all
uvicorn services.main:app --reload --port 8000
celery -A services.celery_app worker --loglevel=info
# 3. 前端
cd packages/desktop && npm install
npm run electron:dev        # Vite dev 15168，/api 代理到 18000（见 vite.config.ts，如后端在 8000 需调整）
```

`start.py` / `start.bat`：环境自检（Python 版本/依赖/PG/Redis/.env）+ 建库 + 启动 uvicorn。

## 环境变量全表（前缀 `BMP_`，见 `core/settings.py`）

### 基础

| 变量 | 说明 | 默认 |
|------|------|------|
| BMP_DEBUG / BMP_HOST / BMP_PORT | 调试/监听/端口 | true / 0.0.0.0 / 8000 |
| BMP_DATABASE_URL | PostgreSQL 连接串（asyncpg） | postgresql+asyncpg://postgres:postgres@localhost:5432/bidmaster |
| BMP_REDIS_URL | Redis（Celery broker） | redis://localhost:6379/0 |
| BMP_CHROMA_DIR | 向量库目录 | ./chroma_db |
| BMP_PROJECTS_ROOT | 项目文件根目录 | ./projects |
| BMP_TENDER_TEXT_MAX_CHARS | 招标文本截断上限 | 32000 |

### LLM（详见 08）

| 变量 | 说明 | 默认 |
|------|------|------|
| BMP_LLM_DEFAULT_MODEL | 默认模型（`provider/model` 或裸模型名） | deepseek/deepseek-chat |
| BMP_LLM_API_KEY / BMP_LLM_API_BASE | 凭证与网关地址 | - / https://api.deepseek.com |
| BMP_LLM_FALLBACK_MODES | 降级模型（逗号分隔） | ollama/qwen2.5 |
| BMP_LLM_MAX_RETRIES | 最大重试次数 | 3 |

### 嵌入

| 变量 | 说明 | 默认 |
|------|------|------|
| BMP_EMBEDDING_MODE | api / local | api |
| BMP_EMBEDDING_MODEL | 嵌入模型 | text-embedding-v3 |
| BMP_EMBEDDING_API_KEY / _API_BASE | DashScope 凭证 | - / https://dashscope.aliyuncs.com/compatible-mode/v1 |

### MinerU OCR

| 变量 | 说明 | 默认 |
|------|------|------|
| BMP_MINERU_MODE | cloud / self_hosted | cloud |
| BMP_MINERU_API_KEY / _ENDPOINT | 凭证/端点 | - / https://mineru.net/api/v4 |
| BMP_MINERU_TIMEOUT / _POLL_INTERVAL / _MAX_POLLS | 超时 180s / 轮询 5s / 最多 60 次 | |
| BMP_MINERU_MODEL_VERSION | vlm / pipeline | vlm |

> MinerU 与 LLM 默认模型均可在前端"平台设置"页配置（写入 .env 或 DB），无需手改文件。

## 生产注意事项

- `.env` 含明文 API Key（llm_provider_configs 表亦明文存储），权限收紧 0600，勿入镜像/仓库
- 修改 DB 中已有表的字段需手工 ALTER（create_all 不会加列）
- Celery beat 每小时触发商机监控，确认 Redis 可达
- 前端 vite dev 代理目标端口（18000）与后端 BMP_PORT（8000）不一致，本地联调需对齐
