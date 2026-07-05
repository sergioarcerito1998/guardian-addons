#!/usr/bin/env python3
"""Guardian Connector: read-only Home Assistant discovery client."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1.0"


class ConnectorError(RuntimeError):
    pass


def api_get(base_url: str, token: str, path: str, timeout: int = 15) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConnectorError(f"Home Assistant API returned HTTP {exc.code} for {path}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"Cannot reach Home Assistant: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Invalid JSON returned by Home Assistant for {path}") from exc


def build_passport(base_url: str, token: str) -> dict[str, Any]:
    api_status = api_get(base_url, token, "/api/")
    config = api_get(base_url, token, "/api/config")
    states = api_get(base_url, token, "/api/states")

    if not isinstance(states, list):
        raise ConnectorError("Unexpected Home Assistant states response")

    domains: dict[str, int] = {}
    unavailable = 0
    unknown = 0
    entities = []

    for state in states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".", 1)[0] if "." in entity_id else "unknown"
        domains[domain] = domains.get(domain, 0) + 1
        current_state = state.get("state")
        unavailable += current_state == "unavailable"
        unknown += current_state == "unknown"
        entities.append(
            {
                "entity_id": entity_id,
                "domain": domain,
                "state": current_state,
                "friendly_name": state.get("attributes", {}).get("friendly_name"),
                "device_class": state.get("attributes", {}).get("device_class"),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"type": "home_assistant", "url": base_url.rstrip("/")},
        "home_assistant": {
            "api_status": api_status.get("message") if isinstance(api_status, dict) else None,
            "version": config.get("version"),
            "location_name": config.get("location_name"),
            "time_zone": config.get("time_zone"),
            "unit_system": config.get("unit_system"),
        },
        "summary": {
            "entity_count": len(entities),
            "unavailable_count": unavailable,
            "unknown_count": unknown,
            "domains": dict(sorted(domains.items())),
        },
        "entities": entities,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a read-only Guardian House Passport")
    parser.add_argument("--url", default=os.getenv("HA_URL"), help="Home Assistant base URL (or HA_URL)")
    parser.add_argument("--token", default=os.getenv("HA_TOKEN"), help="Home Assistant long-lived access token (or HA_TOKEN)")
    parser.add_argument("--output", default="house-passport.json", help="Output JSON path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.url or not args.token:
        print("ERROR: provide Home Assistant URL and token via arguments or environment variables.", file=sys.stderr)
        return 2

    try:
        passport = build_passport(args.url, args.token)
        output = Path(args.output)
        output.write_text(json.dumps(passport, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        from connector.sync_pipeline import SyncPipeline

        sync_result = SyncPipeline(output.parent).process(passport)
    except (ConnectorError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Guardian House Passport created: {output}")
    print(f"Entities discovered: {passport['summary']['entity_count']}")
    print(f"Unavailable: {passport['summary']['unavailable_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
