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


def _sanitize_entity_id(entity_id: str, salt: str) -> str:
    sensitive = (
        entity_id.startswith(SENSITIVE_ENTITY_PREFIXES)
        or any(
            fragment in entity_id
            for fragment in SENSITIVE_ENTITY_FRAGMENTS
        )
    )

    if not sensitive:
        return entity_id

    domain = entity_id.split(".", 1)[0]
    return f"{domain}.{pseudonymize(entity_id, salt)}"


def _sanitize_identifier(value: Any, salt: str) -> Any:
    if isinstance(value, str) and value:
        return pseudonymize(value, salt)

    if isinstance(value, list):
        return [
            pseudonymize(item, salt)
            if isinstance(item, str) and item
            else item
            for item in value
        ]

    return value


def sanitize_passport_v2(
    passport: dict[str, Any],
    salt: str,
) -> dict[str, Any]:
    sanitized = deepcopy(passport)
    pseudonymized_entities = 0

    entity_sections = [
        sanitized.get("entities", []),
        sanitized.get("diagnostic_inventory", {}).get(
            "registry_only_entities", []
        ),
        sanitized.get("diagnostic_inventory", {}).get(
            "disabled_entities", []
        ),
        sanitized.get("entity_diagnostics", {}).get(
            "entities", []
        ),
    ]

    for section in entity_sections:
        for entity in section:
            if not isinstance(entity, dict):
                continue

            entity_id = entity.get("entity_id")
            if isinstance(entity_id, str):
                replacement = _sanitize_entity_id(entity_id, salt)

                if replacement != entity_id:
                    pseudonymized_entities += 1

                entity["entity_id"] = replacement

            for field in (
                "config_entry_id",
                "device_id",
                "area_id",
            ):
                entity[field] = _sanitize_identifier(
                    entity.get(field),
                    salt,
                )

    inventory = sanitized.get("inventory", {})

    for device in inventory.get("devices", []):
        if not isinstance(device, dict):
            continue

        for field in ("id", "area_id", "config_entries"):
            device[field] = _sanitize_identifier(
                device.get(field),
                salt,
            )

        for field in ("name", "name_by_user", "serial_number"):
            device.pop(field, None)

    for area in inventory.get("areas", []):
        if not isinstance(area, dict):
            continue

        area["area_id"] = _sanitize_identifier(
            area.get("area_id"),
            salt,
        )
        area.pop("name", None)

    diagnostic = sanitized.get("diagnostic_inventory", {})

    entity_diagnostics = sanitized.get("entity_diagnostics", {})
    summary = entity_diagnostics.get("summary", {})

    by_device = summary.get("by_device", {})
    sanitized_by_device = {}

    for device_id, count in by_device.items():
        if device_id == "no_device":
            sanitized_by_device[device_id] = count
        else:
            sanitized_by_device[
                pseudonymize(device_id, salt)
            ] = count

    summary["by_device"] = sanitized_by_device

    for device in diagnostic.get("devices", []):
        if not isinstance(device, dict):
            continue

        for field in ("id", "area_id", "config_entries"):
            device[field] = _sanitize_identifier(
                device.get(field),
                salt,
            )

    for area in diagnostic.get("areas", []):
        if not isinstance(area, dict):
            continue

        area["area_id"] = _sanitize_identifier(
            area.get("area_id"),
            salt,
        )

    sanitized["privacy"] = {
        "version": "2.2.0",
        "pseudonymized_entity_count": pseudonymized_entities,
    }

    return sanitized

# Guardian v3.4 health_report is derived exclusively from already-sanitized
# stable diagnostic issue metadata and contains no raw log messages.

# Guardian v3.6 health_timeline contains bounded derived diagnostic metadata
# only; raw log messages are never persisted in timeline snapshots.
