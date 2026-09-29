# 04 数据模型

定义于 `services/models.py`（SQLAlchemy 2.0 声明式，全异步）。

## 迁移机制（重要）

- `alembic.ini` 存在但**迁移目录缺失**，实际建表依赖 `init_db()` 的 `Base.metadata.create_all`
- `create_all` 只建新表、**不会给已有表加列** —— 给现有表加字段需手工执行 `ALTER TABLE` 或删库重建
- `db/init_pg.sql` / `db/init_mysql.sql` 为容器初始化脚本（建库/建扩展/初始数据）

## 业务主表

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `users` | email(unique)、name、password_hash、is_active | 用户 |
| `projects` | user_id→users、name、status、tender_file_path、config(JSON) | 项目，config 存各阶段偏好 |
| `documents` | project_id、doc_type、file_path、parsed_content(MEDIUMTEXT) | 上传与解析后的文档 |
| `analyses` | project_id、analysis_type、result(JSON) | 解读结果（关键信息/评分矩阵/风险） |
| `outlines` | project_id、content(JSON) | 投标大纲 |
| `chapters` | outline_id、title、content(MEDIUMTEXT)、mode | 章节，mode A-D 区分生成方式 |
| `check_reports` | project_id、check_type、result(JSON)、score | 检查报告（21 项检查共用） |
| `notifications` | user_id、type、content、is_read | 站内通知 |

## 配置类表

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `llm_provider_configs` | provider_id、display_name、api_key(明文)、api_base、default_model、is_default、enabled、note | LLM 供应商配置，一供应商可多条（多 Key 负载/备用）；is_default 唯一（路由层维护），写操作后热重建运行时网关（见 08） |
| `agent_configs` | name(unique)、workflow_dsl(JSON)、skills(JSON)、config(JSON)、enabled | 每 Agent 的 model/temperature/max_tokens 配置（注意：目前运行时调用链未消费 model 字段） |
| `skill_configs` | name、config(JSON)、enabled | Skill 级配置 |
| `templates`（format 模板） | name、config(JSON) | 排版模板（来源 `templates/default.yaml`） |

## 知识库与资讯

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `knowledge_bases` | name、description、doc_count | 知识库（向量数据在 ChromaDB，非 PG） |
| `monitoring_tasks` | keywords、sites、interval_minutes、enabled | 商机监控任务 |
| `crawl_results` | task_id、title、url、content、score | 抓取结果 |
| `news_source_registry` | code、name、industry_code、enabled | 资讯源注册表（对应 `services/news/sources.yaml`） |
| `hotspot_items` | title、industry_code、score、is_hot | 今日热点聚合 |

## RBAC 四表

`rbac_roles`、`rbac_permissions`、`rbac_role_permissions`（多对多）、`rbac_user_roles`（多对多）。权限为 code + category 两级（菜单级/操作级），由 `rbac_middleware.require_permission` 消费。

## API Key 相关（服务端部署模式）

| 表 | 关键字段 | 说明 |
|----|----------|------|
| `api_keys` | key、type(subscription/credits)、user_email(弱关联)、expires_at | 桌面端访问服务端凭证 |
| `api_key_usage` | api_key_id、endpoint、tokens | 用量流水 |

## 关系总览

```
users 1──N projects 1──N documents / analyses / outlines / check_reports
outlines 1──N chapters
monitoring_tasks 1──N crawl_results
rbac_users N──N rbac_roles N──N rbac_permissions
```

> 注意：部分关联用逻辑外键（字符串 id），未强制 FK 约束，删除时需应用层保证一致性。
