"""Post-action verification for Guardian autonomy."""

from __future__ import annotations

from typing import Any


def verify_execution(
    plan: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    status = execution.get("execution_status")
    changed = execution.get("changed") is True

    if status == "completed" and not changed:
        verification_status = "verified_no_change"
        success = True
    elif status == "completed":
        verification_status = "verification_required"
        success = False
    else:
        verification_status = "not_applicable"
        success = False

    return {
        "issue_key": plan.get("issue_key"),
        "action": plan.get("action"),
        "verification_status": verification_status,
        "success": success,
    }
