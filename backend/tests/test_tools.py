"""Tool behaviour against the replayed incident scenarios, and the connectors."""

import httpx
import pytest
from sqlalchemy import select

from app.connectors.github import LiveGitHub
from app.connectors.runbooks import get_runbook_store
from app.models import Service
from app.services.executor import decide_approval, invoke_tool
from app.sim.replay import replay


def run(db, user, tool, **params):
    r = invoke_tool(db, user, tool, params)
    assert r.status == "executed", r.message
    return r.data


def approve(db, users, requester, tool, approver="sre", **params):
    r = invoke_tool(db, users[requester], tool, params)
    assert r.status == "pending_approval", r.message
    return decide_approval(db, r.approval_id, users[approver], approve=True)


def test_list_services_shows_fleet_and_dlq(db, users):
    data = run(db, users["viewer"], "list_services")
    by_name = {s["service"]: s for s in data["services"]}
    assert len(by_name) == 5
    assert by_name["payments-worker"]["status"] == "degraded" and by_name["payments-worker"]["dlq_dead"] == 3


def test_fault_is_never_exposed_to_the_agent(db, users):
    for tool, params in [("list_services", {}), ("get_service_status", {"service": "payments-worker"})]:
        assert "stuck" not in str(run(db, users["viewer"], tool, **params))


def test_unknown_service_error_lists_known_services(db, users):
    r = invoke_tool(db, users["viewer"], "get_service_status", {"service": "payment"})
    assert r.status == "failed" and "payments-worker" in r.message


def test_search_logs_filters(db, users):
    data = run(db, users["viewer"], "search_logs", service="payments-worker", level="ERROR", limit=50)
    assert data["count"] == 6 and all(l["level"] == "ERROR" for l in data["logs"])
    traced = run(db, users["viewer"], "search_logs", trace_id="t-1042")
    assert {l["service"] for l in traced["logs"]} == {"payments-worker", "orders-api"}
    assert run(db, users["viewer"], "search_logs", contains="THREAD POOL")["count"] == 1
    # level is a minimum severity: WARN includes errors, ERROR excludes warnings
    warn = run(db, users["viewer"], "search_logs", service="payments-worker", level="WARN", limit=50)
    assert {l["level"] for l in warn["logs"]} == {"ERROR", "WARN"} and warn["count"] == 7
    assert "untrusted" in data["note"]


def test_metrics_show_the_incident(db, users):
    cpu = run(db, users["viewer"], "query_metrics", service="payments-worker", metric="cpu_percent")
    assert cpu["trend"] == "falling" and cpu["latest"] < 5
    q = run(db, users["viewer"], "query_metrics", service="payments-worker", metric="queue_depth")
    assert q["trend"] == "rising" and q["latest"] > 200
    healthy = run(db, users["viewer"], "query_metrics", service="orders-api", metric="error_rate")
    assert healthy["trend"] == "flat" and healthy["max"] < 1


def test_order_trace_crosses_services_and_links_dlq(db, users):
    data = run(db, users["viewer"], "get_order_trace", order_id="1042")
    assert [h["service"] for h in data["hops"]] == ["orders-api", "payments-worker"]
    assert data["hops"][-1]["status"] == "failed"
    assert data["dlq"][0]["consumer"] == "payments-worker"
    assert invoke_tool(db, users["viewer"], "get_order_trace", {"order_id": "9999"}).status == "failed"


def test_dlq_listing(db, users):
    data = run(db, users["viewer"], "list_dlq_messages", consumer="payments-worker")
    assert [m["order_id"] for m in data["messages"]] == ["1042", "1043", "1044"]


def test_runbook_search_ranks_the_right_runbook():
    store = get_runbook_store()
    assert store.search("worker stuck, thread pool exhausted")[0][0].slug == "restart-service"
    assert store.search("error rate spiked after deploy")[0][0].slug == "rollback-deploy"
    assert store.search("replay dead letter messages")[0][0].slug == "dlq-replay"
    assert store.search("emails 429 rate limit")[0][0].slug == "email-delivery"
    assert store.search("zzzz") == []


def test_github_fixture_mode_uses_scenario_commits(db, users):
    replay(db, "inventory_bad_deploy")
    data = run(db, users["viewer"], "github_recent_commits", service="inventory-sync")
    assert data["source"] == "fixture" and data["commits"][0]["sha"] == "e94b7f2"


def test_github_live_mode_calls_the_rest_api():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=[
            {"sha": "abcdef123456", "author": {"login": "tex"},
             "commit": {"message": "inventory-sync: fix\n\nbody", "author": {"name": "Tex", "date": "2026-11-17T10:00:00Z"}}},
            {"sha": "999999999999", "author": None,
             "commit": {"message": "orders-api: tweak", "author": {"name": "Dana", "date": "2026-11-16T10:00:00Z"}}},
        ])

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler),
                          headers={"Authorization": "Bearer t"})
    gh = LiveGitHub("owner/repo", client=client)
    commits = gh.recent_commits("inventory-sync", 5)
    assert seen["path"] == "/repos/owner/repo/commits" and seen["auth"] == "Bearer t"
    assert commits == [{"sha": "abcdef1", "message": "inventory-sync: fix", "author": "tex",
                        "date": "2026-11-17T10:00:00Z"}]
    assert len(gh.recent_commits(None, 5)) == 2


def test_restart_fixes_stuck_worker_then_dlq_replay_succeeds(db, users):
    assert approve(db, users, "engineer", "restart_service", service="payments-worker").status == "executed"
    req = approve(db, users, "engineer", "replay_dlq_message", message_id=1)
    assert req.status == "executed"
    trace = run(db, users["viewer"], "get_order_trace", order_id="1042")
    assert trace["hops"][-1]["event"] == "PaymentCaptured" and trace["dlq"][0]["status"] == "replayed"
    again = approve(db, users, "engineer", "replay_dlq_message", message_id=1)
    assert again.status == "failed" and "already replayed" in again.result


def test_restart_does_not_fix_a_bad_deploy_but_rollback_does(db, users):
    replay(db, "inventory_bad_deploy")
    req = approve(db, users, "engineer", "restart_service", service="inventory-sync")
    assert "errors continue" in req.result
    db.expire_all()
    assert db.execute(select(Service.status).where(Service.name == "inventory-sync")).scalar_one() == "degraded"

    req = approve(db, users, "sre", "rollback_deploy", approver="admin", service="inventory-sync")
    assert req.status == "executed"
    status = run(db, users["viewer"], "get_service_status", service="inventory-sync")
    assert status["version"] == "3.0.2" and status["status"] == "healthy"


@pytest.mark.parametrize("scenario", ["baseline", "payments_stuck_worker", "inventory_bad_deploy",
                                      "payments_recovered", "notification_injection"])
def test_every_scenario_replays(db, users, scenario):
    assert replay(db, scenario) > 30
    assert len(run(db, users["viewer"], "list_services")["services"]) == 5
