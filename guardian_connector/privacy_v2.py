from __future__ import annotations

from copy import deepcopy
from typing import Any

from connector.inventory_v2 import pseudonymize


SENSITIVE_ENTITY_PREFIXES = (
    "person.",
    "device_tracker.",
)

SENSITIVE_ENTITY_FRAGMENTS = (
    "iphone_di_",
    "watch_",
)


def sanitize_passport_v2(
    passport: dict[str, Any],
    salt: str,
) -> dict[str, Any]:
    sanitized = deepcopy(passport)

    entity_id_map: dict[str, str] = {}

    for entity in sanitized.get("entities", []):
        entity_id = entity.get("entity_id")

        if not isinstance(entity_id, str):
            continue

        sensitive = (
            entity_id.startswith(SENSITIVE_ENTITY_PREFIXES)
            or any(
                fragment in entity_id
                for fragment in SENSITIVE_ENTITY_FRAGMENTS
            )
        )

        if sensitive:
            domain = entity_id.split(".", 1)[0]
            replacement = f"{domain}.{pseudonymize(entity_id, salt)}"
            entity_id_map[entity_id] = replacement
            entity["entity_id"] = replacement

        for field in (
            "config_entry_id",
            "device_id",
            "area_id",
        ):
            value = entity.get(field)
            if isinstance(value, str) and value:
                entity[field] = pseudonymize(value, salt)

    inventory = sanitized.get("inventory", {})

    devices = inventory.get("devices", [])
    for device in devices:
        if not isinstance(device, dict):
            continue

        for field in ("id", "area_id", "config_entries"):
            value = device.get(field)

            if isinstance(value, str) and value:
                device[field] = pseudonymize(value, salt)
            elif isinstance(value, list):
                device[field] = [
                    pseudonymize(item, salt)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]

        for field in ("name", "name_by_user", "serial_number"):
            device.pop(field, None)

    areas = inventory.get("areas", [])
    for area in areas:
        if not isinstance(area, dict):
            continue

        if isinstance(area.get("area_id"), str):
            area["area_id"] = pseudonymize(area["area_id"], salt)

        area.pop("name", None)

    sanitized["privacy"] = {
        "version": "2.0.0",
        "pseudonymized_entity_count": len(entity_id_map),
    }

    return sanitized
