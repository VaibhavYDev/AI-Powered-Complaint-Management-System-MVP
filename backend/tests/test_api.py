from io import BytesIO

from app.ai.llm import AIConfigError, AIOutputError
from app.ai.nodes import NoComplaintToEdit
from app.schemas import Intent
from tests.conftest import DRAFT, RISK

LOG_RESULT = {"intent": Intent.LOG, "draft": DRAFT, "risk": RISK, "reply": "Logged."}


def test_log_creates_complaint(client, fake_graph):
    fake_graph(LOG_RESULT)
    r = client.post("/api/chat", json={"message": "Customer reports broken tablets.", "complaint_id": None})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "LOG" and body["complaint_id"] > 0
    assert body["complaint"]["product"]["batch_number"] == "PCM24031"
    assert body["complaint"]["complainant"]["email"] is None
    assert body["risk_assessment"]["severity_class"] == "III"
    assert body["complaint"]["reference"].startswith("CC-")


def test_edit_patches_only_requested_field(client, fake_graph):
    fake_graph(LOG_RESULT)
    cid = client.post("/api/chat", json={"message": "x"}).json()["complaint_id"]

    patch = {"product": {"batch_number": "PCM24099"}}
    fake_graph({"intent": Intent.EDIT, "patch": patch, "draft": DRAFT, "reply": "Updated batch number."})
    r = client.post("/api/chat", json={"message": "Change the batch number to PCM24099", "complaint_id": cid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "EDIT" and body["patch"] == patch
    assert body["complaint"]["product"]["batch_number"] == "PCM24099"
    assert body["complaint"]["product"]["product_name"] == "Paracetamol 500 mg Tablets"
    assert body["complaint"]["complainant"]["name"] == "Rahul Sharma"
    assert body["complaint"]["risk_assessment"]["severity_class"] == "III"

    stored = client.get(f"/api/complaints/{cid}").json()
    assert stored["product"]["batch_number"] == "PCM24099" and stored["complainant"]["name"] == "Rahul Sharma"


def test_edit_without_complaint_is_400(client, fake_graph):
    fake_graph(NoComplaintToEdit("There is no complaint loaded to edit."))
    r = client.post("/api/chat", json={"message": "Change batch to B999"})
    assert r.status_code == 400 and "no complaint" in r.json()["detail"].lower()


def test_unknown_complaint_is_404(client, fake_graph):
    fake_graph(LOG_RESULT)
    r = client.post("/api/chat", json={"message": "x", "complaint_id": 999999})
    assert r.status_code == 404


def test_upload_rejects_non_pdf(client):
    r = client.post("/api/upload", files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")})
    assert r.status_code == 415
    r = client.post("/api/upload", files={"file": ("bad.pdf", BytesIO(b"not a pdf"), "application/pdf")})
    assert r.status_code == 400


def test_upload_extracts(client, fake_graph, monkeypatch):
    fake_graph({"intent": Intent.EXTRACT, "draft": DRAFT, "risk": RISK, "reply": "Extracted."})
    monkeypatch.setattr("app.api.complaints.extract_pdf_text", lambda data: "Complaint text")
    r = client.post("/api/upload", files={"file": ("complaint.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["intent"] == "EXTRACT" and r.json()["complaint"]["source"] == "document"


def test_ai_failures_map_to_http(client, fake_graph):
    for exc, status in ((AIOutputError("bad json"), 502), (AIConfigError("GROQ_API_KEY is not configured."), 503)):
        fake_graph(exc)
        r = client.post("/api/chat", json={"message": "x"})
        assert r.status_code == status and r.json()["detail"]


def test_health(client):
    body = client.get("/api/health").json()
    assert body["database"] == "ok" and body["groq_configured"] is True


def test_hosted_postgres_urls_get_the_psycopg_driver():
    from app.config import Settings

    for url in ("postgres://u:p@host/db", "postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"):
        assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@host/db"
    assert Settings(database_url="sqlite:///x.db").database_url == "sqlite:///x.db"
