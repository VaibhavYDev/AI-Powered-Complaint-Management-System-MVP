"""Graph routing and risk-reassessment rules."""

import pytest

from app.ai import graph, nodes
from app.schemas import Intent


@pytest.mark.parametrize("patch, expected", [
    ({"product": {"strength": "650 mg"}}, "assess_risk"),
    ({"product": {"dosage_form": "injection"}}, "assess_risk"),
    ({"product": {"product_name": "Amoxiclav-DS"}}, "assess_risk"),
    ({"complaint": {"defect_category": "contamination"}}, "assess_risk"),
    ({"patient": {"hospitalization_required": True}}, "assess_risk"),
    ({"product": {"strength": "650 mg"}, "complainant": {"email": "a@b.com"}}, "assess_risk"),
])
def test_risk_relevant_edits_trigger_reassessment(patch, expected):
    # A product change (wrong strength, different dosage form) changes the patient risk,
    # so the stale assessment must not survive the edit.
    assert graph._after_edit({"patch": patch}) == expected


@pytest.mark.parametrize("patch", [
    {"complainant": {"email": "a@b.com"}},
    {"complainant": {"phone": None}},
    {"product": {"lot_number": "L-1"}},
    {"product": {"manufacturing_date": "2026-01-01"}},
])
def test_non_risk_edits_skip_reassessment(patch):
    # Contact details and traceability identifiers do not change the hazard.
    assert graph._after_edit({"patch": patch}) == "__end__"


def test_document_routing_is_deterministic(monkeypatch):
    # A PDF upload already establishes EXTRACT; classifying it again with the LLM is a
    # needless call and an extra failure point.
    def fail(*args, **kwargs):
        raise AssertionError("document routing must not call the model")

    monkeypatch.setattr(nodes, "structured", fail)
    assert nodes.route({"source": "document", "text": "complaint report"}) == {"intent": Intent.EXTRACT}


def test_chat_routing_still_uses_the_classifier(monkeypatch):
    calls = []

    def fake(schema, system, user):
        calls.append(user)
        return schema(intent=Intent.LOG)

    monkeypatch.setattr(nodes, "structured", fake)
    assert nodes.route({"source": "chat", "text": "broken tablets from batch B1"}) == {"intent": Intent.LOG}
    assert calls == ["broken tablets from batch B1"]
