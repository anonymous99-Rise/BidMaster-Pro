# 03 核心引擎（core/）

## LLM 网关 `core/llm_gateway/`

### gateway.py — `LLMGateway`

基于 `openai.AsyncOpenAI` 直连任何 OpenAI 兼容 API（DeepSeek/硅基流动/Ollama/Sub2API 网关等）。

| 成员 | 说明 |
|------|------|
| `__init__(config)` | config：`{providers:[{api_key,api_base}], default_model, fallback_models, max_retries}`；`api_base` 自动补 `/v1` 后缀 |
| `_strip_provider_prefix(model)` | 剥离 `provider/model` 前缀（白名单含 deepseek/openai/ollama/zhipu/dashscope/…/sub2api/custom） |
| `_build_client()` | 取 `providers[0]` 构建客户端，timeout 300s，内部重试关闭（自行控制） |
| `chat(messages, model, temperature, stream, response_format, max_tokens)` | 主入口；按 `max_retries` 重试 + `fallback_models` 降级；`response_format` 不支持时自动去掉重试 |
| `collect_json(messages, schema, validator, ...)` | 强制 `json_object` 模式 + `JsonRepairEngine` 修复 + schema 校验 |
| `stream_chat(messages, ...)` | 流式输出；中断时带已收集内容续写重试 |
| `chat_with_tools(messages, tools, ...)` | function calling，返回 `ToolCallResponse` |
| `get_token_summary()` | 内存 token 用量统计（deque 上限 10000 条） |

### json_repair.py — `JsonRepairEngine`

处理 LLM 返回的脏 JSON：剥离 think 标签/代码块围栏、提取括号片段、修复常见语法错误、按 schema 校验，必要时回调 `repair_chat_fn` 让 LLM 自修复。

## Agent 引擎 `core/agent_engine/`

| 文件 | 职责 |
|------|------|
| `orchestrator.py` | `AgentOrchestrator`：按 pipeline DSL（entry/nodes/edges，node 绑定 skill、可要求 gate）构建 LangGraph `StateGraph` 并执行 |
| `gate_keeper.py` | 阶段门禁：`mark_passed(project_id, stage)` / `is_passed()`，保证解读→生成→检查→排版顺序 |
| `state.py` | 流水线共享状态定义 |

## Agent 框架 `core/agent_framework/`

| 文件 | 职责 |
|------|------|
| `agent.py` / `types.py` | Agent 基类与核心类型（ToolCallItem/ToolCallResponse 等） |
| `registry.py` | AgentRegistry：按名注册/发现 Agent |
| `supervisor.py` | 多 Agent 监督调度 |
| `message_bus.py` | Agent 间消息总线 |
| `memory.py` | Agent 会话记忆 |
| `pool.py` | Agent 实例池 |
| `circuit_breaker.py` | LLM 调用熔断器 |
| `checkpoint.py` | 执行检查点（配合 /api/agent/resume） |
| `tool.py` / `db_query_tools.py` | Tool 抽象与 DB 查询工具 |

## Skill 引擎 `core/skill_engine/`

| 文件 | 职责 |
|------|------|
| `base.py` | `Skill` 抽象类（name/description/category/version + `execute(ctx)`）、`SkillContext{project_id, db, llm, parameters}`、`SkillResult{success, data, tokens_consumed}` |
| `registry.py` | `SkillRegistry` 单例：register/get/list |
| `loader.py` | 从外部目录动态加载 Skill |
| `check_normalizer.py` | 检查结果归一化 |

新增 Skill 步骤：继承 `Skill` → 实现 `execute` → 在 `services/skill_bootstrap.py` 注册。

## RAG 引擎 `core/rag_engine/`

| 文件 | 职责 |
|------|------|
| `embedder.py` | 嵌入客户端：API 模式走 DashScope compatible-mode（`BMP_EMBEDDING_MODEL=text-embedding-v3`），local 模式走 sentence-transformers |
| `vector_store.py` | ChromaDB 封装（持久化目录 `BMP_CHROMA_DIR`） |
| `retriever.py` | `HybridRetriever`：向量 + BM25 混合召回 + RRF 融合重排，支持公司画像过滤 |

## 文档引擎 `core/doc_engine/`

| 文件 | 职责 |
|------|------|
| `parsers/` | `pdf_parser.py`（pdfplumber+PyMuPDF）、`docx_parser.py`（python-docx/mammoth）、`txt_parser.py`，注册表模式（`base.py`） |
| `section_detector.py` | 章节结构识别（标题层级/编号规则） |
| `onnx_classifier.py` | ONNX Runtime 文档分类模型 |

## OCR `core/ocr/mineru_client.py`

MinerU 客户端：cloud（mineru.net SaaS）/ self_hosted 两种模式，上传→轮询→取 markdown 结果。参数见 `BMP_MINERU_*`（超时/轮询间隔/最大轮询次数/模型版本 vlm|pipeline）。

## 全局配置 `core/settings.py`

pydantic-settings，环境变量前缀 `BMP_`（完整变量表见 07 部署文档）。另有 `core/task_manager.py`（任务管理）、`core/exceptions.py`（`LLMGatewayError` 等异常层级）。
