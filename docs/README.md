# 智能招投标平台项目文档

按模块划分的技术文档索引。

| 文档 | 内容 |
|------|------|
| [01-architecture.md](01-architecture.md) | 总体架构：系统分层、技术栈、核心数据流 |
| [02-backend-services.md](02-backend-services.md) | services 层：FastAPI 入口、16 个路由、中间件、Celery 任务、Agent |
| [03-core-engines.md](03-core-engines.md) | core 层：LLM 网关、Agent 引擎、Skill 引擎、RAG、文档引擎、OCR |
| [04-database.md](04-database.md) | 数据模型：全部 SQLAlchemy 表、字段、关系、迁移说明 |
| [05-skills.md](05-skills.md) | Skill 清单：47 个内置 Skill 按分类详解 |
| [06-frontend.md](06-frontend.md) | 前端：Electron + React 结构、路由、状态管理、API 封装、设置页 |
| [07-deployment.md](07-deployment.md) | 部署：Docker Compose、本地开发、环境变量全表 |
| [08-llm-providers.md](08-llm-providers.md) | LLM 供应商配置指南：内置供应商、Sub2API 自定义网关、生效链路 |

## 快速导航

- **想了解整体设计** → 01 架构
- **要改后端接口** → 02 服务层 + 04 数据模型
- **要调 LLM / 配 Sub2API** → 08 LLM 供应商配置
- **要扩展检查规则** → 05 Skill 清单 + 03 Skill 引擎
- **要改界面** → 06 前端
- **要部署** → 07 部署
