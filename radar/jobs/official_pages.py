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

    Returns the int result from alert_service.process_official_page directly.
    canonical_name is the raw URL; display_name is derived from the extracted page title.
    """
    url = str(page_config.url)
    html = fetch_html(url)

    observation = build_observation(
        html=html,
        url=url,
        canonical_name=url,
        keywords=page_config.whitelist_keywords,
    )

    return alert_service.process_official_page(page_config, observation)
