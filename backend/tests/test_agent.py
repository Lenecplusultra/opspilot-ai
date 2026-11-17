"""The LangChain agent loop, driven by a scripted model (no network)."""

import anyio
from sqlalchemy import select
from sqlalchemy.orm import object_session

from app.agents.agent import run_agent
from app.agents.llm import ScriptedChatModel
from app.models import AuditLog, Service
from tests.conftest import login


def agent(session_factory, user, script, history=None, max_steps=8):
    llm = ScriptedChatModel(script=script)
    history = history or [{"role": "user", "content": "order 1042 has not been charged"}]
    user_id = user.id
    user_session = object_session(user)
    if user_session is not None:
        user_session.rollback()  # end the test session's snapshot so it sees the agent's writes
    return anyio.run(lambda: run_agent(llm, session_factory, user_id, history, max_steps))


INVESTIGATE_AND_RESTART = [
    {"tool_calls": [{"name": "get_order_trace", "args": {"order_id": "1042"}}]},
    {"tool_calls": [{"name": "search_logs", "args": {"service": "payments-worker", "level": "ERROR"}},
                    {"name": "query_metrics", "args": {"service": "payments-worker", "metric": "cpu_percent"}}]},
    {"tool_calls": [{"name": "restart_service", "args": {"service": "payments-worker", "reason": "stuck threads"}}]},
    {"final": "payments-worker is stuck. I requested a restart; it needs approval."},
]


def test_agent_investigates_then_requests_approval(session_factory, users, db):
    run = agent(session_factory, users["engineer"], INVESTIGATE_AND_RESTART)
    assert [s.tool for s in run.steps] == ["get_order_trace", "search_logs", "query_metrics", "restart_service"]
    assert [s.status for s in run.steps] == ["executed"] * 3 + ["pending_approval"]
    assert len(run.approval_ids) == 1 and run.stop_reason == "final_answer"
    # Nothing destructive ran
    assert db.execute(select(Service.restart_count).where(Service.name == "payments-worker")).scalar_one() == 0
    # Every agent call is in the audit log, tagged with the agent channel
    assert {a.channel for a in db.execute(select(AuditLog)).scalars()} == {"agent"}
    assert db.execute(select(AuditLog)).scalars().all().__len__() == 4


def test_tools_hidden_by_rbac_are_unavailable_to_the_agent(session_factory, users, db):
    run = agent(session_factory, users["viewer"], [
        {"tool_calls": [{"name": "restart_service", "args": {"service": "orders-api"}}]},
        {"final": "You do not have permission to restart services."},
    ])
    assert run.steps[0].status == "unavailable"
    assert db.execute(select(AuditLog)).first() is None  # never reached the executor


def test_conflict_is_reported_back_to_the_model(session_factory, users):
    script = [
        {"tool_calls": [{"name": "restart_service", "args": {"service": "payments-worker"}},
                        {"name": "restart_service", "args": {"service": "payments-worker"}}]},
        {"final": "done"},
    ]
    run = agent(session_factory, users["engineer"], script)
    assert [s.status for s in run.steps] == ["pending_approval", "conflict"]


def test_agent_stops_at_max_steps(session_factory, users):
    loop = [{"tool_calls": [{"name": "list_services", "args": {}}]}] * 10
    run = agent(session_factory, users["viewer"], loop, max_steps=3)
    assert run.stop_reason == "max_steps" and len(run.steps) == 3


def test_chat_endpoint(client, llm_holder):
    llm_holder["llm"] = ScriptedChatModel(script=INVESTIGATE_AND_RESTART)
    r = client.post("/api/chat", headers=login(client, "engineer"),
                    json={"messages": [{"role": "user", "content": "order 1042 has not been charged"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("payments-worker is stuck")
    assert len(body["steps"]) == 4 and len(body["approval_ids"]) == 1


def test_chat_without_api_key_returns_503(client):
    r = client.post("/api/chat", headers=login(client, "viewer"),
                    json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503
