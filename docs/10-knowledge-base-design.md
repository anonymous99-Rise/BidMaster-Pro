# 知识库模块设计 — 商务标为核心的知识库与智能投标决策链路

> 状态:设计稿 v5(2026-10-09,定稿。新增公司空间/知识图谱/多代理工作流架构,
> 开发计划已确认。基于两份真实招标文件 + 4 仓库源码级深挖 + 公开信息验证)
> 定位:知识库是**与"招标工作流、资讯与管理"同级的顶级模块**,
> 是阶段 1~4(备选→初筛→分析→评分)的地基。
> **核心认知(用户定调,两份真实文件实证):商务部分是投标的生命线**——
> 资格不过直接出局,红线踩中直接废标,商务得分点(业绩/团队/售后人员)
> 在真实评分表中可达 22 分,商务文件编制占标书工作量一半以上。
> 知识库的第一使命是商务标:资格勾对、红线检查、团队/业绩算分、商务文件自动生成。

---

## 一、商务标三关模型(整个模块的核心框架)

用真实招标文件(某市医保局数据智能化应用监管系统,服务类公开招标)校准,
商务部分的"生死线"是三道关,知识库的一切设计围绕这三关:

```
                       ┌─────────────────────────────────────────┐
                       │           商务标三关(知识库逐关支撑)        │
                       └─────────────────────────────────────────┘

第一关【资格关】资格性审查(8 项,全 pass/fail)──── 不过 = 出局,无评分资格
   营业执照/授权书/财务制度/设备与技术能力/税收社保/无违法记录/
   未列失信名单(可自动查信用中国)/中小企业声明函
   → 知识库支撑:资质库/财务库/信用库逐项勾对 + 承诺函自动生成
   (已对比两份西部省区政采招标文件:资格条件高度一致,均为政采法22条
     +中小企业声明——资格规则库通用性强,一次建成全项目复用)

第二关【红线关】符合性审查(9 条废标红线)────────── 踩中任一条 = 废标
   超预算/未签章/多方案/投标有效期不足/附加不可接受条件/不满足实质要求/
   其他无效条款/机器制作码一致(雷同标)/保证金同账号
   → 知识库支撑:规则库逐条检查(真实废标案例:本企业因"未响应投标
     有效期"被废,2026-08-17 某卫健部门项目公告——红线检查价值实证)

第三关【文件关+得分关】商务文件编制 + 商务得分点─── 编制质量+库底厚薄 = 商务分
   文件侧:商务要求响应表(条款逐条对照+偏离情况)/类似业绩证明/
     人员配备表/售后服务/中小企业声明/评审因素响应详情
     → 自动预填响应表,证明材料一键汇编,人只处理偏离项
   得分侧(某卫健部门全员人口二期真实评分表):业绩 5 分(近三年类似
     业绩每项1分)+ 项目团队 15 分(软考证书组合计分)+ 售后人员
     5 分(驻场/售后明细清单及证书)——商务得分点合计 22 分
     → 业绩库/人员库/证书库直接算分出材料(见 8.1 团队配置优化器)
```

> 前两关一票否决,第三关既出文件又出分——这才是"商务部分非常重要"的
> 完整含义。评分表里"商务响应"那 5 分只是冰山一角。

---

## 二、设计原则(含已拍板决策)

1. **商务优先**:知识库子模块按商务三关的价值排序建设,方案素材库(技术标)后置
2. **双库联动**(智标AI/钛投标/元启智标行业共识):企业私有库(准)+ 行业公开库(全),
   公开库定位"AI 预填 80% + 人审 20%"
3. **保守三态**:初筛判定只输出 ✓/✗/?,证据缺失一律进人审,绝不猜 matched
   (错杀可人工推翻,错放直接废标,代价不对称——rag-tender 实证设计)
4. **规则可沉淀**:每次人工修正回流规则库(错例沉淀),越用越准
5. **评分权重不拍脑袋**:解析招标文件真实细则优先,行业模板仅兜底
6. **【已拍板】商机分析独立成模块**(可另起名,如"商机雷达/投标决策"):
   备选库/分析库/投标库三页签,不并入资讯中心
7. **【已拍板】多租户架构**:company_id 贯穿所有知识库/商机/分析表,
   公司(企业)= 租户主线;单企业部署即只有一个 company,数据层天然隔离
8. **证书类型清单做成可配置字典**:初始内置 IT 集成建议稿
   (ISO三系/ITSS/CCRC/CMMI/涉密/安防/软考系列等),用户随时自定义增删
   ——不阻塞开发,先按建议稿跑起来

## 三、模块结构(前端导航,已按拍板更新)

```
智能招投标平台
├── 工作台 (Dashboard)
├── 招标工作流
│   ├── 标书解读 (Interpret)   ← 产出:资格条件/评分办法/废标条款 三大结构化 JSON
│   ├── 标书生成 (Generate)
│   ├── 标书排版 (Format)
│   └── 标书检查 (Check)
├── 资讯中心 (News)             ← 只做资讯入口,不再挂商机阶段
├── ★ 知识库 (KnowledgeBase) —— 新顶级模块(商务标优先,公司主线)
│   │   【公司空间: 左侧公司树(多租户) → 右侧子库页签 + 图谱视图】
│   ├── 企业资质 (certificate: 营业执照/ISO三系/ITSS/CCRC/CMMI/涉密/安防...)
│   ├── 从业人员 (personnel: 档案/职称/社保/软考证书)
│   ├── 证书库 (certificate(category=personnel): 注册类/职称类/特种作业)
│   ├── 业绩库 (achievement: 项目/金额/业主/证明文件, 公开采集预填)
│   ├── 财务与信用 (financial + credit: 审计/纳税/AAA/失信自查)
│   ├── 规则库 (rule: 数值规则/红线规则/证照同义词/错例修正沉淀)
│   ├── 商务文函 (doc_template: 承诺函/声明函/授权书/响应表模板)
│   ├── 方案素材 (material: 技术方案/施组 RAG, 二期)
│   └── 图谱视图 (graph: 公司资质全景关系图, 见第七章)
├── ★ 商机分析 (OpportunityInsight, 独立模块【已拍板】, 定名可再议:
│     备选叫法"商机雷达/投标决策/智能投标")
│   ├── 备选库 [阶段1] (资讯匹配落库 + 画像筛选)
│   ├── 分析库 [阶段3] (初筛结果 + 异步深度分析)
│   └── 投标库 [阶段4] (评分报告 + 商务响应表 + 决策建议)
└── 系统 (Settings)
```

### 3.1 公司空间与知识图谱(Obsidian 式构建,核心交互形态)

**用户原话**:以公司为主线构建——`某科技公司/
1.资质库/2.从业人员库/3.证书库/4.业绩库` 这样的分类结构,
用户去上传,子 agent 构建结构化图谱,像 Obsidian 一样。

**Obsidian 概念到本系统的映射**:

| Obsidian | 本系统对应物 |
|---|---|
| Vault(仓库) | 公司空间 CompanySpace(多租户:一个公司一个空间) |
| 文件夹结构 | 子库:资质库/从业人员/证书库/业绩库/财务信用 |
| 笔记(md 文件) | **实体卡片**:证书卡/人员卡/业绩卡/财务卡(结构化数据+来源文件) |
| 附件 | 来源文件:证照扫描件/合同 PDF/社保证明(挂在卡片上) |
| 双链 [[link]] | **关系边**:人员—持有→证书、人员—参与→业绩、业绩—响应→招标要求、
证书—满足→资格条件、公司—中标→业绩(公开采集) |
| 关系图谱视图 | 公司资质全景图谱:投标前看家底,勾对时看路径 |
| 插件/Obsidian API | 子 agent 构建流水线 + skills |

**关键设计决策**:文件是"实体的证据来源",不是知识本体——
上传的 PDF 存 MinIO,卡片是结构化实体(表里一行),链接是关系边。
这比 Obsidian 纯文件+frontmatter 更进一步:结构化数据才能做
勾对引擎/算分/有效期提醒(Obsidian 做不了这些)。

**用户上传体验(M1 核心场景)**:
1. 用户在"公司空间"直接拖入一个文件夹(如整包"资质材料/"),
   或按 Obsidian 式目录 `某公司/资质库/xxx.pdf` 整包上传
2. 子 agent 流水线自动:遍历→按文件名+内容分类到子库→OCR/抽取→
   建实体卡片→猜关系边(人员↔证书↔业绩)→全部标 `待人审`
3. 用户在"人审队列"逐卡片确认/改分类/补字段(批量操作),确认后
   is_audited=true 进可用池,关系边同时生效
4. 图谱视图实时更新:节点=实体卡片(按子库着色),边=关系;
   支持从图谱节点直达卡片详情

**关系边数据模型**(在第四章表之上):
```sql
knowledge_edge (
  id, company_id,
  src_type, src_id,        -- certificate/personnel/achievement/requirement...
  edge_type,               -- holds(持有)/participates(参与)/responds(响应)/
                           -- satisfies(满足)/wins(中标)/belongs(归属)
  dst_type, dst_id,
  confidence,              -- agent 猜的置信度, 人审后=1.0
  source                   -- agent_inferred/manual/public_agent
)
```

## 四、多代理工作流架构(skills + workflow + multiagent)

善用现有基础设施:Skill 引擎(core/skill_engine)+ Celery + LLM 网关。
**工作流 = 节点图;节点 = skill;节点间 = celery 任务链**。
(依赖图/增量重跑/人工门禁的设计抄 BidPilot engine.py 的
invalidated_by + human_gate,映射到 celery)

```
【工作流 W1:知识库构建】(上传触发, KB-M1)
  扫描遍历 → 分类 agent(文件名+首页内容→子库+实体类型)
           → 抽取 agent(正则→LLM→Vision 四级兜底)
           → 关联 agent(实体间猜关系边, 同名/同证号/同项目匹配)
           → 质检节点(有效期/证明齐套/必填字段缺失→待办)
           → 【human gate】人审队列(批量确认)
           → 入池(is_audited=true)

【工作流 W2:公开采集】(定时+手动, KB-M2)
  搜索(企业名→政采网/ggzy 已接源) → 解析(中标公告→业绩字段)
  → 去重(复用 compute_fingerprint) → 【human gate】人审 → 业绩库

【工作流 W3:商机初筛】(备选库逐条, KB-M6)
  解读(三大 JSON, 复用 Interpret) → 分流 → 数值规则(零成本)
  → 证据矩阵 → LLM 兜底 → 三态汇总
  → 产物: 资格勾对报告 + 红线检查报告 + 响应表草稿
  → 【human gate】人审队列 → 进分析库

【工作流 W4:深度分析+评分】(分析库逐项目并行, celery 异步, KB-M7)
  逐项并行: 团队配置优化器(纯规则) / 业绩算分 / 评分细则逐项
  / 红线复查 → 汇总评分报告(docx/pdf, 复用 Format 管线)
  → 投标库
```

**multi-agent 分工原则**(省钱+可控):
- 规则能算的绝不用 LLM(数值规则/团队优化器/业绩计数/红线比对)
- LLM 只做:分类置信度低时的兜底、模糊条款判定、深度分析叙述
- 每个节点落库(输入/输出/token 用量),可重跑、可审计
- human gate 是一等公民:三处人审点(知识库入池/采集确认/初筛复核)

## 五、数据模型(核心表,源码级借鉴已标注,company_id 全贯穿【多租户已拍板】)

```sql
-- ========== 商务知识库 6 张主表(综合 rag-tender qualifications/performance_projects
-- ========== 与 BidPilot models.py) ==========

certificate (        -- 企业资质证书(一证一记录, 关联来源文件)
  id, file_id,       -- 扫描件(knowledge_files, OCR 缓存 extracted_text)
  name, number,      -- 证书名称/编号, 如 "ISO9001 质量管理体系认证"
  category,          -- enterprise/personnel/financial
  level, scope,      -- 等级/覆盖范围( scope 是勾对关键: "信息系统集成" vs 要求比对)
  holder,            -- 持证主体(企业名/人员名)
  issue_date, expiry_date, issuing_authority,
  status,            -- valid/expiring(≤90天)/expired/needs_completion(计算字段)
  raw_text, is_audited,   -- OCR 原文/人审标记(未审核不进自动勾对)
  source             -- manual/ocr/public_agent
)

achievement (        -- 业绩库
  id, project_name, client_name, contract_no,
  contract_amount,   -- 金额(统一万元, 浮点)
  sign_date, completion_date, year,
  project_scope,     -- 项目内容摘要(与招标行业分类对齐)
  file_ids,          -- JSON: 合同/验收/发票 证明文件
  source, confidence -- manual / public_agent(中标公告解析, 人审后 verified)
)

personnel (          -- 人员
  id, name, id_number_enc, gender, title,     -- 职称
  role,              -- 拟派岗位(项目经理/技术负责人...)
  dept, social_insurance_proof_file_id        -- 社保证明(商务分常查)
)
personnel_certificate (
  id, personnel_id, cert_type,                -- 注册建造师/安全B证/特种作业...
  major, level, cert_no, expiry_date, file_id
)

financial (          -- 财务库
  id, report_type,   -- audit_report/financial_statement/tax/credit_rating
  period_start, period_end,
  total_assets, revenue, debt_ratio,          -- 勾对数值规则用(营收≥X万/负债率≤Y%)
  audit_agency, file_id
)

credit (             -- 信用库
  id, credit_type,   -- aaa_certificate/award/no_violation/credit_check_snapshot
  check_date, check_url, holder, file_id
)

-- ========== 规则库(可沉淀, 本项目原创设计) ==========

rule (
  id, rule_type,     -- numeric(数值)/redline(红线)/synonym(同义词)/custom
  name,              -- "注册资本要求"/"投标有效期红线"/"ISO体系同义词组"
  pattern,           -- numeric: 正则+运算符; redline: 检查项描述; synonym: 词组JSON
  operator, threshold, unit,   -- >=, 100, 万元
  severity,          -- critical(废标)/major/minor
  enabled, source,   -- built_in(内置)/learned(错例沉淀)
  hit_count, last_hit_at       -- 统计使用频率
)
match_correction (   -- 人工修正回流(抄 rag-tender match_corrections)
  id, match_result_id, original_status, corrected_status,
  reason, evidence_snapshot, created_at
)

-- ========== 招标文件解读产物(Interpret 扩展, 全 JSONB) ==========

tender_requirement ( -- 资格/商务要求(抄 BidPilot Requirement)
  id, tender_id, req_type,   -- qualification/commercial/scoring/delivery/format
  title, content, raw_text,
  mandatory,          -- true(必须/须/应当)/false(可以/建议加分)
  risk_level,         -- high(含废标词)/medium/low
  subject, action, condition, deadline, penalty,  -- 谁要做/做什么/条件/时限/罚则
  source_page, confidence
)
scoring_item (       -- 评分项(抄 BidPilot ScoringItem)
  id, tender_id, parent_id,
  title, score, min_score, max_score, criteria,  -- 分档描述原文
  scoring_method,     -- 客观评分/主观评分/价格评分
  evidence, source_page, coverage_status         -- uncovered/partial/covered
)

-- ========== 初筛结果与证据链 ==========

match_result (       -- 逐条要求勾对结果(抄 rag-tender match_results)
  id, requirement_id, qualification_id,
  status,             -- matched/unmatched/needs_review(保守三态)
  reason, mismatch_detail, expected_qualification,
  in_knowledge_base, similarity_score,
  evidence_items,     -- JSON: [{check_key,label,expected,actual,status,reason,critical}]
  confirmed_status    -- 人工确认(可推翻机器判定)
)
requirement_evidence_link (  -- 要求↔证明材料证据链(抄 BidPilot)
  id, requirement_id, source_page, quote,
  knowledge_evidence_ids, coverage_status,
  human_confirmed
)

-- ========== 商务文件与公开采集 ==========

doc_template (       -- 商务文函模板
  id, name,          -- "授权委托书"/"中小企业声明函"/"商务要求响应表"
  category,          -- commitment(承诺)/declaration(声明)/authorization/response_table
  file_id, placeholders,  -- JSON 占位符定义: {{company_name}}, {{legal_person}}
  last_used_at
)
intel_task, hotspot_items.stage, analysis_pool  -- (同 v2 设计, 略)
```

## 六、招标文件解读引擎(Interpret 扩展)——商务要求从哪来

解读产出三大结构化 JSON,是初筛三关的全部输入。
schema 与 prompt 技巧源码级借鉴 -bid-analysis(B1/B2/B3/B4 表格骨架 +
"样例即 schema" prompt 技法):

**1. 资格条件**(进第一关):
```json
{"sections":[
  {"id":"B1","title":"基本资格条件","columns":["序号","资格条件","具体要求"]},
  {"id":"B2","title":"禁止情形","columns":["序号","禁止情形"]},
  {"id":"B3","title":"专业资质要求","columns":["序号","资质名称","具体要求"]},
  {"id":"B4","title":"联合体要求","type":"text"}],
 "requirements":[{"text","type":"qualification","mandatory":true,
   "risk_level":"high","source_page","confidence",
   "subject","action","deadline","penalty"}]}
```

**2. 评分办法**(进评分报告):
```json
{"scoring_items":[{"parent_id","title","score","min_score","max_score",
   "criteria","scoring_method":"客观评分|主观评分|价格评分",
   "source_page","coverage_status":"uncovered"}]}
```

**3. 废标条款**(进红线关):
```json
{"clauses":[{"clause_text","severity":"critical|major|minor",
   "basis_text"(回拼原文页码),"source_module"}]}
```

**Prompt 关键技巧**(从 -bid-analysis prompts 目录提炼,直接采用):
- 样例即 schema:prompt 内嵌含具体 rows 的完整 JSON 示例
- 反编造:"文档中找不到就省略该 section"、"编号标题与原文一致,不得编造"
- 跨章汇总:"资格条件散落在公告/须知/专章等多处,需全部汇总"
- 硬软区分:"区分'必须/应当'(硬性)与'可以/建议'(加分)"
- 分值自校验:"各评分项分值加总应与总分一致,偏差须标注"
- 纯事实过滤(BidPilot):项目名称/编号/预算等前缀且不含"必须/须/应/提供"→不抽成要求

**章节定位三策略**(rule_splitter):Word Heading 样式 → 中文编号正则
(`第X章`/`一、`/`(一)`)→ 关键词表(评标办法/评分细则/资格要求…),
置信度 <0.7 才调 LLM 兜底(省钱)。评分章节追加规则:含表格且含"分/%"的段落强制入选;
交叉引用("详见X章/见附件Y")按引用展开。

## 七、初筛规则引擎(阶段 2)——三关逐条勾对(工作流 W3)

源码级参考 rag-tender `match_service.py`(1457 行完整实现)。

```
tender_requirement 逐条 →
  ①分流 _should_match:
      product_spec→技术响应表 / 提交时限类→待办 / 声明承诺类(信用中国、
      无重大违法等 20+ 关键词)→跳过资质匹配,转文函生成
  ②数值规则(零成本先跑):
      RULE_PATTERNS 5 类: 注册资本/合同金额/营收/资产负债率/年限
      正则提取 "注册资本≥100万元" → {value,operator,unit} → 与知识库
      financial/certificate 数值做运算符比较(≥≤><)
  ③候选匹配: 同义词表归一(ISO三系/社保/职称…9 组) + token 打分选候选
  ④证据矩阵 _verify_qualification_evidence(核心!):
      每条候选逐字段核验 certificate_type/holder/expiry_date/scope,
      各字段 pass/fail/unknown + critical 标记;
      相似度只选候选,全部 critical 项 pass 才自动 matched,
      任一缺失→needs_review(绝不猜)
  ⑤LLM 兜底: 规则判不了的模糊条款("具备类似项目经验")→三分类+理由
  ⑥输出三态: 全✓自动进阶段3 / 任一✗标记资格不符 / 含?进人审队列
```

**初筛的三大产物**(不只给一个结论):
1. **资格勾对报告**——逐项 ✓✗? + 证据明细(证书名/有效期/持有人对照)
2. **废标红线检查报告**——9 类红线逐条过(投标有效期/预算/签章/保证金…),
   人工修正写 match_correction 沉淀回规则库
3. **商务要求响应表草稿**——直接生成招标文件要求的"商务要求响应表"
   (条款/招标文件规定/投标文件响应/偏离情况),响应列从知识库自动预填,
   人工只审偏离项 → 这就是第三关"文件关"的自动化入口

## 八、证照录入链路(知识库建设的主力流程,工作流 W1 的抽取节点)

参考 rag-tender `knowledge_service.py` 完整链路:

```
上传(扩展名/大小校验, 按 category 存盘)
 → 解析(status=parsing):
    图片→Vision 全文 OCR
    docx/xlsx→转 PDF→文本提取,<10 字符的扫描页逐页 Vision OCR 兜底
    文本缓存入库(重解析不重复 OCR)
 → 结构化抽取(四级兜底):
    本地正则(身份证/营业执照/ISO三系/财报/审计/纳税/资信 分支)
    → LLM JSON 抽取 → 图片 Vision 抽取 → 占位记录(status=needs_completion,
    scope="待人工补全:原因", 前端待办列表提醒)
 → 字段规范化(日期归一 YYYY-MM-DD, list/dict 归一字符串)
 → 入库(status 由 expiry_date 计算: <0天 expired / ≤90天 expiring / valid)
 → 人审(is_audited=true 后才进自动勾对)
每日定时: 重算 status, expiring 生成到期提醒(90 天窗口)
```

公开采集预填(KB-M2):中标公告搜企业名 → 业绩预填
(已验证:样板 IT 集成企业在政采网/ggzy.gov.cn 有持续中标
记录——政务数字化转型、教育信息化、运政系统等
50~1000 万级,与已接源重合)。未中标记录(含废标原因)同样采集,
用于复盘。

## 九、评分模型(阶段 4)——双轨 + 行业模板库

1. **解析真实评分细则**(优先):Interpret 产出 scoring_items →
   逐项 {score, max_score, evidence, source_page, coverage_status} 打分
2. **行业模板**(兜底):

**已用两份真实 IT 服务类招标文件对比校准——同为服务类公开招标
综合评分法,结构差异巨大,模板只能粗兜底,解析真实细则必须优先**:

| 评审项目 | 文件1:某市医保局数据智能化系统 | 文件2:某卫健部门全员人口系统二期 |
|---|---|---|
| 投标报价 | 10 | 10(同公式:基准价/报价×10) |
| 技术参数响应 | — | 10(每低于一项减1分,客观) |
| 技术方案类(需求分析/总体/实施/质量/应急/培训) | 80(总体30+实施20+质量15+售后15) | 43(需求10+总体10+实施10+质量5+应急5+培训5) |
| 系统演示 | 5(5点×1分) | 10(5点×2分) |
| **业绩** | **无** | **5(近三年类似业绩每项1分)** |
| **项目团队** | **无** | **15(负责人3+技术负责人3+团队成员9)** |
| **售后承诺/人员** | — | **2(驻场2人信息)+3(售后人员明细及证书)** |
| 商务响应情况 | 5 | — |

> 结论修正(v4 重要更新):IT 服务类**不是**商务分都极小——文件2 商务
> 得分点实打实 22 分,且"项目团队 15 分"是单项最大分项之一。
> 商务知识库(业绩/人员/证书)直接是评分得分点,不是只有门槛作用。

**模板 B:工程/货物类**(行业实务,商务部分占总分 10%~20%):
类似业绩 30 / 资质证书 25 / 人员配置 20 / 财务状况 10 / 信用获奖 10 / 商务响应 5

按 industry_code 自动路由模板,真实细则永远优先。
产出:综合评分预评报告(docx/pdf):结论(建议投/谨慎/放弃)+
逐项得分与依据 + 失分风险点 + 补强建议。

### 9.1 团队配置优化器(项目团队评分的自动化,知识库杀手场景)

文件2 的"项目团队 15 分"是典型可全自动计算的评分项,规则:
- 项目负责人(1人):信息系统项目管理师(高级)+2;软考中级证书每项+1,满3
- 技术负责人(1人):系统分析师/系统架构设计师+2;软考中级每项+1,满3
- 团队成员:软考高级每人1分/中级0.5分;**同一人多证按最高级别计一次**,满9
- 硬约束:每人只计一次分;须提供 2025 年度任一月社保 + 证书扫描件清晰

→ 纯规则+组合优化,无需 LLM:从 personnel/personnel_certificate 库
自动算出①本企业此项目最高可得团队分②最优班子名单(谁任负责人/
技术负责人/成员)③缺什么证书、补谁能涨几分(如"再招1名软考高级+1分")。
业绩分同理自动算(近三年类似业绩计数×1分,上限5)。
证明材料质检规则:合同扫描件须含项目名称/标的物/签订时间/签章清晰,
知识库对每条业绩标记证明齐套状态。

## 十、商务文函自动化(第三关落点,本项目原创重点)

| 文函类型 | 来源 | 自动化方式 |
|---|---|---|
| 商务要求响应表 | 招标文件商务条款 | 初筛结果直接转表格,响应列预填,偏离项标红 |
| 资格承诺函(8项) | 资格审查表 | 模板+公司信息占位符自动生成 docx |
| 中小企业声明函 | 政采政策要求 | 模板生成(自动判企业规模) |
| 授权委托书 | 资格要求 | 模板+人员库(法人/被授权人)生成 |
| 类似业绩证明汇编 | 业绩库 | 按评分要求筛业绩→合同/验收扫描件一键打包 |
| 人员配备表 | 人员库 | 拟派班子选择→证书/社保/职称复印件汇编 |

复用现有 Format 管线(docx 生成)+ rag-tender fill_service 的
模板占位符填充思路。BiaoShu 模板库 16 份商务标范文(bid_doc_* 系列)
可作商务文函模板种子入库。

## 十一、开发计划(定稿,2026-10-09 拍板后)

**已拍板**:商机分析独立成模块(定名可再议)/ 多租户(company_id 贯穿)/
证书清单配置化(先用 IT 集成建议稿)/ 公司主线 + 图谱构建形态。

| 里程碑 | 内容 | 对应三关/工作流 | 前置 |
|---|---|---|---|
| **KB-M1** | 知识库骨架(公司空间):company 多租户底座 + 6 表 + knowledge_edge + 上传/文件夹整包导入 + W1 构建流水线(分类/抽取/关联 agent + 人审队列)+ 有效期提醒 | 弹药库 | 无 |
| **KB-M2** | 图谱视图:公司资质全景(节点=卡片按子库着色,边=关系),从图谱直达卡片 | 展示层 | M1 |
| **KB-M3** | 公开采集(W2):中标公告搜业绩 → AI 预填 → 人审入库(样板企业已验证) | 弹药库 | M1 |
| **KB-M4** | 商机分析独立模块骨架:备选库页签(stage 流转 + 画像筛选),从资讯落库 | 阶段1 | M1(画像已有) |
| **KB-M5** | 解读扩展(W3 前置):资格条件/评分办法/废标条款三大 JSON(Interpret 升级,-bid-analysis prompt 套路) | 三关输入 | 无(可与 M1 并行) |
| **KB-M6** | 初筛引擎(W3):分流→数值规则→证据矩阵→LLM 兜底→三态 + 三大产物(勾对报告/红线报告/响应表草稿)+ 修正回流规则库 + 团队配置优化器 | 第一/二关 | M1, M4, M5 |
| **KB-M7** | 深度分析+评分报告(W4):celery 并行逐项目 + 团队/业绩自动算分 + 双轨评分 docx/pdf + 商务文函自动化(响应表/承诺函/汇编) | 第三关+得分 | M6 |

> 排序逻辑:M1 是一切的地基先做;M2 图谱是公司主线的可视化承诺,
> 早做让用户"看得见"价值;M5 与 M1 无依赖可并行;M4 轻量搭框架让
> 商机流先跑起来;M6/M7 是重头戏,依赖全部就位后做。
> 证书类型字典表在 M1 就建(configurable),内容用建议稿,用户随时改。

## 十二、参考仓库精读版照抄清单(2026-10-09 源码级深挖)

**rag-tender(E:\pro_01\_refs\rag-tender)——规则引擎+知识库录入,最有用**:
- `backend/app/services/match_service.py`:RULE_PATTERNS(L80,5类数值正则)、
  `_MATCH_SYNONYMS`(L100,9组证照同义词)、`_should_match`(L203,三级分流)、
  `_check_numeric_rule`(L309,运算符比较)、`_verify_qualification_evidence`
  (L401,证据矩阵+保守三态)、`match_corrections` 修正回流
- `backend/app/database.py`:qualifications(L72)/match_results(L91)/
  performance_projects(L288) 表 DDL
- `backend/app/services/knowledge_service.py`:录入链 upload_file(L1094)→
  parse_file(L1449)→四级兜底抽取→`_compute_status`(L118,有效期三态)
- 不抄:RAG-Anything 重依赖、伪语义匹配(token 计分当检索)、无任务队列

**-bid-analysis(E:\pro_01\_refs\-bid-analysis)——招标文件解读,最有用**:
- `src/extractor/module_b.py` + `config/prompts/module_b.txt`(资格条件 B1~B4
  表格骨架 prompt)、`module_c.py`(评分办法)+ `module_e`(废标条款)
- `src/extractor/base.py`:build_input_text、parse_llm_json(截断/中文引号修复)、
  分批与 merge
- `src/indexer/rule_splitter.py`(三策略切分+置信度)、`tagger.py`(章节语义标签)
- `src/extractor/scoring.py` + `config/keyword_scores.yaml`(三档关键词得分制:
  high=7/medium=4/low=2,阈值 3~5,min_count=5 保底,向量补漏)
- `src/reviewer/clause_extractor.py`(条款 critical/major/minor 分级+[N]原文回拼)
- `server/app/models/task.py`(文件化中间产物+JSONB+进度字段)
- 不抄:haha-code Node agent 整套(只抄 skill 设计)

**BidPilot-AI(E:\pro_01\_refs\BidPilot-AI)——数据模型+工作流,最有用**:
- `app/domain/models.py`:Requirement(L202,subject/action/deadline/penalty)、
  ScoringItem(L257,min/max/criteria/coverage_status)、
  RequirementEvidenceLink(L231,证据链五态覆盖)、KnowledgeChunk(L551,
  is_audited/valid_until)、DocumentPage(L166,page_number/parse_method)
- `app/workflows/engine.py`(依赖图+invalidated_by 增量重跑+human_gate
  →映射到我们 Celery)、`app/agents/planner_agent.py`(Pydantic 白名单+固定 fallback)
- `app/application/knowledge_service.py` retrieve(过期+未审三重过滤)
- `app/application/evidence_service.py`(_quote_for_requirement 原文摘录定位)
- 不抄:无 Celery 的内联同步、SQLite+hash 伪 embedding、无资质人员库

**BiaoShu-SKILL(E:\pro_01\_refs\BiaoShu-SKILL)——规则兜底+模板种子**:
- `BiaoShu-writer-pro/scripts/extract_requirements.py`(资质四桶关键词表:
  enterprise/certifications/personnel/performance,纯规则无 LLM 保底)
- `scripts/extract_scoring.py`(评分章节定位正则 + scoring_criteria.json schema)
- `BiaoShu-writer-pro/templates/bid_doc_*` 16 份商务标范文模板(文函种子入库)
- 不抄:正则解析当主力(我们 LLM 结构化输出+规则兜底)、机械同义替换

**复用策略一句话**:解读抄 -bid-analysis 的 prompt 与切分,勾对抄 rag-tender
的 match_service,表结构抄 BidPilot models,规则兜底与文函模板抄 BiaoShu;
四仓库均无"三关闭环",组合+自研。

## 十三、遗留确认项(均已不阻塞开发)

1. ~~商机分析独立 vs 并入~~ → **已拍板:独立模块**(定名待定:
   "商机分析/商机雷达/投标决策"均可,M4 骨架先行用"商机分析")
2. ~~多租户~~ → **已拍板:多租户**,company_id 全贯穿
3. 证书类型清单 → 已决策**配置化**(字典表 M1 建好,内置 IT 集成建议稿:
   ISO9001/14001/45001、ITSS、CCRC、CMMI、涉密、安防、软考系列),
   用户后续在设置页自行增删即可,无需提前给全
4. OCR:KB-M1 录入链按"文本提取→LLM 结构化→Vision OCR 兜底"实现
   (rag-tender 同款四级兜底),扫描件比例高时 Vision 调用成本可控,
   不再单独分一期二期
