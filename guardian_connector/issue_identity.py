"""Stable diagnostic issue identity and history migration for Guardian."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

ISSUE_IDENTITY_SCHEMA_VERSION = 1


def _normalize_text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default

    text = str(value).strip().lower()

    return text or default


def _normalize_source(source: Any) -> list[Any]:
    if not isinstance(source, (list, tuple)) or not source:
        return ["unknown", None]

    path = _normalize_text(source[0])

    line = None
    if len(source) > 1:
        raw_line = source[1]
        if isinstance(raw_line, int) and raw_line >= 0:
            line = raw_line

    return [path, line]


def build_issue_identity(record: dict[str, Any]) -> dict[str, Any]:
    category = _normalize_text(record.get("category"), "other")
    level = _normalize_text(record.get("level"))
    source = _normalize_source(record.get("source"))
    exception_type = _normalize_text(record.get("exception_type"))

    identity = {
        "category": category,
        "level": level,
        "source": source,
        "exception_type": exception_type,
    }

    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    issue_key = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]

    return {
        "issue_key": issue_key,
        "identity": identity,
    }


def build_issue_key(record: dict[str, Any]) -> str:
    return build_issue_identity(record)["issue_key"]


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0

    if isinstance(value, int) and value >= 0:
        return value

    return 0


def _minimum_timestamp(left: Any, right: Any) -> Any:
    values = [
        value
        for value in (left, right)
        if isinstance(value, str) and value
    ]

    return min(values) if values else None


def _maximum_timestamp(left: Any, right: Any) -> Any:
    values = [
        value
        for value in (left, right)
        if isinstance(value, str) and value
    ]

    return max(values) if values else None


def _merge_records(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(existing)

    merged["first_seen"] = _minimum_timestamp(
        existing.get("first_seen"),
        incoming.get("first_seen"),
    )

    merged["last_seen"] = _maximum_timestamp(
        existing.get("last_seen"),
        incoming.get("last_seen"),
    )

    merged["runs_seen"] = (
        _safe_int(existing.get("runs_seen"))
        + _safe_int(incoming.get("runs_seen"))
    )

    merged["observations"] = (
        _safe_int(existing.get("observations"))
        + _safe_int(incoming.get("observations"))
    )

    merged["peak_count"] = max(
        _safe_int(existing.get("peak_count")),
        _safe_int(incoming.get("peak_count")),
    )

    existing_active = existing.get("active") is True
    incoming_active = incoming.get("active") is True

    merged["active"] = existing_active or incoming_active

    if merged["active"]:
        active_records = [
            record
            for record in (existing, incoming)
            if record.get("active") is True
        ]

        latest_active = max(
            active_records,
            key=lambda record: record.get("last_seen") or "",
        )

        merged["last_count"] = _safe_int(
            latest_active.get("last_count")
        )

        merged["consecutive_runs_seen"] = max(
            _safe_int(
                record.get("consecutive_runs_seen")
            )
            for record in active_records
        )

        merged["resolved_at"] = None

    else:
        latest_record = max(
            (existing, incoming),
            key=lambda record: record.get("last_seen") or "",
        )

        merged["last_count"] = _safe_int(
            latest_record.get("last_count")
        )
        merged["consecutive_runs_seen"] = 0
        merged["resolved_at"] = _maximum_timestamp(
            existing.get("resolved_at"),
            incoming.get("resolved_at"),
        )

    fingerprints = set()

    for record in (existing, incoming):
        fingerprint = record.get("fingerprint")

        if isinstance(fingerprint, str) and fingerprint:
            fingerprints.add(fingerprint)

        previous = record.get("fingerprints")

        if isinstance(previous, list):
            fingerprints.update(
                item
                for item in previous
                if isinstance(item, str) and item
            )

    merged["fingerprints"] = sorted(fingerprints)
    merged["fingerprint_count"] = len(fingerprints)
    merged.pop("fingerprint", None)

    return merged


def migrate_history_to_stable_issues(
    history: dict[str, Any],
) -> dict[str, Any]:
    migrated = deepcopy(history)

    raw_fingerprints = migrated.get("fingerprints", {})

    if not isinstance(raw_fingerprints, dict):
        raw_fingerprints = {}

    issues: dict[str, dict[str, Any]] = {}

    for fingerprint, raw_record in raw_fingerprints.items():
        if not isinstance(raw_record, dict):
            continue

        record = deepcopy(raw_record)

        if not isinstance(record.get("fingerprint"), str):
            record["fingerprint"] = fingerprint

        identity = build_issue_identity(record)
        issue_key = identity["issue_key"]

        record["issue_key"] = issue_key
        record["identity"] = identity["identity"]
        record["fingerprints"] = [record["fingerprint"]]
        record["fingerprint_count"] = 1

        if issue_key in issues:
            issues[issue_key] = _merge_records(
                issues[issue_key],
                record,
            )
        else:
            record.pop("fingerprint", None)
            issues[issue_key] = record

    migrated["issue_identity_schema_version"] = (
        ISSUE_IDENTITY_SCHEMA_VERSION
    )
    migrated["issues"] = dict(sorted(issues.items()))

    return migrated
