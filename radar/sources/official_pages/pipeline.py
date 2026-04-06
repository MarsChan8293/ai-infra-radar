"""Pipeline that turns a fetched page into a normalised observation dict."""
from __future__ import annotations

from radar.sources.official_pages.extractor import extract_release_signal


def build_observation(
    *,
    html: str,
    url: str,
    canonical_name: str,
    display_name: str,
    keywords: list[str],
) -> dict:
    """Fetch, extract, and normalise a page into an observation-ready dict.

    score is 1.0 when at least one keyword matched, else 0.0.
    """
    signal = extract_release_signal(html=html, url=url, keywords=keywords)

    score = 1.0 if signal["matched_keywords"] else 0.0

    return {
        "canonical_name": canonical_name,
        "display_name": display_name,
        "url": url,
        "title": signal["title"],
        "content_hash": signal["content_hash"],
        "matched_keywords": signal["matched_keywords"],
        "normalized_payload": {
            "title": signal["title"],
            "url": url,
            "matched_keywords": signal["matched_keywords"],
        },
        "raw_payload": {"html_snippet": html[:500]},
        "score": score,
    }
