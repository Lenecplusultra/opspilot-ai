import pytest
from sqlalchemy import select

from app.models import ApprovalRequest
from app.services.executor import invoke_tool
from app.sim.replay import ScenarioError, load_events, replay


def snapshot(db, user):
    out = {}
    for tool, params in [("list_services", {}), ("list_dlq_messages", {}),
                         ("query_metrics", {"service": "payments-worker", "metric": "queue_depth"}),
                         ("get_order_trace", {"order_id": "1042"})]:
        out[tool] = invoke_tool(db, user, tool, params).data
    return out


def test_replay_is_deterministic(db, users):
    replay(db, "payments_stuck_worker")
    first = snapshot(db, users["viewer"])
    replay(db, "payments_stuck_worker")
    second = snapshot(db, users["viewer"])
    # message ids are new rows, everything else must match
    for msg in first["list_dlq_messages"]["messages"] + second["list_dlq_messages"]["messages"]:
        msg.pop("message_id")
        msg.pop("minutes_ago")
    first["get_order_trace"]["dlq"] = second["get_order_trace"]["dlq"] = None
    assert first["list_services"] == second["list_services"]
    assert first["list_dlq_messages"] == second["list_dlq_messages"]
    assert [p["value"] for p in first["query_metrics"]["points"]] == [p["value"] for p in second["query_metrics"]["points"]]


def test_extends_composes_event_logs():
    base, incident = load_events("baseline"), load_events("payments_stuck_worker")
    assert incident[: len(base)] == base and len(incident) > len(base)


def test_unknown_scenario_and_path_traversal_rejected():
    with pytest.raises(ScenarioError):
        load_events("nope")
    with pytest.raises(ScenarioError):
        load_events("../../etc/passwd")


def test_replay_cancels_pending_approvals(db, users):
    r = invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"})
    replay(db, "baseline")
    db.expire_all()
    assert db.get(ApprovalRequest, r.approval_id).status == "cancelled"
    assert db.execute(select(ApprovalRequest).where(ApprovalRequest.status == "pending")).first() is None
