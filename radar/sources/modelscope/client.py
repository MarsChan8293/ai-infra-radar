from __future__ import annotations

import httpx


class ModelScopeClient:
    BASE = "https://www.modelscope.cn/api/v1/models/"

    def __init__(self, *, timeout: int = 10) -> None:
        self._timeout = timeout

    def list_models_for_organization(self, organization: str, page_size: int = 100) -> list[dict]:
        payload = {"Path": organization, "PageNumber": 1, "PageSize": page_size}
        response = httpx.put(self.BASE, json=payload, timeout=self._timeout)
        response.raise_for_status()
        body = response.json()
        # Response shape: {Code, Data: {Models: [...]}, Message, RequestId, Success}
        models = body.get("Data", {}).get("Models", [])
        return models
