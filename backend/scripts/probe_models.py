"""Check what Groq actually serves for this key and that the fallback model works in
JSON mode with the same call path the app uses.

    cd backend && .venv/Scripts/python scripts/probe_models.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from groq import APIStatusError, Groq
from pydantic import BaseModel

from app.ai import llm
from app.config import settings

if not settings.groq_api_key:
    raise SystemExit("GROQ_API_KEY is not set in backend/.env")

client = Groq(api_key=settings.groq_api_key)
served = sorted(m.id for m in client.models.list().data)
print(f"{len(served)} models served for this key:")
print("  " + "\n  ".join(served))

for label, model in (("configured", settings.groq_model), ("fallback", settings.groq_fallback_model), ("larger option", "openai/gpt-oss-120b")):
    try:
        client.models.retrieve(model)
        print(f"{label:14} {model:28} AVAILABLE")
    except APIStatusError as exc:
        print(f"{label:14} {model:28} UNAVAILABLE ({llm._error_code(exc) or exc.status_code})")

llm.resolve_model()
print("resolved:", json.dumps(llm.model_status()))


class Probe(BaseModel):
    product: str
    batch_number: str
    severity_class: str


t = time.perf_counter()
result = llm.structured(
    Probe,
    'Extract the product, batch number and a severity class ("I", "II" or "III") from the message. Answer with JSON only.',
    "Chipped Paracetamol 500 mg tablets from batch PCM24031, no patient harm.",
)
print(f"JSON-mode call via {llm.model_status()['active_model']} in {time.perf_counter() - t:.1f}s -> {result.model_dump()}")
