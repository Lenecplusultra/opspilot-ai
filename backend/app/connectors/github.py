"""GitHub connector.

- Live mode (GITHUB_REPO=owner/repo set): calls the GitHub REST API for recent commits.
- Fixture mode (default): reads the commit history replayed from the active scenario,
  so incident scenarios have deploys that line up with their commits.
"""

from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CodeChange, utcnow


class GitHubError(Exception):
    pass


class GitHubConnector(Protocol):
    source: str

    def recent_commits(self, service: str | None, limit: int) -> list[dict]: ...


class FixtureGitHub:
    source = "fixture"

    def __init__(self, db: Session):
        self.db = db

    def recent_commits(self, service: str | None, limit: int) -> list[dict]:
        q = select(CodeChange).order_by(CodeChange.committed_at.desc()).limit(limit)
        if service:
            q = q.where(CodeChange.service_name == service)
        now = utcnow()
        out = []
        for c in self.db.execute(q).scalars():
            committed = c.committed_at if c.committed_at.tzinfo else c.committed_at.replace(tzinfo=now.tzinfo)
            out.append({"sha": c.sha, "message": c.message, "author": c.author,
                        "minutes_ago": round((now - committed).total_seconds() / 60)})
        return out


class LiveGitHub:
    source = "github"

    def __init__(self, repo: str, token: str = "", client: httpx.Client | None = None):
        self.repo = repo
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(base_url="https://api.github.com", headers=headers, timeout=5.0)

    def recent_commits(self, service: str | None, limit: int) -> list[dict]:
        # Fetch a wider page when filtering so a service filter still returns results.
        per_page = min(limit * 5, 100) if service else limit
        try:
            resp = self.client.get(f"/repos/{self.repo}/commits", params={"per_page": per_page})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub API request failed: {exc}") from exc
        out = []
        for item in resp.json():
            message = item["commit"]["message"].splitlines()[0]
            if service and service.lower() not in message.lower():
                continue
            out.append({"sha": item["sha"][:7], "message": message,
                        "author": (item.get("author") or {}).get("login") or item["commit"]["author"]["name"],
                        "date": item["commit"]["author"]["date"]})
            if len(out) >= limit:
                break
        return out


def get_github(db: Session) -> GitHubConnector:
    if settings.github_repo:
        return LiveGitHub(settings.github_repo, settings.github_token)
    return FixtureGitHub(db)
