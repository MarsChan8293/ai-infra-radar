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
        if body.get("Success") is not True:
            raise ValueError(f"ModelScope API returned unsuccessful response: {body!r}")
        if body.get("Code") not in {0, 200}:
            raise ValueError(f"ModelScope API returned unexpected code: {body!r}")
        data = body.get("Data")
        if not isinstance(data, dict) or not isinstance(data.get("Models"), list):
            raise ValueError(f"ModelScope API returned malformed payload: {body!r}")
        models = data["Models"]
        return models
