"""Manual GitHub ops API routes."""
from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from radar.core.config import GitHubSettings
from radar.sources.github.client import expand_query_date_placeholders
from radar.sources.github.manual_fetch import collect_readme_candidates
from radar.sources.github.readme_ai_filter import apply_readme_ai_second_pass

router = APIRouter(prefix="/ops/github", tags=["ops-github"])

_COARSE_FIELDS = (
    "full_name",
    "name",
    "owner_login",
    "html_url",
    "description",
    "stars",
    "forks",
    "language",
    "topics",
    "created_at",
    "updated_at",
    "pushed_at",
    "default_branch",
    "readme_status",
)


class ManualGitHubFetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github_config_yaml: str

    @field_validator("github_config_yaml")
    @classmethod
    def _require_non_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


@router.post("/manual-fetch")
def manual_fetch_github(
    payload: ManualGitHubFetchRequest, request: Request
) -> dict[str, Any]:
    github_client = getattr(request.app.state, "github_client", None)
    if github_client is None:
        raise HTTPException(
            status_code=503,
            detail="GitHub manual fetch is unavailable because the GitHub client is not configured.",
        )

    readme_ai_filter = getattr(request.app.state, "github_readme_ai_filter", None)
    if readme_ai_filter is None:
        raise HTTPException(
            status_code=503,
            detail="README AI filtering is unavailable because the runtime dependency is not configured.",
        )

    github_settings = _load_manual_github_settings(payload.github_config_yaml)
    readme_prompt = _resolve_readme_prompt(github_settings, request)

    expanded_query = expand_query_date_placeholders(github_settings.queries[0])
    search_items = github_client.search_repositories(expanded_query)
    candidates = collect_readme_candidates(
        search_items,
        fetch_readme_text=github_client.fetch_readme_text,
    )

    errors: list[dict[str, str]] = []
    secondary_results: list[dict[str, Any]] = []

    for candidate in candidates:
        if candidate["readme_status"] != "ok":
            error = _build_readme_fetch_error(candidate)
            if error is not None:
                errors.append(error)
            continue

        try:
            second_pass = apply_readme_ai_second_pass(
                candidate,
                prompt=readme_prompt,
                readme_ai_filter=readme_ai_filter,
            )
        except Exception as exc:
            errors.append(
                {
                    "full_name": candidate["full_name"],
                    "stage": "ai_filter",
                    "message": str(exc),
                }
            )
            continue

        if second_pass["keep"]:
            secondary_results.append(
                _serialize_secondary_result(candidate, second_pass)
            )

    return {
        "request": {
            "queries": [expanded_query],
            "burst_threshold": github_settings.burst_threshold,
            "readme_prompt": readme_prompt,
        },
        "summary": {
            "coarse_count": len(candidates),
            "readme_success_count": sum(
                candidate["readme_status"] == "ok" for candidate in candidates
            ),
            "readme_failure_count": sum(
                candidate["readme_status"] != "ok" for candidate in candidates
            ),
            "secondary_keep_count": len(secondary_results),
        },
        "coarse_results": [_serialize_coarse_result(candidate) for candidate in candidates],
        "secondary_results": secondary_results,
        "errors": errors,
    }


def _load_manual_github_settings(yaml_text: str) -> GitHubSettings:
    try:
        payload = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid github_config_yaml: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="github_config_yaml must decode to a mapping.",
        )
    try:
        return GitHubSettings.model_validate(
            {
                "enabled": True,
                "token": None,
                **payload,
            }
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _resolve_readme_prompt(github_settings: GitHubSettings, request: Request) -> str:
    configured_prompt = github_settings.ai_readme_filter.default_prompt
    if isinstance(configured_prompt, str):
        configured_prompt = configured_prompt.strip()
        if configured_prompt:
            return configured_prompt

    default_prompt = (
        getattr(
            getattr(
                getattr(getattr(request.app.state, "settings", None), "sources", None),
                "github",
                None,
            ),
            "ai_readme_filter",
            None,
        )
    )
    configured_prompt = getattr(default_prompt, "default_prompt", None)
    if isinstance(configured_prompt, str):
        configured_prompt = configured_prompt.strip()
        if configured_prompt:
            return configured_prompt

    raise HTTPException(
        status_code=503,
        detail="README AI filtering is unavailable because the default prompt is not configured.",
    )


def _serialize_coarse_result(candidate: dict[str, Any]) -> dict[str, Any]:
    return {field: candidate.get(field) for field in _COARSE_FIELDS}


def _serialize_secondary_result(
    candidate: dict[str, Any], second_pass: dict[str, Any]
) -> dict[str, Any]:
    return {
        **_serialize_coarse_result(candidate),
        "reason_zh": second_pass["reason_zh"],
        "matched_signals": second_pass["matched_signals"],
    }


def _build_readme_fetch_error(candidate: dict[str, Any]) -> dict[str, str] | None:
    if candidate["readme_status"] == "fetch_error":
        message = candidate["readme_error"] or "Unknown README fetch failure."
    elif candidate["readme_status"] == "missing_readme":
        message = "README not found."
    else:
        return None
    return {
        "full_name": candidate["full_name"],
        "stage": "readme_fetch",
        "message": message,
    }
