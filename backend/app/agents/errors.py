"""Turn agent failures into messages that say what went wrong and how to fix it.

The MCP client session runs inside an anyio task group, so an exception from
the model (for example an OpenAI 401) arrives wrapped in one or more
ExceptionGroups. root_cause() unwraps it.
"""

import openai

from app.core.config import settings


def root_cause(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def describe_agent_error(exc: BaseException) -> tuple[int, str]:
    """(HTTP status, message) for a failed agent run. 502 means the model provider failed."""
    exc = root_cause(exc)
    model = settings.openai_model

    if isinstance(exc, openai.AuthenticationError):
        return 502, ("OpenAI rejected the API key (401). Check OPENAI_API_KEY in your .env file, "
                     "then restart the backend.")
    if isinstance(exc, openai.RateLimitError):
        if getattr(exc, "code", None) == "insufficient_quota" or "quota" in str(exc).lower():
            return 502, ("OpenAI says this account has no remaining quota (429 insufficient_quota). "
                         "Add credits under Billing at platform.openai.com, then try again.")
        return 502, "OpenAI rate-limited the request (429). Wait a few seconds and try again."
    if isinstance(exc, (openai.NotFoundError, openai.PermissionDeniedError)):
        return 502, (f"The model '{model}' is not available to this API key ({exc.status_code}). "
                     "Set OPENAI_MODEL in your .env file to a model your account can use.")
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return 502, "Could not reach the OpenAI API. Check the network connection and try again."
    if isinstance(exc, openai.APIStatusError):
        return 502, f"OpenAI returned an error ({exc.status_code}): {exc.message}"
    return 500, f"The agent failed: {type(exc).__name__}: {exc}"
