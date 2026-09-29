# 08 LLM 供应商配置指南（含 Sub2API）

## 配置架构总览

```
配置入口（三处）
├── .env / 环境变量        BMP_LLM_*（core/settings.py 读取）—— 兜底
├── 数据库 llm_provider_configs 表 —— 主要方式（平台设置页维护）
└── agent_configs 表       每 Agent 的 model/temperature（运行时调用链暂未消费）

运行时生效链路
DB 默认配置（is_default=true 且 enabled）
  → llm_config 路由写操作后调 set_llm_gateway_from_provider() 热重建单例网关
  → 无 DB 默认配置时回退 .env（get_llm_gateway() 惰性初始化）
```

所有调用最终经 `core/llm_gateway/gateway.py` 的 `LLMGateway`（openai.AsyncOpenAI 直连 OpenAI 兼容 API，自动补 `/v1`，重试 + 降级 + response_format 自动降级）。

## 内置供应商（GET /api/llm/providers）

| id | 名称 | 默认 API Base | 预设模型示例 |
|----|------|---------------|--------------|
| deepseek | DeepSeek | https://api.deepseek.com | deepseek-chat, deepseek-reasoner |
| zhipu | 智谱AI | https://open.bigmodel.cn/api/paas/v4 | glm-4-plus |
| qianfan | 百度千帆 | https://aip.baidubce.com | ernie-4.0 |
| dashscope | 阿里百炼 | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-max/plus/turbo |
| siliconflow | 硅基流动 | https://api.siliconflow.cn/v1 | deepseek-ai/DeepSeek-V3 等 |
| ollama | Ollama(本地) | http://localhost:11434 | qwen2.5, llama3.1 |
| openai | OpenAI | https://api.openai.com/v1 | gpt-4o 等 |
| **sub2api** | **Sub2API(自定义网关)** | 无（用户自填） | 无预设，动态拉取 |

## Sub2API 自定义模型配置

[Sub2API](https://github.com) 类网关把订阅账号池转成 **OpenAI 兼容 API**，模型随账号池动态变化，因此平台提供动态拉取能力。

### 前提

- 网关需暴露 `GET {base}/v1/models` 与 `POST {base}/v1/chat/completions`（标准 OpenAI 兼容端点；部分反代只提供 `/v1/responses` 的不适用）
- 拿到网关地址与访问 Key

### 平台设置页配置步骤

1. 平台设置 → LLM 供应商 → 新增配置
2. 供应商选 **Sub2API(自定义网关)**
3. 填 **API Base URL**（必填，如 `http://your-sub2api-host:8000`；无需带 `/v1`，后端自动补）
4. 填 **API Key**
5. 点 **获取模型列表** → 后端调 `GET {base}/v1/models` 拉取模型 → 预设下拉自动填充（也可手动输入任意模型名）
6. 选定默认模型 → 保存 → 点 **设为默认** → 运行时网关立即切换（无需重启）

多模型场景：同一网关可建多条配置（相同 Base/Key、不同默认模型），在"智能体模型配置"里为不同 Agent 选不同模型。

### .env 方式（无 UI / 服务端部署）

```bash
BMP_LLM_API_BASE=http://your-sub2api-host:8000
BMP_LLM_DEFAULT_MODEL=claude-sonnet-4-5    # 网关暴露的模型名，可不带 provider 前缀
BMP_LLM_API_KEY=sk-xxx
```

模型名带 `sub2api/` 前缀（如 `sub2api/claude-sonnet-4-5`）也可，网关会自动剥离前缀（白名单见 gateway.py `_strip_provider_prefix`）。

### 相关 API

| 端点 | 说明 |
|------|------|
| `POST /api/llm/fetch-models` | `{api_base, api_key}` → `{success, models: [id...]}`，拉取网关模型列表 |
| `POST /api/llm/test` | 临时构建网关发一条测试消息验证连通 |
| `POST /api/llm/configs` | 新建配置（provider_id 校验 `^[A-Za-z0-9._\-]{1,64}$`，api_base 校验 http(s)） |
| `POST /api/llm/configs/{id}/default` | 设为默认（**热重建运行时网关**） |
| `GET /api/llm/configs/{id}/reveal` | 查看 Key 明文（需登录） |

### 生效机制说明（2025-09 更新）

早期版本"设为默认"只改 DB 标志，运行时网关仍读 `.env`，两者脱节。现已在 `services/routers/llm_config.py` 引入 `_refresh_default_gateway()`：**新建/更新/删除/设默认**任一写操作后，从 DB 读当前默认配置并调用 `services/llm_factory.set_llm_gateway_from_provider()` 重建单例网关；无默认配置时回退 `.env`。

## 已知限制与排查

| 现象 | 原因/处理 |
|------|-----------|
| 配置保存后调用仍走旧模型 | 确认已点"设为默认"且配置 enabled；DB 无默认时回退 .env |
| 获取模型列表 404/405 | 网关不含 `/v1/models` 端点，手动输入模型名即可 |
| `response_format` 报错 | 网关自动去掉 json_object 重试，属正常降级 |
| agent_configs 的模型字段不生效 | 该表 model 字段运行时调用链暂未消费，按 Agent 分流请建多条供应商配置 |
| Token 用量统计为空 | 统计在网关内存 deque（进程生命周期内），重启清零 |
