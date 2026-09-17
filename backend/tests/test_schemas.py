import pytest
from pydantic import ValidationError

from app.schemas import ComplaintData, RiskAssessment


def test_llm_formatting_quirks_are_normalised():
    data = ComplaintData.model_validate(
        {
            "complainant": {"name": "Rahul", "email": "Not provided", "contact_channel": "Email"},
            "product": {"strength": 500},
            "complaint": {"defect_category": "Physical Defect", "sample_available": "yes", "affected_quantity": 3},
            "patient": {"patient_age": "45 years", "patient_gender": "M", "hospitalization_required": "no"},
        }
    )
    assert data.complainant.email is None
    assert data.complainant.contact_channel == "email"
    assert data.product.strength == "500"
    assert data.complaint.defect_category == "physical_defect"
    assert data.complaint.sample_available is True
    assert data.patient.patient_age == 45 and data.patient.patient_gender == "male"
    assert data.patient.hospitalization_required is False


def test_missing_fields_stay_null():
    data = ComplaintData.model_validate({"product": {"batch_number": "B1"}})
    assert data.complainant.name is None and data.product.expiry_date is None


RISK = {"severity_class": "II", "severity_reason": "r", "immediate_actions": ["a"], "recommended_follow_up": ["b"], "confidence": 0.5}


def test_risk_assessment_normalisation():
    risk = RiskAssessment.model_validate({**RISK, "severity_class": "Class II", "confidence": 85, "immediate_actions": ["a", " ", ""]})
    assert risk.severity_class == "II" and risk.confidence == 0.85 and risk.immediate_actions == ["a"]
    assert "regulatory determination" in risk.model_dump()["disclaimer"].lower()


@pytest.mark.parametrize("bad", [
    {"severity_class": "IV"},
    {"severity_reason": ""},
    {"immediate_actions": []},
    {"recommended_follow_up": []},
    {"confidence": 1.5},
    {"confidence": -0.1},
])
def test_risk_assessment_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        RiskAssessment.model_validate({**RISK, **bad})


def test_unparseable_date_is_rejected():
    with pytest.raises(ValidationError):
        ComplaintData.model_validate({"product": {"expiry_date": "next year"}})
