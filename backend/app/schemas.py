"""Canonical complaint schema.

Single source of truth for LLM structured output, API responses, database JSON
columns and the frontend form. Every fact field is optional: the AI must leave
anything not stated in the source as null rather than guess.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class ContactChannel(str, Enum):
    email = "email"
    phone = "phone"
    letter = "letter"
    web_form = "web_form"
    sales_rep = "sales_rep"
    other = "other"


class DefectCategory(str, Enum):
    physical_defect = "physical_defect"
    packaging = "packaging"
    labeling = "labeling"
    contamination = "contamination"
    efficacy = "efficacy"
    adverse_reaction = "adverse_reaction"
    counterfeit = "counterfeit"
    other = "other"


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class SeverityClass(str, Enum):
    I = "I"
    II = "II"
    III = "III"


class Intent(str, Enum):
    LOG = "LOG"
    EDIT = "EDIT"
    EXTRACT = "EXTRACT"


NULL_WORDS = {"", "null", "none", "n/a", "na", "unknown", "not stated", "not specified", "not provided", "not mentioned"}


def _loose_enum(enum_cls: type[Enum], value: Any, fallback: Enum | None) -> Enum | None:
    """Map free-form LLM strings ('Physical Defect', 'Class II') onto enum members."""
    if value is None or isinstance(value, enum_cls):
        return value
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    for member in enum_cls:
        if key == member.value.lower():
            return member
    return fallback


class Section(BaseModel):
    """Base for AI-populated sections: tolerant of common LLM formatting quirks."""

    model_config = ConfigDict(coerce_numbers_to_str=True, use_enum_values=True)

    @model_validator(mode="before")
    @classmethod
    def _blank_placeholders_to_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and v.strip().lower() in NULL_WORDS else v) for k, v in data.items()}
        return data


class Complainant(Section):
    name: str | None = Field(None, description="full name of the person raising the complaint")
    email: str | None = None
    phone: str | None = None
    organization: str | None = Field(None, description="hospital, pharmacy, distributor or company")
    country: str | None = None
    contact_channel: ContactChannel | None = Field(None, description="how the complaint was received")

    @field_validator("contact_channel", mode="before")
    @classmethod
    def _channel(cls, v):
        return _loose_enum(ContactChannel, v, ContactChannel.other)


class Product(Section):
    product_name: str | None = Field(None, description="brand/trade name as stated, e.g. 'Paracetamol 500 mg Tablets'")
    generic_name: str | None = Field(None, description="INN / active ingredient")
    manufacturer: str | None = None
    dosage_form: str | None = Field(None, description="tablet, capsule, injection, API powder, ...")
    strength: str | None = Field(None, description="e.g. '500 mg'")
    batch_number: str | None = None
    lot_number: str | None = Field(None, description="only if a lot number is stated separately from the batch number")
    manufacturing_date: date | None = None
    expiry_date: date | None = None


class ComplaintDetails(Section):
    complaint_received_date: date | None = Field(None, description="date the company received the complaint")
    event_date: date | None = Field(None, description="date the problem was observed/occurred")
    complaint_description: str | None = Field(None, description="concise summary of the complaint in the customer's terms")
    defect_category: DefectCategory | None = None
    defect_description: str | None = Field(None, description="specific observed defect, e.g. 'tablets chipped and broken inside blister'")
    affected_quantity: str | None = Field(None, description="quantity affected as stated, e.g. '3 tablets', '2 cartons'")
    sample_available: bool | None = Field(None, description="true only if the customer says a sample is available/retained")
    suspected_counterfeit: bool | None = None

    @field_validator("defect_category", mode="before")
    @classmethod
    def _category(cls, v):
        return _loose_enum(DefectCategory, v, DefectCategory.other)


class Patient(Section):
    patient_involved: bool | None = Field(None, description="true if a patient/consumer actually used or was exposed to the product")
    patient_age: int | None = None
    patient_gender: Gender | None = None
    adverse_event: bool | None = Field(None, description="true if any health effect was reported")
    medical_attention_required: bool | None = None
    hospitalization_required: bool | None = None
    death_reported: bool | None = None

    @field_validator("patient_gender", mode="before")
    @classmethod
    def _gender(cls, v):
        v = {"m": "male", "f": "female"}.get(str(v).strip().lower(), v) if isinstance(v, str) else v
        return _loose_enum(Gender, v, Gender.unknown)

    @field_validator("patient_age", mode="before")
    @classmethod
    def _age(cls, v):
        if isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            return int(digits) if digits else None
        return v


class RiskAssessment(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    severity_class: SeverityClass
    severity_reason: str
    immediate_actions: list[str] = []
    recommended_follow_up: list[str] = []
    confidence: float = Field(ge=0, le=1)

    @field_validator("severity_class", mode="before")
    @classmethod
    def _severity(cls, v):
        if isinstance(v, str):
            v = v.strip().upper().removeprefix("CLASS").strip()
            v = {"1": "I", "2": "II", "3": "III"}.get(v, v)
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_fraction(cls, v):
        return v / 100 if isinstance(v, (int, float)) and 1 < v <= 100 else v


class ComplaintData(BaseModel):
    """The AI-populated part of a complaint. Produced by LOG and EXTRACT."""

    complainant: Complainant = Complainant()
    product: Product = Product()
    complaint: ComplaintDetails = ComplaintDetails()
    patient: Patient = Patient()


SECTIONS: dict[str, type[Section]] = {
    name: field.annotation for name, field in ComplaintData.model_fields.items()
}
FIELD_SECTION: dict[str, str] = {
    field: section for section, model in SECTIONS.items() for field in model.model_fields
}


class ComplaintPatch(ComplaintData):
    """Partial update produced by EDIT. Only fields the model explicitly returned are
    considered set, so `model_dump(exclude_unset=True)` yields the patch."""

    @model_validator(mode="before")
    @classmethod
    def _lift_flat_keys(cls, data: Any) -> Any:
        # Small models sometimes answer {"batch_number": "X"} instead of {"product": {"batch_number": "X"}}.
        if not isinstance(data, dict):
            return data
        out: dict[str, dict] = {}
        for key, value in data.items():
            if key in SECTIONS and isinstance(value, dict):
                out.setdefault(key, {}).update(value)
            elif key in FIELD_SECTION:
                out.setdefault(FIELD_SECTION[key], {})[key] = value
        return out


class Complaint(ComplaintData):
    """A persisted complaint as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    risk_assessment: RiskAssessment | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def reference(self) -> str:
        return f"CC-{self.created_at:%Y}-{self.id:04d}"


class RouterDecision(BaseModel):
    intent: Intent


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    complaint_id: int | None = None


class CopilotResponse(BaseModel):
    intent: Intent
    message: str
    complaint_id: int
    complaint: Complaint
    patch: dict | None = None
    risk_assessment: RiskAssessment | None = None
