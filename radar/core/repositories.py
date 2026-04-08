"""Repository helpers for Radar persistence and query access."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from radar.core.models import Alert, DeliveryLog, Entity, JobRun, Observation


class RadarRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def upsert_entity(
        self,
        *,
        source: str,
        entity_type: str,
        canonical_name: str,
        display_name: str,
        url: str,
    ) -> Entity:
        with self._session_factory() as session:
            entity = session.scalar(
                select(Entity).where(Entity.canonical_name == canonical_name)
            )
            if entity is None:
                entity = Entity(
                    source=source,
                    entity_type=entity_type,
                    canonical_name=canonical_name,
                    display_name=display_name,
                    url=url,
                )
                session.add(entity)
            else:
                entity.source = source
                entity.entity_type = entity_type
                entity.display_name = display_name
                entity.url = url
            session.commit()
            session.refresh(entity)
            return entity

    def get_entity_by_canonical_name(self, canonical_name: str) -> Entity | None:
        with self._session_factory() as session:
            return session.scalar(
                select(Entity).where(Entity.canonical_name == canonical_name)
            )

    def record_observation(
        self,
        *,
        entity_id: int,
        source: str,
        raw_payload: dict,
        normalized_payload: dict,
        dedupe_key: str,
        content_hash: str,
    ) -> Observation:
        with self._session_factory() as session:
            observation = Observation(
                entity_id=entity_id,
                source=source,
                raw_payload=raw_payload,
                normalized_payload=normalized_payload,
                dedupe_key=dedupe_key,
                content_hash=content_hash,
            )
            session.add(observation)
            session.commit()
            session.refresh(observation)
            return observation

    def get_latest_observation_for_entity(
        self,
        entity_id: int,
        *,
        source: str,
    ) -> Observation | None:
        with self._session_factory() as session:
            return session.scalar(
                select(Observation)
                .where(Observation.entity_id == entity_id, Observation.source == source)
                .order_by(Observation.observed_at.desc(), Observation.id.desc())
            )

    def create_alert(
        self,
        *,
        alert_type: str,
        entity_id: int,
        source: str,
        score: float,
        dedupe_key: str,
        reason: dict,
    ) -> Alert:
        with self._session_factory() as session:
            alert = Alert(
                alert_type=alert_type,
                entity_id=entity_id,
                source=source,
                score=score,
                dedupe_key=dedupe_key,
                reason=reason,
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def alert_exists(self, *, source: str, dedupe_key: str) -> bool:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(Alert).where(
                        Alert.source == source, Alert.dedupe_key == dedupe_key
                    )
                )
                is not None
            )

    def record_delivery_log(
        self,
        *,
        alert_id: int | None,
        channel: str,
        status: str,
        idempotency_key: str | None = None,
    ) -> DeliveryLog:
        with self._session_factory() as session:
            log = DeliveryLog(
                alert_id=alert_id,
                channel=channel,
                status=status,
                idempotency_key=idempotency_key or f"{alert_id or 'raw'}:{channel}",
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log

    def get_delivery_logs(self, *, alert_id: int | None) -> list[DeliveryLog]:
        with self._session_factory() as session:
            predicate = (
                DeliveryLog.alert_id.is_(None)
                if alert_id is None
                else DeliveryLog.alert_id == alert_id
            )
            return list(
                session.scalars(
                    select(DeliveryLog).where(predicate)
                )
            )

    def record_job_run(self, *, job_name: str, status: str) -> JobRun:
        with self._session_factory() as session:
            job_run = JobRun(job_name=job_name, status=status)
            session.add(job_run)
            session.commit()
            session.refresh(job_run)
            return job_run

    def list_alerts(self, *, limit: int = 100, offset: int = 0) -> list[Alert]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Alert).order_by(Alert.id.desc()).limit(limit).offset(offset)
                )
            )

    def get_alert(self, alert_id: int) -> Alert | None:
        with self._session_factory() as session:
            return session.scalar(select(Alert).where(Alert.id == alert_id))

    def list_report_days(self) -> list[str]:
        with self._session_factory() as session:
            created_at_rows = session.execute(
                select(Alert.created_at).order_by(Alert.created_at.desc(), Alert.id.desc())
            )
            seen_days: set[str] = set()
            ordered_days: list[str] = []
            for created_at, in created_at_rows:
                day = created_at.date().isoformat()
                if day in seen_days:
                    continue
                seen_days.add(day)
                ordered_days.append(day)
            return ordered_days

    def list_alerts_for_day(self, day: str) -> list[dict]:
        start = datetime.fromisoformat(f"{day}T00:00:00+00:00")
        end = start + timedelta(days=1)
        with self._session_factory() as session:
            rows = session.execute(
                select(Alert, Entity)
                .join(Entity, Entity.id == Alert.entity_id)
                .where(Alert.created_at >= start, Alert.created_at < end)
                .order_by(Alert.score.desc(), Alert.created_at.desc(), Alert.id.desc())
            )
            return [
                {
                    "id": alert.id,
                    "alert_type": alert.alert_type,
                    "entity_id": alert.entity_id,
                    "source": alert.source,
                    "score": alert.score,
                    "dedupe_key": alert.dedupe_key,
                    "reason": alert.reason,
                    "created_at": alert.created_at.isoformat(),
                    "status": alert.status,
                    "display_name": entity.display_name,
                    "canonical_name": entity.canonical_name,
                    "url": entity.url,
                }
                for alert, entity in rows
            ]

    def get_digest_candidates(self, *, limit: int = 50, window_hours: int = 24) -> list[Alert]:
        """Return recent alerts ranked by score descending, up to *limit* rows."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Alert)
                    .where(Alert.created_at >= cutoff)
                    .order_by(Alert.score.desc())
                    .limit(limit)
                )
            )
