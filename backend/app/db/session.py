from typing import Callable

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str, **kwargs) -> Engine:
    """Build an engine. SQLite gets the documented fixes so SAVEPOINTs behave."""
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    else:
        kwargs.setdefault("pool_pre_ping", True)
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _no_driver_autobegin(dbapi_conn, _record):
            dbapi_conn.isolation_level = None

        @event.listens_for(engine, "begin")
        def _emit_begin(conn):
            conn.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)


def get_session_factory() -> Callable[[], Session]:
    """Overridden in tests. The agent needs a factory, not one session, because
    every MCP tool call opens its own short transaction."""
    return SessionLocal


def get_db(factory: Callable[[], Session] = Depends(get_session_factory)):
    db = factory()
    try:
        yield db
    finally:
        db.close()
