from app.tools.base import Tool, ToolError  # noqa: F401
from app.tools.definitions import ALL_TOOLS

REGISTRY: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}
