from __future__ import annotations

import hashlib
import json
import urllib.parse
from typing import Any

try:
    import websocket
except ImportError:
    websocket = None


class HomeAssistantWebSocketError(RuntimeError):
    pass


def _websocket_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    base_path = parsed.path.rstrip("/")
    websocket_path = f"{base_path}/api/websocket"

    return urllib.parse.urlunparse(
        (scheme, parsed.netloc, websocket_path, "", "", "")
    )


def websocket_command(
    base_url: str,
    token: str,
    command_type: str,
    timeout: int = 30,
) -> Any:
    if websocket is None:
        raise HomeAssistantWebSocketError(
            "websocket-client dependency is not installed"
        )

    ws = websocket.create_connection(
        _websocket_url(base_url),
        timeout=timeout,
    )

    try:
        hello = json.loads(ws.recv())
        if hello.get("type") != "auth_required":
            raise HomeAssistantWebSocketError(
                f"Unexpected WebSocket hello: {hello.get('type')}"
            )

        ws.send(json.dumps({
            "type": "auth",
            "access_token": token,
        }))

        auth = json.loads(ws.recv())
        if auth.get("type") != "auth_ok":
            raise HomeAssistantWebSocketError(
                f"Home Assistant WebSocket authentication failed: "
                f"{auth.get('type')}"
            )

        ws.send(json.dumps({
            "id": 1,
            "type": command_type,
        }))

        response = json.loads(ws.recv())

        if (
            response.get("type") != "result"
            or response.get("id") != 1
            or response.get("success") is not True
        ):
            raise HomeAssistantWebSocketError(
                f"Home Assistant WebSocket command failed: {command_type}"
            )

        return response.get("result")
    finally:
        ws.close()


def fetch_inventory(base_url: str, token: str) -> dict[str, Any]:
    entity_registry = websocket_command(
        base_url, token, "config/entity_registry/list"
    )
    device_registry = websocket_command(
        base_url, token, "config/device_registry/list"
    )
    area_registry = websocket_command(
        base_url, token, "config/area_registry/list"
    )

    if not isinstance(entity_registry, list):
        raise HomeAssistantWebSocketError(
            "Unexpected entity registry response"
        )
    if not isinstance(device_registry, list):
        raise HomeAssistantWebSocketError(
            "Unexpected device registry response"
        )
    if not isinstance(area_registry, list):
        raise HomeAssistantWebSocketError(
            "Unexpected area registry response"
        )

    return {
        "entity_registry": entity_registry,
        "device_registry": device_registry,
        "area_registry": area_registry,
    }


def enrich_passport(
    passport: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    registry_by_entity = {
        item.get("entity_id"): item
        for item in inventory["entity_registry"]
        if isinstance(item, dict) and item.get("entity_id")
    }

    for entity in passport.get("entities", []):
        registry = registry_by_entity.get(entity.get("entity_id"), {})
        entity["platform"] = registry.get("platform")
        entity["config_entry_id"] = registry.get("config_entry_id")
        entity["device_id"] = registry.get("device_id")
        entity["area_id"] = registry.get("area_id")
        entity["disabled_by"] = registry.get("disabled_by")

    passport["inventory"] = {
        "devices": inventory["device_registry"],
        "areas": inventory["area_registry"],
    }
    passport["schema_version"] = "2.0.0"
    return passport


def pseudonymize(value: str, salt: str) -> str:
    digest = hashlib.sha256(
        f"{salt}:{value}".encode("utf-8")
    ).hexdigest()[:16]
    return f"anon_{digest}"
