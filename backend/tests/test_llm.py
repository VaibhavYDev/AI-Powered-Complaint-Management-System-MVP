"""Model resolution and structured-output plumbing, with Groq mocked out."""

import httpx
import pytest
from groq import BadRequestError, InternalServerError, NotFoundError
from pydantic import BaseModel

from app.ai import llm
from app.config import settings


def groq_error(cls, status: int, code: str):
    response = httpx.Response(status, request=httpx.Request("GET", "https://api.groq.com"))
    return cls(f"{code}", response=response, body={"error": {"code": code, "message": code}})


class FakeModels:
    def __init__(self, errors: dict):
        self.errors, self.calls = errors, []

    def retrieve(self, model):
        self.calls.append(model)
        if model in self.errors:
            raise self.errors[model]
        return {"id": model}


@pytest.fixture
def groq(monkeypatch):
    """Install a fake Groq client; returns a function to set per-model errors."""
    state = {}

    def install(errors=None):
        state["models"] = FakeModels(errors or {})
        monkeypatch.setattr(llm, "Groq", lambda api_key: type("Client", (), {"models": state["models"]})())
        return state["models"]

    monkeypatch.setattr(llm, "_active_model", settings.groq_model)
    monkeypatch.setattr(llm, "_fallback_reason", None)
    return install


def test_configured_models():
    assert settings.groq_model == "gemma2-9b-it"
    assert settings.groq_fallback_model == "openai/gpt-oss-20b"


def test_no_key_skips_probe(groq, monkeypatch):
    models = groq()
    monkeypatch.setattr(settings, "groq_api_key", "")
    llm.resolve_model()
    assert models.calls == [] and llm.model_status()["active_model"] == "gemma2-9b-it"


def test_configured_model_available(groq):
    models = groq()
    llm.resolve_model()
    assert models.calls == ["gemma2-9b-it"]
    assert llm.model_status() == {"configured_model": "gemma2-9b-it", "active_model": "gemma2-9b-it", "fallback_reason": None}


@pytest.mark.parametrize("error", [
    groq_error(NotFoundError, 404, "model_not_found"),
    groq_error(BadRequestError, 400, "model_decommissioned"),
])
def test_switches_to_fallback_when_configured_model_is_gone(groq, error):
    models = groq({"gemma2-9b-it": error})
    llm.resolve_model()
    assert models.calls == ["gemma2-9b-it", "openai/gpt-oss-20b"]
    status = llm.model_status()
    assert status["active_model"] == "openai/gpt-oss-20b"
    assert status["fallback_reason"] == error.body["error"]["code"]


def test_reports_when_fallback_is_also_unavailable(groq):
    groq({"gemma2-9b-it": groq_error(NotFoundError, 404, "model_not_found"),
          "openai/gpt-oss-20b": groq_error(NotFoundError, 404, "model_not_found")})
    llm.resolve_model()
    status = llm.model_status()
    assert status["active_model"] == "openai/gpt-oss-20b"
    assert "fallback openai/gpt-oss-20b also unavailable" in status["fallback_reason"]


def test_transient_probe_error_leaves_configuration_alone(groq):
    groq({"gemma2-9b-it": groq_error(InternalServerError, 500, "")})
    llm.resolve_model()
    assert llm.model_status()["active_model"] == "gemma2-9b-it"


class Answer(BaseModel):
    value: int


class FakeChatGroq:
    """Stands in for langchain_groq.ChatGroq: `behaviour[model]` is a list of outcomes
    (an exception to raise or a parsed object to return) consumed per invoke."""

    behaviour: dict = {}
    invoked: list = []

    def __init__(self, model, **kwargs):
        self.model = model

    def with_structured_output(self, schema, method):
        assert method == "json_mode"
        return self

    def invoke(self, messages):
        FakeChatGroq.invoked.append((self.model, len(messages)))
        outcome = FakeChatGroq.behaviour[self.model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(llm, "ChatGroq", FakeChatGroq)
    monkeypatch.setattr(llm, "_active_model", settings.groq_model)
    monkeypatch.setattr(llm, "_fallback_reason", None)
    FakeChatGroq.invoked = []

    def install(behaviour):
        FakeChatGroq.behaviour = {k: list(v) for k, v in behaviour.items()}

    return install


def test_structured_falls_back_mid_flight(chat):
    chat({"gemma2-9b-it": [groq_error(BadRequestError, 400, "model_decommissioned")], "openai/gpt-oss-20b": [Answer(value=1)]})
    assert llm.structured(Answer, "sys", "user") == Answer(value=1)
    assert [m for m, _ in FakeChatGroq.invoked] == ["gemma2-9b-it", "openai/gpt-oss-20b"]
    assert llm.model_status()["fallback_reason"] == "model_decommissioned"


def test_structured_retries_once_then_fails(chat):
    from langchain_core.exceptions import OutputParserException

    chat({"gemma2-9b-it": [OutputParserException("bad", llm_output="{"), Answer(value=2)]})
    assert llm.structured(Answer, "sys", "user") == Answer(value=2)
    assert [n for _, n in FakeChatGroq.invoked] == [2, 4]  # retry carries the rejected output + correction

    chat({"gemma2-9b-it": [groq_error(BadRequestError, 400, "json_validate_failed"), OutputParserException("bad")]})
    with pytest.raises(llm.AIOutputError):
        llm.structured(Answer, "sys", "user")


def test_structured_without_key(chat, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(llm.AIConfigError):
        llm.structured(Answer, "sys", "user")
