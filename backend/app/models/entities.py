import datetime as dt

from sqlalchemy import (
    DDL,
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ImmutableRecordError(Exception):
    """Raised when code tries to modify or delete an audit record."""


# ---------------------------------------------------------------- identity


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))


# ---------------------------------------------------------------- simulated fleet


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="healthy")  # healthy|degraded|down
    version: Mapped[str] = mapped_column(String(32))
    previous_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    # Hidden root cause used by the simulation. Never returned by any tool:
    # the agent has to infer it from logs, metrics, traces and deploys.
    # 'stuck' is cleared by a restart, 'bad_deploy' only by a rollback.
    fault: Mapped[str | None] = mapped_column(String(20), nullable=True)
    restart_count: Mapped[int] = mapped_column(default=0)
    deployed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(default=False)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[str] = mapped_column(String(10), index=True)
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MetricSample(Base):
    __tablename__ = "metric_samples"
    __table_args__ = (Index("ix_metric_lookup", "service_name", "metric", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DomainEvent(Base):
    """An event flowing between services for one order (the distributed trace)."""

    __tablename__ = "domain_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(32), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    service_name: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # ok|failed|retrying
    detail: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DLQMessage(Base):
    __tablename__ = "dlq_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    consumer: Mapped[str] = mapped_column(String(64), index=True)  # service that failed to process it
    event_type: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(String(32), index=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=3)
    status: Mapped[str] = mapped_column(String(16), default="dead", index=True)  # dead|replayed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CodeChange(Base):
    """Commit history used by the GitHub connector in fixture mode."""

    __tablename__ = "code_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha: Mapped[str] = mapped_column(String(40))
    service_name: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(64))
    committed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- control plane


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        # At most one pending request per resource. The database enforces this,
        # so two conflicting requests cannot both be created even under a race.
        Index(
            "uq_pending_resource",
            "resource_key",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON)
    resource_key: Mapped[str] = mapped_column(String(128), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    # pending -> rejected | executing -> executed | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Insert-only. Every tool call, approval decision and denial lands here."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(16), default="api")  # api|agent|mcp
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    params: Mapped[dict] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Layer 1: the ORM refuses to update or delete audit rows.
@event.listens_for(AuditLog, "before_update")
def _block_audit_update(*_):
    raise ImmutableRecordError("audit_logs rows cannot be updated")


@event.listens_for(AuditLog, "before_delete")
def _block_audit_delete(*_):
    raise ImmutableRecordError("audit_logs rows cannot be deleted")


# Layer 2: on PostgreSQL, a trigger refuses it too, so raw SQL cannot bypass the ORM.
_AUDIT_TRIGGER = DDL(
    """
    CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING MESSAGE = 'audit_logs is append-only: ' || TG_OP || ' blocked';
    END;
    $$ LANGUAGE plpgsql;
    CREATE TRIGGER audit_logs_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
    """
)
event.listen(AuditLog.__table__, "after_create", _AUDIT_TRIGGER.execute_if(dialect="postgresql"))
