from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from connector.guardian_sync import retry_with_backoff


class GitHubTransportError(RuntimeError):
    pass


class GitHubTransport:
    def __init__(
        self,
        token: str,
        repository: str,
        target_path: str = "runtime/public-passport.json",
        api_url: str = "https://api.github.com",
    ):
        if not token:
            raise ValueError("GitHub token is required")
        if not repository or repository.count("/") != 1:
            raise ValueError("repository must use owner/name format")

        self.token = token
        self.repository = repository
        self.target_path = target_path
        self.api_url = api_url.rstrip("/")

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Guardian-Home-Assistant-Sync",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise GitHubTransportError(
                f"GitHub API returned HTTP {exc.code}: {body[:300]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GitHubTransportError(
                f"Cannot reach GitHub API: {exc.reason}"
            ) from exc

    def _contents_url(self) -> str:
        return (
            f"{self.api_url}/repos/{self.repository}/contents/"
            f"{self.target_path}"
        )

    def get_remote_sha(self) -> str | None:
        try:
            result = self._request("GET", self._contents_url())
            return result.get("sha")
        except GitHubTransportError as exc:
            if "HTTP 404:" in str(exc):
                return None
            raise

    def upload(self, passport_path: str | Path) -> dict[str, Any]:
        passport_path = Path(passport_path)
        content = passport_path.read_bytes()
        sha = self.get_remote_sha()

        payload: dict[str, Any] = {
            "message": "chore: sync Guardian public passport",
            "content": base64.b64encode(content).decode("ascii"),
        }

        if sha:
            payload["sha"] = sha

        return retry_with_backoff(
            lambda: self._request("PUT", self._contents_url(), payload),
            attempts=5,
            base_delay=1.0,
            max_delay=30.0,
        )
