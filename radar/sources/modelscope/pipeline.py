from __future__ import annotations

import hashlib
from typing import Any


def build_modelscope_observation(item: dict[str, Any]) -> dict:
    """Normalize a raw ModelScope model item into an observation dict."""
    org = item["Path"]
    name = item["Name"]
    model_id = f"{org}/{name}"
    last_updated_time = item["LastUpdatedTime"]
    content_hash = hashlib.sha256(f"{model_id}|{last_updated_time}".encode()).hexdigest()

    normalized = {
        "model_id": model_id,
        "organization": org,
        "name": name,
        "modelscope_id": item["Id"],
        "created_time": item["CreatedTime"],
        "last_updated_time": last_updated_time,
        "downloads": item.get("Downloads"),
        "content_hash": content_hash,
    }

    return {
        "canonical_name": f"modelscope:{model_id}",
        "display_name": model_id,
        "url": f"https://www.modelscope.cn/models/{model_id}",
        "raw_payload": item,
        "normalized_payload": normalized,
        "content_hash": content_hash,
        "score": 1.0,
    }
