"""HTTP client for the GitHub repository search API."""
from __future__ import annotations

import httpx

_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
_DEFAULT_PER_PAGE = 30


def fetch_search_results(query: str, token: str | None = None) -> list[dict]:
    """Call the GitHub repository search API and return the ``items`` list.

    Parameters
    ----------
    query:
        A GitHub search query string (e.g. ``"topic:llm stars:>100"``).
    token:
        Optional personal access token for authenticated requests.
        Pass ``None`` for unauthenticated requests (lower rate limit).

    Raises
    ------
    httpx.HTTPStatusError
        On any non-2xx response.
    """
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = httpx.get(
        _GITHUB_SEARCH_URL,
        params={"q": query, "sort": "updated", "order": "desc", "per_page": _DEFAULT_PER_PAGE},
        headers=headers,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["items"]
