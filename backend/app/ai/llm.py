"""Groq access for the graph nodes. Every call goes through `structured()`, which is
the only place raw model output exists: it is parsed and validated into a Pydantic
model before anything else in the app sees it.

Model selection: GROQ_MODEL (the assignment's gemma2-9b-it, shut down by Groq) is
checked once at startup against the model catalogue; if it is not served, requests go
to GROQ_FALLBACK_MODEL and /api/health reports the switch.

Output method: gpt-oss models get Groq Structured Outputs (strict JSON Schema derived
from the Pydantic model); any other model gets JSON Object Mode. Either way the
result is validated by the same Pydantic model.
"""

import json
import logging
import time
from collections import Counter
from typing import TypeVar

from groq import APIConnectionError, APIError, APIStatusError, Groq
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from ..config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

STRICT_SCHEMA_MODELS = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
UNAVAILABLE_CODES = {"model_decommissioned", "model_not_found"}
# JSON Schema keywords outside Groq's strict-mode subset; constraints are still enforced by Pydantic.
UNSUPPORTED_KEYWORDS = {
    "default", "title", "format", "minLength", "maxLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "pattern",
}


class AIConfigError(RuntimeError):
    pass


class AIOutputError(RuntimeError):
    pass


class AIProviderError(RuntimeError):
    pass


# Privacy-safe counters. Nothing here records prompts, documents or model output: only how many
# calls were made, how long they took, how many tokens they cost and what went wrong.
telemetry: dict = {
    "calls": 0,
    "retries": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "seconds": 0.0,
    "errors": Counter(),
}


def reset_telemetry() -> None:
    telemetry.update(calls=0, retries=0, prompt_tokens=0, completion_tokens=0, total_tokens=0, seconds=0.0)
    telemetry["errors"] = Counter()


class _TokenCounter(BaseCallbackHandler):
    """Reads the usage the provider reports; it never sees more than the token totals."""

    def on_llm_end(self, response, **kwargs) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        telemetry["prompt_tokens"] += usage.get("prompt_tokens", 0)
        telemetry["completion_tokens"] += usage.get("completion_tokens", 0)
        telemetry["total_tokens"] += usage.get("total_tokens", 0)


_counter = _TokenCounter()


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
    """Startup: one catalogue request decides which model serves requests, so no real
    completion is ever sent to a decommissioned GROQ_MODEL."""
    if not settings.groq_api_key:
        return
    try:
        # Short timeout: uvicorn binds the port only after startup, so this must never hang or crash the app.
        served = {m.id for m in Groq(api_key=settings.groq_api_key, timeout=10, max_retries=1).models.list().data}
    except APIError as exc:
        log.warning("Could not list Groq models (%s); will fall back on demand", getattr(exc, "status_code", type(exc).__name__))
        return
    if settings.groq_model in served:
        log.info("Groq model %s is available", settings.groq_model)
        return
    _switch_to_fallback(f"{settings.groq_model} is not served by Groq for this key")
    if settings.groq_fallback_model not in served:
        log.error("Fallback model %s is not served either", settings.groq_fallback_model)
        _set_reason(f"{_fallback_reason}; fallback {settings.groq_fallback_model} also unavailable")


def _switch_to_fallback(reason: str) -> None:
    global _active_model
    _active_model = settings.groq_fallback_model
    _set_reason(reason)
    log.warning("Using fallback model %s (%s)", _active_model, reason)


def _set_reason(reason: str) -> None:
    global _fallback_reason
    _fallback_reason = reason


def strict_json_schema(model: type[BaseModel]) -> dict:
    """Groq strict mode needs every property required, additionalProperties=false on
    each object, nullable/enum unions written as type lists, and only a subset of
    keywords. Derived from the Pydantic model."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def is_date(prop: dict) -> bool:
        return prop.get("format") == "date" or any(b.get("format") == "date" for b in prop.get("anyOf", []))

    def flatten_union(prop: dict) -> dict:
        # anyOf[{type: X}, {type: null}] -> type [X, null]; anyOf[{$ref: Enum}, null] -> inline enum + null.
        types, enum = [], None
        for branch in prop.get("anyOf", []):
            target = defs.get(branch["$ref"].rsplit("/", 1)[-1]) if "$ref" in branch else branch
            if target is None or not isinstance(target.get("type"), str) or (set(target) - {"type", "enum", "format", "description", "title"}):
                return prop  # object unions etc. are left alone
            types.append(target["type"])
            enum = target.get("enum", enum)
        if not types:
            return prop
        out = {key: value for key, value in prop.items() if key != "anyOf"}
        out["type"] = types
        if enum is not None:
            out["enum"] = enum + ([None] if "null" in types else [])
        return out

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
            for name, prop in node["properties"].items():
                if is_date(prop):
                    prop["description"] = (prop.get("description", "") + " (YYYY-MM-DD)").strip()
                node["properties"][name] = flatten_union(prop)
        return {key: walk(value) for key, value in node.items() if key not in UNSUPPORTED_KEYWORDS}

    schema = walk(raw)
    text = json.dumps(schema)
    if "$defs" in schema:  # drop definitions nothing references any more (inlined enums)
        schema["$defs"] = {name: d for name, d in schema["$defs"].items() if f'"#/$defs/{name}"' in text}
        if not schema["$defs"]:
            del schema["$defs"]
    schema["title"] = model.__name__
    return schema


def output_method(model: str) -> str:
    return "json_schema" if model in STRICT_SCHEMA_MODELS else "json_mode"


def strict_mode() -> bool:
    return output_method(_active_model) == "json_schema"


def _client(**extra) -> ChatGroq:
    """The one place a provider client is built.

    `max_retries` is the SDK's own bounded retry with exponential backoff and jitter, which is
    what absorbs the 429s that token-per-minute limits produce in bursts. `timeout` bounds a
    single attempt so a stalled inference cannot hold a worker open.
    """
    return ChatGroq(
        model=_active_model,
        api_key=settings.groq_api_key,
        temperature=0,
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout_seconds,
        **extra,
    )


def _runnable(schema: type[BaseModel]):
    if strict_mode():
        client = _client(reasoning_effort=settings.groq_reasoning_effort)
        return client.with_structured_output(strict_json_schema(schema), method="json_schema", strict=True)
    return _client().with_structured_output(method="json_mode")


def _error_code(exc: APIStatusError) -> str:
    return str(_error_field(exc, "code"))


def _error_field(exc: APIStatusError, field: str) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    return str((body.get("error") or {}).get(field) or "")


def _call(schema: type[T], runnable, messages) -> T:
    """One model call -> dict -> Pydantic. Any bad output surfaces as OutputParserException."""
    telemetry["calls"] += 1
    started = time.perf_counter()
    try:
        raw = runnable.invoke(messages, config={"callbacks": [_counter]})
    except APIStatusError as exc:
        telemetry["errors"][_error_code(exc) or f"http_{exc.status_code}"] += 1
        if _error_code(exc) == "json_validate_failed":  # Groq itself rejected the generation
            raise OutputParserException("Model produced invalid JSON.", llm_output="") from exc
        raise
    except APIConnectionError:
        telemetry["errors"]["connection"] += 1
        raise
    finally:
        telemetry["seconds"] += time.perf_counter() - started
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        telemetry["errors"]["schema_validation"] += 1
        raise OutputParserException(f"Schema validation failed: {exc}", llm_output=json.dumps(raw)) from exc


def _call_with_one_retry(schema: type[T], runnable, messages) -> T:
    try:
        return _call(schema, runnable, messages)
    except OutputParserException as exc:
        telemetry["retries"] += 1
        log.warning("Invalid %s output, retrying once: %s", schema.__name__, str(exc)[:300])
        messages += [
            AIMessage(exc.llm_output or "{}"),
            HumanMessage(f"That JSON was rejected: {exc}\nReturn the corrected JSON object only."),
        ]
        try:
            return _call(schema, runnable, messages)
        except OutputParserException as exc2:
            raise AIOutputError(f"The AI returned malformed {schema.__name__} data.") from exc2


def structured(schema: type[T], system_prompt: str, user_content: str) -> T:
    if not settings.groq_api_key:
        raise AIConfigError("GROQ_API_KEY is not configured.")
    messages = [SystemMessage(system_prompt), HumanMessage(user_content)]
    try:
        return _call_with_one_retry(schema, _runnable(schema), messages)
    except APIStatusError as exc:
        code = _error_code(exc)
        if code in UNAVAILABLE_CODES and _active_model != settings.groq_fallback_model:
            _switch_to_fallback(code)  # safety net if the model disappears after startup
            return structured(schema, system_prompt, user_content)
        raise AIProviderError(f"AI provider error ({exc.status_code}): {code or _error_field(exc, 'message')[:200] or 'request failed'}") from exc
    except APIConnectionError as exc:
        raise AIProviderError("AI provider is unreachable; please try again.") from exc
