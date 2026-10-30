"""Extraction for the Care Documentation Reliability Lab.

One model call turns a note into structured observations; everything afterwards - evidence,
attribution, contradictions, care-plan gaps - is deterministic, so the reliability of the output
does not rest on the model being asked nicely.
"""

import json
from datetime import date

from ..ai.llm import strict_json_schema, strict_mode, structured
from .checks import analyse
from .schemas import CareExtraction, CareNote, CarePlanEntry

SYSTEM = """\
You are reading a caregiver's shift note from a residential care home and turning it into
structured documentation for a human reviewer.

Rules:
- Use ONLY what the note says. Never infer a diagnosis, a cause or a treatment.
- Quote findings from the note or paraphrase them closely. Do not add detail that is not there.
- Attribute every observation to the resident the note attributes it to. If you cannot tell which
  resident an observation belongs to, leave `resident` null and say so in `open_questions`.
- A negated statement is not a finding. "No pain reported" means there was no pain.
- Leave anything the note does not state as null. Record what is missing or ambiguous in
  `open_questions` instead of guessing.
- Dates must be ISO YYYY-MM-DD. Today is {today}.
- Notes may be in English or German; keep findings in the language of the note.
{guide}"""

GUIDE = """
Return JSON of this shape:
{
  "residents": ["every resident named in the note"],
  "observations": [
    {
      "resident": "name or null",
      "category": "wound|mobility|nutrition|hydration|pain|behaviour|vital_signs|medication|hygiene|other",
      "finding": "what was observed",
      "body_site": "where, or null",
      "severity": "none|mild|moderate|severe|unknown",
      "measurement": "value as written, or null",
      "action_taken": "what the caregiver did, or null",
      "follow_up_required": true/false/null,
      "observed_on": "YYYY-MM-DD or null"
    }
  ],
  "open_questions": ["anything ambiguous a person should settle"]
}"""


def prompt() -> str:
    # In strict schema mode the shape travels with the request, so the guide is redundant.
    return SYSTEM.format(today=date.today().isoformat(), guide="" if strict_mode() else GUIDE)


def extract(source: str, care_plan: list[CarePlanEntry] | None = None) -> CareExtraction:
    note = structured(CareNote, prompt(), source)
    evidence, alerts = analyse(note, source, care_plan)
    return CareExtraction(note=note, evidence=evidence, alerts=alerts)


def schema_preview() -> dict:
    """Used by the tests to prove the care schema is acceptable to strict structured output."""
    return strict_json_schema(CareNote)


def plan_from(raw: list[dict] | None) -> list[CarePlanEntry]:
    return [CarePlanEntry.model_validate(entry) for entry in (raw or [])]


def dump_plan(plan: list[CarePlanEntry]) -> str:
    return json.dumps([entry.model_dump() for entry in plan])
