from __future__ import annotations

from typing import Any, Callable


def build_created_range_query(query: str, *, start_date: str, end_date: str) -> str:
    base_query = query.strip()
    created_clause = f"created:{start_date}..{end_date}"
    if not base_query:
        return created_clause
    return f"{base_query} {created_clause}"


def collect_readme_candidates(
    search_items: list[dict[str, Any]],
    *,
    fetch_readme_text: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for item in search_items:
        full_name = item["full_name"]
        candidate: dict[str, Any] = {
            "full_name": full_name,
            "name": item.get("name"),
            "owner_login": item.get("owner", {}).get("login"),
            "html_url": item.get("html_url"),
            "description": item.get("description"),
            "stars": item.get("stargazers_count", 0),
            "forks": item.get("forks_count", 0),
            "language": item.get("language"),
            "topics": item.get("topics", []),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "pushed_at": item.get("pushed_at"),
            "default_branch": item.get("default_branch"),
            "readme_status": "missing_readme",
            "readme_text": None,
            "readme_error": None,
            "raw_item": item,
        }

        try:
            readme_text = fetch_readme_text(full_name)
        except Exception as exc:
            candidate["readme_status"] = "fetch_error"
            candidate["readme_error"] = str(exc)
        else:
            if readme_text is not None:
                candidate["readme_status"] = "ok"
                candidate["readme_text"] = readme_text

        candidates.append(candidate)

    return candidates
