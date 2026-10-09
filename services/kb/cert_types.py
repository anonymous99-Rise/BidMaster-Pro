"""证书类型字典种子 (内置 IT 集成建议稿)。

启动时幂等写入 kb_cert_types: 已存在的 code 不覆盖 (保留用户改动),
仅补齐缺失的内置项。用户可在设置页自定义增删。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# (code, name, category, default_valid_months, scope_hint)
BUILTIN_CERT_TYPES: list[tuple[str, str, str, int, str]] = [
    # ---- 企业资质 (enterprise) ----
    ("business_license", "营业执照", "enterprise", 0, "统一社会信用代码/经营范围"),
    ("iso9001", "ISO9001 质量管理体系认证", "enterprise", 36, "信息系统集成/软件开发"),
    ("iso14001", "ISO14001 环境管理体系认证", "enterprise", 36, "环境管理"),
    ("iso45001", "ISO45001 职业健康安全管理体系认证", "enterprise", 36, "职业健康安全"),
    ("iso27001", "ISO27001 信息安全管理体系认证", "enterprise", 36, "信息安全管理"),
    ("itss", "ITSS 信息技术服务标准符合性证书", "enterprise", 36, "信息技术服务运行维护/咨询设计"),
    ("ccrc", "CCRC 信息安全服务资质", "enterprise", 36, "安全集成/安全运维/风险评估"),
    ("cmmi", "CMMI 能力成熟度模型集成认证", "enterprise", 36, "软件开发成熟度"),
    ("cs_rating", "信息系统建设和服务能力评估(CS)", "enterprise", 48, "信息系统建设和服务能力"),
    ("secret_qual", "涉密信息系统集成资质", "enterprise", 36, "涉密系统集成/软件开发"),
    ("security_engineering", "安防工程企业资质", "enterprise", 36, "安全技术防范工程设计施工"),
    ("construction_electronic", "电子与智能化工程专业承包资质", "enterprise", 60, "电子与智能化工程"),
    ("safety_production", "安全生产许可证", "enterprise", 36, "建筑施工"),
    ("high_tech_enterprise", "高新技术企业证书", "enterprise", 36, "高新技术企业"),
    ("software_enterprise", "软件企业认定证书", "enterprise", 12, "软件产品/软件开发"),
    ("software_copyright", "计算机软件著作权登记证书", "enterprise", 0, "软件著作权"),
    ("software_product", "软件产品登记证书", "enterprise", 60, "软件产品"),

    # ---- 人员证书 (personnel) ----
    ("soft_exam_senior", "软考高级(信息系统项目管理师/系统分析师/系统架构设计师)", "personnel", 0, "软考高级"),
    ("soft_exam_mid", "软考中级(系统集成项目管理工程师/软件设计师等)", "personnel", 0, "软考中级"),
    ("soft_exam_primary", "软考初级", "personnel", 0, "软考初级"),
    ("pmp", "PMP 项目管理专业人士", "personnel", 36, "项目管理"),
    ("registered_builder", "注册建造师", "personnel", 36, "工程建造"),
    ("safety_officer_b", "安全生产考核合格证(B证)", "personnel", 36, "项目负责人安全考核"),
    ("safety_officer_c", "安全生产考核合格证(C证)", "personnel", 36, "专职安全员"),
    ("cost_engineer", "造价工程师", "personnel", 48, "工程造价"),
    ("supervisor", "监理工程师", "personnel", 48, "工程监理"),
    ("title_senior", "高级工程师职称", "personnel", 0, "高级职称"),
    ("title_mid", "工程师职称", "personnel", 0, "中级职称"),
    ("itss_personnel", "ITSS 服务工程师/服务项目经理", "personnel", 36, "ITSS 人员"),
    ("ccrc_personnel", "CCRC 信息安全服务人员证书", "personnel", 36, "信息安全服务人员"),

    # ---- 财务/信用 (financial/credit 类别归类) ----
    ("audit_report", "审计报告", "financial", 12, "年度审计"),
    ("tax_credit_a", "纳税信用 A 级", "financial", 12, "纳税信用等级"),
    ("aaa_credit", "AAA 信用等级证书", "financial", 12, "企业信用评级"),
    ("credit_china", "信用中国无违法记录查询", "financial", 0, "信用记录自查"),
]


async def seed_cert_types(db) -> int:
    """幂等写入内置证书类型。返回新增条数。"""
    from sqlalchemy import select
    from services.models import KbCertType

    result = await db.execute(select(KbCertType.code))
    existing = {row[0] for row in result.all()}

    added = 0
    for i, (code, name, category, months, scope) in enumerate(BUILTIN_CERT_TYPES):
        if code in existing:
            continue
        db.add(KbCertType(
            code=code, name=name, category=category,
            default_valid_months=months, scope_hint=scope,
            is_builtin=True, enabled=True, sort_order=i,
        ))
        added += 1
    if added:
        await db.flush()
        logger.info(f"证书类型字典: 新增 {added} 条内置项")
    return added