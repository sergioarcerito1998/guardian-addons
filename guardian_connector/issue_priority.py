"""Deterministic diagnostic issue priority engine for Guardian."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CATEGORY_WEIGHT = {
    "authentication": 28,
    "firmware": 24,
    "network": 22,
    "connection": 20,
    "timeout": 18,
    "energy": 16,
    "signal": 14,
    "config": 12,
    "diagnostic": 8,
    "other": 10,
}

LEVEL_WEIGHT = {
    "critical": 35,
    "fatal": 35,
    "error": 25,
    "warning": 12,
    "warn": 12,
    "info": 2,
    "debug": 0,
    "unknown": 5,
}


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _normalized(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip().lower()
    return text or default


def _severity(score: int, active: bool) -> str:
    if not active:
        return "resolved"
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def prioritize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(issue)

    active = issue.get("active") is True
    category = _normalized(issue.get("category"), "other")
    level = _normalized(issue.get("level"), "unknown")

    consecutive = _safe_int(issue.get("consecutive_runs_seen"))
    runs_seen = _safe_int(issue.get("runs_seen"))
    fingerprint_count = _safe_int(issue.get("fingerprint_count"))
    last_count = _safe_int(issue.get("last_count"))
    peak_count = _safe_int(issue.get("peak_count"))

    score = 0
    reasons: list[str] = []

    if active:
        score += 20
        reasons.append("active_issue")
    else:
        reasons.append("resolved_issue")

    category_score = CATEGORY_WEIGHT.get(category, CATEGORY_WEIGHT["other"])
    score += category_score
    reasons.append(f"category_{category}")

    level_score = LEVEL_WEIGHT.get(level, LEVEL_WEIGHT["unknown"])
    score += level_score
    reasons.append(f"level_{level}")

    if consecutive >= 10:
        score += 25
        reasons.append("persistent_10_runs")
    elif consecutive >= 5:
        score += 18
        reasons.append("persistent_5_runs")
    elif consecutive >= 2:
        score += 10
        reasons.append("persistent_2_runs")

    if runs_seen >= 20:
        score += 15
        reasons.append("frequent_20_runs")
    elif runs_seen >= 10:
        score += 10
        reasons.append("frequent_10_runs")
    elif runs_seen >= 3:
        score += 5
        reasons.append("frequent_3_runs")

    if fingerprint_count >= 10:
        score += 12
        reasons.append("high_recurrence")
    elif fingerprint_count >= 3:
        score += 6
        reasons.append("recurring_issue")

    if peak_count >= 1000:
        score += 12
        reasons.append("very_high_peak_count")
    elif peak_count >= 100:
        score += 8
        reasons.append("high_peak_count")
    elif peak_count >= 10:
        score += 4
        reasons.append("elevated_peak_count")

    if last_count >= 100:
        score += 6
        reasons.append("high_current_count")
    elif last_count >= 10:
        score += 3
        reasons.append("elevated_current_count")

    if not active:
        score = min(score, 20)

    score = min(score, 100)

    result["priority_score"] = score
    result["severity"] = _severity(score, active)
    result["reason_codes"] = reasons

    return result


def prioritize_issues(
    issues: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked = [
        prioritize_issue(issue)
        for issue in issues.values()
        if isinstance(issue, dict)
    ]

    return sorted(
        ranked,
        key=lambda issue: (
            issue.get("active") is not True,
            -_safe_int(issue.get("priority_score")),
            issue.get("issue_key", ""),
        ),
    )
