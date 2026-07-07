"""Deterministic registry of Guardian autonomous actions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ACTION_REGISTRY: dict[str, dict[str, Any]] = {
    "observe_issue": {
        "risk": "none",
        "mutating": False,
        "requires_verification": False,
        "cooldown_runs": 0,
        "max_attempts": 0,
    },
    "defer_to_manual": {
        "risk": "manual",
        "mutating": False,
        "requires_verification": False,
        "cooldown_runs": 0,
        "max_attempts": 0,
    },
}


def get_action_definition(action: str) -> dict[str, Any] | None:
    definition = ACTION_REGISTRY.get(action)

    if definition is None:
        return None

    return deepcopy(definition)


def is_registered_action(action: str) -> bool:
    return action in ACTION_REGISTRY
