"""Alert orchestration service: dedupe, create, dispatch."""
from __future__ import annotations

from typing import Any


class AlertService:
    """Orchestrates alert creation, deduplication, and dispatch.

    Parameters
    ----------
    repository:
        A ``RadarRepository`` (or compatible) instance.
    dispatcher:
        An ``AlertDispatcher`` instance.
    channels:
        Channel configuration dict forwarded to
        ``AlertDispatcher.dispatch``.
    """

    def __init__(
        self,
        *,
        repository: Any,
        dispatcher: Any,
        channels: dict[str, Any],
    ) -> None:
        self._repo = repository
        self._dispatcher = dispatcher
        self._channels = channels

    def emit_alert(
        self,
        *,
        alert_type: str,
        entity_id: int,
        source: str,
        score: float,
        dedupe_key: str,
        reason: dict,
        alert_payload: dict,
    ) -> int:
        """Create and dispatch a single alert, skipping duplicates.

        Returns 1 if a new alert was created and dispatched, 0 if suppressed.
        """
        if self._repo.alert_exists(source=source, dedupe_key=dedupe_key):
            return 0

        alert = self._repo.create_alert(
            alert_type=alert_type,
            entity_id=entity_id,
            source=source,
            score=score,
            dedupe_key=dedupe_key,
            reason=reason,
        )
        self._dispatcher.dispatch(
            alert_id=alert.id,
            alert_payload={**alert_payload, "alert_id": alert.id},
            channels=self._channels,
        )
        return 1

    def process_github_burst(
        self,
        observation: dict,
    ) -> int:
        """Persist a GitHub burst observation and emit a github_burst alert.

        Mirrors the official-pages flow: upsert entity → record observation →
        emit alert (with deduplication).

        Returns 1 if a new alert was created and dispatched, 0 if suppressed.
        """
        normalized_payload = observation["normalized_payload"]
        full_name: str = normalized_payload["full_name"]
        url = observation["url"]

        entity = self._repo.upsert_entity(
            source="github",
            entity_type="repository",
            canonical_name=observation["canonical_name"],
            display_name=observation["display_name"],
            url=url,
        )
        self._repo.record_observation(
            entity_id=entity.id,
            source="github",
            raw_payload=observation["raw_payload"],
            normalized_payload=observation["normalized_payload"],
            dedupe_key=observation["content_hash"],
            content_hash=observation["content_hash"],
        )
        reason = {
            "full_name": full_name,
            "stars": normalized_payload.get("stars", 0),
            "forks": normalized_payload.get("forks", 0),
        }

        return self.emit_alert(
            alert_type="github_burst",
            entity_id=entity.id,
            source="github",
            score=observation["score"],
            dedupe_key=observation["content_hash"],
            reason=reason,
            alert_payload={
                "full_name": full_name,
                "url": url,
                "score": observation["score"],
                "reason": reason,
            },
        )

    def process_official_page(
        self,
        page_config: Any,
        observation: dict,
    ) -> int:
        """Persist an official-page observation and emit an official_release alert.

        Returns 1 if a new alert was created, 0 if suppressed.
        """
        url = str(page_config.url)

        entity = self._repo.upsert_entity(
            source="official_pages",
            entity_type="page",
            canonical_name=observation["canonical_name"],
            display_name=observation["display_name"],
            url=url,
        )
        self._repo.record_observation(
            entity_id=entity.id,
            source="official_pages",
            raw_payload=observation["raw_payload"],
            normalized_payload=observation["normalized_payload"],
            dedupe_key=observation["content_hash"],
            content_hash=observation["content_hash"],
        )

        return self.emit_alert(
            alert_type="official_release",
            entity_id=entity.id,
            source="official_pages",
            score=observation["score"],
            dedupe_key=observation["content_hash"],
            reason={"title": observation.get("title", ""), "matched_keywords": observation.get("matched_keywords", [])},
            alert_payload={"title": observation.get("title", ""), "url": url, "score": observation["score"]},
        )
