"""The MCP server, exercised through a real MCP client session."""

import json

import anyio
from mcp.shared.memory import create_connected_server_and_client_session
from sqlalchemy import select

from app.mcp_server.server import build_server
from app.models import ApprovalRequest, AuditLog


def with_client(session_factory, user_id, fn, db=None):
    if db is not None:
        db.rollback()

    async def main():
        async with create_connected_server_and_client_session(build_server(session_factory, user_id)) as c:
            return await fn(c)
    result = anyio.run(main)
    if db is not None:
        db.rollback()
    return result


def test_tool_list_is_filtered_by_role(session_factory, users):
    async def names(c):
        return {t.name for t in (await c.list_tools()).tools}

    viewer = with_client(session_factory, users["viewer"].id, names)
    engineer = with_client(session_factory, users["engineer"].id, names)
    admin = with_client(session_factory, users["admin"].id, names)
    assert len(viewer) == 8 and "restart_service" not in viewer
    assert len(engineer) == 11 and "rollback_deploy" not in engineer
    assert len(admin) == 12


def test_tools_carry_schema_and_destructive_annotations(session_factory, users):
    async def tools(c):
        return {t.name: t for t in (await c.list_tools()).tools}

    t = with_client(session_factory, users["admin"].id, tools)
    assert t["restart_service"].annotations.destructiveHint is True
    assert t["search_logs"].annotations.readOnlyHint is True
    assert "metric" in t["query_metrics"].inputSchema["properties"]


def test_call_goes_through_executor_and_is_audited_as_mcp(session_factory, users, db):
    async def call(c):
        return await c.call_tool("restart_service", {"service": "payments-worker", "reason": "stuck"})

    res = with_client(session_factory, users["engineer"].id, call, db)
    body = json.loads(res.content[0].text)
    assert res.isError is False and body["status"] == "pending_approval"
    assert db.get(ApprovalRequest, body["approval_id"]).status == "pending"
    audit = db.execute(select(AuditLog)).scalar_one()
    assert audit.channel == "mcp" and audit.outcome == "pending_approval"


def test_hidden_tool_called_directly_is_still_denied(session_factory, users, db):
    async def call(c):
        return await c.call_tool("restart_service", {"service": "orders-api"})

    res = with_client(session_factory, users["viewer"].id, call, db)
    assert res.isError is True and json.loads(res.content[0].text)["status"] == "denied"
    assert db.execute(select(AuditLog.outcome)).scalar_one() == "denied"


def test_invalid_arguments_reach_executor_and_are_audited(session_factory, users, db):
    async def call(c):
        return await c.call_tool("query_metrics", {"service": "orders-api", "metric": "bogus"})

    res = with_client(session_factory, users["viewer"].id, call, db)
    assert res.isError is True and json.loads(res.content[0].text)["status"] == "invalid"
    assert db.execute(select(AuditLog.outcome)).scalar_one() == "invalid"


def test_runbooks_are_mcp_resources(session_factory, users):
    async def read(c):
        listed = [str(r.uri) for r in (await c.list_resources()).resources]
        body = await c.read_resource("runbook://rollback-deploy")
        return listed, body.contents[0].text

    listed, text = with_client(session_factory, users["viewer"].id, read)
    assert "runbook://restart-service" in listed and text.startswith("# Rolling back")
