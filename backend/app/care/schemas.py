"""Care Documentation Reliability Lab - structured shape of a caregiver note.

An independent case study. All residents, notes and care plans used with it are fictional.
Nothing here makes a clinical judgement: the output is documentation to be reviewed by a person.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(str, Enum):
    wound = "wound"
    mobility = "mobility"
    nutrition = "nutrition"
    hydration = "hydration"
    pain = "pain"
    behaviour = "behaviour"
    vital_signs = "vital_signs"
    medication = "medication"
    hygiene = "hygiene"
    other = "other"


class Severity(str, Enum):
    none = "none"
    mild = "mild"
    moderate = "moderate"
    severe = "severe"
    unknown = "unknown"


NULL_WORDS = {"", "unknown", "unbekannt", "n/a", "none", "keine angabe", "not stated"}


class Observation(BaseModel):
    """One thing a caregiver recorded about one resident."""

    model_config = ConfigDict(use_enum_values=True)

    resident: str | None = Field(None, description="the resident this observation is about, exactly as written")
    category: Category = Field(description="what kind of observation this is")
    finding: str = Field(min_length=1, description="what was observed, quoted or closely paraphrased from the note")
    body_site: str | None = Field(None, description="where on the body, when stated, e.g. 'left heel'")
    severity: Severity = Severity.unknown
    measurement: str | None = Field(None, description="any measured value exactly as written, e.g. '2 x 3 cm'")
    action_taken: str | None = Field(None, description="what the caregiver did about it, when stated")
    follow_up_required: bool | None = Field(None, description="true only if the note says follow-up is needed")
    observed_on: date | None = Field(None, description="date of the observation if the note states one")

    @field_validator("resident", "body_site", "measurement", "action_taken", mode="before")
    @classmethod
    def _blank_to_null(cls, v):
        return None if isinstance(v, str) and v.strip().lower() in NULL_WORDS else v


class CareNote(BaseModel):
    """Everything taken from one note, plus what the reader could not settle."""

    residents: list[str] = Field(default_factory=list, description="every resident named in the note")
    observations: list[Observation] = Field(default_factory=list)
    open_questions: list[str] = Field(
        default_factory=list,
        description="anything ambiguous or missing that a person should resolve; abstain here rather than guessing",
    )

    @model_validator(mode="after")
    def _residents_include_those_observed(self):
        named = {r for r in self.residents if r}
        for observation in self.observations:
            if observation.resident and observation.resident not in named:
                self.residents.append(observation.resident)
                named.add(observation.resident)
        return self


class CarePlanEntry(BaseModel):
    """A line from a fictional care plan, used to look for documentation gaps."""

    resident: str
    category: Category
    body_site: str | None = None
    instruction: str


class Alert(BaseModel):
    """Something a reviewer should look at. Never a diagnosis or an instruction to treat."""

    kind: str
    severity: str  # "high" | "medium" | "low" - how much reviewer attention it deserves
    message: str
    observation_index: int | None = None
    evidence_path: str | None = None


class CareExtraction(BaseModel):
    """What the lab returns for one note."""

    note: CareNote
    evidence: dict[str, dict] = {}
    alerts: list[Alert] = []
