"""Daily digest job: aggregate recent top alerts and dispatch one summary payload."""
from __future__ import annotations

from typing import Any, Callable


def run_daily_digest_job(
    repository: Any,
    dispatch: Callable[[dict], None],
) -> int:
    """Gather digest candidates and dispatch one summary payload.

    Use the repository to fetch recent Alert objects, serialize them and
    enrich GitHub-source items with entity and observation metadata where
    available.
    """
    candidates = repository.get_digest_candidates()
    if not candidates:
        return 0

    items = []
    from radar.core.models import Entity

    for alert in candidates:
        item = {
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "source": alert.source,
            "score": alert.score,
        }

        # Enrich GitHub alerts with repository metadata when available.
        if alert.source == "github":
            # Fetch entity (entities table) and latest observation for this entity
            with repository._session_factory() as session:
                entity = session.get(Entity, alert.entity_id)
            if entity is not None:
                item["repo_url"] = entity.url

            obs = repository.get_latest_observation_for_entity(alert.entity_id, source="github")
            # repo_name comes from the alert reason (full_name) when present
            if isinstance(alert.reason, dict) and alert.reason.get("full_name"):
                item["repo_name"] = alert.reason.get("full_name")
            elif entity is not None:
                item["repo_name"] = entity.display_name

            if obs is not None and isinstance(obs.normalized_payload, dict):
                desc = obs.normalized_payload.get("description")
                if desc:
                    item["repo_description"] = desc

        items.append(item)

    payload = {
        "type": "daily_digest",
        "count": len(items),
        "items": items,
    }
    dispatch(payload)
    return 1
