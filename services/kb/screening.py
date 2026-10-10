"""W3 初筛引擎 (KB-M6): 资格条件逐条勾对 → 三态结论 + 三大产物。

参考 rag-tender match_service.py 实证设计:
- ①分流: 声明承诺类条款(信用中国/无重大违法等)不进资质匹配 → 转商务文函生成
- ②数值规则(零成本): 注册资本/合同金额/营收/资产负债率/年限 正则提取后与知识库比较
- ③候选匹配: 同义词表归一(ISO三系/社保/职称…9组) + 知识库逐卡打分
- ④证据矩阵: 每候选逐字段核验(名称/持有人/有效期), 全 critical pass 才 matched,
  任一缺失 → needs_review (保守三态: 绝不猜 matched —— 错杀可人工推翻, 错放直接废标)
- ⑤修正回流: 人工改判记录进 kb_screening_corrections, 下次同条款直接按修正结论

三态: matched(资格符合) / failed(资格不符) / needs_review(进人审队列)。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, date
from typing import Optional

# ── 数值规则 (5 类) ──────────────────────────────────────────────
_GE = r"(?:不低于|不少于|不低于|达|至少|大于等于|≥|>=|>){0,2}"
_LE = r"(?:不超过|不超过|小于等于|≤|<=|<){0,2}"
_RULE_PATTERNS = {
    "registered_capital": (r"注册资本" + _GE + r"\s*(\d+(?:\.\d+)?)\s*万元?", 1),
    "contract_amount": (r"(?:合同金额|类似业绩|单项合同)" + _GE + r"\s*(\d+(?:\.\d+)?)\s*万元?", 1),
    "revenue": (r"营业收入" + _GE + r"\s*(\d+(?:\.\d+)?)\s*万元?", 1),
    "debt_ratio": (r"资产负债率" + _LE + r"\s*(\d+(?:\.\d+)?)\s*%", -1),
    "personnel_years": (r"(?:从业|工作)?(?:年限|经验)" + _GE + r"\s*(\d+)\s*年", 1),
}

# ── 同义词表 (9 组) ──────────────────────────────────────────────
_MATCH_SYNONYMS = {
    "营业执照": ["营业执照", "独立法人", "法人资格", "工商执照"],
    "社保证明": ["社保", "社会保险", "参保证明", "养老保险", "缴纳社保证明"],
    "职称证书": ["职称", "工程师", "助理工程师", "高级工程师", "资格证书"],
    "毕业证书": ["学历", "毕业证", "学历证书", "专业学习"],
    "管理体系认证": ["ISO9001", "ISO14001", "ISO45001", "质量管理体系", "环境管理体系",
                   "职业健康安全管理体系", "体系认证", "ISO三系"],
    "纳税证明": ["纳税", "完税证明", "缴纳税收", "税收完税证明"],
    "财务审计报告": ["财务会计报告", "财务报表", "审计报告", "财务会计制度", "健全的财务"],
    "信用证明": ["信用中国", "失信被执行人", "重大税收违法", "信用记录", "信用报告"],
    "身份证明": ["身份证", "居民身份证", "身份证明"],
}

# ── 声明承诺类关键词 (命中 → 不进资质匹配, 转文函生成) ────────────
_SKIP_KEYWORDS = (
    "信用中国", "失信被执行", "重大违法", "书面声明", "承诺函", "声明函",
    "提供承诺", "自行承诺", "如实声明", "承诺提供", "声明并承诺",
)

# ── 评分表相似度分词 ─────────────────────────────────────────────
_TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9]{2,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text or ""))


def classify_clause(text: str) -> str:
    """①分流: skip=声明承诺类(转文函) / numeric=数值规则 / qualification=资质勾对。"""
    for kw in _SKIP_KEYWORDS:
        if kw in text:
            return "skip"
    for pat in _RULE_PATTERNS.values():
        if re.search(pat[0], text):
            return "numeric"
    return "qualification"


def extract_numeric(text: str) -> Optional[dict]:
    """②数值规则: 提取 {rule, value} — 命中任一即返回。"""
    for rule, (pat, _direction) in _RULE_PATTERNS.items():
        m = re.search(pat, text)
        if m:
            return {"rule": rule, "value": float(m.group(1))}
    return None


def _normalize_name(text: str) -> str:
    """同义词归一: 返回规范名 (未命中原样返回)。"""
    low = text or ""
    for canonical, syns in _MATCH_SYNONYMS.items():
        if canonical in low or any(s in low for s in syns):
            return canonical
    return low


def _synonym_of(text: str, target: str) -> bool:
    """判断条款文本是否属于 target 的同义簇。"""
    if target in text:
        return True
    for s in _MATCH_SYNONYMS.get(target, []):
        if s in text:
            return True
    return False


def check_numeric(company_values: dict, req: dict) -> dict:
    """数值比较: company_values 形如 {registered_capital: 500.0, ...}。
    要求 ≥ 类规则: 公司值 ≥ 要求值 → pass; 值缺失 → needs_review。
    资产负债率方向相反: 公司值 ≤ 要求值 → pass。
    """
    rule, need = req["rule"], req["value"]
    have = company_values.get(rule)
    if have is None:
        return {"verdict": "needs_review", "reason": f"知识库缺少 {rule} 数值"}
    direction = _RULE_PATTERNS[rule][1]
    ok = (have >= need) if direction > 0 else (have <= need)
    return {
        "verdict": "matched" if ok else "failed",
        "reason": f"要求{need} 实际{have} ({rule})",
        "required": need, "actual": have, "rule": rule,
    }


def score_candidate(req_text: str, card_name: str) -> float:
    """③候选匹配: token 交集比例打分 0~1。"""
    a, b = _tokens(req_text), _tokens(card_name)
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), 1)


def verify_evidence(req_text: str, card: dict) -> dict:
    """④证据矩阵: 核验候选卡片 (名称归一/有效期/状态)。

    card 字段: name, holder, expiry_date, status, is_audited
    返回 {verdict, checks: [{field, result, critical}]}
    """
    checks = []
    name = _normalize_name(card.get("name") or "")
    req_norm = _normalize_name(req_text)

    # 1) 名称核验 (critical): 归一后至少一方包含另一方, 或 token 分 ≥0.5
    sim = score_candidate(req_norm, name)
    name_pass = sim >= 0.5 or _synonym_of(req_text, card.get("name") or "") \
        or _synonym_of(card.get("name") or "", req_text)
    checks.append({"field": "name", "result": "pass" if name_pass else "fail",
                   "critical": True, "similarity": round(sim, 2)})

    # 2) 有效期核验 (critical): 有效期缺失→unknown(转人审), 过期→fail
    expiry = card.get("expiry_date") or ""
    if not expiry:
        checks.append({"field": "expiry_date", "result": "unknown", "critical": True})
    else:
        try:
            expired = str(expiry)[:10] < datetime.utcnow().strftime("%Y-%m-%d")
            checks.append({"field": "expiry_date",
                           "result": "fail" if expired else "pass", "critical": True})
        except (ValueError, TypeError):
            checks.append({"field": "expiry_date", "result": "unknown", "critical": True})

    # 3) 人审状态 (非 critical): 未审卡片不阻塞但提示
    if not card.get("is_audited", False):
        checks.append({"field": "is_audited", "result": "unknown", "critical": False})

    critical_bad = any(c["critical"] and c["result"] == "fail" for c in checks)
    critical_unknown = any(c["critical"] and c["result"] == "unknown" for c in checks)
    if critical_bad:
        verdict = "failed"
    elif critical_unknown:
        verdict = "needs_review"
    else:
        verdict = "matched"
    return {"verdict": verdict, "checks": checks, "card": {
        "id": card.get("id"), "name": card.get("name"),
        "category": card.get("category"),
    }}


def screen_requirements(requirements: list[dict], kb_cards: list[dict],
                        company_values: dict,
                        corrections: Optional[dict] = None) -> dict:
    """主入口: 逐条勾对 → 三态结论。

    requirements 形如 [{"id": "B1-1", "text": "注册资本不低于500万元"}, ...]
    kb_cards 为该公司 knowledge 库卡片 (certificate/financial/credit 等)。
    corrections 形如 {"<条款指纹>": "matched|failed"} — 人工修正回流。
    corrections = corrections or {}
    """
    corrections = corrections or {}
    results = []
    for item in requirements:
        text = item.get("text", "")
        fp = str(uuid.uuid5(uuid.NAMESPACE_URL, text))[:32]
        route = classify_clause(text)

        # 修正回流: 历史人工修正优先
        if fp in corrections:
            results.append({"id": item.get("id"), "text": text, "route": route,
                            "verdict": corrections[fp],
                            "source": "correction", "reason": "沿用人工修正结论"})
            continue

        if route == "skip":
            results.append({"id": item.get("id"), "text": text, "route": "skip",
                            "verdict": "matched", "source": "skip",
                            "reason": "声明承诺类 → 转商务文函生成"})
            continue
        if route == "numeric":
            req = extract_numeric(text)
            r = check_numeric(company_values, req)
            results.append({"id": item.get("id"), "text": text, "route": "numeric",
                            **r, "source": "rule"})
            continue

        # qualification: 同义词归一 + 候选匹配 + 证据矩阵
        target = _normalize_name(text)
        candidates = []
        for card in kb_cards:
            sim = score_candidate(target, _normalize_name(card.get("name") or ""))
            if sim >= 0.3 or _synonym_of(text, card.get("name") or ""):
                candidates.append((sim, card))
        candidates.sort(key=lambda x: -x[0])

        if not candidates:
            results.append({"id": item.get("id"), "text": text, "route": "qualification",
                            "verdict": "needs_review",
                            "reason": "知识库无候选证据 → 进人审", "source": "evidence"})
            continue

        best = verify_evidence(text, candidates[0][1])
        results.append({"id": item.get("id"), "text": text, "route": "qualification",
                        **best, "source": "evidence",
                        "candidates_checked": len(candidates)})

    ok = all(r["verdict"] == "matched" for r in results)
    bad = any(r["verdict"] == "failed" for r in results)
    overall = "passed" if ok else ("failed" if bad else "needs_review")
    return {"overall": overall,
            "stats": {
                "total": len(results),
                "matched": sum(1 for r in results if r["verdict"] == "matched"),
                "failed": sum(1 for r in results if r["verdict"] == "failed"),
                "needs_review": sum(1 for r in results if r["verdict"] == "needs_review"),
            },
            "items": results}


def build_response_table(requirements: list[dict], screen_result: dict) -> list[dict]:
    """产物③: 商务要求响应表草稿 — 响应列从勾对结论预填, 人工只审偏离项。"""
    verdict_map = {r["id"]: r for r in screen_result["items"]}
    rows = []
    for req in requirements:
        r = verdict_map.get(req.get("id"), {})
        if r.get("verdict") == "failed":
            deviation = "偏离"
        elif r.get("verdict") == "matched":
            deviation = "无偏离"
        else:
            deviation = "待人工确认"
        rows.append({
            "clause": req.get("text", ""),
            "response": ("完全响应" if r.get("verdict") == "matched"
                         else "部分响应" if r.get("verdict") == "failed"
                         else "待确认"),
            "deviation": deviation,
            "evidence": [c.get("name") for c in [r.get("card")] if c],
        })
    return rows
