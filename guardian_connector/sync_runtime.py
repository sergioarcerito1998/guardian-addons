from __future__ import annotations

from pathlib import Path
from typing import Any

from connector.github_transport import GitHubTransport


def flush_sync_queue(
    queue: Any,
    token: str,
    repository: str,
) -> dict[str, Any]:
    items = queue.items()

    if not items:
        return {"uploaded": 0, "remaining": 0}

    transport = GitHubTransport(token, repository)
    uploaded = 0

    for item in items:
        transport.upload(item)
        item.unlink()
        uploaded += 1

    return {
        "uploaded": uploaded,
        "remaining": len(queue.items()),
    }
