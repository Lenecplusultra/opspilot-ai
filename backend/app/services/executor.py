"""The single entry point for running tools.

The REST API, the MCP server and therefore the LangChain agent all go through
invoke_tool() and decide_approval(), so RBAC, the approval gate and audit
logging cannot be bypassed by adding a new caller.

Concurrency guarantees (tested against PostgreSQL in tests/test_postgres.py):
- Two conflicting requests on one resource: a partial unique index allows only
  one *pending* request per resource_key; the loser gets status 'conflict'.
- Two approvers deciding one request: the request row is locked with
  SELECT ... FOR UPDATE and moved out of 'pending' with a compare-and-set, so
  exactly one decision wins and the action runs once.
- Destructive handlers lock the rows they change (service, flag, DLQ message).
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.rbac import has_role
from app.models import ApprovalRequest, AuditLog, User, utcnow
from app.tools import REGISTRY

Status = Literal["executed", "pending_approval", "denied", "invalid", "unknown_tool", "conflict", "failed"]
Channel = Literal["api", "agent", "mcp"]


class ToolResult(BaseModel):
    status: Status
    message: str = ""
    data: dict[str, Any] | None = None
    approval_id: int | None = None


class ApprovalError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def record_audit(db: Session, user: User, tool_name: str, params: dict, outcome: str, detail: str = "",
                 approval_id: int | None = None, channel: str = "api") -> None:
    db.add(AuditLog(user_id=user.id, role=user.role, channel=channel, tool_name=tool_name, params=params,
                    outcome=outcome, detail=detail[:2000], approval_id=approval_id))


def invoke_tool(db: Session, user: User, tool_name: str, raw_params: dict, channel: Channel = "api") -> ToolResult:
    def finish(params: dict, result: ToolResult) -> ToolResult:
        record_audit(db, user, tool_name, params, result.status, result.message, result.approval_id, channel)
        db.commit()
        return result

    tool = REGISTRY.get(tool_name)
    if tool is None:
        return finish(raw_params, ToolResult(status="unknown_tool", message=f"no such tool '{tool_name}'"))

    try:
        params = tool.params_model(**(raw_params or {}))
    except ValidationError as exc:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return finish(raw_params, ToolResult(status="invalid", message=detail))
    clean = params.model_dump()

    if not has_role(user.role, tool.min_role):
        return finish(clean, ToolResult(
            status="denied", message=f"{tool_name} requires role {tool.min_role.name.lower()} or higher"))

    if not tool.destructive:
        try:
            with db.begin_nested():
                data = tool.handler(db, params)
        except Exception as exc:  # a tool failure is a normal, audited outcome
            return finish(clean, ToolResult(status="failed", message=str(exc)))
        return finish(clean, ToolResult(status="executed", data=data))

    # Destructive: never run now. Validate the target exists, then queue for approval.
    resource = tool.resource(params)
    request = ApprovalRequest(requested_by=user.id, tool_name=tool_name, params=clean, resource_key=resource,
                              reason=getattr(params, "reason", "") or "", status="pending")
    try:
        with db.begin_nested():
            db.add(request)
            db.flush()
    except IntegrityError:
        return finish(clean, ToolResult(
            status="conflict", message=f"another request for {resource} is already pending approval"))
    return finish(clean, ToolResult(
        status="pending_approval", approval_id=request.id,
        message=f"approval request #{request.id} created; needs a {tool.approver_role.name.lower()} "
                f"or higher to approve. Nothing has been executed yet."))


def decide_approval(db: Session, approval_id: int, approver: User, approve: bool) -> ApprovalRequest:
    # Row lock (real on PostgreSQL) so concurrent deciders serialize on this request.
    request = db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
    ).scalar_one_or_none()
    if request is None:
        db.rollback()
        raise ApprovalError(404, "approval request not found")
    tool = REGISTRY[request.tool_name]

    def deny(message: str):
        record_audit(db, approver, request.tool_name, request.params, "denied", message, request.id)
        db.commit()
        raise ApprovalError(403, message)

    if not has_role(approver.role, tool.approver_role):
        deny(f"approving {tool.name} requires role {tool.approver_role.name.lower()} or higher")
    if request.requested_by == approver.id:
        deny("you cannot decide your own request")

    # Compare-and-set: only one decider can move the request out of 'pending',
    # even where FOR UPDATE is a no-op (SQLite).
    claimed = db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == request.id, ApprovalRequest.status == "pending")
        .values(status="executing" if approve else "rejected", decided_by=approver.id, decided_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise ApprovalError(409, "request was already decided")
    db.refresh(request)

    if not approve:
        record_audit(db, approver, tool.name, request.params, "rejected", "", request.id)
        db.commit()
        return request

    record_audit(db, approver, tool.name, request.params, "approved", "", request.id)
    try:
        with db.begin_nested():
            data = tool.handler(db, tool.params_model(**request.params))
        request.status, request.result, outcome = "executed", json.dumps(data), "executed"
    except Exception as exc:
        request.status, request.result, outcome = "failed", str(exc), "failed"
    record_audit(db, approver, tool.name, request.params, outcome, request.result or "", request.id)
    db.commit()
    return request
