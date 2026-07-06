"""Persistent bounded health timeline for Guardian diagnostics."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HEALTH_STATE_SCHEMA_VERSION = 1
DEFAULT_TIMELINE_LIMIT = 90


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_name, path)

    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def empty_health_state() -> dict[str, Any]:
    return {
        "schema_version": HEALTH_STATE_SCHEMA_VERSION,
        "runs": 0,
        "previous_report": None,
        "timeline": [],
    }


def load_health_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)

    if not state_path.exists():
        return empty_health_state()

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty_health_state()

    if not isinstance(payload, dict):
        return empty_health_state()

    if payload.get("schema_version") != HEALTH_STATE_SCHEMA_VERSION:
        return empty_health_state()

    if not isinstance(payload.get("runs"), int):
        return empty_health_state()

    if not isinstance(payload.get("timeline"), list):
        return empty_health_state()

    previous_report = payload.get("previous_report")

    if previous_report is not None and not isinstance(
        previous_report,
        dict,
    ):
        return empty_health_state()

    return payload


def _active_priorities(report: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}

    top_issues = report.get("top_issues", [])

    if not isinstance(top_issues, list):
        return result

    for issue in top_issues:
        if not isinstance(issue, dict):
            continue

        issue_key = issue.get("issue_key")
        priority = issue.get("operational_priority")

        if isinstance(issue_key, str) and isinstance(priority, str):
            result[issue_key] = priority

    return result


def _priority_changes(
    previous_report: dict[str, Any] | None,
    current_report: dict[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(previous_report, dict):
        return []

    previous = _active_priorities(previous_report)
    current = _active_priorities(current_report)

    changes: list[dict[str, str]] = []

    for issue_key in sorted(previous.keys() & current.keys()):
        old_priority = previous[issue_key]
        new_priority = current[issue_key]

        if old_priority != new_priority:
            changes.append({
                "issue_key": issue_key,
                "from": old_priority,
                "to": new_priority,
            })

    return changes


def _trend(
    score_delta: int | None,
    new_count: int,
    cleared_count: int,
    priority_changes: list[dict[str, str]],
) -> str:
    if score_delta is None:
        return "baseline"

    priority_rank = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "urgent": 4,
    }

    worsened = any(
        priority_rank.get(change["to"], 0)
        > priority_rank.get(change["from"], 0)
        for change in priority_changes
    )

    improved = any(
        priority_rank.get(change["to"], 0)
        < priority_rank.get(change["from"], 0)
        for change in priority_changes
    )

    if score_delta <= -3 or new_count > 0 or worsened:
        return "degrading"

    if score_delta >= 3 or cleared_count > 0 or improved:
        return "improving"

    return "stable"


def enrich_health_report(
    current_report: dict[str, Any],
    previous_report: dict[str, Any] | None,
) -> dict[str, Any]:
    report = deepcopy(current_report)

    current_score = _safe_int(report.get("health_score"))

    previous_score: int | None = None

    if isinstance(previous_report, dict):
        value = previous_report.get("health_score")

        if isinstance(value, int) and not isinstance(value, bool):
            previous_score = value

    score_delta = (
        None
        if previous_score is None
        else current_score - previous_score
    )

    changes = _priority_changes(previous_report, report)

    new_keys = report.get("new_issue_keys", [])
    cleared_keys = report.get("cleared_issue_keys", [])

    if not isinstance(new_keys, list):
        new_keys = []

    if not isinstance(cleared_keys, list):
        cleared_keys = []

    report["health_score_delta"] = score_delta
    report["priority_changes"] = changes
    report["trend"] = _trend(
        score_delta,
        len(new_keys),
        len(cleared_keys),
        changes,
    )

    return report


def build_timeline_snapshot(
    report: dict[str, Any],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    summary = report.get("summary", {})

    if not isinstance(summary, dict):
        summary = {}

    return {
        "observed_at": observed_at or _utc_now(),
        "status": report.get("status"),
        "health_score": _safe_int(report.get("health_score")),
        "health_score_delta": report.get("health_score_delta"),
        "trend": report.get("trend"),
        "active": _safe_int(summary.get("active")),
        "resolved": _safe_int(summary.get("resolved")),
        "urgent": _safe_int(summary.get("urgent")),
        "high": _safe_int(summary.get("high")),
        "medium": _safe_int(summary.get("medium")),
        "low": _safe_int(summary.get("low")),
        "new_issue_keys": list(report.get("new_issue_keys", [])),
        "cleared_issue_keys": list(
            report.get("cleared_issue_keys", [])
        ),
        "priority_changes": deepcopy(
            report.get("priority_changes", [])
        ),
    }


def persist_health_state(
    path: str | Path,
    current_report: dict[str, Any],
    *,
    observed_at: str | None = None,
    timeline_limit: int = DEFAULT_TIMELINE_LIMIT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if timeline_limit < 1:
        raise ValueError("timeline_limit must be at least 1")

    state_path = Path(path)
    state = load_health_state(state_path)

    previous_report = state.get("previous_report")

    enriched_report = enrich_health_report(
        current_report,
        previous_report
        if isinstance(previous_report, dict)
        else None,
    )

    timeline = state.get("timeline", [])

    if not isinstance(timeline, list):
        timeline = []

    timeline = list(timeline)
    timeline.append(
        build_timeline_snapshot(
            enriched_report,
            observed_at=observed_at,
        )
    )
    timeline = timeline[-timeline_limit:]

    updated_state = {
        "schema_version": HEALTH_STATE_SCHEMA_VERSION,
        "runs": _safe_int(state.get("runs")) + 1,
        "previous_report": deepcopy(enriched_report),
        "timeline": timeline,
    }

    _atomic_write_json(state_path, updated_state)

    return updated_state, enriched_report
