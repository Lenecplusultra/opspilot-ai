"""RBAC, approval gate and audit log, at the executor level."""

import pytest
from sqlalchemy import select

from app.models import ApprovalRequest, AuditLog, FeatureFlag, ImmutableRecordError, Service
from app.services.executor import ApprovalError, decide_approval, invoke_tool
from app.tools import REGISTRY


def svc(db, name):
    db.expire_all()
    return db.execute(select(Service).where(Service.name == name)).scalar_one()


def outcomes(db):
    return [a.outcome for a in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]


def test_there_are_twelve_tools_four_destructive():
    assert len(REGISTRY) == 12
    assert sorted(t.name for t in REGISTRY.values() if t.destructive) == [
        "replay_dlq_message", "restart_service", "rollback_deploy", "toggle_feature_flag"]


def test_viewer_can_read_and_it_is_audited(db, users):
    r = invoke_tool(db, users["viewer"], "get_service_status", {"service": "orders-api"})
    assert r.status == "executed" and r.data["version"] == "2.4.1"
    assert outcomes(db) == ["executed"]


@pytest.mark.parametrize("tool,params", [
    ("restart_service", {"service": "orders-api"}),
    ("rollback_deploy", {"service": "orders-api"}),
    ("toggle_feature_flag", {"flag": "new-checkout", "enabled": True}),
    ("replay_dlq_message", {"message_id": 1}),
])
def test_viewer_cannot_request_any_destructive_tool(db, users, tool, params):
    r = invoke_tool(db, users["viewer"], tool, params)
    assert r.status == "denied"
    assert db.execute(select(ApprovalRequest)).first() is None
    assert outcomes(db) == ["denied"]


def test_engineer_cannot_request_rollback(db, users):
    assert invoke_tool(db, users["engineer"], "rollback_deploy", {"service": "orders-api"}).status == "denied"


def test_restart_does_not_run_until_approved(db, users):
    r = invoke_tool(db, users["engineer"], "restart_service", {"service": "payments-worker", "reason": "stuck"})
    assert r.status == "pending_approval" and r.approval_id
    assert svc(db, "payments-worker").restart_count == 0
    assert svc(db, "payments-worker").status == "degraded"

    req = decide_approval(db, r.approval_id, users["sre"], approve=True)
    assert req.status == "executed" and req.reason == "stuck"
    assert svc(db, "payments-worker").restart_count == 1
    assert svc(db, "payments-worker").status == "healthy"
    assert outcomes(db) == ["pending_approval", "approved", "executed"]


def test_rejected_request_never_executes(db, users):
    r = invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"})
    req = decide_approval(db, r.approval_id, users["sre"], approve=False)
    assert req.status == "rejected" and svc(db, "orders-api").restart_count == 0
    assert outcomes(db)[-1] == "rejected"


def test_requester_cannot_approve_own_request(db, users):
    r = invoke_tool(db, users["sre"], "restart_service", {"service": "orders-api"})
    with pytest.raises(ApprovalError) as e:
        decide_approval(db, r.approval_id, users["sre"], approve=True)
    assert e.value.status_code == 403
    assert svc(db, "orders-api").restart_count == 0
    decide_approval(db, r.approval_id, users["sre2"], approve=True)  # a different SRE can
    assert svc(db, "orders-api").restart_count == 1


def test_underprivileged_approver_is_denied_and_audited(db, users):
    r = invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"})
    with pytest.raises(ApprovalError) as e:
        decide_approval(db, r.approval_id, users["viewer"], approve=True)
    assert e.value.status_code == 403
    assert outcomes(db)[-1] == "denied"


def test_rollback_needs_admin_approval_not_sre(db, users):
    r = invoke_tool(db, users["sre"], "rollback_deploy", {"service": "orders-api"})
    with pytest.raises(ApprovalError):
        decide_approval(db, r.approval_id, users["sre2"], approve=True)
    decide_approval(db, r.approval_id, users["admin"], approve=True)
    assert svc(db, "orders-api").version == "2.4.0"


def test_second_decision_on_same_request_is_rejected(db, users):
    r = invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"})
    decide_approval(db, r.approval_id, users["sre"], approve=True)
    with pytest.raises(ApprovalError) as e:
        decide_approval(db, r.approval_id, users["admin"], approve=True)
    assert e.value.status_code == 409
    assert svc(db, "orders-api").restart_count == 1  # ran exactly once


def test_conflicting_pending_request_on_same_service_is_blocked(db, users):
    first = invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"})
    second = invoke_tool(db, users["sre"], "rollback_deploy", {"service": "orders-api"})
    assert first.status == "pending_approval" and second.status == "conflict"
    decide_approval(db, first.approval_id, users["sre"], approve=False)  # frees the resource
    assert invoke_tool(db, users["sre"], "rollback_deploy", {"service": "orders-api"}).status == "pending_approval"


def test_requests_on_different_resources_do_not_conflict(db, users):
    assert invoke_tool(db, users["engineer"], "restart_service", {"service": "orders-api"}).status == "pending_approval"
    assert invoke_tool(db, users["engineer"], "restart_service", {"service": "api-gateway"}).status == "pending_approval"


def test_failed_execution_is_recorded_and_state_unchanged(db, users):
    r = invoke_tool(db, users["engineer"], "replay_dlq_message", {"message_id": 1})
    req = decide_approval(db, r.approval_id, users["sre"], approve=True)  # payments-worker still stuck
    assert req.status == "failed" and "still unhealthy" in req.result
    assert outcomes(db)[-1] == "failed"


def test_invalid_params_and_unknown_tool_are_audited(db, users):
    assert invoke_tool(db, users["viewer"], "query_metrics", {"service": "x", "metric": "nope"}).status == "invalid"
    assert invoke_tool(db, users["viewer"], "drop_database", {}).status == "unknown_tool"
    assert outcomes(db) == ["invalid", "unknown_tool"]


def test_feature_flag_toggle_via_approval(db, users):
    r = invoke_tool(db, users["engineer"], "toggle_feature_flag", {"flag": "new-checkout", "enabled": True})
    decide_approval(db, r.approval_id, users["sre"], approve=True)
    db.expire_all()
    assert db.execute(select(FeatureFlag).where(FeatureFlag.name == "new-checkout")).scalar_one().enabled


def test_audit_records_channel(db, users):
    invoke_tool(db, users["viewer"], "list_services", {}, channel="agent")
    assert db.execute(select(AuditLog.channel)).scalar_one() == "agent"


def test_audit_rows_cannot_be_updated_or_deleted_through_orm(db, users):
    invoke_tool(db, users["viewer"], "get_service_status", {"service": "orders-api"})
    row = db.execute(select(AuditLog)).scalars().first()
    row.detail = "tampered"
    with pytest.raises(ImmutableRecordError):
        db.flush()
    db.rollback()
    db.delete(db.execute(select(AuditLog)).scalars().first())
    with pytest.raises(ImmutableRecordError):
        db.flush()
