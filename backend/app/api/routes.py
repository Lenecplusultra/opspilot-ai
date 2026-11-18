import datetime as dt
import logging
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.agents.agent import run_agent
from app.agents.errors import describe_agent_error
from app.api.deps import current_user, get_llm, require_role
from app.connectors import metrics as metrics_conn
from app.core.config import settings
from app.core.rbac import Role, has_role
from app.core.security import create_access_token, verify_password
from app.db.session import get_db, get_session_factory
from app.models import ApprovalRequest, AuditLog, DLQMessage, Service, User
from app.services.executor import ApprovalError, decide_approval, invoke_tool
from app.sim.replay import ScenarioError, list_scenarios, replay
from app.tools import REGISTRY

router = APIRouter()
log = logging.getLogger("opspilot.api")

HTTP_STATUS = {"executed": 200, "failed": 200, "pending_approval": 202, "denied": 403,
               "unknown_tool": 404, "invalid": 422, "conflict": 409}


# ------------------------------------------------------------------ schemas


class LoginIn(BaseModel):
    email: str
    password: str


class InvokeIn(BaseModel):
    params: dict[str, Any] = {}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


class ApprovalOut(BaseModel):
    id: int
    tool_name: str
    params: dict
    reason: str
    status: str
    requested_by: str
    decided_by: str | None
    approver_role: str
    result: str | None
    created_at: dt.datetime
    decided_at: dt.datetime | None


class AuditOut(BaseModel):
    id: int
    user: str
    role: str
    channel: str
    tool_name: str
    params: dict
    outcome: str
    detail: str
    approval_id: int | None
    created_at: dt.datetime


# ------------------------------------------------------------------ auth


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "invalid credentials")
    return {"access_token": create_access_token(user.id), "role": user.role, "email": user.email}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role}


# ------------------------------------------------------------------ tools and agent


@router.get("/tools")
def list_tools(user: User = Depends(current_user)):
    """Tools the caller's role may invoke. The MCP server applies the same filter."""
    return [
        {"name": t.name, "description": t.description, "destructive": t.destructive,
         "min_role": t.min_role.name.lower(),
         "approver_role": t.approver_role.name.lower() if t.approver_role else None,
         "schema": t.params_model.model_json_schema()}
        for t in REGISTRY.values() if has_role(user.role, t.min_role)
    ]


@router.post("/tools/{name}/invoke")
def invoke(name: str, body: InvokeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = invoke_tool(db, user, name, body.params, channel="api")
    return JSONResponse(result.model_dump(), status_code=HTTP_STATUS[result.status])


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(current_user), llm: BaseChatModel = Depends(get_llm),
               factory: Callable[[], Session] = Depends(get_session_factory)):
    if body.messages[-1].role != "user":
        raise HTTPException(422, "last message must be from the user")
    try:
        run = await run_agent(llm, factory, user.id, [m.model_dump() for m in body.messages],
                              max_steps=settings.agent_max_steps)
    except Exception as exc:
        status, message = describe_agent_error(exc)
        log.exception("agent run failed: %s", message)
        raise HTTPException(status, message)
    return {
        "reply": run.reply,
        "stop_reason": run.stop_reason,
        "steps": [s.__dict__ for s in run.steps],
        "approval_ids": run.approval_ids,
    }


# ------------------------------------------------------------------ approvals


def _approval_rows(db: Session, *where) -> list[ApprovalOut]:
    requester, decider = aliased(User), aliased(User)
    rows = db.execute(
        select(ApprovalRequest, requester.email, decider.email)
        .join(requester, requester.id == ApprovalRequest.requested_by)
        .outerjoin(decider, decider.id == ApprovalRequest.decided_by)
        .where(*where).order_by(ApprovalRequest.id.desc()).limit(200)
    ).all()
    return [ApprovalOut(
        id=a.id, tool_name=a.tool_name, params=a.params, reason=a.reason, status=a.status,
        requested_by=req, decided_by=dec, approver_role=REGISTRY[a.tool_name].approver_role.name.lower(),
        result=a.result, created_at=a.created_at, decided_at=a.decided_at) for a, req, dec in rows]


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(status: str | None = "pending", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """SRE and above see the whole queue; everyone else sees only their own requests."""
    where = [ApprovalRequest.status == status] if status else []
    if not has_role(user.role, Role.SRE):
        where.append(ApprovalRequest.requested_by == user.id)
    return _approval_rows(db, *where)


def _decide(approval_id: int, approve: bool, user: User, db: Session) -> ApprovalOut:
    try:
        decide_approval(db, approval_id, user, approve)
    except ApprovalError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return _approval_rows(db, ApprovalRequest.id == approval_id)[0]


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
def approve(approval_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _decide(approval_id, True, user, db)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
def reject(approval_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _decide(approval_id, False, user, db)


# ------------------------------------------------------------------ audit


@router.get("/audit", response_model=list[AuditOut])
def audit(limit: int = 100, outcome: str | None = None, tool: str | None = None, channel: str | None = None,
          _: User = Depends(require_role(Role.SRE)), db: Session = Depends(get_db)):
    q = (select(AuditLog, User.email).join(User, User.id == AuditLog.user_id)
         .order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 500)))
    if outcome:
        q = q.where(AuditLog.outcome == outcome)
    if tool:
        q = q.where(AuditLog.tool_name == tool)
    if channel:
        q = q.where(AuditLog.channel == channel)
    return [AuditOut(id=a.id, user=email, role=a.role, channel=a.channel, tool_name=a.tool_name, params=a.params,
                     outcome=a.outcome, detail=a.detail, approval_id=a.approval_id, created_at=a.created_at)
            for a, email in db.execute(q).all()]


# ------------------------------------------------------------------ system health (dashboard)


@router.get("/system/overview")
def overview(_: User = Depends(current_user), db: Session = Depends(get_db)):
    services = db.execute(select(Service).order_by(Service.name)).scalars().all()
    dead = dict(db.execute(select(DLQMessage.consumer, func.count()).where(DLQMessage.status == "dead")
                           .group_by(DLQMessage.consumer)).all())
    pending = db.execute(select(func.count()).select_from(ApprovalRequest)
                         .where(ApprovalRequest.status == "pending")).scalar_one()
    out = []
    for s in services:
        out.append({
            "service": s.name, "status": s.status, "version": s.version, "depends_on": s.depends_on,
            "restart_count": s.restart_count, "dlq_dead": dead.get(s.name, 0),
            "metrics": metrics_conn.latest_snapshot(db, s.name),
            "series": {m: [p["value"] for p in metrics_conn.summarize(db, s.name, m, 60).get("points", [])]
                       for m in ("error_rate", "latency_p95_ms")},
        })
    return {"services": out, "dlq_dead_total": sum(dead.values()), "pending_approvals": pending}


@router.get("/system/scenarios")
def scenarios(_: User = Depends(current_user)):
    return list_scenarios()


@router.post("/system/scenarios/{name}/replay")
def replay_scenario(name: str, _: User = Depends(require_role(Role.ADMIN)), db: Session = Depends(get_db)):
    try:
        count = replay(db, name)
    except ScenarioError as exc:
        raise HTTPException(404, str(exc))
    return {"scenario": name, "events_replayed": count}
