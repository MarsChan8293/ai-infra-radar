"""HTTP client for the Hugging Face models API."""
from __future__ import annotations

import httpx


class HuggingFaceClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str) -> list[dict]:
        response = httpx.get(
            "https://huggingface.co/api/models",
            params={"author": organization, "full": "true"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

