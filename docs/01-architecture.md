# 01 总体架构

## 定位

BidMaster Pro 是基于 AI Agent 架构的全流程智能招投标平台，覆盖 4 阶段流水线：**招标解读 → 投标生成 → 投标检查 → 文档排版**，另含资讯监控、知识库、RBAC 权限等辅助能力。

## 系统分层

```
┌─────────────────────────────────────────────────────┐
│  Desktop Client（packages/desktop）                  │
│  Electron 41 + React 19 + TypeScript + Vite 7      │
│  main/(主进程) preload/ renderer/(React SPA)        │
└──────────────────┬──────────────────────────────────┘
                   │ REST API（/api/*，Bearer Token）
                   │ SSE（生成内容流式输出）
┌──────────────────▼──────────────────────────────────┐
│  FastAPI Server（services/）                         │
│  main.py 入口 + 16 个 Router + 中间件（RBAC/APIKey） │
├─────────────────────────────────────────────────────┤
│  业务编排层                                           │
│  ├── services/agents/     6 个业务 Agent             │
│  ├── services/{stage}/skills/  47 个内置 Skill       │
│  └── core/agent_engine/   LangGraph 流水线编排 + 门禁│
├─────────────────────────────────────────────────────┤
│  核心引擎（core/）                                    │
│  ├── llm_gateway    OpenAI 兼容直连网关（含重试/降级）│
│  ├── skill_engine   Skill 抽象 + 注册表 + 加载器      │
│  ├── rag_engine     向量检索（Chroma + BM25 + RRF）  │
│  ├── doc_engine     多格式解析 + 章节检测 + ONNX 分类│
│  ├── agent_framework  Agent 基类/注册表/熔断/记忆    │
│  └── ocr/mineru_client  扫描件 OCR 客户端            │
├─────────────────────────────────────────────────────┤
│  基础设施                                             │
│  PostgreSQL 16(AsyncPG) / Redis 7(Celery)           │
│  MinIO(对象存储) / ChromaDB(向量) / Celery Worker   │
└─────────────────────────────────────────────────────┘
```

## 技术栈速查

| 层 | 技术 | 说明 |
|----|------|------|
| 后端 | FastAPI + Python 3.12 | `services/main.py` 入口，uvicorn 启动 |
| ORM | SQLAlchemy 2.0 (async) + AsyncPG | 建表靠 `init_db()` 的 `create_all`（无 alembic 迁移） |
| LLM | openai.AsyncOpenAI 直连 | `core/llm_gateway/gateway.py`，OpenAI 兼容 API（DeepSeek/硅基流动/Sub2API 等） |
| 编排 | LangGraph | `core/agent_engine/orchestrator.py`，按 DSL 组装 StateGraph |
| 向量 | ChromaDB + Sentence-Transformers | 嵌入走 DashScope API（`BMP_EMBEDDING_*`） |
| 异步任务 | Celery + Redis | 资讯监控、批量检查、批量排版 |
| 前端 | React 19 + Zustand + TanStack Query | 样式为内联 style + CSS 变量（`styles/globals.css`） |

## 核心数据流（投标生成示例）

```
上传招标文件 → POST /api/interpret/upload
  → doc_engine 解析(PDF/DOCX/TXT) → documents.parsed_content
→ POST /api/interpret/analyze
  → TenderInterpretSkill → LLMGateway.chat → analyses 表
  → gate_keeper.mark_passed(project, "interpret")
→ POST /api/generate/outline
  → OutlineGenSkill（可挂 RAG 知识检索）→ outlines 表
→ POST /api/generate/stream/{chapter_id}   (SSE)
  → ContentGenSkill → stream_chat 流式写回前端 → chapters 表
→ POST /api/check/full
  → 21 项检查 Skill 串/并执行 → check_reports 表
→ POST /api/format/export
  → docx（唯一中间格式）→ doc/pdf 转换 → 文件下载
```

## 阶段门禁（Gate Keeper）

四阶段流水线由 `core/agent_engine/gate_keeper.py` 控制顺序：前一阶段未通过则后一阶段接口拒绝执行（`GateNotPassedException`）。门禁状态按 project 记录。

## 关键设计决策

| 决策 | 说明 |
|------|------|
| 弃用 LiteLLM 运行时 | 早期经 LiteLLM 转发，因参数转发问题改为 openai SDK 直连 OpenAI 兼容 API（见 gateway.py 模块注释）；模型名仍保留 `provider/model` 的 litellm 风格前缀，由 `_strip_provider_prefix` 剥离 |
| docx 为唯一中间格式 | 所有导出（doc/pdf）先产出 docx 再转换，避免多源头格式漂移 |
| 无 alembic 迁移 | `alembic.ini` 存在但迁移目录缺失，实际建表走 `init_db()` create_all；给已有表加列需手工 SQL |
| DB 配置热生效 | LLM 供应商配置存 DB（`llm_provider_configs`），写操作后经 `set_llm_gateway_from_provider` 重建运行时网关；无 DB 默认配置时回退 `.env` |
| Skill 为最小能力单元 | 所有 AI 能力封装为 Skill（`core/skill_engine/base.py`），由 LangGraph 流水线或 Agent 工具两种方式消费 |

## 目录结构

```
BidMaster-Pro/
├── core/                  # 核心引擎（见 03）
├── services/              # FastAPI 应用（见 02）
│   ├── routers/           # 16 个 API 路由
│   ├── agents/            # 6 个业务 Agent
│   ├── {interpret,generate,check,format,news}/skills/
│   ├── middleware/        # RBAC / API Key
│   ├── mcp/               # MCP server
│   └── models.py          # 全部 SQLAlchemy 模型（见 04）
├── db/                    # init_pg.sql / init_mysql.sql 初始化脚本
├── packages/desktop/      # Electron 前端（见 06）
│   ├── main/ preload/ renderer/src/
├── templates/default.yaml # 公文排版参数模板
├── docker/                # docker-compose + Dockerfile（见 07）
├── skills/                # SKILL.md 说明文档（非代码）
├── start.py / start.bat   # 本地快速启动脚本
└── docs/                  # 本文档目录
```
