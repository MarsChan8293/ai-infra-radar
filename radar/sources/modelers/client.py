"""HTTP client for the Modelers model listing API."""
from __future__ import annotations

import httpx


class ModelersClient:
    BASE_URL = "https://modelers.cn/server/model"

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str, page_size: int = 100) -> list[dict]:
        response = httpx.get(
            self.BASE_URL,
            params={
                "page_num": 1,
                "count_per_page": page_size,
                "count": True,
                "owner": organization,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("data", {}).get("models", [])

