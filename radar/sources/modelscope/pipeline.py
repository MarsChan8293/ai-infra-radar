from __future__ import annotations

from typing import Any


def build_modelscope_observation(item: dict[str, Any]) -> dict:
    """Normalize a raw ModelScope model item into an observation dict.

    Expected raw fields: Id, Name, Path (org/name), CreatedTime, LastUpdatedTime, Downloads
    """
    path = item.get("Path") or ""
    if "/" in path:
        org, name = path.split("/", 1)
    else:
        org = ""
        name = item.get("Name") or path

    canonical_name = f"modelscope:{org}/{name}"
    url = f"https://www.modelscope.cn/models/{org}/{name}"

    normalized = {
        "model_id": f"{org}/{name}",
        "last_updated_time": item.get("LastUpdatedTime"),
        "downloads": item.get("Downloads"),
        "name": item.get("Name"),
        "id": item.get("Id"),
    }

    observation = {
        "canonical_name": canonical_name,
        "display_name": normalized["name"] or canonical_name,
        "url": url,
        "raw_payload": item,
        "normalized_payload": normalized,
        "content_hash": normalized.get("last_updated_time") or "",
        "score": 1.0,
    }
    return observation
