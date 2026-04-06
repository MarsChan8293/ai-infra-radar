"""HTTP client for official release pages."""
from __future__ import annotations

import httpx


def fetch_html(url: str) -> str:
    response = httpx.get(url, timeout=10.0, follow_redirects=True)
    response.raise_for_status()
    return response.text
