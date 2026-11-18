"""The real ChatOpenAI client, with OpenAI's HTTP API mocked at the transport layer.

Covers what the scripted model cannot: the request LangChain sends to OpenAI,
parsing OpenAI tool calls, and turning OpenAI errors into actionable messages.
"""

import json

import httpx
import pytest
from langchain_openai import ChatOpenAI

from tests.conftest import login


def openai_llm(handler) -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", api_key="sk-test", max_retries=0,
                      http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def completion(message: dict, finish: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "c", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def ask(client, who="engineer"):
    return client.post("/api/chat", headers=login(client, who),
                       json={"messages": [{"role": "user", "content": "Why is order 1042 not charged?"}]})


def test_tool_call_round_trip_through_openai_format(client, llm_holder):
    requests = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return completion({"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "get_order_trace", "arguments": json.dumps({"order_id": "1042"})}}]},
                "tool_calls")
        return completion({"role": "assistant", "content": "payments-worker is stuck."}, "stop")

    llm_holder["llm"] = openai_llm(handler)
    r = ask(client)
    assert r.status_code == 200, r.text
    assert r.json()["steps"][0] == {"tool": "get_order_trace", "args": {"order_id": "1042"},
                                    "status": "executed", "message": "", "approval_id": None}

    first, second = requests
    names = {t["function"]["name"] for t in first["tools"]}
    assert len(names) == 11 and "rollback_deploy" not in names  # engineer's tools only
    assert all(t["function"]["parameters"]["type"] == "object" for t in first["tools"])
    tool_msg = second["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
    assert json.loads(tool_msg["content"])["data"]["order_id"] == "1042"


@pytest.mark.parametrize("status,code,message,expect", [
    (401, "invalid_api_key", "Incorrect API key provided: sk-****abcd.", "OPENAI_API_KEY"),
    (429, "insufficient_quota", "You exceeded your current quota.", "Billing"),
    (429, None, "You have no credits remaining. Add credits to continue using the API.", "Billing"),
    (429, "rate_limit_exceeded", "Rate limit reached.", "try again"),
    (404, "model_not_found", "The model does not exist.", "OPENAI_MODEL"),
    (400, "bad_request", "Something about the request.", "Something about the request"),
])
def test_openai_errors_become_clear_messages(client, llm_holder, status, code, message, expect):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": message, "type": "x", "code": code}})

    llm_holder["llm"] = openai_llm(handler)
    r = ask(client)
    assert r.status_code == 502
    assert expect in r.json()["detail"]


def test_unreachable_openai(client, llm_holder):
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    llm_holder["llm"] = openai_llm(handler)
    r = ask(client)
    assert r.status_code == 502 and "Could not reach" in r.json()["detail"]
