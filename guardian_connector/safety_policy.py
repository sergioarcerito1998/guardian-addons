"""Safety policy for Guardian autonomous repair plans."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from connector.action_registry import get_action_definition


SAFE_AUTONOMOUS_RISKS = {"none", "low"}


def evaluate_action(plan: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(plan)

    action = str(plan.get("action", ""))
    definition = get_action_definition(action)

    if definition is None:
        result["policy_decision"] = "deny"
        result["policy_reason"] = "unregistered_action"
        return result

    risk = str(definition.get("risk", "unknown"))
    mutating = definition.get("mutating") is True

    if mutating and risk not in SAFE_AUTONOMOUS_RISKS:
        result["policy_decision"] = "manual_required"
        result["policy_reason"] = "risk_not_autonomously_allowed"
        return result

    if action == "defer_to_manual":
        result["policy_decision"] = "manual_required"
        result["policy_reason"] = "explicit_manual_action"
        return result

    result["policy_decision"] = "allow"
    result["policy_reason"] = "registered_safe_action"
    return result
