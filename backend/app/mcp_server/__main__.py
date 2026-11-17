"""Run the OpsPilot MCP server over stdio for external MCP clients.

    OPSPILOT_TOKEN=<token from POST /auth/login> python -m app.mcp_server

The token decides which user (and so which role) the client acts as.
"""

import os
import sys

import anyio
import jwt
from mcp.server.stdio import stdio_server

import app.models  # noqa: F401
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.mcp_server.server import build_server


async def _main() -> None:
    token = os.environ.get("OPSPILOT_TOKEN", "")
    try:
        user_id = int(decode_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        sys.exit("OPSPILOT_TOKEN is missing, invalid or expired. Get one from POST /auth/login.")
    server = build_server(SessionLocal, user_id, channel="mcp")
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(_main)
