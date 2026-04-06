"""Normalise GitHub search API items into observation-ready dicts."""
from __future__ import annotations

import hashlib


def normalize_github_item(item: dict) -> dict:
    """Return a normalised observation dict for a single GitHub search result *item*.

    The ``content_hash`` is derived from ``full_name``, ``pushed_at``, and
    ``stargazers_count`` so that a new push or a fresh burst of stars produces
    a new hash (and therefore a new alert), while repeat processing of the same
    snapshot is deduplicated.
    """
    full_name: str = item["full_name"]
    canonical_name = f"github:{full_name}"
    url: str = item["html_url"]

    hash_input = (
        f"{full_name}|{item.get('pushed_at', '')}|{item.get('stargazers_count', 0)}"
    )
    content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    normalized_payload: dict = {
        "full_name": full_name,
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "pushed_at": item.get("pushed_at"),
        "description": item.get("description"),
        "content_hash": content_hash,
    }

    return {
        "canonical_name": canonical_name,
        "display_name": full_name,
        "url": url,
        "title": full_name,
        "content_hash": content_hash,
        "raw_payload": item,
        "normalized_payload": normalized_payload,
    }
