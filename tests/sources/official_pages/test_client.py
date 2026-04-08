"""Tests for the official_pages HTTP client (fetch_html retry behaviour)."""
from __future__ import annotations

import httpx
import pytest
import respx


@respx.mock
def test_fetch_html_succeeds_on_first_attempt() -> None:
    """fetch_html returns body on a straightforward 200 response."""
    from radar.sources.official_pages.client import fetch_html

    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(200, text="<html>OK</html>")
    )
    assert fetch_html("https://example.com/page") == "<html>OK</html>"


@respx.mock
def test_fetch_html_retries_on_503_and_succeeds(monkeypatch) -> None:
    """fetch_html retries once after a 503 and returns body on subsequent 200."""
    monkeypatch.setattr("radar.sources.official_pages.client.time.sleep", lambda _: None)
    from radar.sources.official_pages.client import fetch_html

    respx.get("https://example.com/page").mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, text="<html>OK</html>"),
        ]
    )
    result = fetch_html("https://example.com/page")
    assert result == "<html>OK</html>"


@respx.mock
def test_fetch_html_retries_on_429_and_succeeds(monkeypatch) -> None:
    """fetch_html retries once after a 429 and returns body on subsequent 200."""
    monkeypatch.setattr("radar.sources.official_pages.client.time.sleep", lambda _: None)
    from radar.sources.official_pages.client import fetch_html

    respx.get("https://example.com/page").mock(
        side_effect=[
            httpx.Response(429, text="Too Many Requests"),
            httpx.Response(200, text="<html>DONE</html>"),
        ]
    )
    result = fetch_html("https://example.com/page")
    assert result == "<html>DONE</html>"


@respx.mock
def test_fetch_html_raises_after_max_retries(monkeypatch) -> None:
    """fetch_html raises an exception when all retry attempts are exhausted."""
    monkeypatch.setattr("radar.sources.official_pages.client.time.sleep", lambda _: None)
    from radar.sources.official_pages.client import fetch_html

    # Always return 503 — should exhaust retries and raise.
    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(Exception):
        fetch_html("https://example.com/page")


@respx.mock
def test_fetch_html_retries_on_network_error_and_succeeds(monkeypatch) -> None:
    """fetch_html retries after a transient network error."""
    monkeypatch.setattr("radar.sources.official_pages.client.time.sleep", lambda _: None)
    from radar.sources.official_pages.client import fetch_html

    respx.get("https://example.com/page").mock(
        side_effect=[
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, text="<html>RECOVERED</html>"),
        ]
    )
    result = fetch_html("https://example.com/page")
    assert result == "<html>RECOVERED</html>"
