from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_diagnostic_inventory(
    passport: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(passport)

    state_entities = {
        entity.get("entity_id"): entity
        for entity in result.get("entities", [])
        if isinstance(entity, dict) and entity.get("entity_id")
    }

    registry_entities = [
        entity
        for entity in inventory.get("entity_registry", [])
        if isinstance(entity, dict) and entity.get("entity_id")
    ]

    registry_only = []
    disabled = []

    for registry in registry_entities:
        entity_id = registry["entity_id"]

        item = {
            "entity_id": entity_id,
            "platform": registry.get("platform"),
            "config_entry_id": registry.get("config_entry_id"),
            "device_id": registry.get("device_id"),
            "area_id": registry.get("area_id"),
            "disabled_by": registry.get("disabled_by"),
        }

        if registry.get("disabled_by") is not None:
            disabled.append(item)

        if entity_id not in state_entities:
            registry_only.append(item)

    unavailable = [
        entity
        for entity in result.get("entities", [])
        if entity.get("state") == "unavailable"
    ]

    unknown = [
        entity
        for entity in result.get("entities", [])
        if entity.get("state") == "unknown"
    ]

    devices = []

    for index, device in enumerate(
        inventory.get("device_registry", []),
        start=1,
    ):
        if not isinstance(device, dict):
            continue

        devices.append({
            "id": device.get("id"),
            "label": f"device_{index:02d}",
            "area_id": device.get("area_id"),
            "config_entries": device.get("config_entries", []),
            "manufacturer": device.get("manufacturer"),
            "model": device.get("model"),
            "model_id": device.get("model_id"),
            "sw_version": device.get("sw_version"),
            "hw_version": device.get("hw_version"),
        })

    areas = []

    for index, area in enumerate(
        inventory.get("area_registry", []),
        start=1,
    ):
        if not isinstance(area, dict):
            continue

        areas.append({
            "area_id": area.get("area_id"),
            "alias": f"area_{index:02d}",
        })

    result["diagnostic_inventory"] = {
        "summary": {
            "state_entities": len(state_entities),
            "registry_entities": len(registry_entities),
            "registry_only": len(registry_only),
            "disabled": len(disabled),
            "unavailable": len(unavailable),
            "unknown": len(unknown),
            "devices": len(devices),
            "areas": len(areas),
        },
        "registry_only_entities": registry_only,
        "disabled_entities": disabled,
        "devices": devices,
        "areas": areas,
    }

    result["schema_version"] = "2.1.0"
    return result
