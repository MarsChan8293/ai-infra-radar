"""Normalise Hugging Face models into observation-ready dicts."""
from __future__ import annotations

import hashlib


def build_huggingface_observation(item: dict) -> dict:
    model_id = item["id"]
    last_modified = item["lastModified"]
    content_hash = hashlib.sha256(f"{model_id}|{last_modified}".encode()).hexdigest()
    return {
        "canonical_name": f"huggingface:{model_id}",
        "display_name": model_id,
        "url": f"https://huggingface.co/{model_id}",
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "model_id": model_id,
            "organization": model_id.split("/", 1)[0],
            "last_modified": last_modified,
            "private": item.get("private", False),
            "gated": item.get("gated", False),
            "downloads": item.get("downloads"),
            "content_hash": content_hash,
        },
    }
