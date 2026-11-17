"""OpsPilot MCP server.

Exposes the tool registry over the Model Context Protocol:
- tools/list    the tools the bound user's role may invoke (others are hidden)
- tools/call    goes through services.executor.invoke_tool, so RBAC, the approval
                gate and audit logging apply to every MCP client
- resources     runbooks, readable as runbook://<slug>

One server instance is bound to one authenticated user. The in-app LangChain
agent connects to it in-process (channel 'agent'); external MCP clients such as
Claude Desktop or Cursor connect over stdio with an API token (channel 'mcp').
"""

import json
from typing import Callable

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from pydantic import AnyUrl
from sqlalchemy.orm import Session

from app.connectors.runbooks import get_runbook_store
from app.core.rbac import has_role
from app.models import User
from app.services.executor import invoke_tool
from app.tools import REGISTRY

SERVER_NAME = "opspilot"
OK_STATUSES = {"executed", "pending_approval"}


class UnknownUserError(Exception):
    pass


def build_server(session_factory: Callable[[], Session], user_id: int, channel: str = "mcp") -> Server:
    server: Server = Server(SERVER_NAME, instructions=(
        "Operational tools for the OpsPilot fleet. Destructive tools create approval requests; "
        "nothing destructive runs until a human approves it."))

    def _role() -> str:
        with session_factory() as db:
            user = db.get(User, user_id)
            if user is None:
                raise UnknownUserError(f"user {user_id} no longer exists")
            return user.role

    def _invoke(name: str, arguments: dict) -> dict:
        with session_factory() as db:
            user = db.get(User, user_id)
            if user is None:
                raise UnknownUserError(f"user {user_id} no longer exists")
            return invoke_tool(db, user, name, arguments, channel=channel).model_dump()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        role = await anyio.to_thread.run_sync(_role)
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.params_model.model_json_schema(),
                annotations=types.ToolAnnotations(readOnlyHint=not t.destructive, destructiveHint=t.destructive),
            )
            for t in REGISTRY.values() if has_role(role, t.min_role)
        ]

    # validate_input=False: the executor validates parameters itself so that
    # invalid calls are audited like every other call.
    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
        result = await anyio.to_thread.run_sync(_invoke, name, arguments or {})
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, default=str))],
            structuredContent=result,
            isError=result["status"] not in OK_STATUSES,
        )

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [types.Resource(uri=AnyUrl(f"runbook://{rb.slug}"), name=rb.slug, title=rb.title,
                               mimeType="text/markdown") for rb in get_runbook_store().all()]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        slug = str(uri).removeprefix("runbook://")
        rb = get_runbook_store().get(slug)
        if rb is None:
            raise ValueError(f"unknown resource {uri}")
        return rb.body

    return server
