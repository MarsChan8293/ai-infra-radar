from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from radar.core.http_retry import send_with_retries


class GitHubReadmeAIFilter(Protocol):
    def evaluate(
        self,
        *,
        repository: dict[str, Any],
        readme_text: str,
        prompt: str,
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


class OpenAIGitHubReadmeAIFilter:
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

    def evaluate(
        self,
        *,
        repository: dict[str, Any],
        readme_text: str,
        prompt: str,
    ) -> dict[str, Any]:
        payload = self._request_json(
            prompt=json.dumps(
                {
                    "repository": repository,
                    "readme_text": readme_text,
                },
                ensure_ascii=False,
            )[: self._max_input_chars],
            system_prompt=prompt,
        )
        return {
            "keep": _get_required_bool(payload, "keep"),
            "reason_zh": _get_required_string(payload, "reason_zh"),
            "matched_signals": _get_string_list(payload, "matched_signals"),
        }

    def _request_json(self, *, system_prompt: str, prompt: str) -> dict[str, Any]:
        response = send_with_retries(
            lambda: self._client.post(
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
        )
        try:
            payload = json.loads(_extract_content(response.json()))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Malformed README AI provider output: content was not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Malformed README AI provider output: content must decode to a JSON object."
            )
        return payload

    def close(self) -> None:
        self._client.close()


def apply_readme_ai_second_pass(
    candidate: dict[str, Any],
    *,
    prompt: str,
    readme_ai_filter: GitHubReadmeAIFilter,
) -> dict[str, Any]:
    payload = readme_ai_filter.evaluate(
        repository=candidate,
        readme_text=_get_required_readme_text(candidate),
        prompt=prompt,
    )
    return {
        "keep": _get_required_bool(payload, "keep"),
        "reason_zh": _get_required_string(payload, "reason_zh"),
        "matched_signals": _get_string_list(payload, "matched_signals"),
    }


def _get_required_readme_text(candidate: dict[str, Any]) -> str:
    if candidate.get("readme_status") != "ok":
        raise RuntimeError("README AI second-pass requires readme_status='ok' with README text.")
    readme_text = candidate.get("readme_text")
    if not isinstance(readme_text, str):
        raise RuntimeError("README AI second-pass requires readme_status='ok' with README text.")
    return readme_text


def _get_required_bool(payload: Any, field_name: str) -> bool:
    value = _get_mapping_value(payload, field_name)
    if isinstance(value, bool):
        return value
    raise RuntimeError(f"Malformed README AI provider output: field {field_name!r} must be a boolean.")


def _get_required_string(payload: Any, field_name: str) -> str:
    value = _get_mapping_value(payload, field_name)
    if isinstance(value, str):
        return value
    raise RuntimeError(
        f"Malformed README AI provider output: field {field_name!r} must be a string."
    )


def _get_string_list(payload: Any, field_name: str) -> list[str]:
    value = _get_mapping_value(payload, field_name)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(
            f"Malformed README AI provider output: field {field_name!r} must be a list of strings."
        )
    return value


def _get_mapping_value(payload: Any, field_name: str) -> Any:
    if not isinstance(payload, dict):
        raise RuntimeError("Malformed README AI provider output: expected a JSON object response.")
    return payload.get(field_name)


def _extract_content(response_payload: Any) -> str:
    if not isinstance(response_payload, dict):
        raise RuntimeError("Malformed README AI provider output: expected a JSON object response.")
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            "Malformed README AI provider output: expected choices[0].message.content string."
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError(
            "Malformed README AI provider output: expected choices[0].message.content string."
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(
            "Malformed README AI provider output: expected choices[0].message.content string."
        )
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(
            "Malformed README AI provider output: expected choices[0].message.content string."
        )
    return content
