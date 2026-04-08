"""Normalise Modelers models into observation-ready dicts."""
from __future__ import annotations

import hashlib


def build_modelers_observation(item: dict) -> dict:
    owner = item["owner"]
    name = item["name"]
    model_id = f"{owner}/{name}"
    updated_at = item["updated_at"]
    content_hash = hashlib.sha256(f"{model_id}|{updated_at}".encode()).hexdigest()
    return {
        "canonical_name": f"modelers:{model_id}",
        "display_name": model_id,
        "url": f"https://modelers.cn/models/{model_id}",
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "model_id": model_id,
            "organization": owner,
            "name": name,
            "created_at": item.get("created_at"),
            "updated_at": updated_at,
            "download_count": item.get("download_count"),
            "visibility": item.get("visibility"),
            "content_hash": content_hash,
        },
        "score": 1.0,
    }
