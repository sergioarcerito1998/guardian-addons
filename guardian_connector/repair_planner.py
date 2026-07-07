"""Deterministic repair planner for Guardian stable issues."""

from __future__ import annotations

from typing import Any


AUTONOMOUS_MIN_CONFIDENCE = 0.80


def plan_issue(issue: dict[str, Any]) -> dict[str, Any]:
    issue_key = issue.get("issue_key")
    active = issue.get("active") is True
    priority = str(issue.get("operational_priority", "low"))
    confidence = issue.get("confidence", 0.0)

    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    if not active:
        action = "observe_issue"
        mode = "observe_only"
        reason = "issue_not_active"

    elif priority in {"urgent", "high"} and confidence < AUTONOMOUS_MIN_CONFIDENCE:
        action = "defer_to_manual"
        mode = "manual_required"
        reason = "insufficient_confidence_for_high_priority_issue"

    else:
        action = "observe_issue"
        mode = "observe_only"
        reason = "no_safe_registered_repair"

    return {
        "issue_key": issue_key,
        "action": action,
        "mode": mode,
        "planner_reason": reason,
        "operational_priority": priority,
        "confidence": round(float(confidence), 2),
    }


def build_repair_plans(
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        plan_issue(issue)
        for issue in issues
        if isinstance(issue, dict)
    ]
