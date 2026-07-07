"""Guardian Autonomy Core v1 runtime orchestration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from connector.operation_journal import (
    append_entries,
    load_operation_journal,
    persist_operation_journal,
)
from connector.repair_executor import execute_action
from connector.repair_planner import build_repair_plans
from connector.repair_verifier import verify_execution
from connector.safety_policy import evaluate_action


AUTONOMY_SCHEMA_VERSION = 1


def run_autonomy_cycle(
    health_report: dict[str, Any],
    journal_path: str | Path,
) -> dict[str, Any]:
    top_issues = health_report.get("top_issues", [])

    if not isinstance(top_issues, list):
        top_issues = []

    raw_plans = build_repair_plans(top_issues)

    plans = []
    operations = []

    for raw_plan in raw_plans:
        plan = evaluate_action(raw_plan)
        execution = execute_action(plan)
        verification = verify_execution(plan, execution)

        plans.append(plan)

        operations.append({
            "issue_key": plan.get("issue_key"),
            "action": plan.get("action"),
            "mode": plan.get("mode"),
            "policy_decision": plan.get("policy_decision"),
            "execution_status": execution.get("execution_status"),
            "execution_reason": execution.get("execution_reason"),
            "changed": execution.get("changed") is True,
            "verification_status": verification.get(
                "verification_status"
            ),
            "verified": verification.get("success") is True,
        })

    journal = load_operation_journal(journal_path)
    journal = append_entries(journal, operations)
    persist_operation_journal(journal_path, journal)

    summary = {
        "plans": len(plans),
        "allowed": sum(
            plan.get("policy_decision") == "allow"
            for plan in plans
        ),
        "manual_required": sum(
            plan.get("policy_decision") == "manual_required"
            for plan in plans
        ),
        "denied": sum(
            plan.get("policy_decision") == "deny"
            for plan in plans
        ),
        "executed": sum(
            operation.get("execution_status") == "completed"
            for operation in operations
        ),
        "changed": sum(
            operation.get("changed") is True
            for operation in operations
        ),
        "verified": sum(
            operation.get("verified") is True
            for operation in operations
        ),
    }

    return {
        "schema_version": AUTONOMY_SCHEMA_VERSION,
        "summary": summary,
        "plans": deepcopy(plans),
        "operations": operations,
        "journal_runs": journal["runs"],
        "journal_entries": len(journal["entries"]),
    }
