"""Manual GitHub ops API routes."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from radar.sources.github.manual_fetch import (
    build_created_range_query,
    collect_readme_candidates,
)
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

    start_date: date
    end_date: date
    query: str
    readme_prompt: str

    @field_validator("query")
    @classmethod
    def _require_non_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @model_validator(mode="after")
    def _validate_date_range(self) -> "ManualGitHubFetchRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


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

    readme_prompt = _resolve_readme_prompt(payload, request)

    expanded_query = build_created_range_query(
        payload.query,
        start_date=payload.start_date.isoformat(),
        end_date=payload.end_date.isoformat(),
    )
    search_items = github_client.search_repositories(expanded_query)
    candidates = collect_readme_candidates(
        search_items,
        fetch_readme_text=github_client.fetch_readme_text,
    )

    errors: list[dict[str, str]] = []
    secondary_results: list[dict[str, Any]] = []

    for candidate in candidates:
        if candidate["readme_status"] == "fetch_error":
            errors.append(
                {
                    "full_name": candidate["full_name"],
                    "stage": "readme_fetch",
                    "message": candidate["readme_error"] or "Unknown README fetch failure.",
                }
            )
            continue

        if candidate["readme_status"] != "ok":
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
            "query": expanded_query,
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
            "readme_prompt": readme_prompt,
        },
        "summary": {
            "coarse_count": len(candidates),
            "readme_success_count": sum(
                candidate["readme_status"] == "ok" for candidate in candidates
            ),
            "readme_failure_count": sum(
                candidate["readme_status"] == "fetch_error" for candidate in candidates
            ),
            "secondary_keep_count": len(secondary_results),
        },
        "coarse_results": [_serialize_coarse_result(candidate) for candidate in candidates],
        "secondary_results": secondary_results,
        "errors": errors,
    }


def _resolve_readme_prompt(payload: ManualGitHubFetchRequest, request: Request) -> str:
    readme_prompt = payload.readme_prompt.strip()
    if readme_prompt:
        return readme_prompt

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
