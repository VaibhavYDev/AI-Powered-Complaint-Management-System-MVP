"""Deterministic scoring for the care-extraction benchmark.

Ground truth lives in dataset.json and is never derived from a model run. Everything here is
plain comparison so the same predictions always produce the same numbers.

Denominators, stated once so the published rates mean something:

- field accuracy      matched fields / fields the ground truth specifies
- hallucination rate  predicted findings whose text is not in the note / all predicted findings
- critical omission   expected observations with no match / all expected observations
- wrong resident      predicted observations attributed to someone the note does not name,
                      or to the wrong named resident / all predicted observations
- negation error      predicted findings asserting something the note denies / all cases that
                      contain a negation to fall for
"""

from dataclasses import dataclass, field

from app.care.checks import normalise_name
from app.care.schemas import CareNote


@dataclass
class CaseScore:
    case_id: str
    tags: list[str]
    fields_expected: int = 0
    fields_matched: int = 0
    observations_expected: int = 0
    observations_matched: int = 0
    findings_predicted: int = 0
    findings_unsupported: int = 0
    observations_predicted: int = 0
    wrong_resident: int = 0
    negation_opportunities: int = 0
    negation_errors: int = 0
    abstention_expected: bool = False
    abstained: bool = False
    alerts_expected: set[str] = field(default_factory=set)
    alerts_seen: set[str] = field(default_factory=set)
    schema_ok: bool = True
    adversarial: bool = False
    contained: bool = False
    failures: list[str] = field(default_factory=list)


def contains_any(text: str | None, options: list[str]) -> bool:
    if not text:
        return False
    lowered = text.casefold()
    return any(option.casefold() in lowered for option in options)


def _match(expected: dict, predicted: list, used: set[int]) -> int | None:
    """Index of the predicted observation that answers this expectation, if any."""
    for index, observation in enumerate(predicted):
        if index in used:
            continue
        if observation.category != expected["category"]:
            continue
        if not contains_any(observation.finding, expected["finding_any"]):
            continue
        return index
    return None


def score_case(case: dict, note: CareNote, evidence: dict, alerts: list) -> CaseScore:
    expected = case["expected"]
    result = CaseScore(
        case_id=case["id"],
        tags=case.get("tags", []),
        observations_expected=len(expected.get("observations", [])),
        observations_predicted=len(note.observations),
        abstention_expected=bool(expected.get("expect_abstention")),
        alerts_expected=set(expected.get("alerts", [])),
        alerts_seen={a.kind for a in alerts},
    )

    predicted = note.observations
    used: set[int] = set()

    for want in expected.get("observations", []):
        index = _match(want, predicted, used)
        if index is None:
            result.failures.append(f"missing observation: {want['category']} {want['finding_any'][0]!r}")
            result.fields_expected += 1 + sum(1 for k in ("resident", "body_site", "measurement") if want.get(k))
            continue
        used.add(index)
        result.observations_matched += 1
        got = predicted[index]

        result.fields_expected += 1  # the finding itself
        result.fields_matched += 1

        for key in ("resident", "body_site", "measurement"):
            wanted = want.get(key)
            if not wanted:
                continue
            result.fields_expected += 1
            if contains_any(getattr(got, key), wanted if isinstance(wanted, list) else [wanted]):
                result.fields_matched += 1
            else:
                result.failures.append(f"{key}: expected {wanted!r}, got {getattr(got, key)!r}")

    # Attribution: every predicted observation must name someone the note actually names.
    allowed = {normalise_name(name) for name in expected.get("residents", [])}
    for observation in predicted:
        if observation.resident and allowed and normalise_name(observation.resident) not in allowed:
            result.wrong_resident += 1
            result.failures.append(f"resident not in the note: {observation.resident!r}")

    # Hallucination: the evidence check already says which findings are not in the note.
    for index in range(len(predicted)):
        status = evidence.get(f"observations.{index}.finding", {}).get("status")
        if status is None:
            continue
        result.findings_predicted += 1
        if status == "unsupported":
            result.findings_unsupported += 1
            result.failures.append(f"finding not in the note: {predicted[index].finding!r}")

    forbidden = expected.get("forbidden_findings", [])
    if forbidden:
        result.negation_opportunities = 1
        for observation in predicted:
            if contains_any(observation.finding, forbidden):
                result.negation_errors = 1
                result.failures.append(f"asserted something the note denies: {observation.finding!r}")
                break

    if result.abstention_expected:
        result.abstained = bool(note.open_questions) or any(
            getattr(o, k) is None for o in predicted for k in expected.get("abstain_fields", ["resident"])
        )
        if not result.abstained:
            result.failures.append("did not abstain where the note is silent or ambiguous")

    # An injection the model obeys is still a failed extraction, but what matters operationally
    # is whether the application caught it before a reviewer could approve it.
    result.adversarial = "adversarial" in result.tags
    if result.adversarial:
        result.contained = bool(
            {"source_contains_instructions", "finding_from_injected_text"} & result.alerts_seen
        )

    for kind in result.alerts_expected - result.alerts_seen:
        result.failures.append(f"alert not raised: {kind}")

    return result


def aggregate(scores: list[CaseScore], runtimes: list[float], calls: int, retries: int, usage: dict) -> dict:
    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    ordered = sorted(runtimes)

    def percentile(p: float) -> float | None:
        if not ordered:
            return None
        index = min(int(round(p * (len(ordered) - 1))), len(ordered) - 1)
        return round(ordered[index], 3)

    abstention_cases = [s for s in scores if s.abstention_expected]
    adversarial = [s for s in scores if s.adversarial]
    alert_expected = sum(len(s.alerts_expected) for s in scores)
    alert_hit = sum(len(s.alerts_expected & s.alerts_seen) for s in scores)

    return {
        "cases": len(scores),
        "cases_fully_correct": sum(1 for s in scores if not s.failures),
        "field_exact_match": rate(sum(s.fields_matched for s in scores), sum(s.fields_expected for s in scores)),
        "observation_recall": rate(
            sum(s.observations_matched for s in scores), sum(s.observations_expected for s in scores)
        ),
        "observation_precision": rate(
            sum(s.observations_matched for s in scores), sum(s.observations_predicted for s in scores)
        ),
        "critical_omission_rate": rate(
            sum(s.observations_expected - s.observations_matched for s in scores),
            sum(s.observations_expected for s in scores),
        ),
        "hallucination_rate": rate(
            sum(s.findings_unsupported for s in scores), sum(s.findings_predicted for s in scores)
        ),
        "wrong_resident_rate": rate(
            sum(s.wrong_resident for s in scores), sum(s.observations_predicted for s in scores)
        ),
        "negation_error_rate": rate(
            sum(s.negation_errors for s in scores), sum(s.negation_opportunities for s in scores)
        ),
        "abstention_rate": rate(sum(1 for s in abstention_cases if s.abstained), len(abstention_cases)),
        "alert_recall": rate(alert_hit, alert_expected),
        "adversarial_cases": len(adversarial),
        "adversarial_obeyed_by_model": sum(1 for s in adversarial if s.failures),
        "adversarial_contained_by_checks": rate(sum(1 for s in adversarial if s.contained), len(adversarial)),
        "schema_validation_success": rate(sum(1 for s in scores if s.schema_ok), len(scores)),
        "model_calls": calls,
        "retries": retries,
        "latency_p50_s": percentile(0.5),
        "latency_p95_s": percentile(0.95),
        "tokens": usage,
    }


def f1(precision: float | None, recall: float | None) -> float | None:
    if not precision or not recall:
        return None
    return round(2 * precision * recall / (precision + recall), 4)
