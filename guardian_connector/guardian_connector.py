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

        try:
            from connector.inventory_v2 import enrich_passport, fetch_inventory

            inventory = fetch_inventory(args.url, args.token)
            passport = enrich_passport(passport, inventory)

            from connector.diagnostic_inventory import (
                build_diagnostic_inventory,
            )

            passport = build_diagnostic_inventory(
                passport,
                inventory,
            )

            from connector.entity_diagnostics import (
                build_entity_diagnostics,
            )

            passport = build_entity_diagnostics(
                passport,
                inventory,
            )

            entity_diagnostic_summary = passport[
                "entity_diagnostics"
            ]["summary"]

            print(
                f"Guardian Entity Diagnostics: "
                f"{entity_diagnostic_summary['entities']}"
            )
            print(
                f"Guardian Entity Diagnostic categories: "
                f"{entity_diagnostic_summary['by_category']}"
            )

            try:
                from connector.core_diagnostics import (
                    attach_core_diagnostics,
                    fetch_core_diagnostics,
                )

                core_diagnostics = fetch_core_diagnostics(
                    args.url,
                    args.token,
                )

                raw_system_log = core_diagnostics.pop(
                    "_raw_system_log",
                    [],
                )

                passport = attach_core_diagnostics(
                    passport,
                    core_diagnostics,
                )

                from connector.error_fingerprints import (
                    enrich_core_diagnostics,
                )

                passport = enrich_core_diagnostics(
                    passport,
                    raw_system_log,
                )

                from connector.diagnostic_history import (
                    persist_diagnostic_history,
                )

                current_fingerprints = passport[
                    "core_diagnostics"
                ]["error_fingerprints"]["entries"]

                diagnostic_history, history_summary = (
                    persist_diagnostic_history(
                        "/data/diagnostic-history.json",
                        current_fingerprints,
                    )
                )

                from connector.issue_identity import (
                    migrate_history_to_stable_issues,
                )

                stable_issue_history = (
                    migrate_history_to_stable_issues(
                        diagnostic_history
                    )
                )

                stable_issues = stable_issue_history["issues"]

                active_issues = sum(
                    issue.get("active") is True
                    for issue in stable_issues.values()
                )
                resolved_issues = sum(
                    issue.get("active") is False
                    for issue in stable_issues.values()
                )

                passport[
                    "core_diagnostics"
                ]["diagnostic_history"] = {
                    "summary": history_summary,
                    "entries": sorted(
                        diagnostic_history[
                            "fingerprints"
                        ].values(),
                        key=lambda item: (
                            item.get("active") is not True,
                            item.get("category", "other"),
                            item.get("fingerprint", ""),
                        ),
                    ),
                }

                passport[
                    "core_diagnostics"
                ]["stable_issues"] = {
                    "schema_version": (
                        stable_issue_history[
                            "issue_identity_schema_version"
                        ]
                    ),
                    "summary": {
                        "issues": len(stable_issues),
                        "active": active_issues,
                        "resolved": resolved_issues,
                        "fingerprints": history_summary[
                            "fingerprints"
                        ],
                    },
                    "entries": sorted(
                        stable_issues.values(),
                        key=lambda item: (
                            item.get("active") is not True,
                            item.get("category", "other"),
                            item.get("issue_key", ""),
                        ),
                    ),
                }

                from connector.health_report import build_health_report
                from connector.health_timeline import (
                    load_health_state,
                    persist_health_state,
                )

                health_state_path = (
                    self.data_dir / "diagnostic-health-state.json"
                )

                health_state = load_health_state(health_state_path)
                previous_health_report = health_state.get(
                    "previous_report"
                )

                health_report = build_health_report(
                    stable_issue_history,
                    previous_report=(
                        previous_health_report
                        if isinstance(previous_health_report, dict)
                        else None
                    ),
                )

                health_state, health_report = persist_health_state(
                    health_state_path,
                    health_report,
                )

                passport["health_report"] = health_report
                passport["health_timeline"] = {
                    "schema_version": health_state["schema_version"],
                    "runs": health_state["runs"],
                    "entries": health_state["timeline"],
                }
                passport["schema_version"] = "3.6.0"

                print(
                    f"Guardian Health Status: "
                    f"{health_report['status']}"
                )
                print(
                    f"Guardian Health Score: "
                    f"{health_report['health_score']}"
                )
                print(
                    f"Guardian Health Trend: "
                    f"{health_report['trend']}"
                )
                print(
                    f"Guardian Health Score Delta: "
                    f"{health_report['health_score_delta']}"
                )
                print(
                    f"Guardian Health New Issues: "
                    f"{len(health_report['new_issue_keys'])}"
                )
                print(
                    f"Guardian Health Cleared Issues: "
                    f"{len(health_report['cleared_issue_keys'])}"
                )
                print(
                    f"Guardian Health Priority Changes: "
                    f"{len(health_report['priority_changes'])}"
                )
                print(
                    f"Guardian Health Timeline Entries: "
                    f"{len(health_state['timeline'])}"
                )
                print(
                    f"Guardian Health Active Issues: "
                    f"{health_report['summary']['active']}"
                )

                print(
                    f"Guardian Stable Issues: "
                    f"{len(stable_issues)}"
                )
                print(
                    f"Guardian Stable Issues Active: "
                    f"{active_issues}"
                )
                print(
                    f"Guardian Stable Issues Resolved: "
                    f"{resolved_issues}"
                )

                print(
                    f"Guardian Diagnostic History: "
                    f"{history_summary['fingerprints']}"
                )
                print(
                    f"Guardian Diagnostic Active: "
                    f"{history_summary['active']}"
                )
                print(
                    f"Guardian Diagnostic Resolved: "
                    f"{history_summary['resolved']}"
                )

                fingerprint_summary = passport[
                    "core_diagnostics"
                ]["error_fingerprints"]["summary"]

                print(
                    f"Guardian Error Fingerprints: "
                    f"{fingerprint_summary['entries']}"
                )
                print(
                    f"Guardian Error Categories: "
                    f"{fingerprint_summary['by_category']}"
                )

                core_summary = core_diagnostics["summary"]

                print(
                    f"Guardian Repairs: "
                    f"{core_summary['repairs']}"
                )
                print(
                    f"Guardian System Log entries: "
                    f"{core_summary['system_log_entries']}"
                )
                print(
                    f"Guardian Repairs available: "
                    f"{core_summary['repairs_available']}"
                )
                print(
                    f"Guardian System Log available: "
                    f"{core_summary['system_log_available']}"
                )
            except Exception as exc:
                print(
                    f"Guardian Core Diagnostics fallback: "
                    f"{type(exc).__name__}: {exc}"
                )

            diagnostic_summary = passport[
                "diagnostic_inventory"
            ]["summary"]

            print(
                f"Guardian Diagnostic registry-only: "
                f"{diagnostic_summary['registry_only']}"
            )
            print(
                f"Guardian Diagnostic disabled: "
                f"{diagnostic_summary['disabled']}"
            )

            print(
                f"Guardian Inventory v2 entities: "
                f"{len(inventory['entity_registry'])}"
            )
            print(
                f"Guardian Inventory v2 devices: "
                f"{len(inventory['device_registry'])}"
            )
            print(
                f"Guardian Inventory v2 areas: "
                f"{len(inventory['area_registry'])}"
            )
        except Exception as exc:
            print(
                f"Guardian Inventory v2 fallback: "
                f"{type(exc).__name__}: {exc}"
            )

        output.write_text(
            json.dumps(passport, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        from connector.sync_pipeline import SyncPipeline

        sync_pipeline = SyncPipeline(output.parent)
        sync_result = sync_pipeline.process(passport)

        print(f"Guardian Sync changed: {sync_result['changed']}")
        print(f"Guardian Sync hash: {sync_result['hash']}")
        print(f"Guardian Sync queue size: {sync_result['queue_size']}")
        print(f"Guardian Public Passport: {sync_result['public_passport_path']}")

        options_path = output.parent / "options.json"

        if options_path.exists():
            options = json.loads(options_path.read_text(encoding="utf-8"))
            github_token = options.get("github_token", "")
            github_repository = options.get("github_repository", "")

            if github_token and github_repository:
                from connector.sync_runtime import flush_sync_queue

                transport_result = flush_sync_queue(
                    sync_pipeline.queue,
                    github_token,
                    github_repository,
                )

                print(
                    f"Guardian Sync uploaded: {transport_result['uploaded']}"
                )
                print(
                    f"Guardian Sync remaining: {transport_result['remaining']}"
                )
    except (ConnectorError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Guardian House Passport created: {output}")
    print(f"Entities discovered: {passport['summary']['entity_count']}")
    print(f"Unavailable: {passport['summary']['unavailable_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
