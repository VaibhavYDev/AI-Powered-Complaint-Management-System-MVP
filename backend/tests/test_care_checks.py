"""Reliability checks over an extracted care note. All residents and notes are fictional."""

import pytest

from app.care.checks import analyse
from app.care.schemas import CareNote, CarePlanEntry, Observation

NOTE = """[page 1]
Shift notes, 14 March 2026.
Frau Anna Keller: redness at the left heel, about 2 x 3 cm, not broken. Cream applied.
Herr Josef Brandt: walked to the dining room with a frame. No pain reported.
"""

PLAN = [
    CarePlanEntry(resident="Anna Keller", category="mobility", instruction="Assist with transfers"),
    CarePlanEntry(resident="Josef Brandt", category="mobility", body_site=None, instruction="Walking frame"),
]


def note(**kwargs) -> CareNote:
    return CareNote.model_validate(kwargs)


def obs(**kwargs) -> dict:
    return {"category": "wound", "finding": "redness at the left heel", **kwargs}


def kinds(alerts) -> list[str]:
    return [a.kind for a in alerts]


def test_a_quoted_finding_for_a_named_resident_raises_no_attribution_alert():
    extracted = note(residents=["Anna Keller", "Josef Brandt"], observations=[obs(resident="Anna Keller", body_site="left heel")])
    evidence, alerts = analyse(extracted, NOTE, PLAN)

    assert evidence["observations.0.finding"]["status"] in {"verbatim", "normalized"}
    assert "unsupported_finding" not in kinds(alerts)
    assert "resident_not_in_note" not in kinds(alerts)


def test_a_finding_that_is_not_in_the_note_is_flagged():
    extracted = note(residents=["Anna Keller"], observations=[obs(resident="Anna Keller", finding="open pressure ulcer grade 3")])
    _, alerts = analyse(extracted, NOTE, PLAN)

    unsupported = [a for a in alerts if a.kind == "unsupported_finding"]
    assert len(unsupported) == 1 and unsupported[0].severity == "high"


def test_a_resident_who_is_not_in_the_note_is_flagged():
    extracted = note(residents=["Anna Keller"], observations=[obs(resident="Maria Schmidt")])
    _, alerts = analyse(extracted, NOTE, PLAN)
    assert "resident_not_in_note" in kinds(alerts)


def test_an_unattributed_observation_is_flagged_when_the_note_names_several_residents():
    extracted = note(residents=["Anna Keller", "Josef Brandt"], observations=[obs(resident=None)])
    _, alerts = analyse(extracted, NOTE, PLAN)

    unattributed = [a for a in alerts if a.kind == "unattributed_observation"]
    assert len(unattributed) == 1 and unattributed[0].severity == "high"


def test_a_single_resident_note_does_not_demand_attribution():
    single = "[page 1]\nFrau Anna Keller: redness at the left heel. Cream applied."
    extracted = note(residents=["Anna Keller"], observations=[obs(resident=None)])
    _, alerts = analyse(extracted, single, PLAN)
    assert "unattributed_observation" not in kinds(alerts)


def test_a_finding_lifted_from_a_negated_sentence_is_flagged():
    extracted = note(
        residents=["Josef Brandt"],
        observations=[{"category": "pain", "finding": "pain reported", "resident": "Josef Brandt"}],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)

    negation = [a for a in alerts if a.kind == "possible_negation"]
    assert len(negation) == 1 and "negate" in negation[0].message


@pytest.mark.parametrize("german", ["kein Druckgeschwür", "keine Schmerzen"])
def test_german_negations_are_recognised(german):
    source = f"[page 1]\nFrau Anna Keller: {german} festgestellt."
    extracted = note(
        residents=["Anna Keller"],
        observations=[{"category": "wound", "finding": german.split(" ", 1)[1], "resident": "Anna Keller"}],
    )
    _, alerts = analyse(extracted, source, [])
    assert "possible_negation" in kinds(alerts)


def test_two_entries_for_the_same_site_that_disagree_are_flagged():
    extracted = note(
        residents=["Anna Keller"],
        observations=[
            obs(resident="Anna Keller", body_site="left heel", severity="mild"),
            obs(resident="Anna Keller", body_site="left heel", severity="severe"),
        ],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)
    assert "contradiction" in kinds(alerts)


def test_agreeing_entries_are_not_flagged_as_contradictions():
    extracted = note(
        residents=["Anna Keller"],
        observations=[
            obs(resident="Anna Keller", body_site="left heel", severity="mild"),
            obs(resident="Anna Keller", body_site="left heel", severity="mild"),
        ],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)
    assert "contradiction" not in kinds(alerts)


def test_a_wound_absent_from_the_care_plan_is_reported_as_a_documentation_gap():
    """The scenario the lab is built around: a new wound with nothing about it in the plan."""
    extracted = note(residents=["Anna Keller"], observations=[obs(resident="Anna Keller", body_site="left heel")])
    _, alerts = analyse(extracted, NOTE, PLAN)

    gap = [a for a in alerts if a.kind == "not_in_care_plan"]
    assert len(gap) == 1
    assert "Anna Keller" in gap[0].message and "wound" in gap[0].message
    assert gap[0].severity == "medium"
    # A documentation gap, never a clinical instruction.
    assert "Documentation may be missing" in gap[0].message


def test_a_covered_observation_produces_no_gap():
    extracted = note(
        residents=["Josef Brandt"],
        observations=[{"category": "mobility", "finding": "walked to the dining room with a frame", "resident": "Josef Brandt"}],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)
    assert "not_in_care_plan" not in kinds(alerts)


def test_a_plan_entry_for_another_body_site_is_still_a_gap():
    plan = [CarePlanEntry(resident="Anna Keller", category="wound", body_site="right elbow", instruction="Daily dressing")]
    extracted = note(residents=["Anna Keller"], observations=[obs(resident="Anna Keller", body_site="left heel")])
    _, alerts = analyse(extracted, NOTE, plan)
    assert "site_not_in_care_plan" in kinds(alerts)


def test_open_questions_become_low_priority_alerts():
    extracted = note(
        residents=["Anna Keller"],
        observations=[obs(resident="Anna Keller", body_site="left heel")],
        open_questions=["The note does not say when the redness was first seen."],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)

    questions = [a for a in alerts if a.kind == "open_question"]
    assert len(questions) == 1 and questions[0].severity == "low"


def test_observations_name_a_resident_even_if_the_roster_missed_them():
    extracted = note(residents=[], observations=[obs(resident="Anna Keller")])
    assert extracted.residents == ["Anna Keller"]


# --- honorifics ------------------------------------------------------------------------------
# A real run showed the model returning "Frau Anna Keller" while the care plan said
# "Anna Keller", which produced false documentation gaps.

@pytest.mark.parametrize("in_note, in_plan", [
    ("Frau Anna Keller", "Anna Keller"),
    ("Herr Josef Brandt", "Josef Brandt"),
    ("Anna Keller", "Frau Anna Keller"),
    ("Dr. Anna Keller", "Anna Keller"),
    ("Frau Dr. Anna Keller", "Anna Keller"),
])
def test_an_honorific_does_not_hide_a_matching_care_plan_entry(in_note, in_plan):
    plan = [CarePlanEntry(resident=in_plan, category="wound", body_site="left heel", instruction="Daily check")]
    extracted = note(residents=[in_note], observations=[obs(resident=in_note, body_site="left heel")])
    _, alerts = analyse(extracted, NOTE, plan)
    assert "not_in_care_plan" not in kinds(alerts)
    assert "site_not_in_care_plan" not in kinds(alerts)


def test_different_people_are_still_different():
    plan = [CarePlanEntry(resident="Josef Brandt", category="wound", instruction="Daily check")]
    extracted = note(residents=["Frau Anna Keller"], observations=[obs(resident="Frau Anna Keller")])
    _, alerts = analyse(extracted, NOTE, plan)
    assert "not_in_care_plan" in kinds(alerts)


def test_the_same_resident_written_two_ways_still_contradicts_itself():
    extracted = note(
        residents=["Frau Anna Keller"],
        observations=[
            obs(resident="Frau Anna Keller", body_site="left heel", severity="mild"),
            obs(resident="Anna Keller", body_site="left heel", severity="severe"),
        ],
    )
    _, alerts = analyse(extracted, NOTE, PLAN)
    assert "contradiction" in kinds(alerts)


def test_a_negation_in_the_previous_sentence_is_not_borrowed():
    """A real run flagged Josef Brandt's mobility entry because the sentence before it, about a
    different resident, said 'No pain reported.'"""
    extracted = note(
        residents=["Frau Anna Keller", "Herr Josef Brandt"],
        observations=[
            {
                "category": "mobility",
                "finding": "walked to the dining room with a frame",
                "resident": "Herr Josef Brandt",
            }
        ],
    )
    _, alerts = analyse(extracted, NOTE, [])
    assert "possible_negation" not in kinds(alerts)


def test_a_negation_in_the_same_sentence_is_still_caught():
    extracted = note(
        residents=["Herr Josef Brandt"],
        observations=[{"category": "pain", "finding": "pain reported", "resident": "Herr Josef Brandt"}],
    )
    _, alerts = analyse(extracted, NOTE, [])
    assert "possible_negation" in kinds(alerts)
