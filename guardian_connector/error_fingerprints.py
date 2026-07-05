from __future__ import annotations

import hashlib
import re
from collections import Counter
from copy import deepcopy
from typing import Any


SENSITIVE_PATTERNS = (
    (re.compile(r"https?://\S+", re.IGNORECASE), "<url>"),
    (
        re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ),
        "<ip>",
    ),
    (
        re.compile(
            r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b",
            re.IGNORECASE,
        ),
        "<mac>",
    ),
    (
        re.compile(
            r"\b(?:bearer|token|password|secret|api[_-]?key)"
            r"\s*[:=]\s*\S+",
            re.IGNORECASE,
        ),
        "<secret>",
    ),
    (
        re.compile(r"\b\d{5,}\b"),
        "<number>",
    ),
)


CATEGORY_RULES = (
    (
        "timeout",
        (
            "timeout",
            "timed out",
            "timeouterror",
        ),
    ),
    (
        "connection",
        (
            "connection",
            "connecterror",
            "connectionerror",
            "connection refused",
            "connection reset",
            "broken pipe",
            "socket",
        ),
    ),
    (
        "authentication",
        (
            "unauthorized",
            "forbidden",
            "authentication",
            "auth error",
            "401",
            "403",
        ),
    ),
    (
        "network",
        (
            "dns",
            "host unreachable",
            "network unreachable",
            "name resolution",
        ),
    ),
    (
        "rate_limit",
        (
            "rate limit",
            "too many requests",
            "429",
        ),
    ),
    (
        "validation",
        (
            "valueerror",
            "typeerror",
            "keyerror",
            "attributeerror",
            "invalid",
        ),
    ),
)


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (list, tuple)):
        return " ".join(
            _flatten_text(item)
            for item in value
        )

    if isinstance(value, dict):
        return " ".join(
            f"{key} {_flatten_text(item)}"
            for key, item in sorted(value.items())
        )

    return str(value)


def normalize_error_text(value: Any) -> str:
    text = _flatten_text(value).lower()

    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)

    text = re.sub(r"\s+", " ", text).strip()
    return text[:2048]


def classify_error(
    *,
    source: Any,
    message: Any,
    exception: Any,
) -> str:
    text = " ".join((
        normalize_error_text(source),
        normalize_error_text(message),
        normalize_error_text(exception),
    ))

    for category, keywords in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category

    return "other"


def extract_exception_type(exception: Any) -> str | None:
    text = _flatten_text(exception)

    patterns = (
        r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))\s*:",
        r"raise\s+([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))",
    )

    matches = []

    for pattern in patterns:
        matches.extend(re.findall(pattern, text))

    if not matches:
        return None

    return matches[-1].split(".")[-1]


def build_error_fingerprint(entry: dict[str, Any]) -> str:
    canonical = "|".join((
        normalize_error_text(entry.get("source")),
        normalize_error_text(entry.get("message")),
        normalize_error_text(entry.get("exception")),
    ))

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:20]


def enrich_core_diagnostics(
    passport: dict[str, Any],
    raw_system_log: list[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(passport)

    core = result.get("core_diagnostics")

    if not isinstance(core, dict):
        return result

    exported_entries = core.get("system_log", [])

    if not isinstance(exported_entries, list):
        return result

    fingerprints = []

    for index, exported in enumerate(exported_entries):
        if not isinstance(exported, dict):
            continue

        raw = (
            raw_system_log[index]
            if index < len(raw_system_log)
            and isinstance(raw_system_log[index], dict)
            else {}
        )

        fingerprint = build_error_fingerprint(raw)
        category = classify_error(
            source=raw.get("source"),
            message=raw.get("message"),
            exception=raw.get("exception"),
        )
        exception_type = extract_exception_type(
            raw.get("exception")
        )

        exported["fingerprint"] = fingerprint
        exported["category"] = category
        exported["exception_type"] = exception_type

        fingerprints.append({
            "fingerprint": fingerprint,
            "category": category,
            "exception_type": exception_type,
            "level": exported.get("level"),
            "source": exported.get("source"),
            "count": exported.get("count"),
        })

    by_category = Counter(
        item["category"]
        for item in fingerprints
    )

    by_exception_type = Counter(
        item["exception_type"] or "unknown"
        for item in fingerprints
    )

    core["error_fingerprints"] = {
        "summary": {
            "entries": len(fingerprints),
            "by_category": dict(
                sorted(by_category.items())
            ),
            "by_exception_type": dict(
                sorted(by_exception_type.items())
            ),
        },
        "entries": fingerprints,
    }

    result["schema_version"] = "3.1.0"
    return result
