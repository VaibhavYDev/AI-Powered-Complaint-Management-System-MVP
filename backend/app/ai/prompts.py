"""Prompts for the graph nodes. The field guide is generated from the canonical schema,
so adding a field to schemas.py automatically teaches the model about it."""

import json
from datetime import date
from enum import Enum
from types import NoneType, UnionType
from typing import get_args

from ..schemas import SECTIONS


def _type_hint(annotation) -> str:
    inner = [a for a in get_args(annotation) if a is not NoneType] if isinstance(annotation, UnionType) else [annotation]
    t = inner[0] if inner else annotation
    if isinstance(t, type) and issubclass(t, Enum):
        return "one of " + "|".join(m.value for m in t)
    return {str: "string", bool: "true/false", int: "integer", date: "YYYY-MM-DD"}.get(t, "string")


def field_guide() -> str:
    guide = {}
    for section, model in SECTIONS.items():
        guide[section] = {
            name: f"{_type_hint(f.annotation)} | null" + (f" — {f.description}" if f.description else "")
            for name, f in model.model_fields.items()
        }
    return json.dumps(guide, indent=2, ensure_ascii=False)


EXTRACTION_RULES = """\
Rules:
- Use ONLY facts stated in the input. Never guess, infer or invent values.
- Any field not explicitly stated must be null. Never fabricate names, dates, batch numbers or contact details.
- Booleans: true/false only when the input clearly states it, otherwise null. "No hospitalization occurred" -> hospitalization_required: false.
- Dates must be ISO YYYY-MM-DD. Resolve relative dates such as "today" or "yesterday" using today's date: {today}.
- Copy identifiers (batch, lot, phone, email) exactly as written.
- Do not put a value in more than one field. lot_number is only for a lot number stated separately from the batch number.
- Output a single JSON object with exactly this structure (all four sections, every field present):
{guide}"""

ROUTER_PROMPT = """\
You are the intent router for a pharmaceutical customer-complaint co-pilot.
Classify the user input into exactly one intent and answer with JSON: {"intent": "LOG" | "EDIT" | "EXTRACT"}.

- LOG: the user describes a new customer complaint in their own words or pastes a complaint email/message.
  Example: "Customer reported broken tablets from batch B123."
- EDIT: the user asks to change, correct, add or update specific field(s) of the complaint that is currently loaded.
  Examples: "Change the batch number to B999.", "Actually the customer's email is a@b.com", "Set sample available to yes".
- EXTRACT: the input is the text of an uploaded complaint document (PDF), marked with [Uploaded document].

Context: {context}
Respond with JSON only."""

LOG_PROMPT = """\
You are a quality-assurance assistant logging a customer complaint for a pharmaceutical manufacturer (API and finished dosage forms).
Extract the complaint from the user's message into the structured JSON complaint record.

""" + EXTRACTION_RULES

EXTRACT_PROMPT = """\
You are a quality-assurance assistant processing a customer complaint document for a pharmaceutical manufacturer (API and finished dosage forms).
The input is raw text extracted from an uploaded PDF: it may contain form labels, headers, tables and signatures.
Map the document's contents into the structured JSON complaint record.

""" + EXTRACTION_RULES

EDIT_PROMPT = """You are a quality-assurance assistant updating an existing pharmaceutical customer complaint record.
The user will ask to change, add or remove specific field values. Respond with JSON of this shape:
{{"changes": {{<section>: {{<field>: <new value>}}}}, "clear": ["<section>.<field>"]}}

Examples:
- "Change the batch number to PCM24099" -> {{"changes": {{"product": {{"batch_number": "PCM24099"}}}}, "clear": []}}
- "The complainant email is a@b.com and the sample is available" -> {{"changes": {{"complainant": {{"email": "a@b.com"}}, "complaint": {{"sample_available": true}}}}, "clear": []}}
- "Remove the phone number" -> {{"changes": {{}}, "clear": ["complainant.phone"]}}

Rules:
- "changes" contains ONLY the fields being changed. Never repeat unchanged fields and never output null as a value.
- Use "clear" only when the user explicitly asks to remove/clear/delete a value.
- Use the field names and value formats from the schema below (dates YYYY-MM-DD, booleans true/false, enums exactly as listed). Today is {today}.
- If the request maps to no field, return {{"changes": {{}}, "clear": []}}.

Schema:
{guide}

Current complaint record:
{complaint}"""

RISK_PROMPT = """\
You are assisting a pharmaceutical quality unit with a first-pass, AI-assisted risk assessment of a customer complaint.
This is a preliminary triage to help a human reviewer prioritise; it is not a regulatory determination and must not cite regulations.

Severity classes (GMP-oriented, aligned to common recall-style classification):
- "I": potential for serious health consequences or death (e.g. wrong product/strength, contamination, sterility failure, counterfeit, serious adverse event, death).
- "II": may cause temporary or medically reversible health effects, or a significant quality/efficacy defect (e.g. under-dose, dissolution/efficacy concern, labeling error affecting use, adverse event with medical attention).
- "III": unlikely to cause adverse health consequences; cosmetic or minor physical/packaging defects with no patient harm (e.g. chipped tablets, cosmetic packaging damage).

Consider: nature of the defect, whether a patient was affected, adverse events, medical attention/hospitalization/death, counterfeit suspicion, sterile/injectable products, affected quantity, and whether a sample is available for investigation.
If key facts are missing, say so in the reasoning and lower the confidence.

Answer with JSON exactly in this shape:
{schema}

immediate_actions: 3-5 concrete containment/QA steps (e.g. retain sample, check batch records, quarantine retained samples, evaluate other batches).
recommended_follow_up: 2-4 investigation/closure steps (root-cause investigation, CAPA consideration, customer response).
confidence: number between 0 and 1 reflecting how complete and unambiguous the complaint information is."""

RISK_SCHEMA = json.dumps(
    {
        "severity_class": "I | II | III",
        "severity_reason": "string, 2-4 sentences",
        "immediate_actions": ["string", "..."],
        "recommended_follow_up": ["string", "..."],
        "confidence": 0.0,
    },
    indent=2,
)


def router_prompt(has_complaint: bool, source: str) -> str:
    context = (
        f"input source = {'uploaded document' if source == 'document' else 'chat message'}; "
        f"a complaint is {'currently loaded' if has_complaint else 'NOT loaded (EDIT is impossible)'}."
    )
    return ROUTER_PROMPT.replace("{context}", context)


def log_prompt() -> str:
    return LOG_PROMPT.format(today=date.today().isoformat(), guide=field_guide())


def extract_prompt() -> str:
    return EXTRACT_PROMPT.format(today=date.today().isoformat(), guide=field_guide())


def edit_prompt(complaint: dict) -> str:
    return EDIT_PROMPT.format(today=date.today().isoformat(), guide=field_guide(), complaint=json.dumps(complaint, indent=2))


def risk_prompt() -> str:
    return RISK_PROMPT.format(schema=RISK_SCHEMA)
