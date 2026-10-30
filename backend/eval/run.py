"""Run the care-extraction benchmark against the configured model.

    cd backend && .venv/Scripts/python eval/run.py [--limit N] [--out results/<name>.json]

Every number in EVALUATION.md comes from a run of this script. Nothing here invents a result:
if the provider cannot be reached the run fails and says so.
"""

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai import llm  # noqa: E402
from app.care.checks import analyse  # noqa: E402
from app.care.extract import prompt  # noqa: E402
from app.care.schemas import CareNote, CarePlanEntry  # noqa: E402
from app.config import settings  # noqa: E402
from eval.score import aggregate, f1, score_case  # noqa: E402

HERE = Path(__file__).parent


def _cost(model: str, counters: dict, cases: int) -> dict | None:
    """Only reported when a price for this exact model has been recorded in prices.json."""
    prices = json.loads((HERE / "prices.json").read_text(encoding="utf-8"))
    price = prices.get(model)
    if not price or not cases:
        return None
    total = counters["prompt_tokens"] / 1e6 * price["input_per_m"] + counters["completion_tokens"] / 1e6 * price["output_per_m"]
    return {
        "usd_total": round(total, 6),
        "usd_per_case": round(total / cases, 6),
        "price_source": price["source"],
        "price_checked": price["checked"],
    }


def commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=HERE.parents[1]).strip()
    except Exception:
        return "unknown"


def run(limit: int | None, out: Path) -> dict:
    dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    cases = dataset["cases"][:limit] if limit else dataset["cases"]

    llm.resolve_model()
    llm.reset_telemetry()
    model = llm.model_status()["active_model"]
    if not settings.groq_api_key:
        raise SystemExit("GROQ_API_KEY is not set: the benchmark needs a real provider.")

    scores, runtimes, details = [], [], []
    system = prompt()

    for index, case in enumerate(cases, 1):
        plan = [CarePlanEntry.model_validate(entry) for entry in case.get("care_plan", [])]
        started = time.perf_counter()
        schema_ok, note = True, CareNote()
        error = None
        try:
            note = llm.structured(CareNote, system, case["note"])
        except Exception as exc:  # the failure is recorded, never hidden
            schema_ok, error = False, f"{type(exc).__name__}: {exc}"[:200]
        elapsed = time.perf_counter() - started
        runtimes.append(elapsed)

        evidence, alerts = analyse(note, case["note"], plan)
        score = score_case(case, note, evidence, alerts)
        score.schema_ok = schema_ok
        if error:
            score.failures.append(error)
        scores.append(score)

        details.append(
            {
                "id": case["id"],
                "tags": case.get("tags", []),
                "seconds": round(elapsed, 3),
                "schema_ok": schema_ok,
                "failures": score.failures,
                "predicted": note.model_dump(mode="json"),
            }
        )
        print(f"  [{index:>2}/{len(cases)}] {case['id']:<14} {elapsed:5.2f}s {'ok' if not score.failures else 'FAIL'}")

    counters = llm.telemetry
    usage = {
        "prompt": counters["prompt_tokens"],
        "completion": counters["completion_tokens"],
        "total": counters["total_tokens"],
    }
    metrics = aggregate(scores, runtimes, counters["calls"], counters["retries"], usage)
    metrics["errors"] = dict(counters["errors"])
    metrics["tokens_per_case"] = round(counters["total_tokens"] / len(cases), 1) if cases else None
    metrics["cost"] = _cost(model, counters, len(cases))
    metrics["observation_f1"] = f1(metrics["observation_precision"], metrics["observation_recall"])

    report = {
        "benchmark_version": dataset["version"],
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit(),
        "provider": "groq",
        "configured_model": settings.groq_model,
        "model": model,
        "output_method": llm.output_method(model),
        "reasoning_effort": settings.groq_reasoning_effort,
        "python": platform.python_version(),
        "metrics": metrics,
        "cases": details,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--out", type=Path, default=HERE / "results" / "latest.json")
    args = parser.parse_args()

    report = run(args.limit, args.out)
    print("\nmodel:", report["model"], "| commit:", report["git_commit"][:7])
    for key, value in report["metrics"].items():
        print(f"  {key:<28} {value}")
    print("\nwritten to", args.out)


if __name__ == "__main__":
    main()
