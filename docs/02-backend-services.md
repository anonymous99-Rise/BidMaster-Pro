# 02 后端服务层（services/）

## 应用入口 `services/main.py`

- **lifespan 启动流程**：`register_builtin_skills()`（注册 47 个内置 Skill）→ `init_db()`（create_all 建表，DB 不可用时降级启动）
- **CORS**：放行 Electron origins（`file://`、`http://localhost:*`）
- **路由注册**（前缀 `/api`）：16 个 Router，见下表
- **附加端点**：`/api/health`、`/api/stats`

## 路由清单 `services/routers/`

| Router 文件 | 前缀 | 核心端点 | 说明 |
|-------------|------|----------|------|
| `auth.py` | /api/auth | login/register/me | 用户认证（JWT Bearer） |
| `projects.py` | /api/projects | CRUD + 阶段门禁状态 | 项目全生命周期 |
| `interpret.py` | /api/interpret | upload/parse/analyze/scoring-matrix/risk-alert/export | 招标解读：上传→解析→AI 解读→评分矩阵→风险预警 |
| `generate.py` | /api/generate | outline/stream/stream-all/chapter CRUD/export | 投标生成：大纲、逐章 SSE 流式生成、导出 docx（最大最复杂） |
| `check.py` | /api/check | 20+ 检查端点（full/单项/上传模式） | 投标检查，每项检查对应一个 Skill |
| `format_doc.py` | /api/format | format/check/compare/export/templates CRUD | 文档排版：docx 源格式，doc/pdf 导出，模板管理 |
| `skills.py` | /api/skills | list/{name}/execute | Skill 引擎的通用执行入口 |
| `llm_config.py` | /api/llm | providers/configs CRUD/test/fetch-models/default-model/agent-models/usage | LLM 供应商与 Agent 模型配置（见 08） |
| `news.py` | /api/news | tasks CRUD/run/results/today-hot/industries/sources/aggregate/hotspots | 商机监控与热点聚合 |
| `knowledge.py` | /api/knowledge | 知识库 CRUD/upload/search/sync | RAG 知识库管理 |
| `rbac.py` | /api/rbac | roles/permissions/users/assign | 角色权限管理 |
| `agent_runtime.py` | /api/agent | run/run_step/status/resume | Agent 运行时（多步执行/恢复） |
| `ai_image.py` | /api/ai-image | generate | AI 配图 |
| `mineru_config.py` | /api/mineru | config GET/PUT/test、ocr | MinerU OCR 配置与抽取 |
| `api_key.py` | /api/api-keys | CRUD/usage | 桌面端 VIP 用户访问服务端的 ApiKey（subscription/credits 两类） |

## 中间件 `services/middleware/`

| 文件 | 职责 |
|------|------|
| `rbac_middleware.py` | `get_current_user`（JWT 解析注入 User）、`require_permission(code)`（操作级权限校验依赖） |
| `api_key.py` | 桌面端 ApiKey 认证（服务端部署模式） |

## 业务 Agent `services/agents/`

6 个 Agent（继承 `core/agent_framework`），由 `agent_bootstrap.py` 统一装配（工具权限、Skill→Tool 包装、消息总线）：

| Agent | 职责 |
|-------|------|
| `tender_interpret_agent.py` | 招标解读（调用解读类 Skill 为工具） |
| `outline_agent.py` | 大纲生成 |
| `content_agent.py` | 章节内容生成 |
| `compliance_check_agent.py` | 合规检查 |
| `format_agent.py` | 格式排版 |
| `export_agent.py` | 导出 |

`skill_tool_adapter.py` 把 Skill 包装成 Agent 可调用的 Tool。

## Celery 异步任务 `services/celery_app.py`

- broker/backend：Redis（`BMP_REDIS_URL`）
- **beat 定时**：每小时 `run_news_monitor`
- **任务**：`run_news_monitor`（商机抓取）、`run_full_check`（批量检查）、`run_batch_format`（批量排版）——各自新建 event loop 运行异步代码

## 依赖注入

- **DB 会话**：`services/database.py` 全局单例 engine/sessionmaker，`get_db()` yield `AsyncSession` 并自动 commit
- **LLM 网关**：`services/llm_factory.py` 单例 `get_llm_gateway()`；DB 默认配置变化时由 `llm_config` 路由调用 `set_llm_gateway_from_provider()` 热重建；否则回退 `.env` 配置

## MCP Server `services/mcp/server.py`

基于 fastmcp 暴露工具，供外部 MCP 客户端调用平台能力。

## 通用返回约定

写操作返回 `{"success": True, ...}`；校验失败返回 `{"success": False, "error": "..."}` 或 HTTP 4xx；列表端点返回 `{"items": [...]}` 或具名键（如 `{"configs": [...]}`）。前端按各 API 分组对应解析。
