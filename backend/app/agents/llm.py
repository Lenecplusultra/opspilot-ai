"""Chat model factory plus a scripted model for tests and offline evals."""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from app.core.config import settings


class AgentNotConfigured(RuntimeError):
    pass


def make_openai_llm(model: str | None = None) -> BaseChatModel:
    if not settings.openai_api_key:
        raise AgentNotConfigured("OPENAI_API_KEY is not set")
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model or settings.openai_model, temperature=0, api_key=settings.openai_api_key,
                      timeout=60, max_retries=2)


class ScriptedChatModel(BaseChatModel):
    """Replays a fixed list of turns. Each turn is either
    {"tool_calls": [{"name": ..., "args": {...}}, ...]} or {"final": "text"}.

    Used to test the agent loop and to validate the eval harness end to end
    without network access or API cost. It does not measure model quality.
    """

    script: list[dict]
    _turn: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        if self._turn >= len(self.script):
            msg = AIMessage(content="(script exhausted)")
        else:
            turn = self.script[self._turn]
            if "final" in turn:
                msg = AIMessage(content=turn["final"])
            else:
                msg = AIMessage(content="", tool_calls=[
                    {"name": c["name"], "args": c.get("args", {}), "id": f"call_{self._turn}_{i}", "type": "tool_call"}
                    for i, c in enumerate(turn["tool_calls"])
                ])
        self._turn += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])
