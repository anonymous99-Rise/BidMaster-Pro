"""W4 深度分析算分 (KB-M7): 团队配置优化器 + 业绩自动算分。

按 IT 服务类公开招标常见评分表校准 (设计文档 9.1):
- 项目负责人(1人): 软考高级证书 +2, 软考中级每项 +1, 满 3
- 技术负责人(1人): 软考高级 +2, 软考中级每项 +1, 满 3
- 团队成员: 软考高级每人 1 分 / 中级 0.5 分; 同一人多证按最高级计一次, 满 9
- 业绩: 近三年类似业绩每项 1 分, 上限 5

纯规则 + 组合优化, 无需 LLM。
"""
from __future__ import annotations

from datetime import datetime, timedelta

TEAM_CAPS = {"lead": 3.0, "tech_lead": 3.0, "members": 9.0}
PERF_CAP = 5.0

# 软考证书等级识别
_SENIOR_KW = ("信息系统项目管理师", "系统分析师", "系统架构设计师", "网络规划设计师",
              "系统规划与管理师", "高级")
_INTERMEDIATE_KW = ("系统集成项目管理工程师", "软件设计师", "网络工程师", "信息系统监理师",
                    "数据库系统工程师", "中级")


def _cert_level(cert_name: str) -> str:
    """返回 'senior' / 'intermediate' / '' (非软考)。"""
    n = cert_name or ""
    if any(k in n for k in _SENIOR_KW):
        return "senior"
    if any(k in n for k in _INTERMEDIATE_KW):
        return "intermediate"
    return ""


def _person_best_level(certs: list[dict]) -> str:
    """该人员持有的最高软考级别: senior > intermediate > ''。"""
    levels = [_cert_level(c.get("cert_type") or c.get("name") or "") for c in certs]
    if "senior" in levels:
        return "senior"
    if "intermediate" in levels:
        return "intermediate"
    return ""


def optimize_team(personnel: list[dict], certs_by_person: dict) -> dict:
    """团队配置优化器: 输入人员+证书 → 最高团队分 + 最优班子 + 缺口分析。

    personnel: [{id, name, ...}]
    certs_by_person: {person_id: [{cert_type/name, valid_until}, ...]}
    规则: 同一人多证按最高级别计一次 (硬约束)。
    """
    scored = []
    for p in personnel:
        pid = p.get("id")
        certs = certs_by_person.get(pid, [])
        # 只计有效期内证书
        today = datetime.utcnow().strftime("%Y-%m-%d")
        valid = [c for c in certs
                 if not (c.get("valid_until") or "") or str(c["valid_until"])[:10] >= today]
        level = _person_best_level(valid)
        if not level:
            continue
        score = 1.0 if level == "senior" else 0.5  # 成员角色下的基础分
        scored.append({"person_id": pid, "name": p.get("name"),
                       "level": level, "member_score": score})

    # 高级优先当负责人/技术负责人 (每 +2 分)
    seniors = sorted([s for s in scored if s["level"] == "senior"],
                     key=lambda x: -x["member_score"])
    intermediates = [s for s in scored if s["level"] == "intermediate"]

    lead = seniors[0] if seniors else None
    tech_lead = (seniors[1] if len(seniors) > 1
                 else (intermediates[0] if intermediates else None))

    used = {s["person_id"] for s in (lead, tech_lead) if s}
    pool = seniors + intermediates
    members = [s for s in pool if s["person_id"] not in used]

    lead_score = 2.0 if lead else 0.0
    tech_score = 2.0 if tech_lead else 0.0
    member_score = sum(1.0 if m["level"] == "senior" else 0.5
                       for m in members[: int(TEAM_CAPS["members"] / 0.5)])
    member_score = min(member_score, TEAM_CAPS["members"])

    total = min(lead_score, TEAM_CAPS["lead"]) + min(tech_score, TEAM_CAPS["tech_lead"]) \
        + member_score

    gaps = []
    if not lead:
        gaps.append("缺软考高级证书人员 → 任项目负责人 +2 分")
    if not tech_lead:
        gaps.append("缺第 2 名软考高级(或中级) → 任技术负责人 +2 分")
    senior_members = sum(1 for m in members if m["level"] == "senior")
    if senior_members < 9:
        gaps.append(f"成员软考高级 {senior_members}/9 人, 每再增 1 名高级 +1 分")

    return {"max_total": round(total, 1),
            "cap": sum(TEAM_CAPS.values()),
            "roster": {
                "project_lead": lead,
                "tech_lead": tech_lead,
                "members": members[:18],
            },
            "score_detail": {
                "lead": lead_score, "tech_lead": tech_score,
                "members": member_score,
            },
            "gaps": gaps,
            }


def score_performance(achievements: list[dict],
                      similar_keywords: tuple[str, ...] = (),
                      years: int = 3) -> dict:
    """业绩自动算分: 近 N 年类似业绩每项 1 分, 上限 5。

    achievements: [{announce_date/sign_date, project_name, bid_result}]
    similar_keywords 为空 → 视为全部类似 (宽松)。
    """
    cutoff = (datetime.utcnow() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
    similar = []
    for a in achievements:
        d = str(a.get("announce_date") or a.get("sign_date") or "")[:10]
        if d and d < cutoff:
            continue
        if a.get("bid_result") == "loss":
            continue
        name = a.get("project_name") or ""
        if similar_keywords and not any(k in name for k in similar_keywords):
            continue
        similar.append(a)

    score = min(float(len(similar)), PERF_CAP)
    return {"score": score, "cap": PERF_CAP,
            "count_recent_similar": len(similar),
            "gap": ("业绩每项 1 分已满, 上限 5" if score >= PERF_CAP
                    else f"再增 {int(PERF_CAP - score)} 条类似业绩可 +{PERF_CAP - score:.0f} 分")}
