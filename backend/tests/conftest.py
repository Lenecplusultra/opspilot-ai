"""Test fixtures.

By default tests use a throwaway SQLite file. Set TEST_DATABASE_URL to a
PostgreSQL URL to run the whole suite (plus the Postgres-only locking tests)
against Postgres; CI does this.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

import app.models  # noqa: F401
from app.api.deps import get_llm
from app.db.seed import seed
from app.db.session import Base, get_session_factory, make_engine, make_session_factory
from app.main import app as fastapi_app
from app.models import User

PG_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture()
def engine(tmp_path):
    if PG_URL:
        eng = make_engine(PG_URL)
        Base.metadata.drop_all(eng)
    else:
        eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")

        @event.listens_for(eng, "connect")
        def _wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA busy_timeout=5000")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    factory = make_session_factory(engine)
    with factory() as db:
        seed(db, "payments_stuck_worker", rounds=4)  # low bcrypt cost: tests only
    return factory


@pytest.fixture()
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def users(db):
    return {u.email.split("@")[0]: u for u in db.execute(select(User)).scalars()}


@pytest.fixture()
def llm_holder():
    return {"llm": None}


@pytest.fixture()
def client(session_factory, llm_holder):
    def _llm():
        if llm_holder["llm"] is None:
            from fastapi import HTTPException
            raise HTTPException(503, "agent not configured")
        return llm_holder["llm"]

    fastapi_app.dependency_overrides[get_session_factory] = lambda: session_factory
    fastapi_app.dependency_overrides[get_llm] = _llm
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


def login(client, who: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{who}@opspilot.dev", "password": "password"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
