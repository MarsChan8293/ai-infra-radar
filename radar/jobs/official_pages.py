"""Scheduled job that polls official release pages."""
from __future__ import annotations

from typing import Callable

from radar.core.config import OfficialPageEntry
from radar.core.repositories import RadarRepository
from radar.sources.official_pages.client import fetch_html as _default_fetch_html
from radar.sources.official_pages.pipeline import build_observation


def run_official_pages_job(
    *,
    pages: list[OfficialPageEntry],
    repo: RadarRepository,
    alert_service,
    fetch_html: Callable[[str], str] = _default_fetch_html,
) -> dict:
    """Poll each page, build an observation, and delegate to *alert_service*.

    Returns a summary dict with ``created`` equal to the number of alerts created.
    """
    created = 0

    for page_config in pages:
        url = str(page_config.url)
        html = fetch_html(url)

        canonical_name = _url_to_canonical(url)
        display_name = canonical_name.replace("_", " ").title()

        observation = build_observation(
            html=html,
            url=url,
            canonical_name=canonical_name,
            display_name=display_name,
            keywords=page_config.whitelist_keywords,
        )

        result = alert_service.process_official_page(page_config, observation)
        created += result.get("created", 0)

    return {"created": created}


def _url_to_canonical(url: str) -> str:
    """Derive a stable snake_case canonical name from a URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.replace(".", "_").replace("-", "_")
    path = parsed.path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_")
    return f"{host}_{path}".strip("_") if path else host
