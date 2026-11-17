"""Concurrency and immutability guarantees that only a real PostgreSQL can prove.

Skipped unless TEST_DATABASE_URL points at Postgres (CI sets it).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import ApprovalRequest, AuditLog, Service, User
from app.services.executor import ApprovalError, decide_approval, invoke_tool
from tests.conftest import PG_URL

pytestmark = pytest.mark.skipif(not PG_URL.startswith("postgresql"), reason="needs TEST_DATABASE_URL (Postgres)")

WORKERS = 8


def in_thread_session(session_factory, user_id, fn):
    with session_factory() as s:
        return fn(s, s.get(User, user_id))


def race(session_factory, user_ids, fn):
    """Start len(user_ids) calls at the same instant, each in its own session and thread."""
    barrier = threading.Barrier(len(user_ids))

    def worker(uid):
        def go(s, u):
            barrier.wait()
            try:
                return fn(s, u)
            except ApprovalError as exc:
                return exc.status_code
        return in_thread_session(session_factory, uid, go)

    with ThreadPoolExecutor(len(user_ids)) as pool:
        return list(pool.map(worker, user_ids))


def restart_count(session_factory, name="payments-worker"):
    with session_factory() as s:
        return s.execute(select(Service.restart_count).where(Service.name == name)).scalar_one()


def test_concurrent_approvals_execute_exactly_once(session_factory, users, db):
    req = invoke_tool(db, users["engineer"], "restart_service", {"service": "payments-worker"})
    approvers = [users[w].id for w in ("sre", "sre2", "admin")] * 3
    results = race(session_factory, approvers[:WORKERS],
                   lambda s, u: decide_approval(s, req.approval_id, u, approve=True).status)

    assert results.count("executed") == 1
    assert sorted(r for r in results if r != "executed") == [409] * (WORKERS - 1)
    assert restart_count(session_factory) == 1
    with session_factory() as s:
        executed = s.execute(select(AuditLog).where(AuditLog.outcome == "executed")).scalars().all()
    assert len(executed) == 1


def test_concurrent_conflicting_requests_only_one_is_queued(session_factory, users):
    requesters = [users[w].id for w in ("engineer", "sre", "sre2", "admin")] * 2
    results = race(session_factory, requesters,
                   lambda s, u: invoke_tool(s, u, "restart_service", {"service": "orders-api"}).status)

    assert results.count("pending_approval") == 1 and results.count("conflict") == WORKERS - 1
    with session_factory() as s:
        pending = s.execute(select(ApprovalRequest).where(ApprovalRequest.status == "pending")).scalars().all()
    assert len(pending) == 1


def test_row_lock_blocks_a_concurrent_change_until_release(session_factory, users, db):
    """Session A holds FOR UPDATE on the service row. An approved restart in another
    session must wait for A instead of writing over it."""
    req = invoke_tool(db, users["engineer"], "restart_service", {"service": "payments-worker"})
    sre_id = users["sre"].id

    holder = session_factory()
    holder.execute(select(Service).where(Service.name == "payments-worker").with_for_update()).scalar_one()

    result = {}
    t = threading.Thread(target=lambda: result.update(status=in_thread_session(
        session_factory, sre_id, lambda s, u: decide_approval(s, req.approval_id, u, approve=True).status)))
    t.start()
    time.sleep(0.75)
    assert t.is_alive(), "approval should be blocked on the row lock"
    assert restart_count(session_factory) == 0

    holder.commit()  # release the lock
    holder.close()
    t.join(timeout=10)
    assert result["status"] == "executed"
    assert restart_count(session_factory) == 1


def test_audit_log_trigger_blocks_raw_sql(session_factory, users, db):
    invoke_tool(db, users["viewer"], "list_services", {})
    for statement in ("UPDATE audit_logs SET detail = 'tampered'", "DELETE FROM audit_logs"):
        with session_factory() as s, pytest.raises(DBAPIError, match="append-only"):
            s.execute(text(statement))
            s.commit()
    with session_factory() as s:
        assert s.execute(select(AuditLog.detail)).scalar_one() == ""
