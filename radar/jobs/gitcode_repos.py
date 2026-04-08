"""Job that polls GitCode repositories and emits alerts."""
from __future__ import annotations

from radar.sources.gitcode.pipeline import build_gitcode_observation


def run_gitcode_repos_job(items: list[dict], *, alert_service) -> int:
    created = 0
    for item in items:
        created += alert_service.process_gitcode_repository(
            build_gitcode_observation(item)
        )
    return created
