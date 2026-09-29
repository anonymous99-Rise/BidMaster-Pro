# 05 Skill 清单（47 个内置 Skill）

注册入口：`services/skill_bootstrap.py` 的 `register_builtin_skills()`（main.py lifespan 调用）。Skill 基类与上下文见 03 文档；根目录 `skills/` 下的 SKILL.md 为各阶段说明文档。

## 解读类（interpret，4 个）

| Skill | 功能 |
|-------|------|
| TenderInterpretSkill | 招标文件 AI 解读：提取项目概况、资质要求、技术参数、废标条款 |
| ScoringMatrixSkill | 生成评分细则对照矩阵 |
| RiskAlertSkill | 多维度风险评估与废标风险预警 |
| InterpretExportSkill | 解读结果导出 |

## 生成类（generate，9 个）

| Skill | 功能 |
|-------|------|
| OutlineGenSkill | 基于解读结果生成投标大纲（对齐评分项） |
| StructureTemplateSkill / ScoreCoverageSkill | 结构模板生成 / 评分项覆盖率检查 |
| ContentGenSkill | 章节内容生成（支持 SSE 流式） |
| ContentExpandSkill | 内容扩写/优化 |
| MandatoryReqExtractSkill | 强制性要求抽取（供检查阶段对照） |
| KnowledgeAssistSkill | RAG 知识库辅助检索注入 |
| MultiAgentPipelineSkill | 多 Agent 协作流水线（content_cleaner.py 为配套清洗器） |
| AiImageSkill | AI 配图 |

## 检查类（check，22 个）

| Skill | 检查项 |
|-------|--------|
| ComplianceCheckSkill | 综合合规性 |
| MandatoryReqCheckSkill | 强制性要求逐条响应 |
| DisqualificationCheckSkill | 废标项扫描 |
| QualificationCheckSkill | 资格条件符合性 |
| DepositCheckSkill | 保证金 |
| SignatureCheckSkill | 签字盖章 |
| ValidityCheckSkill | 有效期（投标有效期/证件有效期） |
| ConsistencyCheckSkill | 前后文一致性（金额/日期/数量） |
| DuplicateCheckSkill | 重复率/抄袭检测 |
| DocIntegrityCheckSkill | 文档完整性 |
| CrossCheckSkill | 招标-投标交叉核对 |
| PricingCheckSkill | 报价合规 |
| PricingLogicCheckSkill | 报价逻辑与竞争性分析 |
| FitScoreSkill | 评分项匹配打分 |
| SelfcheckListSkill | 自检清单生成 |
| AITextCheckSkill | AI 生成文本痕迹检测 |
| RiskScoreSkill | 综合风险评分 |
| SampleReportCheckSkill | 样例报告检查 |
| JointBidCheckSkill | 联合体投标检查 |
| EbidSubmitCheckSkill | 电子投标递交要求检查 |
| WhitelistFilterSkill | 白名单过滤（检查项启停） |
| CheckReportExportSkill | 检查报告导出 |

## 排版类（format，6 个）

| Skill | 功能 |
|-------|------|
| DocxFormatSkill | 按 `templates/default.yaml` 公文参数排版 docx（字体/字号/页边距/行距） |
| BidDocxExportSkill | 投标文件 docx 导出（**唯一中间格式**） |
| DocExportSkill | docx → doc 转换导出 |
| PdfExportSkill | docx → PDF（WeasyPrint）导出 |
| RevisionSkill | 修订模式（批注/审阅） |
| MinerUOcrSkill | 扫描件 OCR 抽取（调用 `core/ocr/mineru_client`） |

## 资讯类（news，5 个）

| Skill | 功能 |
|-------|------|
| NewsCrawlerSkill | 定时抓取招投标公告（源注册表 `services/news/sources.yaml`；配套 `fetchers.py/dedup.py`） |
| AISemanticFilterSkill | AI 语义过滤（公司画像匹配） |
| NotificationSkill | 通知推送（apprise 多渠道） |
| IndustryClassifySkill | 行业分类（配套 `classify.py`，jieba+规则） |
| HotspotAggregateSkill | 今日热点聚合评分（配套 `scoring.py`） |

## 执行方式

1. **流水线**：`AgentOrchestrator` 按 DSL 编排（node 绑定 skill 名，可设 `require_gate`）
2. **通用执行**：`POST /api/skills/{name}/execute?project_id=...` 直接执行
3. **Agent 工具**：经 `skill_tool_adapter` 包装为 Tool 供 Agent 调用

## 新增 Skill 步骤

1. 在对应阶段目录建 `xxx_skill.py`，继承 `Skill`，实现 `async def execute(self, ctx)`
2. 在 `services/skill_bootstrap.py` import 并 `registry.register(XxxSkill)`
3. 重启服务（lifespan 重新注册）；可选在 `skill_configs` 表存配置
