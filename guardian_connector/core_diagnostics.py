from __future__ import annotations

import json
from typing import Any, Callable

from connector.inventory_v2 import _websocket_url


REPAIRS_COMMANDS = (
    {"type": "repairs/list_issues"},
    {"type": "repairs/issues"},
)

SYSTEM_LOG_COMMANDS = (
    {"type": "system_log/list"},
    {"type": "system_log/list_issues"},
)

MAX_SYSTEM_LOG_ENTRIES = 100


def _send_command(
    ws: Any,
    command_id: int,
    command: dict[str, Any],
) -> dict[str, Any]:
    payload = {"id": command_id, **command}
    ws.send(json.dumps(payload))

    while True:
        response = json.loads(ws.recv())

        if response.get("id") != command_id:
            continue

        if response.get("type") != "result":
            continue

        return response


def _try_commands(
    ws: Any,
    commands: tuple[dict[str, Any], ...],
    start_id: int,
) -> tuple[Any, int, str | None]:
    command_id = start_id
    last_error = None

    for command in commands:
        response = _send_command(ws, command_id, command)
        command_id += 1

        if response.get("success"):
            return response.get("result"), command_id, command["type"]

        error = response.get("error") or {}
        last_error = str(
            error.get("message")
            or error.get("code")
            or "unknown error"
        )

    return None, command_id, last_error


def _normalize_repairs(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        issues = result.get("issues", [])
    elif isinstance(result, list):
        issues = result
    else:
        return []

    normalized = []

    for issue in issues:
        if not isinstance(issue, dict):
            continue

        normalized.append({
            "domain": issue.get("domain"),
            "issue_id": issue.get("issue_id"),
            "severity": issue.get("severity"),
            "is_fixable": issue.get("is_fixable"),
            "is_persistent": issue.get("is_persistent"),
            "breaks_in_ha_version": issue.get(
                "breaks_in_ha_version"
            ),
        })

    return normalized


def _normalize_system_log(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        entries = (
            result.get("entries")
            or result.get("logs")
            or []
        )
    elif isinstance(result, list):
        entries = result
    else:
        return []

    normalized = []

    for entry in entries[:MAX_SYSTEM_LOG_ENTRIES]:
        if not isinstance(entry, dict):
            continue

        normalized.append({
            "level": entry.get("level"),
            "source": entry.get("source"),
            "count": entry.get("count"),
            "first_occurred": entry.get("first_occurred"),
            "last_occurred": entry.get("last_occurred"),
        })

    return normalized


def fetch_core_diagnostics(
    base_url: str,
    token: str,
    *,
    connection_factory: Callable[..., Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    if connection_factory is None:
        import websocket

        connection_factory = websocket.create_connection

    ws = connection_factory(
        _websocket_url(base_url),
        timeout=timeout,
    )

    try:
        auth_required = json.loads(ws.recv())

        if auth_required.get("type") != "auth_required":
            raise RuntimeError(
                "unexpected Home Assistant WebSocket greeting"
            )

        ws.send(json.dumps({
            "type": "auth",
            "access_token": token,
        }))

        auth_result = json.loads(ws.recv())

        if auth_result.get("type") != "auth_ok":
            raise RuntimeError(
                auth_result.get("message")
                or "Home Assistant WebSocket authentication failed"
            )

        repairs_result, next_id, repairs_source = _try_commands(
            ws,
            REPAIRS_COMMANDS,
            1,
        )

        system_log_result, _, system_log_source = _try_commands(
            ws,
            SYSTEM_LOG_COMMANDS,
            next_id,
        )

        repairs = _normalize_repairs(repairs_result)
        system_log = _normalize_system_log(system_log_result)

        raw_system_log = []

        if isinstance(system_log_result, dict):
            raw_system_log = (
                system_log_result.get("entries")
                or system_log_result.get("logs")
                or []
            )
        elif isinstance(system_log_result, list):
            raw_system_log = system_log_result

        raw_system_log = [
            entry
            for entry in raw_system_log[:MAX_SYSTEM_LOG_ENTRIES]
            if isinstance(entry, dict)
        ]

        return {
            "summary": {
                "repairs": len(repairs),
                "system_log_entries": len(system_log),
                "repairs_available": repairs_result is not None,
                "system_log_available": system_log_result is not None,
            },
            "sources": {
                "repairs": repairs_source,
                "system_log": system_log_source,
            },
            "repairs": repairs,
            "system_log": system_log,
            "_raw_system_log": raw_system_log,
        }
    finally:
        ws.close()


def attach_core_diagnostics(
    passport: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    result = dict(passport)
    result["core_diagnostics"] = diagnostics
    result["schema_version"] = "3.0.0"
    return result
