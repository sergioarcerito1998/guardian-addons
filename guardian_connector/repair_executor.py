"""Conservative executor for Guardian autonomous actions."""

from __future__ import annotations

from typing import Any


def execute_action(plan: dict[str, Any]) -> dict[str, Any]:
    action = str(plan.get("action", ""))

    if plan.get("policy_decision") != "allow":
        return {
            "issue_key": plan.get("issue_key"),
            "action": action,
            "execution_status": "not_executed",
            "changed": False,
            "execution_reason": plan.get("policy_reason", "policy_denied"),
        }

    if action == "observe_issue":
        return {
            "issue_key": plan.get("issue_key"),
            "action": action,
            "execution_status": "completed",
            "changed": False,
            "execution_reason": "observation_recorded",
        }

    return {
        "issue_key": plan.get("issue_key"),
        "action": action,
        "execution_status": "not_executed",
        "changed": False,
        "execution_reason": "executor_not_implemented_for_action",
    }
