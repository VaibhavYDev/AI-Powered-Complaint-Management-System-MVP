"""Groq access for the graph nodes. Every call goes through `structured()`, which is
the only place raw model output exists: it is parsed and validated into a Pydantic
model before anything else in the app sees it."""

import logging
from typing import TypeVar

from groq import APIStatusError, BadRequestError, Groq, NotFoundError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from ..config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

UNAVAILABLE_CODES = {"model_decommissioned", "model_not_found"}


class AIConfigError(RuntimeError):
    pass


class AIOutputError(RuntimeError):
    pass


class AIProviderError(RuntimeError):
    pass


# Which model actually serves requests, and why, if it is not the configured one.
_active_model = settings.groq_model
_fallback_reason: str | None = None


def model_status() -> dict:
    return {
        "configured_model": settings.groq_model,
        "active_model": _active_model,
        "fallback_reason": _fallback_reason,
    }


def resolve_model() -> None:
    """Called at startup: ask Groq whether GROQ_MODEL still exists and switch to the
    fallback up front, so /api/health and the logs state the truth from the first request."""
    if not settings.groq_api_key:
        return
    try:
        Groq(api_key=settings.groq_api_key).models.retrieve(settings.groq_model)
        log.info("Groq model %s is available", settings.groq_model)
    except (NotFoundError, BadRequestError) as exc:
        _switch_to_fallback(_error_code(exc) or "model_unavailable")
    except APIStatusError as exc:
        log.warning("Could not verify Groq model availability (%s); will fall back on demand", exc.status_code)


def _switch_to_fallback(reason: str) -> None:
    global _active_model, _fallback_reason
    _active_model, _fallback_reason = settings.groq_fallback_model, reason
    log.warning("Groq model %s unavailable (%s); using fallback %s", settings.groq_model, reason, _active_model)


def _error_code(exc: APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    return str((body.get("error") or {}).get("code") or "")


def _invoke(runnable, messages):
    try:
        return runnable.invoke(messages)
    except APIStatusError as exc:
        # Groq validates JSON mode output itself and rejects unparseable generations.
        if _error_code(exc) == "json_validate_failed":
            raise OutputParserException("Model produced invalid JSON.", llm_output="") from exc
        raise


def structured(schema: type[T], system_prompt: str, user_content: str) -> T:
    """Groq JSON mode -> Pydantic validation. One corrective retry on invalid output."""
    if not settings.groq_api_key:
        raise AIConfigError("GROQ_API_KEY is not configured.")

    llm = ChatGroq(model=_active_model, api_key=settings.groq_api_key, temperature=0, max_retries=2)
    runnable = llm.with_structured_output(schema, method="json_mode")
    messages = [SystemMessage(system_prompt), HumanMessage(user_content)]

    try:
        return _invoke(runnable, messages)
    except OutputParserException as exc:
        log.warning("Invalid %s output, retrying once: %s", schema.__name__, exc)
        messages += [
            AIMessage(exc.llm_output or "{}"),
            HumanMessage(f"That JSON was rejected: {exc}\nReturn the corrected JSON object only."),
        ]
        try:
            return _invoke(runnable, messages)
        except OutputParserException as exc2:
            raise AIOutputError(f"The AI returned malformed {schema.__name__} data.") from exc2
    except APIStatusError as exc:
        code = _error_code(exc)
        if code in UNAVAILABLE_CODES and _active_model != settings.groq_fallback_model:
            _switch_to_fallback(code)  # safety net if the model disappears after startup
            return structured(schema, system_prompt, user_content)
        raise AIProviderError(f"AI provider error ({exc.status_code}): {code or 'request failed'}.") from exc
