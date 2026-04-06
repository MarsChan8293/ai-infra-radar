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

    def create_alert(
        self,
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

    def record_delivery_log(self, *, alert_id: int, channel: str, status: str) -> DeliveryLog:
        with self._session_factory() as session:
            log = DeliveryLog(
                alert_id=alert_id,
                channel=channel,
                status=status,
                idempotency_key=f"{alert_id}:{channel}",
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return log

    def record_job_run(self, *, job_name: str, status: str) -> JobRun:
        with self._session_factory() as session:
            job_run = JobRun(job_name=job_name, status=status)
            session.add(job_run)
            session.commit()
            session.refresh(job_run)
            return job_run
