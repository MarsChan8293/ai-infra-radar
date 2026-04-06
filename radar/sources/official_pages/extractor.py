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
        content_hash: SHA-256 hex digest of the raw HTML
        matched_keywords: subset of *keywords* found (case-insensitive) in the HTML
    """
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        title = (title_tag.get_text(strip=True) if title_tag else "") or url

    html_lower = html.lower()
    matched_keywords = [kw for kw in keywords if kw.lower() in html_lower]

    content_hash = hashlib.sha256(html.encode()).hexdigest()

    return {
        "title": title,
        "content_hash": content_hash,
        "matched_keywords": matched_keywords,
    }
