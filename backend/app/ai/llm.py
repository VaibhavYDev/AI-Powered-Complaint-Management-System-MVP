"""Groq access for the graph nodes. Every call goes through `structured()`, which is
the only place raw model output exists: it is parsed and validated into a Pydantic
model before anything else in the app sees it."""

import logging
from typing import TypeVar

from groq import APIStatusError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from ..config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIConfigError(RuntimeError):
    pass


class AIOutputError(RuntimeError):
    pass


class AIProviderError(RuntimeError):
    pass


_active_model = settings.groq_model


def active_model() -> str:
    return _active_model


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
    """Groq JSON mode -> Pydantic validation. One corrective retry on invalid output;
    transparent fallback to GROQ_FALLBACK_MODEL if the configured model is gone."""
    global _active_model
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
        if code in ("model_decommissioned", "model_not_found") and _active_model != settings.groq_fallback_model:
            log.warning("Model %s unavailable (%s); switching to %s", _active_model, code, settings.groq_fallback_model)
            _active_model = settings.groq_fallback_model
            return structured(schema, system_prompt, user_content)
        raise AIProviderError(f"AI provider error ({exc.status_code}): {code or 'request failed'}.") from exc
