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


@pytest.mark.parametrize("section, field, value", [
    ("complaint", "defect_category", "Broken tablets"),
    ("complainant", "contact_channel", "carrier pigeon"),
    ("patient", "patient_gender", "yes"),
    ("patient", "patient_age", "forty-two"),
    ("patient", "patient_age", True),
])
def test_unknown_enum_values_and_bad_numbers_are_rejected(section, field, value):
    with pytest.raises(ValidationError):
        ComplaintData.model_validate({section: {field: value}})


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


# --- patient age: an exact age or nothing, never an invented number -------------------------

@pytest.mark.parametrize("value, expected", [
    (45, 45),
    (45.0, 45),
    ("45", 45),
    ("45 years", 45),
    ("45 year old", 45),
    (" 45y ", 45),
    ("age 45", 45),
    ("45-year-old male", 45),
    (0, 0),
    (120, 120),
])
def test_unambiguous_ages_are_accepted(value, expected):
    assert ComplaintData.model_validate({"patient": {"patient_age": value}}).patient.patient_age == expected


@pytest.mark.parametrize("value", [
    "5 to 10 years",      # regression: digit concatenation produced 510
    "5-10 years",
    "between 30 and 40",
    "30 or 40",
    "1980-05-01",         # date of birth, not an age
    "01/02/1990",
    "born in 1990",       # single number, but not a plausible age
    "-5",
    "2.5 years",          # fractional age cannot be stored as whole years
    "6 months",           # a different unit must not become 6 years
    "3 weeks",
])
def test_ambiguous_ages_become_null_not_invented(value):
    assert ComplaintData.model_validate({"patient": {"patient_age": value}}).patient.patient_age is None


@pytest.mark.parametrize("value", ["forty-two", True, 42.5, -5, 999, 121])
def test_malformed_ages_are_rejected(value):
    with pytest.raises(ValidationError):
        ComplaintData.model_validate({"patient": {"patient_age": value}})
