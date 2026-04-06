"""Scheduled job that polls official release pages."""
from __future__ import annotations

from typing import Callable

from radar.core.config import OfficialPageEntry
from radar.sources.official_pages.pipeline import build_observation


def run_official_pages_job(
    page_config: OfficialPageEntry,
    fetch_html: Callable[[str], str],
    repository,
    alert_service,
) -> int:
    """Poll *page_config*, build an observation, and delegate to *alert_service*.

    Returns the number of alerts created (int).
    """
    url = str(page_config.url)
    html = fetch_html(url)

    canonical_name = _url_to_canonical(url)

    # Build a preliminary observation to obtain the extracted page title.
    observation = build_observation(
        html=html,
        url=url,
        canonical_name=canonical_name,
        display_name=canonical_name,  # placeholder; overridden below
        keywords=page_config.whitelist_keywords,
    )

    # Align display_name with the extracted title rather than the URL slug.
    observation["display_name"] = observation["title"]

    result = alert_service.process_official_page(page_config, observation)
    return result.get("created", 0)


def _url_to_canonical(url: str) -> str:
    """Derive a stable snake_case canonical name from a URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.replace(".", "_").replace("-", "_")
    path = parsed.path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_")
    return f"{host}_{path}".strip("_") if path else host
