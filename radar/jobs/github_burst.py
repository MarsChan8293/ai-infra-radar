"""Job that scores GitHub search results and emits burst alerts."""
from __future__ import annotations

from typing import Any

from radar.sources.github.pipeline import normalize_github_item
from radar.sources.github.scoring import score_github_item


def run_github_burst_job(
    search_items: list[dict],
    threshold: float,
    repository: Any,
    alert_service: Any,
) -> int:
    """Score *search_items* and call ``alert_service.process_github_burst`` for bursts.

    Parameters
    ----------
    search_items:
        Raw items from the GitHub search API (each a dict with at least
        ``full_name``, ``html_url``, ``stargazers_count``, ``forks_count``).
    threshold:
        Minimum burst score required for an alert to be emitted.
    repository:
        Passed through to ``alert_service``; may be ``None`` in unit tests
        that use a fake service.
    alert_service:
        Must expose ``process_github_burst(item, observation) -> int``.

    Returns
    -------
    int
        Total number of alerts created across all items.
    """
    total = 0
    for item in search_items:
        score = score_github_item(item)
        if score >= threshold:
            observation = normalize_github_item(item)
            observation["score"] = score
            total += alert_service.process_github_burst(item, observation)
    return total
