"""Normalise GitCode repositories into observation-ready dicts."""
from __future__ import annotations

import hashlib


def build_gitcode_observation(item: dict) -> dict:
    full_name = item["full_name"]
    organization, repo_name = full_name.split("/", 1)
    updated_at = item["updated_at"]
    content_hash = hashlib.sha256(f"{full_name}|{updated_at}".encode()).hexdigest()
    return {
        "canonical_name": f"gitcode:{full_name}",
        "display_name": full_name,
        "url": item["html_url"],
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": {
            "full_name": full_name,
            "organization": organization,
            "repo_name": repo_name,
            "updated_at": updated_at,
            "content_hash": content_hash,
        },
        "score": 1.0,
    }
