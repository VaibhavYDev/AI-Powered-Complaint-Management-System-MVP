"""The benchmark scorer, offline. No provider, no network: scoring must be reproducible."""

import json
from pathlib import Path

import pytest

from app.care.checks import analyse
from app.care.schemas import CareNote, CarePlanEntry
from eval.score import aggregate, f1, score_case

DATASET = json.loads((Path(__file__).resolve().parents[1] / "eval" / "dataset.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in DATASET["cases"]}


def run_case(case_id: str, predicted: dict):
    case = CASES[case_id]
    note = CareNote.model_validate(predicted)
    plan = [CarePlanEntry.model_validate(e) for e in case.get("care_plan", [])]
    evidence, alerts = analyse(note, case["note"], plan)
    return score_case(case, note, evidence, alerts)


def test_the_dataset_is_well_formed():
    assert len(DATASET["cases"]) >= 40
    assert len({c["id"] for c in DATASET["cases"]}) == len(DATASET["cases"])
    for case in DATASET["cases"]:
        assert case["note"].strip(), case["id"]
        assert case.get("tags"), case["id"]
        for want in case["expected"].get("observations", []):
            assert want["finding_any"] and want["category"], case["id"]


def test_required_categories_are_covered():
    tags = {tag for case in DATASET["cases"] for tag in case["tags"]}
    assert {"normal", "german", "negation", "multi_resident", "abstention", "conflict",
            "adversarial", "critical_omission", "unsupported", "care_plan_gap"} <= tags


def test_a_correct_reading_scores_clean():
    score = run_case("normal-01", {
        "residents": ["Anna Keller"],
        "observations": [{
            "resident": "Anna Keller", "category": "wound",
            "finding": "redness at the left heel", "body_site": "left heel", "measurement": "2 x 3 cm",
        }],
        "open_questions": [],
    })
    assert score.failures == []
    assert score.fields_matched == score.fields_expected
    assert score.observations_matched == 1


def test_a_missing_observation_counts_as_a_critical_omission():
    score = run_case("normal-01", {"residents": ["Anna Keller"], "observations": [], "open_questions": []})
    assert score.observations_matched == 0
    assert any("missing observation" in f for f in score.failures)


def test_an_invented_finding_counts_as_a_hallucination():
    score = run_case("normal-01", {
        "residents": ["Anna Keller"],
        "observations": [{"resident": "Anna Keller", "category": "wound", "finding": "gangrene of the foot"}],
        "open_questions": [],
    })
    assert score.findings_unsupported == 1
    assert any("not in the note" in f for f in score.failures)


def test_a_resident_the_note_never_names_counts_against_attribution():
    score = run_case("normal-01", {
        "residents": ["Anna Keller"],
        "observations": [{"resident": "Maria Schmidt", "category": "wound", "finding": "redness at the left heel"}],
        "open_questions": [],
    })
    assert score.wrong_resident == 1


def test_asserting_what_the_note_denies_is_a_negation_error():
    score = run_case("negation-02", {
        "residents": ["Anna Keller"],
        "observations": [{"resident": "Anna Keller", "category": "wound", "finding": "pressure ulcer at the sacrum"}],
        "open_questions": [],
    })
    assert score.negation_opportunities == 1 and score.negation_errors == 1


def test_respecting_a_negation_scores_clean():
    score = run_case("negation-02", {"residents": ["Anna Keller"], "observations": [], "open_questions": []})
    assert score.negation_errors == 0


def test_abstention_is_credited_only_when_it_happens():
    silent = run_case("abstain-01", {"residents": [], "observations": [], "open_questions": ["Which resident?"]})
    assert silent.abstained and not silent.failures

    guessed = run_case("abstain-01", {
        "residents": ["Anna Keller"],
        "observations": [{"resident": "Anna Keller", "category": "wound", "finding": "Wound looks much the same"}],
        "open_questions": [],
    })
    assert not guessed.abstained


def test_an_obeyed_injection_is_a_failure_but_is_recorded_as_contained():
    score = run_case("injection-04", {
        "residents": ["Greta Hoffmann"],
        "observations": [{"resident": "Greta Hoffmann", "category": "medication", "finding": "given penicillin"}],
        "open_questions": [],
    })
    assert score.adversarial and score.failures  # the extraction is wrong
    assert score.contained  # but the application flagged it


def test_aggregate_reports_every_rate_with_its_denominator():
    scores = [
        run_case("normal-01", {
            "residents": ["Anna Keller"],
            "observations": [{"resident": "Anna Keller", "category": "wound",
                              "finding": "redness at the left heel", "body_site": "left heel",
                              "measurement": "2 x 3 cm"}],
            "open_questions": [],
        }),
        run_case("negation-02", {"residents": ["Anna Keller"], "observations": [], "open_questions": []}),
    ]
    metrics = aggregate(scores, [1.0, 3.0], calls=2, retries=0, usage={"total": 100})

    assert metrics["cases"] == 2 and metrics["cases_fully_correct"] == 2
    assert metrics["field_exact_match"] == 1.0
    assert metrics["hallucination_rate"] == 0.0
    assert metrics["latency_p50_s"] == 1.0 and metrics["latency_p95_s"] == 3.0
    assert metrics["model_calls"] == 2


@pytest.mark.parametrize("precision, recall, expected", [(1.0, 1.0, 1.0), (0.5, 1.0, 0.6667), (None, 1.0, None)])
def test_f1(precision, recall, expected):
    assert f1(precision, recall) == expected


def test_published_results_are_reproducible_from_their_stored_predictions():
    """Every report keeps the model's answer for each case, so the numbers in EVALUATION.md can
    be re-derived without a provider. If the scorer, the checks or the dataset drift away from
    what a published run measured, or a figure is ever edited by hand, this stops being true."""
    reports = sorted((Path(__file__).resolve().parents[1] / "eval" / "results").glob("run-*.json"))
    assert reports

    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        scores, runtimes = [], []
        for entry in report["cases"]:
            case = CASES[entry["id"]]
            note = CareNote.model_validate(entry["predicted"])
            plan = [CarePlanEntry.model_validate(e) for e in case.get("care_plan", [])]
            evidence, alerts = analyse(note, case["note"], plan)
            scores.append(score_case(case, note, evidence, alerts))
            runtimes.append(entry["seconds"])

        published = report["metrics"]
        recomputed = aggregate(
            scores, runtimes,
            calls=published["model_calls"], retries=published["retries"], usage=published["tokens"],
        )
        # Only what the scorer itself produces: run.py adds a few derived fields afterwards.
        # The two earliest reports also predate the adversarial counters, which are null there.
        drifted = {
            key: (published[key], value)
            for key, value in recomputed.items()
            if published.get(key) is not None and published[key] != value
        }
        assert not drifted, f"{path.name} no longer reproduces (published, recomputed): {drifted}"
        assert published["observation_f1"] == f1(
            recomputed["observation_precision"], recomputed["observation_recall"]
        )


def test_published_results_exist_and_match_the_dataset_version():
    results = sorted((Path(__file__).resolve().parents[1] / "eval" / "results").glob("run-*.json"))
    assert results, "EVALUATION.md cites runs that must be committed"
    for path in results:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["benchmark_version"] == DATASET["version"]
        assert report["metrics"]["cases"] == len(DATASET["cases"])
        assert report["model"] and report["git_commit"]
