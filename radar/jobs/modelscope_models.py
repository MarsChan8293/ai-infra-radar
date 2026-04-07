"""Job that polls ModelScope listings and emits alerts."""
from __future__ import annotations

from radar.sources.modelscope.pipeline import build_modelscope_observation


def run_modelscope_models_job(
    items: list[dict],
    *,
    repository,
    alert_service,
) -> int:
    created = 0
    for item in items:
        observation = build_modelscope_observation(item)
        created += alert_service.process_modelscope_model(observation)
    return created
