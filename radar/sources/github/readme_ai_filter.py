from __future__ import annotations

from typing import Any, Protocol


class GitHubReadmeAIFilter(Protocol):
    def evaluate(
        self,
        *,
        repository: dict[str, Any],
        readme_text: str,
        prompt: str,
    ) -> dict[str, Any]: ...


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
    readme_text = candidate.get("readme_text")
    if not isinstance(readme_text, str):
        raise RuntimeError("README AI second-pass requires a fetched README text.")
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
