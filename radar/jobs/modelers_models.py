"""Job that polls Modelers listings and emits alerts."""
from __future__ import annotations

from radar.sources.modelers.pipeline import build_modelers_observation


def run_modelers_models_job(items: list[dict], *, alert_service) -> int:
    created = 0
    for item in items:
        observation = build_modelers_observation(item)
        created += alert_service.process_modelers_model(observation)
    return created

