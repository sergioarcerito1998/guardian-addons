from __future__ import annotations

import hashlib
import json
import random
import time
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


DROP_HOME_ASSISTANT_FIELDS = {"location_name"}
DROP_ENTITY_FIELDS = {"friendly_name"}
MAX_QUEUE_ITEMS = 24


def sanitize_passport(passport: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(passport)

    source = sanitized.get("source")
    if isinstance(source, dict):
        source.pop("url", None)

    home_assistant = sanitized.get("home_assistant")
    if isinstance(home_assistant, dict):
        for field in DROP_HOME_ASSISTANT_FIELDS:
            home_assistant.pop(field, None)

    entities = sanitized.get("entities")
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict):
                for field in DROP_ENTITY_FIELDS:
                    entity.pop(field, None)

    sanitized["schema_version"] = "public-passport-0.1.0"
    return sanitized


def canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def passport_hash(passport: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(passport)).hexdigest()


class SyncQueue:
    def __init__(self, directory: str | Path, max_items: int = MAX_QUEUE_ITEMS):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items

    def enqueue(self, passport: dict[str, Any]) -> Path:
        digest = passport_hash(passport)
        destination = self.directory / f"{time.time_ns()}-{digest}.json"
        destination.write_bytes(canonical_json(passport) + b"\n")
        self.prune()
        return destination

    def items(self) -> list[Path]:
        return sorted(self.directory.glob("*.json"))

    def prune(self) -> None:
        items = self.items()
        for item in items[:-self.max_items]:
            item.unlink(missing_ok=True)


def retry_with_backoff(
    operation: Callable[[], Any],
    attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    errors: deque[Exception] = deque(maxlen=1)

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            errors.append(exc)
            if attempt == attempts - 1:
                raise

            delay = min(max_delay, base_delay * (2**attempt))
            jitter = random.uniform(0, delay * 0.2)
            sleep(delay + jitter)

    raise errors[-1]
