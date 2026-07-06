"""Persistent diagnostic fingerprint history for Guardian."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def empty_diagnostic_history() -> dict[str, Any]:
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "runs": 0,
        "fingerprints": {},
    }


def load_diagnostic_history(path: str | Path) -> dict[str, Any]:
    history_path = Path(path)

    if not history_path.exists():
        return empty_diagnostic_history()

    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty_diagnostic_history()

    if not isinstance(payload, dict):
        return empty_diagnostic_history()

    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        return empty_diagnostic_history()

    if not isinstance(payload.get("runs"), int):
        return empty_diagnostic_history()

    if not isinstance(payload.get("fingerprints"), dict):
        return empty_diagnostic_history()

    return payload


def update_diagnostic_history(
    history: dict[str, Any],
    current_entries: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
) -> dict[str, Any]:
    now = observed_at or _utc_now()
    updated = deepcopy(history)

    if updated.get("schema_version") != HISTORY_SCHEMA_VERSION:
        updated = empty_diagnostic_history()

    fingerprints = updated.setdefault("fingerprints", {})
    updated["runs"] = int(updated.get("runs", 0)) + 1

    current_by_fingerprint: dict[str, dict[str, Any]] = {}

    for entry in current_entries:
        fingerprint = entry.get("fingerprint")

        if not isinstance(fingerprint, str) or not fingerprint:
            continue

        current_by_fingerprint[fingerprint] = entry

    for fingerprint, record in fingerprints.items():
        if not isinstance(record, dict):
            continue

        if fingerprint not in current_by_fingerprint:
            if record.get("active") is True:
                record["active"] = False
                record["resolved_at"] = now

            record["consecutive_runs_seen"] = 0

    for fingerprint, entry in current_by_fingerprint.items():
        count = entry.get("count", 0)

        if not isinstance(count, int) or count < 0:
            count = 0

        existing = fingerprints.get(fingerprint)

        if not isinstance(existing, dict):
            fingerprints[fingerprint] = {
                "fingerprint": fingerprint,
                "category": entry.get("category", "other"),
                "level": entry.get("level"),
                "source": entry.get("source"),
                "exception_type": entry.get("exception_type"),
                "first_seen": now,
                "last_seen": now,
                "resolved_at": None,
                "active": True,
                "runs_seen": 1,
                "consecutive_runs_seen": 1,
                "observations": 1,
                "last_count": count,
                "peak_count": count,
            }
            continue

        was_active = existing.get("active") is True
        previous_consecutive_runs = int(
            existing.get("consecutive_runs_seen", 0)
        )

        existing["category"] = entry.get(
            "category",
            existing.get("category", "other"),
        )
        existing["level"] = entry.get("level", existing.get("level"))
        existing["source"] = entry.get("source", existing.get("source"))
        existing["exception_type"] = entry.get(
            "exception_type",
            existing.get("exception_type"),
        )
        existing["last_seen"] = now
        existing["resolved_at"] = None
        existing["active"] = True
        existing["runs_seen"] = int(existing.get("runs_seen", 0)) + 1

        if was_active:
            existing["consecutive_runs_seen"] = (
                previous_consecutive_runs + 1
            )
        else:
            existing["consecutive_runs_seen"] = 1

        existing["observations"] = int(existing.get("observations", 0)) + 1
        existing["last_count"] = count
        existing["peak_count"] = max(
            int(existing.get("peak_count", 0)),
            count,
        )

    return updated


def build_diagnostic_history_summary(
    history: dict[str, Any],
) -> dict[str, Any]:
    fingerprints = history.get("fingerprints", {})

    if not isinstance(fingerprints, dict):
        fingerprints = {}

    records = [
        record
        for record in fingerprints.values()
        if isinstance(record, dict)
    ]

    active = sum(record.get("active") is True for record in records)
    resolved = sum(record.get("active") is False for record in records)

    by_category: dict[str, int] = {}

    for record in records:
        category = record.get("category", "other")
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "runs": int(history.get("runs", 0)),
        "fingerprints": len(records),
        "active": active,
        "resolved": resolved,
        "by_category": dict(sorted(by_category.items())),
    }


def persist_diagnostic_history(
    path: str | Path,
    current_entries: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    history_path = Path(path)
    history = load_diagnostic_history(history_path)

    updated = update_diagnostic_history(
        history,
        current_entries,
        observed_at=observed_at,
    )

    _atomic_write_json(history_path, updated)

    return updated, build_diagnostic_history_summary(updated)
