from pathlib import Path

from sqlalchemy import create_engine as _create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from radar.core.models import Base


def create_engine_and_session_factory(db_path: Path) -> tuple[Engine, sessionmaker]:
    engine = _create_engine(f"sqlite:///{db_path}", future=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
