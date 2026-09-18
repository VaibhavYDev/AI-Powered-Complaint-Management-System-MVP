"""Model resolution and structured-output plumbing, with Groq mocked out."""

import json
from types import SimpleNamespace

import httpx
import pytest
from groq import APIConnectionError, BadRequestError, InternalServerError
from langchain_core.exceptions import OutputParserException
from langchain_groq.chat_models import _STRICT_STRUCTURED_OUTPUT_MODELS
from pydantic import BaseModel, Field

from app.ai import llm
from app.config import settings
from app.schemas import ComplaintData, EditProposal, RiskAssessment, RouterDecision

FALLBACK = "openai/gpt-oss-20b"


def groq_error(cls, status: int, code: str):
    response = httpx.Response(status, request=httpx.Request("GET", "https://api.groq.com"))
    return cls(code, response=response, body={"error": {"code": code, "message": code}})


# --- startup model resolution -------------------------------------------------------------

@pytest.fixture
def groq(monkeypatch):
    """Fake Groq client whose catalogue is the given model ids (or raises)."""
    calls = []

    def install(served=(), error=None):
        def list_models():
            calls.append("list")
            if error:
                raise error
            return SimpleNamespace(data=[SimpleNamespace(id=m) for m in served])

        client = SimpleNamespace(models=SimpleNamespace(list=list_models))
        monkeypatch.setattr(llm, "Groq", lambda api_key, **kwargs: client)
        return calls

    monkeypatch.setattr(llm, "_active_model", settings.groq_model)
    monkeypatch.setattr(llm, "_fallback_reason", None)
    return install


def test_configured_models():
    assert settings.groq_model == "gemma2-9b-it"
    assert settings.groq_fallback_model == FALLBACK


def test_no_key_skips_probe(groq, monkeypatch):
    calls = groq(served=["gemma2-9b-it"])
    monkeypatch.setattr(settings, "groq_api_key", "")
    llm.resolve_model()
    assert calls == [] and llm.model_status()["active_model"] == "gemma2-9b-it"


def test_configured_model_available(groq):
    calls = groq(served=["gemma2-9b-it", FALLBACK])
    llm.resolve_model()
    assert calls == ["list"]
    assert llm.model_status() == {"configured_model": "gemma2-9b-it", "active_model": "gemma2-9b-it", "fallback_reason": None}


def test_switches_to_fallback_with_one_catalogue_call(groq):
    calls = groq(served=[FALLBACK, "openai/gpt-oss-120b"])
    llm.resolve_model()
    assert calls == ["list"]
    status = llm.model_status()
    assert status["configured_model"] == "gemma2-9b-it" and status["active_model"] == FALLBACK
    assert status["fallback_reason"] == "gemma2-9b-it is not served by Groq for this key"


def test_reports_when_fallback_is_also_unavailable(groq):
    groq(served=["some-other-model"])
    llm.resolve_model()
    status = llm.model_status()
    assert status["active_model"] == FALLBACK
    assert f"fallback {FALLBACK} also unavailable" in status["fallback_reason"]


@pytest.mark.parametrize("error", [
    groq_error(InternalServerError, 500, ""),
    APIConnectionError(request=httpx.Request("GET", "https://api.groq.com")),  # network down at startup must not crash the app
])
def test_transient_probe_error_leaves_configuration_alone(groq, error):
    groq(error=error)
    llm.resolve_model()
    assert llm.model_status() == {"configured_model": "gemma2-9b-it", "active_model": "gemma2-9b-it", "fallback_reason": None}


# --- strict structured-output configuration -----------------------------------------------

def test_strict_models_are_supported_by_installed_langchain_groq():
    assert llm.STRICT_SCHEMA_MODELS <= set(_STRICT_STRUCTURED_OUTPUT_MODELS)
    assert llm.output_method(FALLBACK) == "json_schema"
    assert llm.output_method("gemma2-9b-it") == "json_mode"


@pytest.mark.parametrize("model", [RouterDecision, ComplaintData, EditProposal, RiskAssessment])
def test_strict_schema_is_derived_from_pydantic_and_groq_compliant(model):
    schema = llm.strict_json_schema(model)
    text = json.dumps(schema)
    assert schema["title"] == model.__name__ and text.count('"title"') == 1  # root name only
    assert not any(f'"{k}"' in text for k in llm.UNSUPPORTED_KEYWORDS - {"title"})

    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node["required"] == list(node["properties"])
                assert node["additionalProperties"] is False
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for item in node:
                check(item)

    check(schema)
    assert set(schema["properties"]) == set(model.model_fields)  # nothing hand-written or dropped


def test_strict_schema_uses_groq_accepted_union_forms():
    # Rules Groq enforced live: nullable unions as type lists (no anyOf), nullable enums inlined with
    # null, no integer/number overlap, unused $defs dropped.
    schema = llm.strict_json_schema(ComplaintData)
    category = schema["$defs"]["ComplaintDetails"]["properties"]["defect_category"]
    assert category["type"] == ["string", "null"] and category["enum"][0] == "physical_defect" and category["enum"][-1] is None
    assert schema["$defs"]["Patient"]["properties"]["patient_age"]["type"] == ["integer", "null"]
    assert "(YYYY-MM-DD)" in schema["$defs"]["Product"]["properties"]["expiry_date"]["description"]
    assert set(schema["$defs"]) == {"Complainant", "ComplaintDetails", "Patient", "Product"}

    value = llm.strict_json_schema(EditProposal)["$defs"]["FieldChange"]["properties"]["value"]
    assert value["type"] == ["string", "integer", "boolean", "null"]
    for model in (RouterDecision, ComplaintData, EditProposal, RiskAssessment):
        assert "anyOf" not in json.dumps(llm.strict_json_schema(model))


def test_binding_sends_strict_json_schema_for_gpt_oss(monkeypatch):
    monkeypatch.setattr(llm, "_active_model", FALLBACK)
    runnable = llm._runnable(RouterDecision)
    assert runnable.first.bound.reasoning_effort == settings.groq_reasoning_effort
    response_format = runnable.first.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["name"] == "RouterDecision"
    assert response_format["json_schema"]["schema"]["required"] == ["intent"]
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False


def test_binding_uses_json_object_mode_for_other_models(monkeypatch):
    monkeypatch.setattr(llm, "_active_model", "gemma2-9b-it")
    runnable = llm._runnable(RouterDecision)
    assert runnable.first.kwargs["response_format"] == {"type": "json_object"}
    assert runnable.first.bound.reasoning_effort is None  # gpt-oss-only parameter
    assert not llm.strict_mode()


# --- structured(): validation, retry, fallback, no key --------------------------------------

class Answer(BaseModel):
    value: int = Field(ge=0)


class FakeChatGroq:
    """Stands in for ChatGroq: `behaviour[model]` is a list of outcomes (exception or
    dict) consumed one per invoke."""

    behaviour: dict = {}
    invoked: list = []

    def __init__(self, model, **kwargs):
        self.model = model

    def with_structured_output(self, schema=None, method=None, strict=None):
        assert method == llm.output_method(self.model)
        assert (schema is not None and strict is True) if method == "json_schema" else (schema is None and strict is None)
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
    monkeypatch.setattr(llm, "_active_model", FALLBACK)
    monkeypatch.setattr(llm, "_fallback_reason", None)
    FakeChatGroq.invoked = []

    def install(behaviour):
        FakeChatGroq.behaviour = {k: list(v) for k, v in behaviour.items()}

    return install


def test_valid_output_is_validated_into_the_model(chat):
    chat({FALLBACK: [{"value": 3}]})
    assert llm.structured(Answer, "sys", "user") == Answer(value=3)


def test_schema_violation_triggers_one_corrective_retry(chat):
    chat({FALLBACK: [{"value": -1}, {"value": 2}]})
    assert llm.structured(Answer, "sys", "user") == Answer(value=2)
    assert [n for _, n in FakeChatGroq.invoked] == [2, 4]  # retry carries the rejected output + correction


def test_unparseable_json_is_retried_then_fails(chat):
    chat({FALLBACK: [groq_error(BadRequestError, 400, "json_validate_failed"), OutputParserException("bad")]})
    with pytest.raises(llm.AIOutputError):
        llm.structured(Answer, "sys", "user")
    assert len(FakeChatGroq.invoked) == 2


def test_falls_back_mid_flight_when_model_is_decommissioned(chat, monkeypatch):
    monkeypatch.setattr(llm, "_active_model", "gemma2-9b-it")
    chat({"gemma2-9b-it": [groq_error(BadRequestError, 400, "model_decommissioned")], FALLBACK: [{"value": 1}]})
    assert llm.structured(Answer, "sys", "user") == Answer(value=1)
    assert [m for m, _ in FakeChatGroq.invoked] == ["gemma2-9b-it", FALLBACK]
    assert llm.model_status()["fallback_reason"] == "model_decommissioned"


@pytest.mark.parametrize("error", [
    groq_error(InternalServerError, 500, ""),
    APIConnectionError(request=httpx.Request("POST", "https://api.groq.com")),
])
def test_other_provider_errors_are_reported_not_retried(chat, error):
    chat({FALLBACK: [error]})
    with pytest.raises(llm.AIProviderError):
        llm.structured(Answer, "sys", "user")


def test_structured_without_key(chat, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(llm.AIConfigError):
        llm.structured(Answer, "sys", "user")
    assert FakeChatGroq.invoked == []
