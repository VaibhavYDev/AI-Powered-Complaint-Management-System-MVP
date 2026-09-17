"""LangGraph nodes. Each node takes the graph state, makes one validated model call
through `llm.structured`, and returns the keys it updates. Nodes never touch the DB."""

import logging
from typing import Literal, TypedDict

from ..merge import apply_patch, describe_changes, patch_from
from ..schemas import ComplaintData, EditProposal, Intent, RiskAssessment, RouterDecision
from . import prompts
from .llm import structured

log = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    source: Literal["chat", "document"]
    text: str
    existing: dict | None  # current complaint sections when one is loaded
    intent: Intent
    draft: ComplaintData  # LOG / EXTRACT result, or merged view after EDIT
    patch: dict  # EDIT result: only the changed fields
    risk: RiskAssessment
    reply: str


class NoComplaintToEdit(Exception):
    pass


class NothingExtracted(Exception):
    pass


def route(state: GraphState) -> GraphState:
    text = f"[Uploaded document]\n{state['text']}" if state["source"] == "document" else state["text"]
    decision = structured(RouterDecision, prompts.router_prompt(bool(state.get("existing")), state["source"]), text)
    log.info("Routed %s input as %s", state["source"], decision.intent.value)
    return {"intent": decision.intent}


def log_complaint(state: GraphState) -> GraphState:
    draft = structured(ComplaintData, prompts.log_prompt(), state["text"])
    _require_content(draft, "I couldn't find any complaint details in that message. Describe the product, batch and problem, or upload the complaint document.")
    return {"draft": draft, "reply": _summarize(draft, "Logged a new complaint")}


def extract_complaint(state: GraphState) -> GraphState:
    draft = structured(ComplaintData, prompts.extract_prompt(), state["text"])
    _require_content(draft, "The document did not contain recognizable complaint information.")
    return {"draft": draft, "reply": _summarize(draft, "Extracted a complaint from the document")}


def edit_complaint(state: GraphState) -> GraphState:
    existing = state.get("existing")
    if not existing:
        raise NoComplaintToEdit("There is no complaint loaded to edit. Log a complaint first or upload a document.")
    proposal = structured(EditProposal, prompts.edit_prompt(existing), state["text"])
    patch = patch_from(proposal)
    ignored = f" Not an editable complaint field: {', '.join(proposal.unknown_fields())}." if proposal.unknown_fields() else ""
    if not patch:
        raise NothingExtracted("I couldn't map that request to any complaint field." + (ignored or " Try naming the field, e.g. \"change the batch number to X\"."))
    merged = ComplaintData.model_validate(apply_patch(existing, patch))
    return {"patch": patch, "draft": merged, "reply": describe_changes(existing, patch) + ignored}


def assess_risk(state: GraphState) -> GraphState:
    risk = structured(RiskAssessment, prompts.risk_prompt(), state["draft"].model_dump_json(indent=2))
    return {"risk": risk}


def _filled(draft: ComplaintData) -> tuple[int, int, list[str]]:
    missing, filled, total = [], 0, 0
    for section, fields in draft.model_dump().items():
        for name, value in fields.items():
            total += 1
            if value is None:
                missing.append(name.replace("_", " "))
            else:
                filled += 1
    return filled, total, missing


def _require_content(draft: ComplaintData, message: str) -> None:
    if _filled(draft)[0] == 0:
        raise NothingExtracted(message)


def _summarize(draft: ComplaintData, verb: str) -> str:
    filled, total, missing = _filled(draft)
    subject = " · ".join(
        s for s in (draft.product.product_name, f"batch {draft.product.batch_number}" if draft.product.batch_number else None,
                    f"reported by {draft.complainant.name}" if draft.complainant.name else None) if s
    )
    reply = f"{verb}{f' for {subject}' if subject else ''}. Captured {filled} of {total} fields."
    if missing:
        reply += f" Still missing: {', '.join(missing[:5])}{'…' if len(missing) > 5 else ''} — tell me if you have them."
    return reply
