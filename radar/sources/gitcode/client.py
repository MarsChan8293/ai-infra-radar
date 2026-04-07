"""HTTP client for the GitCode organization repositories API."""
from __future__ import annotations

import httpx


class GitCodeClient:
    BASE_URL = "https://api.gitcode.com/api/v5/orgs/{organization}/repos"

    def __init__(self, token: str, timeout: float = 15.0) -> None:
        self._token = token
        self._timeout = timeout

    def list_repositories_for_organization(self, organization: str) -> list[dict]:
        response = httpx.get(
            self.BASE_URL.format(organization=organization),
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"GitCode API returned malformed payload: {payload!r}")
        return payload
