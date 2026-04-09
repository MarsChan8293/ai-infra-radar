from __future__ import annotations

import json
from typing import Any, Protocol

import httpx


class CloseableReportSummarizer(Protocol):
    def summarize_entry(self, entry: dict[str, Any]) -> dict[str, str | None]: ...

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, Any]]
    ) -> dict[str, str | None]: ...

    def close(self) -> None: ...


class NullReportSummarizer:
    def summarize_entry(self, entry: dict[str, Any]) -> dict[str, str | None]:
        return {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        return {"briefing_zh": None, "briefing_en": None}

    def close(self) -> None:
        return None


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
        payload = self._request_json(
            system_prompt="Return JSON with title_zh, reason_text_zh, reason_text_en.",
            prompt=prompt,
        )
        return {
            "title_zh": self._get_optional_string(payload, "title_zh"),
            "reason_text_zh": self._get_optional_string(payload, "reason_text_zh"),
            "reason_text_en": self._get_optional_string(payload, "reason_text_en"),
        }

    def summarize_daily_briefing(
        self, *, date: str, entries: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        prompt = json.dumps({"date": date, "entries": entries}, ensure_ascii=False)[
            : self._max_input_chars
        ]
        payload = self._request_json(
            system_prompt="Return JSON with briefing_zh and briefing_en.",
            prompt=prompt,
        )
        return {
            "briefing_zh": self._get_optional_string(payload, "briefing_zh"),
            "briefing_en": self._get_optional_string(payload, "briefing_en"),
        }

    def _request_json(self, *, system_prompt: str, prompt: str) -> dict[str, Any]:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        content = self._extract_content(response.json())
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Malformed summarization provider output: content was not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Malformed summarization provider output: content must decode to a JSON object."
            )
        return payload

    def _get_optional_string(self, payload: dict[str, Any], field_name: str) -> str | None:
        value = payload.get(field_name)
        if value is None or isinstance(value, str):
            return value
        raise RuntimeError(
            f"Malformed summarization provider output: field {field_name!r} must be a string or null."
        )

    def _extract_content(self, response_payload: Any) -> str:
        if not isinstance(response_payload, dict):
            raise RuntimeError(
                "Malformed summarization provider output: expected a JSON object response."
            )
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                "Malformed summarization provider output: expected choices[0].message.content string."
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError(
                "Malformed summarization provider output: expected choices[0].message.content string."
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(
                "Malformed summarization provider output: expected choices[0].message.content string."
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError(
                "Malformed summarization provider output: expected choices[0].message.content string."
            )
        return content

    def close(self) -> None:
        self._client.close()
