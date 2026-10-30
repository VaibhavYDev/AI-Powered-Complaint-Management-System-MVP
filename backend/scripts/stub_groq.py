"""A stand-in for Groq's HTTP API, used only by the browser end-to-end test.

That test exists to prove the application works: LangGraph routing, schema validation, the
evidence check, the database, auth, and the React interface. It has to run on every pull
request, including from forks, which cannot be given a provider key. So the remote endpoint -
and only the remote endpoint - is replaced here. The application is unmodified and unaware of
it: GROQ_BASE_URL and GROQ_API_BASE point its real clients at this server, which answers in
Groq's wire format.

This is not a model and does not pretend to be one. Replies are canned, chosen by the response
schema the application asked for, and anything unrecognised is answered with 400 so that a test
can never pass because the stub improvised. `scripts/e2e.py` is the equivalent check against
the real provider.
"""

import json
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

# Deliberately omits the configured gemma2-9b-it, which Groq retired: the application must take
# its own fallback path here exactly as it does against the real provider.
MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]

TODAY = date.today().isoformat()

COMPLAINT = {
    "complainant": {
        "name": "Rahul Sharma",
        "email": None,
        "phone": None,
        "organization": None,
        "country": None,
        "contact_channel": None,
    },
    "product": {
        "product_name": "Paracetamol 500 mg tablets",
        "generic_name": "Paracetamol",
        "manufacturer": None,
        "dosage_form": "tablet",
        "strength": "500 mg",
        "batch_number": "PCM24031",
        "lot_number": None,
        "manufacturing_date": None,
        "expiry_date": None,
    },
    "complaint": {
        "complaint_received_date": TODAY,
        "event_date": None,
        "complaint_description": "Tablets were chipped and broken inside the blister pack.",
        "defect_category": "physical_defect",
        "defect_description": "tablets chipped and broken inside the blister pack",
        "affected_quantity": None,
        "sample_available": True,
        "suspected_counterfeit": None,
    },
    "patient": {
        "patient_involved": None,
        "patient_age": None,
        "patient_gender": None,
        "adverse_event": None,
        "medical_attention_required": None,
        "hospitalization_required": False,
        "death_reported": None,
    },
}

RISK = {
    "severity_class": "II",
    "severity_reason": "A physical defect in an oral solid dose form with no reported patient harm.",
    "immediate_actions": ["Quarantine the retained sample", "Open a deviation for batch PCM24031"],
    "recommended_follow_up": ["Review batch packaging records", "Inspect retained samples of the batch"],
    "confidence": 0.8,
}

EDIT = {"changes": [{"field": "batch_number", "value": "PCM24099"}], "clear": []}

# Two observations: one genuinely in the note, one taken from an instruction addressed to the
# reader. The second is what the deterministic injection check has to catch.
CARE = {
    "residents": ["Anna Keller", "Josef Brandt"],
    "observations": [
        {
            "resident": "Anna Keller",
            "category": "wound",
            "finding": "redness appeared at the left heel",
            "body_site": "left heel",
            "severity": "mild",
            "measurement": "2 x 3 cm",
            "action_taken": "Barrier cream applied, heel kept free of pressure",
            "follow_up_required": None,
            "observed_on": None,
        },
        {
            "resident": "Anna Keller",
            "category": "medication",
            "finding": "given penicillin",
            "body_site": None,
            "severity": "unknown",
            "measurement": None,
            "action_taken": None,
            "follow_up_required": None,
            "observed_on": None,
        },
    ],
    "open_questions": [],
}


def router(messages: list[dict]) -> dict:
    """The one reply that depends on the input. Keyword matching, not comprehension: the test
    asserts what the application does with each intent, not that a stub can classify."""
    text = " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "user").lower()
    return {"intent": "EDIT" if "actually" in text or "change the" in text else "LOG"}


def reply_for(body: dict) -> dict:
    asked = json.dumps(body.get("response_format", {}))
    for name, payload in (
        ("RouterDecision", lambda: router(body.get("messages", []))),
        ("ComplaintData", lambda: COMPLAINT),
        ("EditProposal", lambda: EDIT),
        ("RiskAssessment", lambda: RISK),
        ("CareNote", lambda: CARE),
    ):
        if f'"{name}"' in asked:
            return payload()
    raise KeyError(f"no canned reply for this request: {asked[:300]}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.endswith("/models"):
            self._send(200, {"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]})
        else:
            self._send(404, {"error": {"message": f"stub has no {self.path}", "code": "not_found"}})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            content = reply_for(body)
        except KeyError as exc:
            self._send(400, {"error": {"message": str(exc), "code": "stub_has_no_reply"}})
            return
        self._send(200, {
            "id": "stub",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model", MODELS[0]),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(content)},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("stub-groq: " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8111
    print(f"stub-groq listening on {port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
