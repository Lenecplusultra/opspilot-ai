"""Runbook connector: markdown runbooks on disk, searched by weighted keyword match.

Small corpus, so keyword scoring with title and tag boosts is predictable and
easy to test. The interface (search/get/list) is what a vector store would sit
behind if the corpus grew.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "is", "it", "my", "how", "do", "i", "what", "why"}


def _terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


@dataclass(frozen=True)
class Runbook:
    slug: str
    title: str
    tags: tuple[str, ...]
    body: str


class RunbookStore:
    def __init__(self, directory: Path):
        self.runbooks: dict[str, Runbook] = {}
        for path in sorted(directory.glob("*.md")):
            text = path.read_text()
            title = text.splitlines()[0].lstrip("# ").strip()
            tags_match = re.search(r"^Tags:\s*(.+)$", text, re.MULTILINE)
            tags = tuple(t.strip().lower() for t in tags_match.group(1).split(",")) if tags_match else ()
            self.runbooks[path.stem] = Runbook(path.stem, title, tags, text)

    def all(self) -> list[Runbook]:
        return list(self.runbooks.values())

    def get(self, slug: str) -> Runbook | None:
        return self.runbooks.get(slug)

    def search(self, query: str, limit: int = 3) -> list[tuple[Runbook, float]]:
        q = set(_terms(query))
        if not q:
            return []
        scored = []
        for rb in self.runbooks.values():
            body = _terms(rb.body)
            title = set(_terms(rb.title))
            tags = set(_terms(" ".join(rb.tags)))
            score = sum(3.0 * (t in title) + 2.0 * (t in tags) + min(body.count(t), 5) * 0.5 for t in q)
            if score > 0:
                scored.append((rb, round(score, 2)))
        scored.sort(key=lambda x: (-x[1], x[0].slug))
        return scored[:limit]


@lru_cache
def get_runbook_store() -> RunbookStore:
    return RunbookStore(settings.runbook_dir)
