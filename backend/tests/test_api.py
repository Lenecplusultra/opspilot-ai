from tests.conftest import login


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@opspilot.dev", "password": "wrong"})
    assert r.status_code == 401


def test_requires_token(client):
    assert client.get("/api/tools").status_code == 401
    assert client.get("/api/tools", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_tool_list_is_filtered_by_role(client):
    viewer = {t["name"] for t in client.get("/api/tools", headers=login(client, "viewer")).json()}
    admin = {t["name"] for t in client.get("/api/tools", headers=login(client, "admin")).json()}
    assert "restart_service" not in viewer and len(viewer) == 8 and len(admin) == 12


def test_full_approval_flow_over_http(client):
    eng, sre = login(client, "engineer"), login(client, "sre")
    r = client.post("/api/tools/restart_service/invoke",
                    json={"params": {"service": "payments-worker", "reason": "stuck"}}, headers=eng)
    assert r.status_code == 202
    approval_id = r.json()["approval_id"]

    mine = client.get("/api/approvals", headers=eng).json()
    assert [a["id"] for a in mine] == [approval_id] and mine[0]["requested_by"] == "engineer@opspilot.dev"
    assert client.get("/api/approvals", headers=login(client, "viewer")).json() == []  # not theirs

    assert client.post(f"/api/approvals/{approval_id}/approve", headers=eng).status_code == 403
    done = client.post(f"/api/approvals/{approval_id}/approve", headers=sre)
    assert done.status_code == 200 and done.json()["status"] == "executed"
    assert done.json()["decided_by"] == "sre@opspilot.dev"
    assert client.post(f"/api/approvals/{approval_id}/approve", headers=sre).status_code == 409

    trail = [a["outcome"] for a in client.get("/api/audit", headers=sre).json()]
    # newest first; the engineer's self-approval attempt is in the trail too
    assert trail[:4] == ["executed", "approved", "denied", "pending_approval"]


def test_audit_requires_sre_and_filters(client):
    assert client.get("/api/audit", headers=login(client, "engineer")).status_code == 403
    v = login(client, "viewer")
    client.post("/api/tools/restart_service/invoke", json={"params": {"service": "orders-api"}}, headers=v)
    denied = client.get("/api/audit?outcome=denied", headers=login(client, "sre")).json()
    assert len(denied) == 1 and denied[0]["user"] == "viewer@opspilot.dev"


def test_status_codes_map_tool_outcomes(client):
    h = login(client, "engineer")
    assert client.post("/api/tools/nope/invoke", json={}, headers=h).status_code == 404
    assert client.post("/api/tools/query_metrics/invoke", json={"params": {}}, headers=h).status_code == 422
    assert client.post("/api/tools/list_services/invoke", json={}, headers=h).status_code == 200
    client.post("/api/tools/restart_service/invoke", json={"params": {"service": "orders-api"}}, headers=h)
    assert client.post("/api/tools/restart_service/invoke", json={"params": {"service": "orders-api"}},
                       headers=h).status_code == 409


def test_system_overview(client):
    data = client.get("/api/system/overview", headers=login(client, "viewer")).json()
    pw = next(s for s in data["services"] if s["service"] == "payments-worker")
    assert pw["status"] == "degraded" and pw["dlq_dead"] == 3 and len(pw["series"]["error_rate"]) > 5
    assert data["dlq_dead_total"] == 3


def test_scenario_replay_is_admin_only(client):
    assert client.post("/api/system/scenarios/baseline/replay", headers=login(client, "sre")).status_code == 403
    r = client.post("/api/system/scenarios/inventory_bad_deploy/replay", headers=login(client, "admin"))
    assert r.status_code == 200
    names = {s["name"] for s in client.get("/api/system/scenarios", headers=login(client, "viewer")).json()}
    assert "inventory_bad_deploy" in names
    assert client.post("/api/system/scenarios/nope/replay", headers=login(client, "admin")).status_code == 404
