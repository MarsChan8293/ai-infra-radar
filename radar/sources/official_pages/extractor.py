"""HTML signal extractor for official release pages."""
from __future__ import annotations

import hashlib

from bs4 import BeautifulSoup


def extract_release_signal(
    *,
    html: str,
    url: str,
    keywords: list[str],
) -> dict:
    """Parse *html* and return a signal dict.

    Returns:
        title: text from <h1> if present, else <title>, else *url*
        content_hash: SHA-256 hex digest of the normalised visible text
        matched_keywords: subset of *keywords* found in the normalised visible text
    """
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        title = (title_tag.get_text(strip=True) if title_tag else "") or url

    # Use normalised visible text for both keyword matching and hashing so
    # that script/style content and raw HTML markup are excluded.
    normalized_text = soup.get_text(" ", strip=True).lower()
    matched_keywords = [kw for kw in keywords if kw.lower() in normalized_text]

    content_hash = hashlib.sha256(normalized_text.encode()).hexdigest()

    return {
        "title": title,
        "content_hash": content_hash,
        "matched_keywords": matched_keywords,
    }
