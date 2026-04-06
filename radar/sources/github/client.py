"""HTTP client for the GitHub repository search API."""
from __future__ import annotations

import httpx

_DEFAULT_PER_PAGE = 30


class GitHubClient:
    """Minimal GitHub repository-search client."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def search_repositories(self, query: str) -> list[dict]:
        """Call the GitHub repository search API and return the ``items`` list.

        Parameters
        ----------
        query:
            A GitHub search query string (e.g. ``"topic:llm stars:>100"``).

        Raises
        ------
        httpx.HTTPStatusError
            On any non-2xx response.
        """
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = httpx.get(
            "https://api.github.com/search/repositories",
            params={
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": _DEFAULT_PER_PAGE,
            },
            headers=headers,
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()["items"]


def fetch_search_results(query: str, token: str | None = None) -> list[dict]:
    """Backward-compatible wrapper around :class:`GitHubClient`.

    Task 6 tests originally targeted a function-level API. Task 7 needs a
    reusable client object for scheduler wiring, so both interfaces are kept.
    """
    return GitHubClient(token).search_repositories(query)
