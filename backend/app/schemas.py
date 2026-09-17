"""Canonical complaint schema.

Single source of truth for LLM structured output, API responses, database JSON
columns and the frontend form. Every fact field is optional: the AI must leave
anything not stated in the source as null rather than guess.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, field_validator, model_validator


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


def _loose_enum(enum_cls: type[Enum], value: Any) -> Any:
    """Normalise LLM spellings ('Physical Defect' -> physical_defect) onto enum members.
    Anything that still does not match is returned unchanged so Pydantic rejects it."""
    if value is None or isinstance(value, enum_cls):
        return value
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return next((member for member in enum_cls if member.value == key), value)


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
        return _loose_enum(ContactChannel, v)


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
        return _loose_enum(DefectCategory, v)


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
        return _loose_enum(Gender, v)

    @field_validator("patient_age", mode="before")
    @classmethod
    def _age(cls, v):
        if isinstance(v, bool):
            raise ValueError("patient_age must be a whole number")
        if isinstance(v, str):  # "45 years" -> 45; non-numeric text falls through and is rejected
            digits = "".join(ch for ch in v if ch.isdigit())
            return int(digits) if digits else v
        return v


RISK_DISCLAIMER = (
    "AI-assisted preliminary triage to support human review. Not a regulatory determination "
    "and not a substitute for the quality unit's investigation."
)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    severity_class: SeverityClass
    severity_reason: str = Field(min_length=1)
    immediate_actions: list[str] = Field(min_length=1)
    recommended_follow_up: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @computed_field
    @property
    def disclaimer(self) -> str:
        return RISK_DISCLAIMER

    @field_validator("severity_class", mode="before")
    @classmethod
    def _severity(cls, v):
        if isinstance(v, str):
            v = v.strip().upper().removeprefix("CLASS").strip()
            v = {"1": "I", "2": "II", "3": "III"}.get(v, v)
        return v

    @field_validator("immediate_actions", "recommended_follow_up", mode="before")
    @classmethod
    def _non_empty_items(cls, v):
        if isinstance(v, str):
            v = [v]
        return [item.strip() for item in v if isinstance(item, str) and item.strip()] if isinstance(v, list) else v

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_fraction(cls, v):
        # 85 -> 0.85; a non-integer like 1.5 is simply invalid and rejected by the bounds.
        return v / 100 if isinstance(v, (int, float)) and 1 < v <= 100 and float(v).is_integer() else v


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


class FieldChange(BaseModel):
    field: str = Field(description="canonical field name from the schema, e.g. 'batch_number'")
    value: str | int | float | bool | None = Field(description="the new value; null is ignored")


class EditProposal(BaseModel):
    """EDIT output: a sparse list of field changes plus explicit clears. Unlisted fields
    are untouched. Nulls in `changes` are ignored; a field is nulled only via `clear`."""

    changes: list[FieldChange] = []
    clear: list[str] = Field(default_factory=list, description="fields to set to null, e.g. 'phone'")

    @field_validator("clear", mode="before")
    @classmethod
    def _known_fields_only(cls, paths: Any) -> list[str]:
        paths = paths if isinstance(paths, list) else [paths]
        fields = [str(p).rsplit(".", 1)[-1] for p in paths]
        return [f"{FIELD_SECTION[f]}.{f}" for f in fields if f in FIELD_SECTION]

    @model_validator(mode="after")
    def _values_fit_schema(self):
        try:
            ComplaintData.model_validate(self.patch())
        except ValidationError as exc:
            raise ValueError(f"change values do not fit the complaint schema: {exc}") from exc
        return self

    def unknown_fields(self) -> list[str]:
        return [c.field for c in self.changes if c.field.rsplit(".", 1)[-1] not in FIELD_SECTION]

    def patch(self) -> dict:
        """{section: {field: value}} as proposed, before normalisation by the section models."""
        patch: dict[str, dict] = {}
        for change in self.changes:
            field = change.field.rsplit(".", 1)[-1]
            if field in FIELD_SECTION and change.value is not None:
                patch.setdefault(FIELD_SECTION[field], {})[field] = change.value
        for path in self.clear:
            section, field = path.split(".")
            patch.setdefault(section, {})[field] = None
        return patch


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
    """What the frontend receives from /api/chat and /api/upload. `complaint` is always
    the full persisted record; `patch` and `risk_assessment` describe what this
    operation changed (a new assessment is only produced by LOG/EXTRACT and by EDITs
    that touch the complaint or patient sections)."""

    intent: Intent
    message: str
    complaint_id: int
    complaint: Complaint
    patch: dict[str, dict] | None = None
    risk_assessment: RiskAssessment | None = None
