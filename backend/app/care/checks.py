"""Deterministic reliability checks over an extracted note.

These are documentation checks, not clinical ones: each result says that something in the
paperwork does not line up and a person should look, never what is wrong with a resident or
what to do about it. Nothing here calls a model.
"""

import re
from difflib import SequenceMatcher

from ..evidence import DERIVED, UNSUPPORTED, verify_values
from .schemas import Alert, CareNote, CarePlanEntry, Observation

# Fields that are a reading of the note rather than a quotation, so not finding them verbatim
# is expected.
JUDGED_FIELDS = {"category", "severity", "follow_up_required"}
NEGATORS = re.compile(r"\b(no|denies|without|kein|keine|ohne|nicht)\b", re.IGNORECASE)
# Notes and care plans disagree about honorifics, so names are compared without them.
HONORIFICS = re.compile(r"^(frau|herr|mr|mrs|ms|miss|dr|prof)\.?\s+", re.IGNORECASE)


def normalise_name(name: str) -> str:
    previous, cleaned = None, name.strip()
    while cleaned != previous:  # "Frau Dr. Keller" carries two
        previous = cleaned
        cleaned = HONORIFICS.sub("", cleaned)
    return " ".join(cleaned.casefold().split())


def same_person(left: str | None, right: str | None) -> bool:
    return bool(left and right) and normalise_name(left) == normalise_name(right)


def observation_values(observations: list[Observation]) -> tuple[dict, set[str]]:
    """Flatten observations into evidence paths, and say which are judgements."""
    values: dict[str, object] = {}
    judgements: set[str] = set()
    for index, observation in enumerate(observations):
        for name, value in observation.model_dump().items():
            path = f"observations.{index}.{name}"
            values[path] = value
            if name in JUDGED_FIELDS:
                judgements.add(path)
    return values, judgements


def analyse(note: CareNote, source: str, care_plan: list[CarePlanEntry] | None = None) -> tuple[dict, list[Alert]]:
    values, judgements = observation_values(note.observations)
    evidence = verify_values(values, source, judgements)

    alerts: list[Alert] = []
    alerts += _unsupported_findings(note, evidence)
    alerts += _resident_attribution(note, source, evidence)
    alerts += _negated_findings(note, evidence, source)
    alerts += _contradictions(note)
    alerts += _care_plan_gaps(note, care_plan or [])
    alerts += _open_questions(note)
    return evidence, alerts


def _unsupported_findings(note: CareNote, evidence: dict) -> list[Alert]:
    alerts = []
    for index, observation in enumerate(note.observations):
        status = evidence.get(f"observations.{index}.finding", {}).get("status")
        if status == UNSUPPORTED:
            alerts.append(
                Alert(
                    kind="unsupported_finding",
                    severity="high",
                    message=f"'{observation.finding}' does not appear in the note.",
                    observation_index=index,
                    evidence_path=f"observations.{index}.finding",
                )
            )
    return alerts


def _resident_attribution(note: CareNote, source: str, evidence: dict) -> list[Alert]:
    """The note names more than one resident, so each observation has to be pinned to one."""
    named = [r for r in note.residents if r]
    alerts = []

    for index, observation in enumerate(note.observations):
        path = f"observations.{index}.resident"
        if not observation.resident:
            if len(named) > 1:
                alerts.append(
                    Alert(
                        kind="unattributed_observation",
                        severity="high",
                        message=(
                            f"The note mentions {len(named)} residents and this observation is not "
                            "attributed to one of them."
                        ),
                        observation_index=index,
                        evidence_path=path,
                    )
                )
            continue

        if evidence.get(path, {}).get("status") in {UNSUPPORTED, DERIVED}:
            alerts.append(
                Alert(
                    kind="resident_not_in_note",
                    severity="high",
                    message=f"'{observation.resident}' is not named in the note.",
                    observation_index=index,
                    evidence_path=path,
                )
            )
            continue

        excerpt = evidence.get(f"observations.{index}.finding", {}).get("excerpt") or ""
        others = [r for r in named if not same_person(r, observation.resident) and r in excerpt]
        if others:
            alerts.append(
                Alert(
                    kind="ambiguous_attribution",
                    severity="high",
                    message=(
                        f"The text supporting this observation also names {', '.join(others)}; "
                        f"confirm it belongs to {observation.resident}."
                    ),
                    observation_index=index,
                    evidence_path=path,
                )
            )
    return alerts


def _negated_findings(note: CareNote, evidence: dict, source: str) -> list[Alert]:
    """A finding quoted from a sentence that negates it is very likely the wrong reading."""
    alerts = []
    for index, observation in enumerate(note.observations):
        excerpt = evidence.get(f"observations.{index}.finding", {}).get("excerpt")
        if not excerpt:
            continue
        before = excerpt.split(observation.finding)[0] if observation.finding in excerpt else excerpt
        if NEGATORS.search(before[-40:]):
            alerts.append(
                Alert(
                    kind="possible_negation",
                    severity="high",
                    message=(
                        f"The note appears to negate this: \"{excerpt}\". Confirm the finding was "
                        "actually present."
                    ),
                    observation_index=index,
                    evidence_path=f"observations.{index}.finding",
                )
            )
    return alerts


def _contradictions(note: CareNote) -> list[Alert]:
    """Two observations about the same resident and site that do not agree."""
    alerts = []
    seen: dict[tuple, tuple[int, Observation]] = {}
    for index, observation in enumerate(note.observations):
        if not observation.body_site:
            continue
        key = (normalise_name(observation.resident or ""), observation.body_site.casefold(), observation.category)
        if key in seen:
            first_index, first = seen[key]
            if _disagree(first, observation):
                alerts.append(
                    Alert(
                        kind="contradiction",
                        severity="medium",
                        message=(
                            f"Two entries for {observation.resident or 'this resident'} at "
                            f"{observation.body_site} do not agree: '{first.finding}' and "
                            f"'{observation.finding}'."
                        ),
                        observation_index=index,
                        evidence_path=f"observations.{first_index}.finding",
                    )
                )
        else:
            seen[key] = (index, observation)
    return alerts


def _disagree(first: Observation, second: Observation) -> bool:
    if first.severity != second.severity and "unknown" not in (first.severity, second.severity):
        return True
    return SequenceMatcher(None, first.finding.casefold(), second.finding.casefold()).ratio() < 0.5


def _care_plan_gaps(note: CareNote, care_plan: list[CarePlanEntry]) -> list[Alert]:
    """An observation with nothing matching it in the plan is a documentation gap to review."""
    alerts = []
    for index, observation in enumerate(note.observations):
        if not observation.resident:
            continue
        relevant = [
            entry
            for entry in care_plan
            if same_person(entry.resident, observation.resident)
            and entry.category == observation.category
        ]
        if not relevant:
            alerts.append(
                Alert(
                    kind="not_in_care_plan",
                    severity="medium",
                    message=(
                        f"The care plan for {observation.resident} has no {observation.category} entry "
                        f"covering '{observation.finding}'. Documentation may be missing."
                    ),
                    observation_index=index,
                )
            )
            continue

        if observation.body_site and not any(
            entry.body_site and entry.body_site.casefold() == observation.body_site.casefold()
            for entry in relevant
        ):
            alerts.append(
                Alert(
                    kind="site_not_in_care_plan",
                    severity="medium",
                    message=(
                        f"The care plan for {observation.resident} covers {observation.category} but not "
                        f"{observation.body_site}. Documentation may be missing."
                    ),
                    observation_index=index,
                )
            )
    return alerts


def _open_questions(note: CareNote) -> list[Alert]:
    return [
        Alert(kind="open_question", severity="low", message=question)
        for question in note.open_questions
    ]
