import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from app.agents.llm import AgentNotConfigured, make_openai_llm
from app.core.rbac import Role, has_role
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(401, "missing bearer token")
    try:
        user_id = int(decode_token(creds.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "unknown user")
    return user


def require_role(minimum: Role):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_role(user.role, minimum):
            raise HTTPException(403, f"requires role {minimum.name.lower()} or higher")
        return user
    return dep


def get_llm() -> BaseChatModel:
    """Overridden in tests with a scripted model."""
    try:
        return make_openai_llm()
    except AgentNotConfigured as exc:
        raise HTTPException(503, f"agent not configured: {exc}. Add it to your .env file.")
