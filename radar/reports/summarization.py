from __future__ import annotations

import json
from typing import Any

import httpx


class NullReportSummarizer:
    def summarize_entry(self, entry: dict[str, Any]) -> dict[str, str | None]:
        return {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        return {"briefing_zh": None, "briefing_en": None}


class OpenAIReportSummarizer:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_input_chars: int,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )
        self._model = model
        self._max_input_chars = max_input_chars

    def summarize_entry(self, entry: dict[str, Any]) -> dict[str, str | None]:
        prompt = json.dumps(
            {
                "display_name": entry["display_name"],
                "source": entry["source"],
                "reason": entry["reason"],
            },
            ensure_ascii=False,
        )[: self._max_input_chars]
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return JSON with title_zh, reason_text_zh, reason_text_en.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(content)
        return {
            "title_zh": payload.get("title_zh"),
            "reason_text_zh": payload.get("reason_text_zh"),
            "reason_text_en": payload.get("reason_text_en"),
        }

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        prompt = json.dumps({"date": date, "entries": entries}, ensure_ascii=False)[: self._max_input_chars]
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return JSON with briefing_zh and briefing_en.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(content)
        return {
            "briefing_zh": payload.get("briefing_zh"),
            "briefing_en": payload.get("briefing_en"),
        }
