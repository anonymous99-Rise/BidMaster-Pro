"""招标公告商机字段提取器

从公告详情页正文(纯文本/窄 HTML)中提取商机关键字段:
    bid_deadline   投标/递交截止时间
    amount         预算/采购金额(以元为单位归一)
    region         项目所在地区(省/市/区)
    owner_org      采购人/招标人
    project_code   项目编号

设计目标:让 5 维商机评分的 紧急度/金额/地域 从"常数死值"变成真实值。
所有提取全部容错 —— 找不到就返回 None/"" (不中断管线,评分回退默认)。
"""
from __future__ import annotations

import re
from typing import Optional

_WS = re.compile(r"\s+")

# ───────────────────────────── 截止时间 ─────────────────────────────
# 常见表述: "投标截止时间:2026年10月20日 09:00" / "递交响应文件截止时间:2026-10-20 09:00"
#           "获取磋商文件 开始时间: ... 截止时间: ..."
_DEADLINE_KW = (
    "截止" , "递交", "应答", "响应", "投标", "开标", "询价", "谈判", "磋商"
)
_DATE_TIME_RE = re.compile(
    r"(\d{4})[年\-\/.](1[0-2]|0?[1-9])[月\-\/.]([12][0-9]|3[01]|0?[1-9])[日号]?"
    r"(?:\s{0,2}[0-2]?[0-9][:：][0-5][0-9])?"
)

def normalize_datetime(s: str) -> str:
    """把各种日期时间写法归一为 ISO 日期(截断时分更稳, 供 scoring 比较)。"""
    s = _WS.sub(" ", s or "").strip()
    m = _DATE_TIME_RE.search(s)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"


def extract_deadline(text: str) -> Optional[str]:
    """从文本中找截止时间。

    策略:
    - 优先找 "截止/递交/开标/响应" 等词后紧跟的日期时间
    - 找不到则退化为正文最后一个日期时间(公告版式通常截止日期在结尾)
    """
    if not text:
        return None
    stripped = _WS.sub(" ", text)

    # 1) 关键词后置日期: "截止时间:2026年10月20日 09:00"
    #   注意: _DATE_TIME_RE 内含捕获组, 不能直接嵌进外层组, 否则组号错位
    #   这里只把"年月日"部分定义为具名组, 时间部分不需要 (normalize 只取日期)
    kw_pattern = re.compile(
        r"(?:截止|递交|开标|响应|投标|文件递交|各投标人须在)[^0-9]{0,30}"
        r"(?P<date>(?:\d{4}[年\-\/.])(?:1[0-2]|0?[1-9])[月\-\/.]"
        r"(?:[12][0-9]|3[01]|0?[1-9])[日号]?)"
    )
    m = kw_pattern.search(stripped)
    if m:
        return normalize_datetime(m.group("date"))

    # 2) 退化: 最后一个日期
    matches = list(_DATE_TIME_RE.finditer(stripped))
    if matches:
        return normalize_datetime(matches[-1].group(0))
    return None


# ───────────────────────────── 金额 ─────────────────────────────
# 常见表述: "预算金额: 人民币 1,250.00 万元" / "预算金额: 1250万元"
#           "采购预算: 1200000元" / "项目预算: 820 万元"
_AMOUNT_ZWAN = re.compile(
    r"(?:预算|采购预算|项目预算|控制价|最高限价|采购金额)[^0-9]{0,20}"
    r"([0-9][0-9,，.]{0,15})\s*万元"
)
_AMOUNT_YUAN = re.compile(
    r"(?:预算|采购预算|项目预算|控制价|最高限价|采购金额)[^0-9]{0,20}"
    r"([0-9][0-9,，.]{0,15})\s*元"
)


def extract_amount(text: str) -> Optional[float]:
    """提取预算金额, 归一化为万元(带小数的万元单位)或绝对万元数。"""
    if not text:
        return None
    # 万元
    m = _AMOUNT_ZWAN.search(text)
    if m:
        try:
            val = float(m.group(1).replace(",", "").replace(",", ""))
            return val
        except ValueError:
            pass
    # 精确元 → /10000 转万元
    m = _AMOUNT_YUAN.search(text)
    if m:
        try:
            val = float(m.group(1).replace(",", "").replace(",", ""))
            return val / 10000.0
        except ValueError:
            pass
    return None


# ───────────────────────────── 地区 ─────────────────────────────
_PROVINCES = [
    "北京", "上海", "天津", "重庆", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东",
    "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏",
    "新疆", "香港", "澳门", "台湾",
]
_CITIES = [
    "石家庄", "太原", "沈阳", "长春", "哈尔滨", "南京", "杭州", "合肥", "福州", "南昌",
    "济南", "郑州", "武汉", "长沙", "广州", "深圳", "南宁", "海口", "成都", "贵阳",
    "昆明", "拉萨", "西安", "兰州", "西宁", "银川", "乌鲁木齐",
]
def extract_region(text: str) -> str:
    """找正文中地区: 优先采购人名称/地址段, 其次任意省份, 最后 "XX市" 地级市模式。"""
    if not text:
        return ""
    result = ""
    # 1) 采购人/招标人 名称或地址段 (名字里常带地区, 如"宣城市民政局")
    addr = re.search(r"(采购人|招标人|采购单位|采购中心)[^，。；\n]{0,6}[:：]?\s*([一-龥]{2,20})", text)
    if addr:
        seg = addr.group(2) or ""
        for p in _PROVINCES:
            if p in seg:
                result = p
                break
        if not result:
            for c in _CITIES:
                if c in seg:
                    result = c
                    break
    # 2) 正文任意省份
    if not result:
        for p in _PROVINCES:
            if p in text:
                result = p
                break
    # 3) 正文任意 "XX市" 地级市模式
    if not result:
        city_m = re.search(r"([一-龥]{2,3})市", text)
        if city_m:
            result = city_m.group(1) + "市"
    return result


# ───────────────────────────── 采购人 / 项目编号 ─────────────────────────────
_OWNER_RE = re.compile(
    r"(?:采购人|招标人|采购单位|招标单位|采购代理机构|项目业主|发包人|业主单位)"
    r"\s*[:：]?\s*"
    r"([一-龥A-Za-z0-9（）()]{3,40}?)"
    r"(?=[、，,。;；\n]|\s*(?:地址|联系方式|联系电话|联系人|电话|采购项目编号|招标项目编号|采购编号|项目编号|招标编号|预算|金额|邮编|电子邮箱|邮箱)|$)"
)
_PROJECT_CODE_RE = re.compile(
    r"(?:项目编号|招标编号|采购编号|项目编号：|招标项目编号|采购项目编号)\s*[:：]?\s*"
    r"([A-Za-z0-9\-_]{4,32})"
)


def extract_owner(text: str, sep: str = "") -> str:
    """找采购人/招标人(排除无意义 stack)。"""
    if not text:
        return ""
    m = _OWNER_RE.search(text)
    if m:
        # 过短(单字/纯数字)视为误捕获
        org = (m.group(1) or "").strip()
        org = sep.join(org.split())
        if len(org) >= 3 and not org.isdigit():
            return org
    return ""


def extract_project_code(text: str) -> str:
    if not text:
        return ""
    m = _PROJECT_CODE_RE.search(text)
    if m and m.group(1):
        return m.group(1).strip()
    return ""


# ───────────────────────────── 公告类型 ─────────────────────────────
_ANNOUNCE_TERMS = {
    "中标": "award",       # 中标公告
    "成交": "award",       # 成交/结果公告
    "流标": "failed",      # 流标/废标
    "废标": "failed",
    "结果": "award",       # 评审结果等(放在流标后, 避免"废标结果"误判)
    "更正": "change",      # 澄清/更正/变更/补充
    "变更": "change",
    "补充": "change",
}


def announce_type_from_title(title: str) -> str:
    """根据公告标题判定类型: tender(招标) / award(中标成交) / change(变更更正) / failed(流标)"""
    if not title:
        return "tender"
    for kw, t in _ANNOUNCE_TERMS.items():
        if kw in title:
            return t
    return "tender"


# ───────────────────────────── 统一入口 ─────────────────────────────
def extract_all(text: str) -> dict:
    """从公告正文提取全部商机字段。返回无需再清洗的 dict。"""
    content_ws = _WS.sub(" ", text or "")
    return {
        "bid_deadline": extract_deadline(content_ws),
        "amount": extract_amount(content_ws),
        "region": extract_region(content_ws),
        "owner_org": extract_owner(content_ws),
        "project_code": extract_project_code(content_ws),
    }