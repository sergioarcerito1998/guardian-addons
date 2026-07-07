"""Persistent bounded operation journal for Guardian autonomy."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


OPERATION_JOURNAL_SCHEMA_VERSION = 1
DEFAULT_JOURNAL_LIMIT = 500


def empty_operation_journal() -> dict[str, Any]:
    return {
        "schema_version": OPERATION_JOURNAL_SCHEMA_VERSION,
        "runs": 0,
        "entries": [],
    }


def load_operation_journal(path: str | Path) -> dict[str, Any]:
    journal_path = Path(path)

    if not journal_path.exists():
        return empty_operation_journal()

    try:
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return empty_operation_journal()

    if not isinstance(payload, dict):
        return empty_operation_journal()

    if payload.get("schema_version") != OPERATION_JOURNAL_SCHEMA_VERSION:
        return empty_operation_journal()

    if not isinstance(payload.get("runs"), int):
        return empty_operation_journal()

    if not isinstance(payload.get("entries"), list):
        return empty_operation_journal()

    return payload


def persist_operation_journal(
    path: str | Path,
    journal: dict[str, Any],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                journal,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_name, destination)

    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def append_entries(
    journal: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    limit: int = DEFAULT_JOURNAL_LIMIT,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    updated = deepcopy(journal)
    existing = updated.get("entries", [])

    if not isinstance(existing, list):
        existing = []

    updated["runs"] = int(updated.get("runs", 0)) + 1
    updated["entries"] = (list(existing) + deepcopy(entries))[-limit:]
    return updated
