from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


DIAGNOSTIC_KEYWORDS = {
    "battery": ("battery", "batteria"),
    "signal": ("signal", "rssi", "lqi", "linkquality"),
    "network": ("network", "wifi", "wi-fi", "ssid", "ip address", "bssid"),
    "firmware": ("firmware", "software", "version", "update"),
    "energy": ("energy", "power", "voltage", "current", "consumption"),
    "temperature": ("temperature", "temperatura"),
    "humidity": ("humidity", "umidita", "umidità"),
    "diagnostic": ("diagnostic", "diagnostica"),
}


def classify_entity(
    registry: dict[str, Any],
) -> str:
    device_class = registry.get("device_class")

    if isinstance(device_class, str) and device_class:
        return device_class

    text = " ".join(
        str(registry.get(field) or "").lower()
        for field in (
            "entity_id",
            "original_name",
            "translation_key",
        )
    )

    for category, keywords in DIAGNOSTIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category

    entity_category = registry.get("entity_category")

    if isinstance(entity_category, str) and entity_category:
        return entity_category

    return "other"


def build_entity_diagnostics(
    passport: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(passport)

    state_ids = {
        entity.get("entity_id")
        for entity in result.get("entities", [])
        if isinstance(entity, dict) and entity.get("entity_id")
    }

    registry_entities = [
        entity
        for entity in inventory.get("entity_registry", [])
        if isinstance(entity, dict) and entity.get("entity_id")
    ]

    diagnostic_entities = []

    for registry in registry_entities:
        if (
            registry["entity_id"] in state_ids
            and registry.get("disabled_by") is None
        ):
            continue

        diagnostic_entities.append({
            "entity_id": registry["entity_id"],
            "platform": registry.get("platform"),
            "config_entry_id": registry.get("config_entry_id"),
            "device_id": registry.get("device_id"),
            "area_id": registry.get("area_id"),
            "disabled_by": registry.get("disabled_by"),
            "device_class": registry.get("device_class"),
            "entity_category": registry.get("entity_category"),
            "diagnostic_category": classify_entity(registry),
            "has_entity_name": bool(registry.get("has_entity_name")),
        })

    by_platform = Counter(
        entity.get("platform") or "unknown"
        for entity in diagnostic_entities
    )

    by_disabled_by = Counter(
        entity.get("disabled_by") or "not_disabled"
        for entity in diagnostic_entities
    )

    by_device = Counter(
        entity.get("device_id") or "no_device"
        for entity in diagnostic_entities
    )

    by_category = Counter(
        entity["diagnostic_category"]
        for entity in diagnostic_entities
    )

    result["entity_diagnostics"] = {
        "summary": {
            "entities": len(diagnostic_entities),
            "by_platform": dict(sorted(by_platform.items())),
            "by_disabled_by": dict(sorted(by_disabled_by.items())),
            "by_device": dict(sorted(by_device.items())),
            "by_category": dict(sorted(by_category.items())),
        },
        "entities": diagnostic_entities,
    }

    result["schema_version"] = "2.2.0"
    return result
