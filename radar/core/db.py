from pathlib import Path

from sqlalchemy import create_engine as _create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from radar.core.models import Base


def create_engine_and_session_factory(db_path: Path) -> tuple[Engine, sessionmaker]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = _create_engine(f"sqlite:///{db_path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
