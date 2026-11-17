from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Service, User
from app.sim.replay import replay

USERS = [
    ("viewer@opspilot.dev", "viewer"),
    ("engineer@opspilot.dev", "engineer"),
    ("sre@opspilot.dev", "sre"),
    ("sre2@opspilot.dev", "sre"),
    ("admin@opspilot.dev", "admin"),
]


def seed_users(db: Session, password: str = "password", rounds: int = 12) -> None:
    if db.execute(select(User.id).limit(1)).first():
        return
    hashed = hash_password(password, rounds)
    db.add_all(User(email=e, hashed_password=hashed, role=r) for e, r in USERS)
    db.commit()


def seed(db: Session, scenario: str, password: str = "password", rounds: int = 12) -> None:
    """Create demo users, and replay a scenario if the fleet is empty."""
    seed_users(db, password, rounds)
    if not db.execute(select(Service.id).limit(1)).first():
        replay(db, scenario)
