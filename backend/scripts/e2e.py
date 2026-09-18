"""End-to-end check of the real pipeline (Groq + PostgreSQL) against a running API.

    cd backend && .venv/Scripts/python scripts/e2e.py [http://localhost:8000]

Exercises LOG -> EDIT (field-only patch) -> EXTRACT (PDF upload) plus the expected
error paths, and prints what came back so the run can be eyeballed.
"""

import json
import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SAMPLES = Path(__file__).resolve().parents[2] / "samples"
client = httpx.Client(base_url=BASE, timeout=120)

LOG_MESSAGE = (
    "Customer Rahul Sharma reported that Paracetamol 500 mg tablets from batch PCM24031 were chipped and "
    "broken inside the blister pack. The complaint was received today. No hospitalization occurred and the sample is available."
)


def show(title: str, body: dict) -> None:
    print(f"\n=== {title}")
    print(json.dumps(body, indent=2, ensure_ascii=False))


def check(cond: bool, msg: str) -> None:
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        sys.exit(1)


health = client.get("/api/health").json()
show("health", health)
check(health["database"] == "ok" and health["groq_configured"], "database up and Groq configured")

# LOG
r = client.post("/api/chat", json={"message": LOG_MESSAGE, "complaint_id": None})
show("LOG", r.json())
check(r.status_code == 200, f"LOG status {r.status_code}")
log = r.json()
cid = log["complaint_id"]
check(log["intent"] == "LOG", "router chose LOG")
check(log["complaint"]["product"]["batch_number"] == "PCM24031", "batch number extracted")
check(log["complaint"]["complainant"]["name"] == "Rahul Sharma", "complainant name extracted")
check(log["complaint"]["complainant"]["email"] is None, "unstated email stays null")
check(log["risk_assessment"]["severity_class"] in ("I", "II", "III"), "risk assessment produced")

# EDIT
r = client.post("/api/chat", json={"message": "Actually change the batch number to PCM24099.", "complaint_id": cid})
show("EDIT", {k: v for k, v in r.json().items() if k != "complaint"} | {"product": r.json().get("complaint", {}).get("product")})
check(r.status_code == 200, f"EDIT status {r.status_code}")
edit = r.json()
check(edit["intent"] == "EDIT", "router chose EDIT")
check(edit["patch"] == {"product": {"batch_number": "PCM24099"}}, "patch contains only the batch number")
before, after = log["complaint"], edit["complaint"]
check(after["product"]["batch_number"] == "PCM24099", "batch number updated")
check({k: v for k, v in after["product"].items() if k != "batch_number"} == {k: v for k, v in before["product"].items() if k != "batch_number"}, "other product fields untouched")
check(after["complainant"] == before["complainant"] and after["complaint"] == before["complaint"] and after["patient"] == before["patient"], "other sections untouched")
check(after["risk_assessment"] == before["risk_assessment"], "risk assessment unchanged for a non-risk edit")

# nested EDIT
r = client.post("/api/chat", json={"message": "The complainant's email is rahul@example.com", "complaint_id": cid})
show("EDIT nested", {k: v for k, v in r.json().items() if k != "complaint"})
check(r.status_code == 200 and r.json()["patch"] == {"complainant": {"email": "rahul@example.com"}}, "nested email patch")
check(r.json()["complaint"]["product"]["batch_number"] == "PCM24099", "earlier edit preserved")
check(r.json()["complaint"]["complainant"]["name"] == "Rahul Sharma", "complainant name preserved")

# multi-field EDIT
r = client.post("/api/chat", json={"message": "Set the strength to 650 mg, the dosage form to film-coated tablet and the manufacturer to Zenith Pharma.", "complaint_id": cid})
show("EDIT multi-field", {k: v for k, v in r.json().items() if k != "complaint"})
check(r.status_code == 200, f"multi-field EDIT status {r.status_code}")
patch = r.json()["patch"]
check(set(patch) == {"product"} and set(patch["product"]) == {"strength", "dosage_form", "manufacturer"}, "patch has exactly the three product fields")
prod = r.json()["complaint"]["product"]
check(prod["batch_number"] == "PCM24099" and prod["product_name"] == before["product"]["product_name"], "batch and product name untouched")
check(r.json()["complaint"]["complainant"]["email"] == "rahul@example.com", "nested edit preserved")

# explicit clear
r = client.post("/api/chat", json={"message": "Remove the complainant's email address.", "complaint_id": cid})
show("EDIT clear", {k: v for k, v in r.json().items() if k != "complaint"})
check(r.status_code == 200 and r.json()["patch"] == {"complainant": {"email": None}}, "explicit clear -> email null")
check(r.json()["complaint"]["complainant"]["name"] == "Rahul Sharma", "name survives the clear")
check(r.json()["complaint"]["product"]["strength"] == "650 mg", "multi-field edit preserved")
check(r.json()["risk_assessment"] is None, "no re-assessment for non-risk edits")

# risk-relevant EDIT triggers a fresh assessment
r = client.post("/api/chat", json={"message": "Update: the customer actually swallowed a broken tablet, needed medical attention and was hospitalised overnight.", "complaint_id": cid})
show("EDIT risk-relevant", {k: v for k, v in r.json().items() if k != "complaint"})
check(r.status_code == 200 and "patient" in r.json()["patch"], "patient section patched")
check(r.json()["complaint"]["patient"]["hospitalization_required"] is True, "hospitalization captured")
check(r.json()["risk_assessment"] is not None, "risk re-assessed after patient facts changed")
check(r.json()["risk_assessment"]["severity_class"] in ("I", "II"), f"severity escalated to {r.json()['risk_assessment']['severity_class']}")
check(r.json()["complaint"]["product"]["batch_number"] == "PCM24099", "product data untouched by patient edit")

stored = client.get(f"/api/complaints/{cid}").json()
check(stored["product"]["batch_number"] == "PCM24099" and stored["complainant"]["email"] is None and stored["patient"]["hospitalization_required"] is True, "all edits persisted in PostgreSQL")

# EXTRACT
pdf = SAMPLES / "complaint_02_adverse_event.pdf"
with pdf.open("rb") as fh:
    r = client.post("/api/upload", files={"file": (pdf.name, fh, "application/pdf")})
show("EXTRACT", r.json())
check(r.status_code == 200, f"EXTRACT status {r.status_code}")
ext = r.json()
check(ext["intent"] == "EXTRACT", "router chose EXTRACT")
check(ext["complaint"]["product"]["batch_number"] == "AMC25017", "batch number extracted from PDF")
check(ext["complaint"]["patient"]["hospitalization_required"] is True, "hospitalization captured from PDF")
check(ext["complaint"]["risk_assessment"]["severity_class"] in ("I", "II"), "adverse event triaged as Class I/II")

# error paths
r = client.post("/api/chat", json={"message": "Change the batch number to B999."})
check(r.status_code == 400, f"EDIT without complaint -> {r.status_code}: {r.json()['detail']}")
r = client.post("/api/chat", json={"message": "hi", "complaint_id": 999999})
check(r.status_code == 404, f"unknown complaint -> {r.status_code}")
r = client.post("/api/upload", files={"file": ("x.txt", b"hello", "text/plain")})
check(r.status_code == 415, f"non-PDF upload -> {r.status_code}")
r = client.post("/api/upload", files={"file": ("x.pdf", b"%PDF-1.4 broken", "application/pdf")})
check(r.status_code == 400, f"corrupt PDF -> {r.status_code}: {r.json()['detail']}")

print("\nAll end-to-end checks passed. Model in use:", client.get("/api/health").json()["active_model"])
