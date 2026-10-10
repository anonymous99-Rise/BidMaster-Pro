from __future__ import annotations

import enum
import sqlalchemy as sql
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Enum, JSON, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid

# 跨方言大文本：MySQL 渲染为 MEDIUMTEXT(16MB)，PostgreSQL 等回退为 Text
LONGTEXT = Text().with_variant(MEDIUMTEXT(), "mysql")


class Base(DeclarativeBase):
    pass


class ProjectStatus(str, enum.Enum):
    CREATED = "created"
    INTERPRETING = "interpreting"
    ANALYZING = "analyzing"
    OUTLINING = "outlining"
    GENERATING = "generating"
    CHECKING = "checking"
    FORMATTING = "formatting"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DocumentType(str, enum.Enum):
    TENDER = "tender"
    BID = "bid"
    TEMPLATE = "template"
    REFERENCE = "reference"


class CheckType(str, enum.Enum):
    COMPLIANCE = "compliance"
    DISQUALIFICATION = "disqualification"
    DUPLICATE = "duplicate"
    CONSISTENCY = "consistency"
    FORMAT = "format"
    QUALIFICATION = "qualification"
    DEPOSIT = "deposit"
    SIGNATURE = "signature"
    PRICING = "pricing"
    MANDATORY = "mandatory"
    VALIDITY = "validity"
    SELFCHECK = "selfcheck"
    FULL_CHECK = "full_check"
    FIT_SCORE = "fit_score"
    AI_TEXT = "ai_text"
    CROSS_CHECK = "cross_check"
    SAMPLE_REPORT = "sample_report"
    JOINT_BID = "joint_bid"
    EBID_SUBMIT = "ebid_submit"
    PRICING_LOGIC = "pricing_logic"
    DOC_INTEGRITY = "doc_integrity"
    RISK_SCORE = "risk_score"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    WRITER = "writer"
    REVIEWER = "reviewer"


def _uuid_default():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default=UserRole.WRITER.value)
    avatar = Column(String(500), nullable=True)
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    projects = relationship("Project", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    status = Column(String(50), default=ProjectStatus.CREATED.value, index=True)
    tender_doc_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    documents = relationship("Document", back_populates="project", foreign_keys="Document.project_id")
    analysis = relationship("Analysis", back_populates="project", uselist=False)
    outline = relationship("Outline", back_populates="project", uselist=False)
    chapters = relationship("Chapter", back_populates="project")
    check_reports = relationship("CheckReport", back_populates="project")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    type = Column(String(20), default=DocumentType.TENDER.value)
    file_path = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    parsed_content = Column(LONGTEXT, nullable=True)
    doc_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="documents", foreign_keys=[project_id])


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    dimensions = Column(JSON, default=dict)
    scoring_matrix = Column(JSON, default=dict)
    risk_flags = Column(JSON, default=dict)
    sections = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="analysis")


class Outline(Base):
    __tablename__ = "outlines"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    mode = Column(String(20), default="aligned")
    tree = Column(JSON, default=dict)
    score_mapping = Column(JSON, default=dict)
    reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="outline")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    outline_id = Column(String(36), ForeignKey("outlines.id"), nullable=True)
    title = Column(String(500), nullable=False)
    content = Column(LONGTEXT, nullable=True)
    mode = Column(String(10), default="A")
    status = Column(String(20), default="pending")
    word_count = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="chapters")


class CheckReport(Base):
    __tablename__ = "check_reports"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    type = Column(String(30), nullable=False, index=True)
    results = Column(JSON, default=dict)
    risk_level = Column(String(20), default="low")
    summary = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="check_reports")


class SkillConfig(Base):
    __tablename__ = "skill_configs"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=False)
    version = Column(String(20), default="1.0.0")
    config = Column(JSON, default=dict)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(100), unique=True, nullable=False)
    workflow_dsl = Column(JSON, default=dict)
    skills = Column(JSON, default=list)
    config = Column(JSON, default=dict)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompanyProfile(Base):
    """公司画像 (业务偏好, 单行配置)

    profile_data 结构:
    {
        "company_name": "××建设集团有限公司",
        "industries": ["03", "05"],     # 行业 code (与 sources/industry 树一致)
        "keywords": ["市政", "桥梁", "绿化"],
        "regions": ["安徽", "浙江"],
        "min_amount": 10.0,              # 万元
        "max_amount": 5000.0,            # 万元
    }
    采集聚合 (aggregate) 时若无显式画像, 会自动读取本表注入评分。
    """
    __tablename__ = "company_profiles"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(100), unique=True, nullable=False, default="default")
    profile_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(200), nullable=False)
    doc_count = Column(Integer, default=0)
    embedding_model = Column(String(100), default="text-embedding-v3")
    collection_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MonitoringTask(Base):
    __tablename__ = "monitoring_tasks"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    keywords = Column(Text, nullable=False)
    exclude_keywords = Column(Text, default="")
    must_contain_keywords = Column(Text, default="")
    sites = Column(JSON, default=list)
    interval_minutes = Column(Integer, default=60)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CrawlResult(Base):
    __tablename__ = "crawl_results"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    task_id = Column(String(36), ForeignKey("monitoring_tasks.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    source = Column(String(500), default="")
    pub_date = Column(String(50), nullable=True)
    content = Column(LONGTEXT, nullable=True)
    keyword_score = Column(Float, default=0.0)
    relevance_score = Column(Float, default=0.0)
    category = Column(String(50), default="general")
    is_hot = Column(Boolean, default=False)
    hot_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class RBACRole(Base):
    __tablename__ = "rbac_roles"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RBACPermission(Base):
    __tablename__ = "rbac_permissions"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    code = Column(String(200), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class RBACUserRole(Base):
    __tablename__ = "rbac_user_roles"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("rbac_roles.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_rbac_user_role"),
    )


class RBACRolePermission(Base):
    __tablename__ = "rbac_role_permissions"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    role_id = Column(String(36), ForeignKey("rbac_roles.id"), nullable=False, index=True)
    permission_id = Column(String(36), ForeignKey("rbac_permissions.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_rbac_role_perm"),
    )


class NewsSourceRegistry(Base):
    """数据源注册表 (YAML -> DB 镜像)

    启动时由 services/news/source_registry.py 同步写入,
    管理员可在 UI 修改 enabled / weight 等字段。
    """
    __tablename__ = "news_source_registry"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    code = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    type = Column(String(20), default="rss", index=True)
    url = Column(String(1000), default="")
    industry_code = Column(String(20), default="12", index=True)
    weight = Column(Float, default=1.0)
    enabled = Column(Boolean, default=True, index=True)
    description = Column(Text, default="")
    extra_config = Column(JSON, default=dict)

    last_crawled_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), default="")
    last_error = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HotspotItem(Base):
    """聚合后的商机/热点数据 (经过去重+评分+分类)"""
    __tablename__ = "hotspot_items"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, index=True)
    source = Column(String(500), default="")
    sources = Column(JSON, default=list)
    pub_date = Column(String(50), nullable=True)
    content = Column(LONGTEXT, nullable=True)
    source_code = Column(String(100), default="", index=True)
    industry_code = Column(String(20), default="12", index=True)
    region = Column(String(50), default="")
    amount = Column(Float, default=0.0)
    bid_deadline = Column(String(50), default="")
    owner_org = Column(String(200), default="")
    project_code = Column(String(100), default="", index=True)
    announce_type = Column(String(20), default="tender", index=True)
    fingerprint = Column(String(255), default="", index=True)
    extra = Column(JSON, default=dict)

    score_total = Column(Float, default=0.0, index=True)
    score_urgency = Column(Float, default=0.0)
    score_match = Column(Float, default=0.0)
    score_amount = Column(Float, default=0.0)
    score_region = Column(Float, default=0.0)
    score_freshness = Column(Float, default=0.0)
    is_hot = Column(Boolean, default=False, index=True)

    is_converted = Column(Boolean, default=False, index=True)
    converted_project_id = Column(String(36), default="")

    # 商机阶段流转 (KB-M4): 空=未入备选, candidate=备选库, analysis=分析库, tender=投标库
    stage = Column(String(20), default="", index=True)
    # 多租户: 该商机归属哪家公司 (KB-M4, 单企业部署可留空)
    company_id = Column(String(36), default="", index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LLMProviderConfig(Base):
    """LLM 供应商配置：一个供应商可有多条记录（多个 key 用于负载均衡 / 备用）。"""
    __tablename__ = "llm_provider_configs"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    provider_id = Column(String(64), nullable=False, index=True)
    display_name = Column(String(128), nullable=True)
    api_key = Column(String(512), nullable=False)
    api_base = Column(String(512), nullable=True)
    default_model = Column(String(128), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    note = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKey(Base):
    """API Key：桌面端 VIP 用户访问服务端数据/算力服务的凭证。

    取代传统 RBAC Bearer Token，简化桌面端-服务端认证。
    - 一个用户可拥有多个 ApiKey
    - type 区分：subscription (订阅制，数据服务) / credits (按量付费，算力服务)
    - 与 User 表弱关联：user_email 用于显示归属，不强约束外键
    """
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)  # sha256(api_key_raw)
    key_prefix = Column(String(20), nullable=False)  # 显示用前缀 "bmp_xxxx..."
    user_email = Column(String(255), nullable=True, index=True)
    user_name = Column(String(100), nullable=True)
    tier = Column(String(20), default="free", nullable=False)  # free / pro / team
    type = Column(String(20), default="subscription", nullable=False)  # subscription / credits
    credits_remaining = Column(Integer, default=0, nullable=False)  # 仅 type=credits 时使用
    credits_total = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    note = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKeyUsage(Base):
    """API Key 调用日志：用于计费、审计、限流"""
    __tablename__ = "api_key_usage"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    api_key_id = Column(String(36), ForeignKey("api_keys.id"), nullable=False, index=True)
    endpoint = Column(String(200), nullable=False)  # e.g. "/api/news/today-hot"
    method = Column(String(10), default="GET", nullable=False)
    status_code = Column(Integer, default=200, nullable=False)
    credits_cost = Column(Integer, default=0, nullable=False)  # 本次调用消耗的 credits
    user_agent = Column(String(256), nullable=True)
    client_ip = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ==========================================================================
# 商务知识库模块 (KB) —— 公司主线 / 多租户 / Obsidian 式子库 + 知识图谱
# 说明: 表名统一 kb_ 前缀, 与既有 knowledge_bases(RAG 文档库) 区分。
#       company_id 贯穿所有数据表, 公司 = 租户 = 空间。
#       实体卡片 = 结构化一行; 来源文件 = 证据; 关系 = kb_edges。
#       一切由 agent 流水线(W1)产出, is_audited=true 后才进自动勾对池。
# ==========================================================================


class KbCompany(Base):
    """公司空间 (多租户底座)。一家企业一个空间, 承载全部子库与图谱。"""
    __tablename__ = "kb_companies"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    name = Column(String(300), nullable=False, unique=True)  # 公司全称
    short_name = Column(String(200), default="")
    unified_social_code = Column(String(64), default="")     # 统一社会信用代码
    legal_person = Column(String(100), default="")           # 法定代表人
    industry_code = Column(String(20), default="12", index=True)  # 与行业树一致
    region = Column(String(100), default="")                 # 注册地
    contact = Column(String(200), default="")
    description = Column(Text, default="")
    is_default = Column(Boolean, default=False, index=True)  # 单企业部署的默认空间
    extra = Column(JSON, default=dict)
    created_by = Column(String(36), default="")              # 创建者 user_id (弱关联)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbCertType(Base):
    """证书类型字典 (可配置, 内置 IT 集成建议稿, 用户可增删)。"""
    __tablename__ = "kb_cert_types"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    code = Column(String(80), nullable=False, unique=True)   # 稳定标识, 如 iso9001
    name = Column(String(200), nullable=False)               # 显示名, 如 ISO9001 质量管理体系认证
    category = Column(String(20), default="enterprise", index=True)  # enterprise/personnel/financial
    default_valid_months = Column(Integer, default=0)        # 典型有效期(月), 0=长期/未知
    scope_hint = Column(String(300), default="")             # 覆盖范围提示, 勾对参考
    is_builtin = Column(Boolean, default=False, index=True)  # 内置不可删(仅可禁用)
    enabled = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class KbFile(Base):
    """来源文件 (证据层)。上传的证照扫描件/合同/财报等, 缓存解析文本。"""
    __tablename__ = "kb_files"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)           # 原始文件名
    rel_dir = Column(String(500), default="")                # 上传时的相对目录(整包上传保留结构)
    stored_path = Column(String(1000), nullable=False)       # 落盘路径
    file_size = Column(Integer, default=0)
    ext = Column(String(20), default="")
    sha256 = Column(String(64), default="", index=True)      # 去重指纹
    extracted_text = Column(LONGTEXT, nullable=True)         # 解析出的全文(重解析不重复 OCR)
    parse_status = Column(String(20), default="pending", index=True)  # pending/parsing/parsed/failed
    parse_method = Column(String(20), default="")            # text/llm/vision/placeholder
    page_count = Column(Integer, default=0)
    category = Column(String(30), default="", index=True)    # agent 分类到的子库
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "sha256", name="uq_kb_file_company_sha"),
    )


class KbCertificate(Base):
    """企业资质证书卡片 (一证一记录, 关联来源文件)。"""
    __tablename__ = "kb_certificates"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    file_id = Column(String(36), default="", index=True)     # 来源文件 kb_files.id
    name = Column(String(300), nullable=False)               # 证书名称
    number = Column(String(200), default="")                 # 证书编号
    category = Column(String(20), default="enterprise", index=True)  # enterprise/personnel/financial
    cert_type_code = Column(String(80), default="", index=True)  # 关联 kb_cert_types.code
    level = Column(String(100), default="")                  # 等级
    scope = Column(String(500), default="")                  # 覆盖范围(勾对关键)
    holder = Column(String(300), default="")                 # 持证主体
    issue_date = Column(String(20), default="")              # YYYY-MM-DD
    expiry_date = Column(String(20), default="", index=True)  # YYYY-MM-DD, 空=长期
    issuing_authority = Column(String(300), default="")
    status = Column(String(20), default="valid", index=True)  # valid/expiring/expired/needs_completion
    raw_text = Column(LONGTEXT, nullable=True)
    is_audited = Column(Boolean, default=False, index=True)  # 人审通过才进自动勾对池
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")            # manual/ocr/public_agent
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbPersonnel(Base):
    """从业人员卡片。"""
    __tablename__ = "kb_personnel"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    file_id = Column(String(36), default="", index=True)
    name = Column(String(100), nullable=False)
    id_number_enc = Column(String(200), default="")          # 身份证号(加密/脱敏存储)
    gender = Column(String(10), default="")
    title = Column(String(100), default="")                  # 职称
    role = Column(String(100), default="")                   # 拟派岗位(项目经理/技术负责人...)
    dept = Column(String(200), default="")
    phone = Column(String(50), default="")
    social_insurance_proof_file_id = Column(String(36), default="")  # 社保证明文件
    is_audited = Column(Boolean, default=False, index=True)
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbPersonnelCertificate(Base):
    """人员证书卡片 (注册类/职称类/软考/特种作业...)。"""
    __tablename__ = "kb_personnel_certificates"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    personnel_id = Column(String(36), ForeignKey("kb_personnel.id"), nullable=False, index=True)
    cert_type = Column(String(200), default="")              # 证书类型名
    cert_type_code = Column(String(80), default="", index=True)
    major = Column(String(200), default="")                  # 专业
    level = Column(String(100), default="")                  # 级别(高级/中级/初级)
    cert_no = Column(String(200), default="")
    issue_date = Column(String(20), default="")
    expiry_date = Column(String(20), default="", index=True)
    issuing_authority = Column(String(300), default="")
    status = Column(String(20), default="valid", index=True)
    file_id = Column(String(36), default="", index=True)
    is_audited = Column(Boolean, default=False, index=True)
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbAchievement(Base):
    """业绩卡片 (项目/金额/业主/证明文件)。公开采集与手工录入共用。"""
    __tablename__ = "kb_achievements"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    project_name = Column(String(500), nullable=False)
    client_name = Column(String(300), default="")            # 业主单位
    contract_no = Column(String(200), default="")
    contract_amount = Column(Float, default=0.0)             # 统一万元
    sign_date = Column(String(20), default="", index=True)   # YYYY-MM-DD
    completion_date = Column(String(20), default="")
    year = Column(Integer, default=0, index=True)            # 签约年份(近三年业绩算分)
    project_scope = Column(String(1000), default="")         # 项目内容摘要
    project_type = Column(String(200), default="")           # 项目类型
    industry_code = Column(String(20), default="", index=True)
    region = Column(String(100), default="")
    bid_result = Column(String(20), default="win")           # win/loss (未中标同样采集复盘)
    winner_name = Column(String(300), default="")            # 公告中的中标人(公开采集)
    source_url = Column(String(1000), default="")            # 来源公告链接(公开采集溯源)
    announce_date = Column(String(20), default="")           # 公告日期(区别于签约日期)
    fingerprint = Column(String(64), default="", index=True)  # 采集去重指纹
    file_ids = Column(JSON, default=list)                    # 合同/验收/发票 证明文件
    is_audited = Column(Boolean, default=False, index=True)
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")            # manual/public_agent
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbFinancial(Base):
    """财务卡片 (审计报告/财报/纳税/资信)。数值规则勾对的数据源。"""
    __tablename__ = "kb_financials"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    report_type = Column(String(40), default="audit_report", index=True)  # audit_report/financial_statement/tax/credit_rating
    period_start = Column(String(20), default="")
    period_end = Column(String(20), default="")
    year = Column(Integer, default=0, index=True)
    total_assets = Column(Float, default=0.0)                # 总资产(万元)
    revenue = Column(Float, default=0.0)                     # 营收(万元)
    net_profit = Column(Float, default=0.0)                  # 净利润(万元)
    debt_ratio = Column(Float, default=0.0)                  # 资产负债率(%)
    audit_agency = Column(String(300), default="")
    file_id = Column(String(36), default="", index=True)
    is_audited = Column(Boolean, default=False, index=True)
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbCredit(Base):
    """信用卡片 (AAA 证书/获奖/无违法记录/信用中国快照)。"""
    __tablename__ = "kb_credits"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    credit_type = Column(String(40), default="aaa_certificate", index=True)  # aaa_certificate/award/no_violation/credit_check_snapshot
    title = Column(String(300), default="")
    holder = Column(String(300), default="")
    check_date = Column(String(20), default="")              # YYYY-MM-DD
    check_url = Column(String(1000), default="")
    result = Column(String(200), default="")                 # 结果/结论
    score = Column(Float, default=0.0)
    file_id = Column(String(36), default="", index=True)
    is_audited = Column(Boolean, default=False, index=True)
    audit_note = Column(Text, default="")
    source = Column(String(20), default="manual")
    confidence = Column(Float, default=0.0)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KbEdge(Base):
    """知识图谱关系边。实体间的关系(持有/参与/响应/满足/中标/归属)。"""
    __tablename__ = "kb_edges"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    src_type = Column(String(30), nullable=False, index=True)  # certificate/personnel/achievement...
    src_id = Column(String(36), nullable=False, index=True)
    edge_type = Column(String(30), nullable=False)             # holds/participates/responds/satisfies/wins/belongs
    dst_type = Column(String(30), nullable=False, index=True)
    dst_id = Column(String(36), nullable=False, index=True)
    confidence = Column(Float, default=0.0)                    # agent 猜的置信度, 人审后=1.0
    source = Column(String(20), default="agent_inferred")      # agent_inferred/manual/public_agent
    is_audited = Column(Boolean, default=False, index=True)
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class KbBuildTask(Base):
    """知识库构建任务 (W1 流水线一次运行的记录)。"""
    __tablename__ = "kb_build_tasks"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)  # pending/running/done/failed
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    created_entities = Column(Integer, default=0)
    created_edges = Column(Integer, default=0)
    error = Column(Text, default="")
    params = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KbScreeningResult(Base):
    """W3 初筛结果 (KB-M6): 一次对某商机的资格条件勾对快照。

    requirements/summary/items 全量 JSON 落库, 供报告/响应表/人审复核。
    """
    __tablename__ = "kb_screening_results"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    opportunity_id = Column(String(36), ForeignKey("hotspot_items.id"), nullable=True, index=True)
    status = Column(String(20), default="done", index=True)   # running/done/failed
    overall = Column(String(20), default="")                  # passed/failed/needs_review
    requirements = Column(JSON, default=list)                 # 输入条款
    summary = Column(JSON, default=dict)                      # {total, matched, failed, needs_review}
    items = Column(JSON, default=list)                        # 逐条结论(含证据矩阵)
    redlines = Column(JSON, default=list)                     # 产物②废标红线清单
    response_table = Column(JSON, default=list)               # 产物③响应表草稿
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class KbScreeningCorrection(Base):
    """人工修正回流 (KB-M6): 改判记录, 同条款指纹下次直接沿用。"""
    __tablename__ = "kb_screening_corrections"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)  # 条款 uuid5 指纹
    clause_text = Column(Text, default="")
    original_verdict = Column(String(20), default="")          # 机器原判
    corrected_verdict = Column(String(20), nullable=False)     # matched/failed
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class KbAnalysisReport(Base):
    """W4 深度分析报告 (KB-M7): 团队优化器+业绩算分+综合结论, 可下载 docx。"""
    __tablename__ = "kb_analysis_reports"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    opportunity_id = Column(String(36), ForeignKey("hotspot_items.id"), nullable=True, index=True)
    status = Column(String(20), default="pending", index=True)  # pending/running/done/failed
    team = Column(JSON, default=dict)                          # optimize_team 输出
    performance = Column(JSON, default=dict)                   # score_performance 输出
    scoring_summary = Column(JSON, default=dict)               # 汇总+建议投/谨慎/放弃
    report_path = Column(String(500), default="")              # docx 相对路径
    error = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class KbCollectTask(Base):
    """公开采集任务 (W2 流水线一次运行的记录)。

    按企业名搜索已接公告源 → 解析中标/未中标记录 → 去重 → 预填业绩人审队列。
    """
    __tablename__ = "kb_collect_tasks"

    id = Column(String(36), primary_key=True, default=_uuid_default)
    company_id = Column(String(36), ForeignKey("kb_companies.id"), nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)  # pending/queued/running/done/failed
    keyword = Column(String(300), default="")                   # 搜索用企业名
    source_codes = Column(JSON, default=list)                   # 本次使用的资讯源 code
    total_found = Column(Integer, default=0)                    # 公告命中总数
    parsed = Column(Integer, default=0)                         # 解析出我方相关记录数
    created_entities = Column(Integer, default=0)               # 新建业绩卡片数
    duplicated = Column(Integer, default=0)                     # 去重跳过数
    error = Column(Text, default="")
    params = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
