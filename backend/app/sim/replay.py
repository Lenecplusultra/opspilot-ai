"""Event replay: rebuild the simulated fleet from a recorded event log.

A scenario is a JSON file holding an ordered list of events (deploys, injected
faults, log lines, metric series, order events, dead-lettered messages, commits).
Replaying it into an empty fleet reproduces exactly the same incident state every
time. The dev seed uses it for the demo, and the eval harness uses it to give the
agent an identical starting point on every run.

Timestamps are stored relative to replay time ("minutes_ago") so a replayed
incident always looks like it is happening now.
"""

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    CodeChange,
    DLQMessage,
    DomainEvent,
    FeatureFlag,
    LogEntry,
    MetricSample,
    Service,
    utcnow,
)

SCENARIO_DIR = Path(__file__).parent / "scenarios"
FLEET_TABLES = [MetricSample, LogEntry, DomainEvent, DLQMessage, CodeChange, FeatureFlag, Service]


class ScenarioError(ValueError):
    pass


def list_scenarios() -> list[dict]:
    out = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        out.append({"name": path.stem, "description": data.get("description", "")})
    return out


def load_events(name: str) -> list[dict]:
    """Resolve a scenario (following 'extends') into one flat event list."""
    path = SCENARIO_DIR / f"{name}.json"
    if not path.is_file() or path.parent != SCENARIO_DIR:
        raise ScenarioError(f"unknown scenario '{name}'")
    data = json.loads(path.read_text())
    base = load_events(data["extends"]) if data.get("extends") else []
    return base + data["events"]


def _ago(now: dt.datetime, minutes: float) -> dt.datetime:
    return now - dt.timedelta(minutes=minutes)


def _jitter(key: str, spread: float) -> float:
    """Deterministic noise in [-spread, +spread] so replays are reproducible."""
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF * 2 - 1) * spread


def _service(db: Session, name: str) -> Service:
    svc = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
    if svc is None:
        raise ScenarioError(f"event references unknown service '{name}'")
    return svc


def apply_event(db: Session, ev: dict[str, Any], now: dt.datetime) -> None:
    kind = ev["type"]
    at = _ago(now, ev.get("minutes_ago", 0))

    if kind == "service_registered":
        db.add(Service(name=ev["service"], version=ev["version"], previous_version=ev.get("previous_version"),
                       depends_on=ev.get("depends_on", []), status="healthy", deployed_at=at))
        db.flush()
    elif kind == "deploy":
        svc = _service(db, ev["service"])
        svc.previous_version, svc.version, svc.deployed_at = svc.version, ev["version"], at
    elif kind == "fault_injected":
        svc = _service(db, ev["service"])
        svc.fault, svc.status = ev["fault"], ev.get("status", "degraded")
    elif kind == "service_restarted":
        svc = _service(db, ev["service"])
        svc.restart_count += 1
        if svc.fault == "stuck":
            svc.fault, svc.status = None, "healthy"
    elif kind == "flag_set":
        flag = db.execute(select(FeatureFlag).where(FeatureFlag.name == ev["flag"])).scalar_one_or_none()
        if flag is None:
            db.add(FeatureFlag(name=ev["flag"], enabled=ev["enabled"]))
        else:
            flag.enabled = ev["enabled"]
    elif kind == "log":
        db.add(LogEntry(service_name=ev["service"], level=ev["level"], message=ev["message"],
                        trace_id=ev.get("trace_id"), occurred_at=at))
    elif kind == "metric_baseline":
        # 13 samples, one every 5 minutes over the last hour, around a steady value.
        for i in range(13):
            minutes = 60 - i * 5
            value = ev["value"] + _jitter(f"{ev['service']}:{ev['metric']}:{i}", ev.get("jitter", 0))
            db.add(MetricSample(service_name=ev["service"], metric=ev["metric"],
                                value=round(max(value, 0), 2), recorded_at=_ago(now, minutes)))
    elif kind == "metric_series":
        # Explicit values, oldest first, the last one recorded 'now'. Replaces any
        # baseline for the same metric so the incident series is the only one.
        db.flush()
        db.execute(delete(MetricSample).where(MetricSample.service_name == ev["service"],
                                              MetricSample.metric == ev["metric"]))
        step = ev.get("interval_minutes", 5)
        values = ev["values"]
        for i, value in enumerate(values):
            db.add(MetricSample(service_name=ev["service"], metric=ev["metric"], value=value,
                                recorded_at=_ago(now, (len(values) - 1 - i) * step)))
    elif kind == "order_event":
        db.add(DomainEvent(order_id=ev["order_id"], trace_id=ev["trace_id"], service_name=ev["service"],
                           event_type=ev["event_type"], status=ev["status"], detail=ev.get("detail", ""),
                           occurred_at=at))
    elif kind == "dead_lettered":
        db.add(DLQMessage(consumer=ev["consumer"], event_type=ev["event_type"], order_id=ev["order_id"],
                          trace_id=ev["trace_id"], error=ev["error"], attempts=ev.get("attempts", 3),
                          created_at=at))
    elif kind == "commit":
        db.add(CodeChange(sha=ev["sha"], service_name=ev["service"], message=ev["message"],
                          author=ev["author"], committed_at=at))
    else:
        raise ScenarioError(f"unknown event type '{kind}'")


def reset_fleet(db: Session) -> None:
    for model in FLEET_TABLES:
        db.execute(delete(model))
    # Pending approvals refer to the old fleet; cancel them rather than leave them actionable.
    db.execute(update(ApprovalRequest).where(ApprovalRequest.status == "pending").values(status="cancelled"))


def replay(db: Session, name: str, now: dt.datetime | None = None) -> int:
    """Wipe the fleet and replay a scenario. Returns the number of events applied."""
    events = load_events(name)
    now = now or utcnow()
    reset_fleet(db)
    for ev in events:
        apply_event(db, ev, now)
    db.commit()
    return len(events)
