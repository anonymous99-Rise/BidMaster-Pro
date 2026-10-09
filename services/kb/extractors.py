"""KB 结构化抽取: 规则优先的正则/关键词抽取器。

设计原则 (multi-agent 分工): 规则能算的绝不用 LLM。
每个抽取器只做"确定性的字段提取", 置信不足返回空字段,
由上层走 LLM 兜底或标记 needs_completion 待人工补全。
"""
from __future__ import annotations

import re

# ============ 通用工具 ============

# 日期表达: 2019年8月1日 / 2019.08.01 / 2019-08-01 / 2019/8/1
_DATE_RE = re.compile(
    r"(?P<y>20\d{2})[年.\-/](?P<m>\d{1,2})[月.\-/]?(?P<d>\d{1,2})?[日]?"
)


def _norm_date(match: re.Match | None) -> str:
    if not match:
        return ""
    y, m, d = match.group("y"), match.group("m"), match.group("d")
    if not y:
        return ""
    m = m or "1"
    d = d or "1"
    return f"{y}-{int(m):02d}-{int(d):02d}"


def find_date(text: str, keyword: str) -> str:
    """在指定关键词附近找日期 (YYYY-MM-DD)。"""
    idx = text.find(keyword)
    if idx < 0:
        return ""
    window = text[idx : idx + 120]
    return _norm_date(_DATE_RE.search(window))


def extract_date_range(text: str) -> tuple[str, str]:
    """提取证书的 (颁发日期, 有效期至)。"""
    issue = find_date(text, "颁发日期") or find_date(text, "发证日期")
    expiry = (
        find_date(text, "有效期至")
        or find_date(text, "有效日期至")
        or find_date(text, "有效期")
    )
    return issue, expiry


def _to_wan(value: str, unit: str) -> float:
    """金额归一到万元。"""
    try:
        num = float(value.replace(",", "").replace("，", ""))
    except ValueError:
        return 0.0
    return round(num / 10000, 4) if unit == "元" else num


# ---------------------------------------------------------------- 分类规则

# 文件名 → 子库 关键词表 (BiaoShu 四桶思路)
FILENAME_RULES: list[tuple[str, list[str]]] = [
    ("certificate", ["资质", "证书", "认证", "营业执照", "许可证", "安许", "体系"]),
    ("personnel", ["人员", "简历", "身份证", "社保", "职称", "聘", "花名册"]),
    ("achievement", ["合同", "业绩", "中标", "验收", "成交", "发票", "结算", "履约"]),
    ("financial", ["审计", "财务", "报表", "资产负债", "利润", "纳税", "完税", "财报"]),
    ("credit", ["信用", "资信", "AAA", "失信", "无违法", "重合同"]),
]

_CONTENT_CERT = [
    "质量管理体系", "ISO9001", "ISO14001", "ISO45001", "信息安全管理体系",
    "ITSS", "CCRC", "CMMI", "软件企业", "软件产品", "安防工程", "涉密信息系统",
    "安全生产许可证", "建筑业企业资质", "电子与智能化", "信息系统集成",
]
_CONTENT_BUSINESS_LICENSE = ["统一社会信用代码", "经营范围", "注册资本", "法定代表人"]
_CONTENT_PERSON = ["身份证", "性别", "民族", "出生日期", "社会保险", "职称", "项目经理"]
_CONTENT_ACHIEVEMENT = ["合同金额", "项目名称", "甲方", "签订", "履约", "供货", "采购人"]
_CONTENT_FINANCIAL = ["资产负债表", "利润表", "现金流量表", "审计报告", "营业收入", "资产总额", "净利润"]
_CONTENT_CREDIT = ["信用评级", "AAA", "纳税信用等级", "重合同守信用", "无重大违法", "信用记录"]


def classify_category(filename: str, text: str) -> str:
    """按文件名+内容分类到子库。默认 certificate(资质库)。"""
    fname = filename.lower()

    score: dict[str, int] = {cat: 0 for cat, _ in FILENAME_RULES}
    for cat, kws in FILENAME_RULES:
        for kw in kws:
            if kw.lower() in fname:
                score[cat] += 2
    best = max(score, key=score.get)
    if score[best] >= 2:
        return best

    head = text[:1200]
    if any(k in head for k in _CONTENT_BUSINESS_LICENSE):
        return "certificate"
    if any(k in text for k in _CONTENT_CERT):
        return "certificate"
    if any(k in head for k in _CONTENT_ACHIEVEMENT):
        return "achievement"
    if any(k in head for k in _CONTENT_FINANCIAL):
        return "financial"
    if any(k in head for k in _CONTENT_CREDIT):
        return "credit"
    if any(k in head for k in _CONTENT_PERSON):
        return "personnel"
    return "certificate"


# ---------------------------------------------------------------- 资质证书
_CERT_INFO_RE = re.compile(r"(证书编号|证书号|编号|NO|No)[:：\s]*([A-Za-z0-9\-—/（）()一-龥]{4,60})")
_CERT_NAME_KEYWORDS = [
    "质量管理体系认证证书", "信息安全管理体系认证", "环境管理体系认证", "职业健康安全管理体系",
    "ITSS", "CCRC", "CMMI", "软件企业认定", "高新技术企业证书", "安防工程企业资质",
    "电子与智能化工程专业承包", "安全生产许可证", "建筑业企业资质证书",
    "计算机信息系统集成资质", "软件著作权", "营业执照",
]


def extract_certificate(text: str, filename: str = "") -> dict:
    rec: dict = {
        "name": "", "number": "", "category": "enterprise",
        "level": "", "scope": "", "holder": "",
        "issue_date": "", "expiry_date": "", "issuing_authority": "",
    }
    head = text[:1500]

    for kw in _CERT_NAME_KEYWORDS:
        if kw in text:
            rec["name"] = kw
            break
    if not rec["name"] and filename:
        stem = filename.rsplit(".", 1)[0]
        if "资质" in stem or "证书" in stem:
            rec["name"] = stem[:200]

    for m in _CERT_INFO_RE.finditer(text[:2500]):
        if m.group(1) in ("证书编号", "证书号", "编号"):
            rec["number"] = m.group(2).strip()
            break

    for kw in ("发证机关", "颁证机构", "认证机构", "发证单位"):
        idx = text.find(kw)
        if idx >= 0:
            seg = text[idx + len(kw) : idx + len(kw) + 60]
            m = re.search(r"[:：]?\s*([一-龥]{4,30})", seg)
            if m:
                rec["issuing_authority"] = m.group(1).strip(" ：:.")
                break

    if "统一社会信用代码" in head or "营业执照" in head:
        rec["holder"] = "company"

    rec["issue_date"], rec["expiry_date"] = extract_date_range(text)
    return {"certificate": rec}


def cert_confidence(rec: dict) -> float:
    s = 0.0
    if rec.get("name"):
        s += 0.35
    if rec.get("number"):
        s += 0.25
    if rec.get("expiry_date"):
        s += 0.2
    if rec.get("issuing_authority"):
        s += 0.2
    return round(min(s, 1.0), 2)


# ---------------------------------------------------------------- 业绩合同
def extract_achievement(text: str, filename: str = "") -> dict:
    rec = {
        "project_name": "", "client_name": "", "contract_no": "",
        "contract_amount": 0.0, "sign_date": "", "completion_date": "",
        "year": 0, "project_scope": "", "project_type": "",
    }

    for kw in ["项目名称", "合同名称", "采购项目", "工程名称"]:
        idx = text.find(kw)
        if idx >= 0:
            seg = text[idx + len(kw) : idx + len(kw) + 120]
            # 到下一个字段关键词或换行为止
            m = re.search(r"[:：]?\s*([^\n\r]{4,80}?)(?=\s*(?:甲方|采购人|合同|中标|成交|金额|签订|签约|项目|编号|$|\n))", seg)
            if m:
                rec["project_name"] = m.group(1).strip(" 。，:：")
                break
    if not rec["project_name"] and filename:
        rec["project_name"] = filename.rsplit(".", 1)[0][:80]

    idx = text.find("甲方")
    if idx < 0:
        idx = text.find("采购人")
    if idx >= 0:
        seg = text[idx + 2 : idx + 120]
        # 甲方可能短至 2 字 (某医院/某局), 非贪婪 + 结尾机构后缀兜底
        m = re.search(r"[:：]?\s*([一-龥]{2,50}?(?:公司|局|处|院|学校|医院|中心|大队|站|政府|集团))", seg)
        if m:
            rec["client_name"] = m.group(1).strip(" ：:")

    m = re.search(
        r"(?:合同总价|合同金额|合同价款|中标金额|成交金额|项目总金额|项目金额|合同)[:：]?\s*[为约是共]?\s*[¥￥]?\s*([\d,，.]+)\s*(万元|万|元)",
        text,
    )
    if m:
        rec["contract_amount"] = _to_wan(m.group(1), m.group(2))
    else:
        m2 = re.search(r"金额[:：]?\s*[为约是共]?\s*[¥￥]?\s*([\d,，.]+)\s*(万元|万|元)", text)
        if m2:
            rec["contract_amount"] = _to_wan(m2.group(1), m2.group(2))

    m = re.search(r"(合同编号|合同号)[:：]?\s*([A-Za-z0-9\-—/（）()一-龥]{4,50})", text)
    if m:
        rec["contract_no"] = m.group(2).strip()

    rec["sign_date"] = find_date(text, "签订") or find_date(text, "签约")
    rec["completion_date"] = find_date(text, "验收") or find_date(text, "完工")
    if rec["sign_date"]:
        rec["year"] = int(rec["sign_date"][:4])
    return {"achievement": rec}


def achievement_confidence(rec: dict) -> float:
    return round(sum([
        0.35 if rec.get("project_name") else 0,
        0.3 if rec.get("client_name") else 0,
        0.25 if rec.get("contract_amount") else 0,
        0.1 if rec.get("sign_date") else 0,
    ]), 2)


# ---------------------------------------------------------------- 人员
_PERSON_NAME_RE = re.compile(r"姓\s*名[:：]?\s*([一-龥]{2,4})")
_ID_CARD_RE = re.compile(r"(\d{17}[\dXx])")
_TITLE_KEYWORDS = ["高级工程师", "工程师", "正高级", "高级", "中级", "初级", "信息系统项目管理师"]


def extract_personnel(text: str, filename: str = "") -> dict:
    rec = {"name": "", "gender": "", "title": "", "role": "",
           "id_number": "", "dept": ""}
    m = _PERSON_NAME_RE.search(text)
    if m:
        rec["name"] = m.group(1)
    if not rec["name"]:
        # 身份证前面常是姓名
        mi = _ID_CARD_RE.search(text)
        if mi:
            pre = text[max(0, mi.start() - 12) : mi.start()]
            m2 = re.search(r"([一-龥]{2,4})\s*$", pre)
            if m2:
                rec["name"] = m2.group(1)
    mi = _ID_CARD_RE.search(text)
    if mi:
        rec["id_number"] = mi.group(1)
        if len(rec["id_number"]) >= 17:
            gender_digit = int(rec["id_number"][16])
            rec["gender"] = "男" if gender_digit % 2 == 1 else "女"
    for kw in _TITLE_KEYWORDS:
        if kw in text:
            rec["title"] = kw
            break
    for kw in ("项目经理", "技术负责人", "项目负责人", "总工", "安全员"):
        if kw in text:
            rec["role"] = kw
            break
    return {"personnel": rec}


def personnel_confidence(rec: dict) -> float:
    return round(sum([
        0.4 if rec.get("name") else 0,
        0.3 if rec.get("id_number") else 0,
        0.2 if rec.get("title") else 0,
        0.1 if rec.get("role") else 0,
    ]), 2)


# 人员资质/证书提取 (软考/职称 系列, 团队配置优化器的数据源)
_CERT_MARKERS = [
    ("信息系统项目管理师", "软考高级", "高级"),
    ("系统分析师", "软考高级", "高级"),
    ("系统架构设计师", "软考高级", "高级"),
    ("系统集成项目管理工程师", "软考中级", "中级"),
    ("软件设计师", "软考中级", "中级"),
    ("数据库系统工程师", "软考中级", "中级"),
    ("信息系统监理师", "软考中级", "中级"),
    ("网络工程师", "软考中级", "中级"),
    ("PMP", "PMP", "高级"),
    ("一级建造师", "建造师", "一级"),
    ("二级建造师", "建造师", "二级"),
]
_CERT_NO_RE = re.compile(r"(?:证书编号|证书号|编号|NO|No)[:：\s]*([A-Za-z0-9\-—/（）()一-龥]{4,40})")


def extract_personnel_certs(text: str) -> list[dict]:
    """从人员文档中提取 人员资质/证书 列表。"""
    certs: list[dict] = []
    for marker, cert_type, level in _CERT_MARKERS:
        idx = text.find(marker)
        if idx < 0:
            # 允许 "高级工程师/信息系统项目管理师" 混排时前缀命中
            if marker not in text:
                continue
            idx = text.find(marker)
        cert_no = ""
        # 证书号通常在证书名称附近
        seg = text[idx : idx + 200]
        m = _CERT_NO_RE.search(seg)
        if m:
            cert_no = m.group(1).strip()
        certs.append({
            "cert_type": marker,
            "cert_type_code": ("soft_exam_senior" if level == "高级" and "软考" in cert_type
                               else "soft_exam_mid" if level == "中级" and "软考" in cert_type
                               else "pmp" if cert_type == "PMP" else ""),
            "level": level,
            "cert_no": cert_no,
            "issue_date": "",
            "expiry_date": "",
        })
    # 去重 (同一证书名称只记一次)
    seen = set()
    unique = []
    for c in certs:
        if c["cert_type"] in seen:
            continue
        seen.add(c["cert_type"])
        unique.append(c)
    return unique


# ---------------------------------------------------------------- 财务
def extract_financial(text: str, filename: str = "") -> dict:
    rec = {"report_type": "financial_statement", "period_start": "", "period_end": "",
           "year": 0, "total_assets": 0.0, "revenue": 0.0, "net_profit": 0.0,
           "debt_ratio": 0.0, "audit_agency": ""}
    if "审计" in filename or "审计报告" in text[:400]:
        rec["report_type"] = "audit_report"

    m = re.search(r"资产总额[:：]?\s*[¥￥]?\s*([\d,，.]+)\s*(万元|万|元)", text)
    if m:
        rec["total_assets"] = _to_wan(m.group(1), m.group(2))
    m = re.search(r"营业收入[:：]?\s*[¥￥]?\s*([\d,，.]+)\s*(万元|万|元)", text)
    if m:
        rec["revenue"] = _to_wan(m.group(1), m.group(2))
    m = re.search(r"(资产负债率|负债率)[:：]?\s*([\d.]+)\s*%", text)
    if m:
        rec["debt_ratio"] = float(m.group(2))
    m = re.search(r"净利润[:：]?\s*[¥￥]?\s*([\d,，.]+)\s*(万元|万|元)", text)
    if m:
        rec["net_profit"] = _to_wan(m.group(1), m.group(2))
    m = re.search(r"(20\d{2})\s*年度?", text[:200])
    if m:
        rec["year"] = int(m.group(1))
    return {"financial": rec}


def financial_confidence(rec: dict) -> float:
    return round(sum([
        0.3 if rec.get("total_assets") else 0,
        0.3 if rec.get("revenue") else 0,
        0.2 if rec.get("debt_ratio") else 0,
        0.2 if rec.get("net_profit") else 0,
    ]), 2)


# ---------------------------------------------------------------- 信用
def extract_credit(text: str, filename: str = "") -> dict:
    rec = {"credit_type": "credit_check_snapshot", "title": "", "check_date": "", "result": ""}
    upper = text.upper()
    if "AAA" in upper or "AAA" in filename.upper() or "资信" in text:
        rec["credit_type"] = "aaa_certificate"
    if "失信" in text or "无重大违法" in text or "无违法" in text:
        rec["credit_type"] = "no_violation"
    m = re.search(r"(信用等级|资信等级)[:：]?\s*([A-Za-z0-9+\-]{1,10})", text)
    if m:
        rec["title"] = m.group(2)
    elif "AAA" in upper:
        rec["title"] = "AAA"
    rec["check_date"] = find_date(text, "查询日期") or find_date(text, "报告日期")
    return {"credit": rec}


def credit_confidence(rec: dict) -> float:
    return round(0.5 if rec.get("title") else 0.2, 2)


# 子库 → (抽取器, 置信度函数)
EXTRACTORS = {
    "certificate": (extract_certificate, cert_confidence),
    "achievement": (extract_achievement, achievement_confidence),
    "personnel": (extract_personnel, personnel_confidence),
    "financial": (extract_financial, financial_confidence),
    "credit": (extract_credit, credit_confidence),
}


def extract_by_category(category: str, text: str, filename: str = "") -> tuple[dict, float] | None:
    """按子库抽取, 返回 ({子库: 字段dict}, 置信度)。未知子库返回 None。"""
    pair = EXTRACTORS.get(category)
    if not pair:
        return None
    fn, conf_fn = pair
    try:
        result = fn(text, filename)
        key = next(iter(result))
        return result, conf_fn(result[key])
    except Exception:
        return None