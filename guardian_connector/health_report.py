"""Calibrated Guardian diagnostic health report builder."""

from __future__ import annotations

from typing import Any

from connector.issue_priority import assess_issues


HEALTH_IMPACT = {
    "urgent": 38,
    "high": 24,
    "medium": 12,
    "low": 4,
}


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0


def _recommendation(issue: dict[str, Any]) -> dict[str, Any]:
    category = str(issue.get("category", "other")).lower()

    actions = {
        "authentication": "verify_credentials_and_tokens",
        "network": "inspect_network_connectivity",
        "connection": "inspect_device_or_service_connection",
        "timeout": "inspect_latency_and_service_availability",
        "firmware": "check_firmware_and_integration_compatibility",
        "energy": "inspect_energy_sensor_configuration",
        "signal": "inspect_wireless_signal_quality",
        "config": "review_integration_configuration",
        "diagnostic": "review_diagnostic_entity_state",
        "other": "inspect_source_and_related_integration",
    }

    return {
        "issue_key": issue.get("issue_key"),
        "technical_severity": issue.get("technical_severity"),
        "operational_priority": issue.get("operational_priority"),
        "priority_score": _safe_int(issue.get("priority_score")),
        "confidence": issue.get("confidence"),
        "action": actions.get(category, actions["other"]),
        "reason_codes": list(issue.get("reason_codes", [])),
    }


def _overall_status(active: list[dict[str, Any]]) -> str:
    priorities = {
        issue.get("operational_priority")
        for issue in active
    }

    if "urgent" in priorities:
        return "critical"
    if "high" in priorities:
        return "degraded"
    if "medium" in priorities:
        return "attention"
    if active:
        return "good"
    return "healthy"


def _health_score(active: list[dict[str, Any]]) -> int:
    if not active:
        return 100

    impacts = [
        HEALTH_IMPACT.get(
            str(issue.get("operational_priority")),
            4,
        )
        for issue in active
    ]

    # Aggregate issue impact with diminishing returns. The highest priority
    # issue matters most; additional issues reduce health less aggressively.
    impacts.sort(reverse=True)

    total_impact = 0.0

    for index, impact in enumerate(impacts):
        total_impact += impact * (0.65 ** index)

    return max(0, round(100 - min(total_impact, 100)))


def build_health_report(
    stable_issue_history: dict[str, Any],
    *,
    previous_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = stable_issue_history.get("issues", {})

    if not isinstance(issues, dict):
        issues = {}

    ranked = assess_issues(issues)

    active = [
        issue
        for issue in ranked
        if issue.get("active") is True
    ]
    resolved = [
        issue
        for issue in ranked
        if issue.get("active") is False
    ]

    current_keys = {
        issue.get("issue_key")
        for issue in active
        if isinstance(issue.get("issue_key"), str)
    }

    previous_keys: set[str] = set()

    if isinstance(previous_report, dict):
        previous = previous_report.get("active_issue_keys", [])

        if isinstance(previous, list):
            previous_keys = {
                item
                for item in previous
                if isinstance(item, str)
            }

    new_keys = sorted(current_keys - previous_keys)
    cleared_keys = sorted(previous_keys - current_keys)

    return {
        "schema_version": 2,
        "status": _overall_status(active),
        "health_score": _health_score(active),
        "summary": {
            "issues": len(ranked),
            "active": len(active),
            "resolved": len(resolved),
            "urgent": sum(
                issue.get("operational_priority") == "urgent"
                for issue in active
            ),
            "high": sum(
                issue.get("operational_priority") == "high"
                for issue in active
            ),
            "medium": sum(
                issue.get("operational_priority") == "medium"
                for issue in active
            ),
            "low": sum(
                issue.get("operational_priority") == "low"
                for issue in active
            ),
            "new": len(new_keys),
            "cleared": len(cleared_keys),
        },
        "active_issue_keys": sorted(current_keys),
        "new_issue_keys": new_keys,
        "cleared_issue_keys": cleared_keys,
        "top_issues": active[:10],
        "resolved_issues": resolved[:10],
        "recommendations": [
            _recommendation(issue)
            for issue in active[:10]
        ],
    }
