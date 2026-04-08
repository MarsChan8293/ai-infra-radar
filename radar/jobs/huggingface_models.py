"""Job that polls Hugging Face model listings and emits alerts."""
from __future__ import annotations

from radar.sources.huggingface.pipeline import build_huggingface_observation


def run_huggingface_models_job(
    items: list[dict],
    *,
    repository,
    alert_service,
) -> int:
    created = 0
    for item in items:
        observation = build_huggingface_observation(item)
        created += alert_service.process_huggingface_model(observation)
    return created
