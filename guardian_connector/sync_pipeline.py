from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from connector.guardian_sync import SyncQueue, passport_hash, sanitize_passport


class SyncPipeline:
    def __init__(self, data_directory: str | Path):
        self.data_directory = Path(data_directory)
        self.data_directory.mkdir(parents=True, exist_ok=True)

        self.public_passport_path = self.data_directory / "public-passport.json"
        self.hash_path = self.data_directory / "last-passport.sha256"
        self.queue = SyncQueue(self.data_directory / "sync-queue")

    def process(self, passport: dict[str, Any]) -> dict[str, Any]:
        public_passport = sanitize_passport(passport)

        if passport.get("schema_version") in ("2.0.0", "2.1.0", "2.2.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.4.0", "3.5.0"):
            from connector.privacy_v2 import sanitize_passport_v2

            public_passport = sanitize_passport_v2(
                public_passport,
                "guardian-local-stable-v2",
            )

        digest = passport_hash(public_passport)

        previous_digest = None
        if self.hash_path.exists():
            previous_digest = self.hash_path.read_text(encoding="utf-8").strip()

        self.public_passport_path.write_text(
            json.dumps(public_passport, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        changed = digest != previous_digest

        if changed:
            self.queue.enqueue(public_passport)
            self.hash_path.write_text(digest + "\n", encoding="utf-8")

        return {
            "changed": changed,
            "hash": digest,
            "queue_size": len(self.queue.items()),
            "public_passport_path": str(self.public_passport_path),
        }
