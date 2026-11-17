"""Metrics connector over the time-series table the simulated fleet writes to."""

import datetime as dt
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MetricSample, utcnow

METRICS = ("latency_p95_ms", "error_rate", "cpu_percent", "queue_depth")


def _aware(ts: dt.datetime) -> dt.datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def series(db: Session, service: str, metric: str, minutes: int) -> list[tuple[float, float]]:
    """(minutes_ago, value) pairs, oldest first."""
    now = utcnow()
    since = now - dt.timedelta(minutes=minutes)
    rows = db.execute(
        select(MetricSample.recorded_at, MetricSample.value)
        .where(MetricSample.service_name == service, MetricSample.metric == metric,
               MetricSample.recorded_at >= since)
        .order_by(MetricSample.recorded_at)
    ).all()
    return [(round((now - _aware(ts)).total_seconds() / 60, 1), v) for ts, v in rows]


def summarize(db: Session, service: str, metric: str, minutes: int) -> dict:
    points = series(db, service, metric, minutes)
    if not points:
        return {"service": service, "metric": metric, "window_minutes": minutes, "samples": 0}
    values = [v for _, v in points]
    half = max(len(values) // 2, 1)
    early, late = mean(values[:half]), mean(values[half:]) if values[half:] else values[-1]
    if early == 0:
        trend = "rising" if late > 0 else "flat"
    else:
        change = (late - early) / early
        trend = "rising" if change > 0.25 else "falling" if change < -0.25 else "flat"
    return {
        "service": service, "metric": metric, "window_minutes": minutes, "samples": len(values),
        "latest": values[-1], "min": min(values), "max": max(values), "avg": round(mean(values), 2),
        "trend": trend,
        "points": [{"minutes_ago": m, "value": v} for m, v in points],
    }


def latest_snapshot(db: Session, service: str) -> dict[str, float]:
    out = {}
    for metric in METRICS:
        row = db.execute(
            select(MetricSample.value)
            .where(MetricSample.service_name == service, MetricSample.metric == metric)
            .order_by(MetricSample.recorded_at.desc()).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            out[metric] = row
    return out


def record(db: Session, service: str, values: dict[str, float]) -> None:
    now = utcnow()
    for metric, value in values.items():
        db.add(MetricSample(service_name=service, metric=metric, value=value, recorded_at=now))
