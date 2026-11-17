from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.rbac import Role


class ToolError(Exception):
    """A tool failed for a reason the caller should see (bad target, bad state)."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params_model: type[BaseModel]
    min_role: Role  # lowest role allowed to invoke (or request) the tool
    handler: Callable[[Session, BaseModel], dict]
    destructive: bool = False
    approver_role: Role | None = None  # lowest role allowed to approve a request
    resource: Callable[[BaseModel], str] | None = None  # key used to detect conflicting requests

    def __post_init__(self):
        if self.destructive and (self.approver_role is None or self.resource is None):
            raise ValueError(f"{self.name}: destructive tools need approver_role and resource")
