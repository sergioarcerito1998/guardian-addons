"""Calibrated deterministic diagnostic issue assessment for Guardian."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


CATEGORY_RISK = {
    "authentication": 32,
    "firmware": 24,
    "network": 24,
    "connection": 22,
    "timeout": 18,
    "energy": 16,
    "signal": 14,
    "config": 12,
    "diagnostic": 8,
    "other": 8,
}

LEVEL_RISK = {
    "critical": 38,
    "fatal": 38,
    "error": 26,
    "warning": 10,
    "warn": 10,
    "info": 2,
    "debug": 0,
    "unknown": 5,
}

HIGH_IMPACT_CATEGORIES = {
    "authentication",
    "firmware",
    "network",
    "connection",
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


def _persistence_band(consecutive_runs: int) -> tuple[int, str | None]:
    if consecutive_runs >= 20:
        return 18, "persistent_20_runs"
    if consecutive_runs >= 10:
        return 14, "persistent_10_runs"
    if consecutive_runs >= 5:
        return 10, "persistent_5_runs"
    if consecutive_runs >= 2:
        return 5, "persistent_2_runs"
    return 0, None


def _recurrence_band(
    runs_seen: int,
    fingerprint_count: int,
) -> tuple[int, str | None]:
    recurrence = max(runs_seen, fingerprint_count)

    if recurrence >= 50:
        return 12, "very_high_recurrence"
    if recurrence >= 20:
        return 9, "high_recurrence"
    if recurrence >= 5:
        return 5, "recurring_issue"
    if recurrence >= 2:
        return 2, "repeated_issue"
    return 0, None


def _intensity_band(
    last_count: int,
    peak_count: int,
) -> tuple[int, str | None]:
    intensity = max(last_count, peak_count)

    if intensity >= 10000:
        return 10, "extreme_event_volume"
    if intensity >= 1000:
        return 7, "very_high_event_volume"
    if intensity >= 100:
        return 4, "high_event_volume"
    if intensity >= 10:
        return 2, "elevated_event_volume"
    return 0, None


def _confidence(
    *,
    active: bool,
    consecutive_runs: int,
    runs_seen: int,
    fingerprint_count: int,
) -> float:
    if not active:
        return 1.0

    evidence = max(runs_seen, fingerprint_count)

    value = 0.45

    if consecutive_runs >= 2:
        value += 0.15
    if consecutive_runs >= 5:
        value += 0.10
    if evidence >= 3:
        value += 0.10
    if evidence >= 10:
        value += 0.10
    if evidence >= 20:
        value += 0.05

    return round(min(value, 1.0), 2)


def _technical_severity(
    *,
    active: bool,
    level: str,
    category: str,
) -> str:
    if not active:
        return "resolved"

    if level in {"critical", "fatal"}:
        return "critical"

    if level == "error":
        if category in HIGH_IMPACT_CATEGORIES:
            return "high"
        return "medium"

    if level in {"warning", "warn"}:
        return "medium"

    return "low"


def _operational_priority(score: int, active: bool) -> str:
    if not active:
        return "resolved"
    if score >= 75:
        return "urgent"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def assess_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(issue)

    active = issue.get("active") is True
    category = _normalized(issue.get("category"), "other")
    level = _normalized(issue.get("level"), "unknown")

    consecutive_runs = _safe_int(
        issue.get("consecutive_runs_seen")
    )
    runs_seen = _safe_int(issue.get("runs_seen"))
    fingerprint_count = _safe_int(
        issue.get("fingerprint_count")
    )
    last_count = _safe_int(issue.get("last_count"))
    peak_count = _safe_int(issue.get("peak_count"))

    reasons: list[str] = []

    if not active:
        result["priority_score"] = 0
        result["technical_severity"] = "resolved"
        result["operational_priority"] = "resolved"
        result["severity"] = "resolved"
        result["confidence"] = 1.0
        result["reason_codes"] = ["resolved_issue"]
        return result

    score = 5
    reasons.append("active_issue")

    category_risk = CATEGORY_RISK.get(
        category,
        CATEGORY_RISK["other"],
    )
    level_risk = LEVEL_RISK.get(
        level,
        LEVEL_RISK["unknown"],
    )

    score += category_risk
    score += level_risk

    reasons.append(f"category_{category}")
    reasons.append(f"level_{level}")

    persistence_score, persistence_reason = _persistence_band(
        consecutive_runs
    )
    recurrence_score, recurrence_reason = _recurrence_band(
        runs_seen,
        fingerprint_count,
    )
    intensity_score, intensity_reason = _intensity_band(
        last_count,
        peak_count,
    )

    score += persistence_score
    score += recurrence_score
    score += intensity_score

    for reason in (
        persistence_reason,
        recurrence_reason,
        intensity_reason,
    ):
        if reason is not None:
            reasons.append(reason)

    technical_severity = _technical_severity(
        active=active,
        level=level,
        category=category,
    )

    # Calibration caps prevent low-information warnings from becoming
    # catastrophic merely because they repeat frequently.
    if level in {"warning", "warn"}:
        score = min(score, 54)

    if category == "other":
        if level in {"warning", "warn", "info", "debug", "unknown"}:
            score = min(score, 44)
        elif level == "error":
            score = min(score, 64)

    confidence = _confidence(
        active=active,
        consecutive_runs=consecutive_runs,
        runs_seen=runs_seen,
        fingerprint_count=fingerprint_count,
    )

    score = min(max(score, 0), 100)

    result["priority_score"] = score
    result["technical_severity"] = technical_severity
    result["operational_priority"] = _operational_priority(
        score,
        active,
    )

    # Compatibility field for existing Passport consumers.
    result["severity"] = technical_severity
    result["confidence"] = confidence
    result["reason_codes"] = reasons

    return result


def assess_issues(
    issues: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    assessed = [
        assess_issue(issue)
        for issue in issues.values()
        if isinstance(issue, dict)
    ]

    return sorted(
        assessed,
        key=lambda issue: (
            issue.get("active") is not True,
            -_safe_int(issue.get("priority_score")),
            issue.get("issue_key", ""),
        ),
    )


def prioritize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return assess_issue(issue)


def prioritize_issues(
    issues: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return assess_issues(issues)
