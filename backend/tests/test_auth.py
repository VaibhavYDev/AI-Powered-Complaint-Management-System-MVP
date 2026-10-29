"""Authentication and owner-scoped authorization."""

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.documents import Document
from app.main import app
from app.schemas import Intent
from tests.conftest import DRAFT, RISK, sign_in

LOG_RESULT = {"intent": Intent.LOG, "draft": DRAFT, "risk": RISK, "reply": "Logged."}


@pytest.fixture
def credentials():
    """Unique per test: the suite shares one database, so a fixed address would collide."""
    return {"email": f"qa-{uuid4().hex[:8]}@example.com", "password": "correct horse battery"}


def log_complaint(c: TestClient) -> int:
    return c.post("/api/chat", json={"message": "broken tablets"}).json()["complaint_id"]


# --- unauthenticated access ------------------------------------------------------------------

@pytest.mark.parametrize("method, path, kwargs", [
    ("get", "/api/complaints", {}),
    ("get", "/api/complaints/1", {}),
    ("get", "/api/auth/me", {}),
    ("post", "/api/chat", {"json": {"message": "broken tablets"}}),
    ("post", "/api/upload", {"files": {"file": ("c.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")}}),
])
def test_persistent_data_is_closed_to_guests(guest, method, path, kwargs):
    assert getattr(guest, method)(path, **kwargs).status_code == 401


def test_health_stays_public(guest):
    assert guest.get("/api/health").status_code == 200


def test_a_guest_cannot_enumerate_existing_records(client, other_client, guest, fake_graph):
    fake_graph(LOG_RESULT)
    log_complaint(client)
    assert guest.get("/api/complaints").status_code == 401
    assert guest.get("/api/complaints/1").status_code == 401


# --- cross-workspace isolation ----------------------------------------------------------------

def test_one_workspace_cannot_read_anothers_record(client, other_client, fake_graph):
    fake_graph(LOG_RESULT)
    mine = log_complaint(client)
    assert client.get(f"/api/complaints/{mine}").status_code == 200
    assert other_client.get(f"/api/complaints/{mine}").status_code == 404


def test_one_workspace_cannot_edit_anothers_record(client, other_client, fake_graph):
    fake_graph(LOG_RESULT)
    mine = log_complaint(client)
    edit = other_client.post("/api/chat", json={"message": "change batch to X", "complaint_id": mine})
    assert edit.status_code == 404
    assert client.get(f"/api/complaints/{mine}").json()["product"]["batch_number"] == "PCM24031"


def test_listing_shows_only_your_own_records(client, other_client, fake_graph):
    fake_graph(LOG_RESULT)
    mine = log_complaint(client)
    theirs = log_complaint(other_client)
    assert [c["id"] for c in client.get("/api/complaints").json()] == [mine]
    assert [c["id"] for c in other_client.get("/api/complaints").json()] == [theirs]


def test_owner_id_is_never_taken_from_the_request(client, other_client, fake_graph):
    """A client-supplied owner must not be able to plant a record in another workspace."""
    fake_graph(LOG_RESULT)
    theirs = other_client.post("/api/auth/me").status_code  # noqa: F841 - ensure the session exists
    created = client.post("/api/chat", json={"message": "broken tablets", "owner_id": 9999})
    assert created.status_code == 200
    assert [c["id"] for c in client.get("/api/complaints").json()] == [created.json()["complaint_id"]]
    assert other_client.get("/api/complaints").json() == []


def test_records_that_predate_ownership_belong_to_nobody(client, fake_graph):
    from app.db import SessionLocal
    from app.models import ComplaintRecord

    fake_graph(LOG_RESULT)
    orphan_id = log_complaint(client)
    db = SessionLocal()
    db.get(ComplaintRecord, orphan_id).owner_id = None
    db.commit()
    db.close()

    assert client.get(f"/api/complaints/{orphan_id}").status_code == 404
    assert client.get("/api/complaints").json() == []


# --- sessions, CSRF, accounts -------------------------------------------------------------------

def test_session_cookie_is_httponly_and_signed(guest):
    from app.auth import read_session

    response = guest.post("/api/auth/anonymous")
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    assert '"uid"' not in cookie  # the payload is signed, not plain text
    assert read_session(guest.cookies["aivoa_session"])["uid"] == response.json()["id"]


def test_a_forged_session_cookie_is_rejected(guest):
    guest.cookies.set("aivoa_session", "eyJ1aWQiOiAxfQ.fake.signature")
    assert guest.get("/api/complaints").status_code == 401


def test_state_changing_requests_need_the_csrf_token(client):
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/chat", json={"message": "broken tablets"}).status_code == 403
    client.headers["X-CSRF-Token"] = "wrong-token"
    assert client.post("/api/chat", json={"message": "broken tablets"}).status_code == 403


def test_reads_do_not_need_the_csrf_token(client):
    client.headers.pop("X-CSRF-Token")
    assert client.get("/api/complaints").status_code == 200


def test_logout_ends_the_session(client, fake_graph):
    fake_graph(LOG_RESULT)
    log_complaint(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/complaints").status_code == 401


def test_register_then_login_reaches_the_same_workspace(guest, fake_graph, credentials):
    fake_graph(LOG_RESULT)
    registered = guest.post("/api/auth/register", json=credentials).json()
    guest.headers["X-CSRF-Token"] = registered["csrf_token"]
    assert registered["anonymous"] is False
    mine = log_complaint(guest)
    guest.post("/api/auth/logout")

    with TestClient(app) as returning:
        identity = returning.post("/api/auth/login", json=credentials).json()
        assert identity["id"] == registered["id"]
        assert [c["id"] for c in returning.get("/api/complaints").json()] == [mine]


def test_duplicate_registration_and_bad_passwords_are_refused(guest, credentials):
    guest.post("/api/auth/register", json=credentials)
    with TestClient(app) as other:
        assert other.post("/api/auth/register", json=credentials).status_code == 409
        assert other.post("/api/auth/login", json={**credentials, "password": "wrong password"}).status_code == 401
        assert other.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}).status_code == 401
        assert other.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 422
        assert other.post("/api/auth/register", json={"email": "not-an-email", "password": "long enough pw"}).status_code == 422


def test_passwords_are_hashed_not_stored(guest, credentials):
    from app.crud import user_by_email
    from app.db import SessionLocal

    guest.post("/api/auth/register", json=credentials)
    db = SessionLocal()
    stored = user_by_email(db, credentials["email"]).password_hash
    db.close()
    assert credentials["password"] not in stored and stored.startswith("$2b$")


def test_ai_endpoints_are_rate_limited(client, fake_graph, monkeypatch):
    from app.auth import ai_limiter

    fake_graph(LOG_RESULT)
    monkeypatch.setattr(ai_limiter, "limit", 3)
    codes = [client.post("/api/chat", json={"message": "broken tablets"}).status_code for _ in range(5)]
    assert codes.count(200) == 3 and codes[-1] == 429


# --- production configuration must fail closed --------------------------------------------------

@pytest.mark.parametrize("overrides", [
    {},
    {"session_secret": "set-but-insecure-cookies"},
    {"secure_cookies": True},
])
def test_production_refuses_to_start_without_hardening(overrides):
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(environment="production", **overrides)


def test_production_starts_when_hardened():
    from app.config import Settings

    settings = Settings(environment="production", session_secret="a-real-secret", secure_cookies=True)
    assert settings.environment == "production"


def test_development_does_not_require_a_secret():
    from app.config import Settings

    assert Settings().session_secret == ""


# --- claiming an anonymous workspace --------------------------------------------------------------

def test_registering_keeps_the_anonymous_workspace_and_its_records(client, fake_graph, credentials):
    fake_graph(LOG_RESULT)
    before = client.get("/api/auth/me").json()
    mine = log_complaint(client)

    registered = client.post("/api/auth/register", json=credentials).json()
    assert registered["id"] == before["id"] and registered["anonymous"] is False
    client.headers["X-CSRF-Token"] = registered["csrf_token"]
    assert [c["id"] for c in client.get("/api/complaints").json()] == [mine]

    client.post("/api/auth/logout")
    with TestClient(app) as returning:
        returning.post("/api/auth/login", json=credentials)
        assert [c["id"] for c in returning.get("/api/complaints").json()] == [mine]


def test_registering_from_an_account_session_starts_a_separate_workspace(client, fake_graph, credentials):
    fake_graph(LOG_RESULT)
    first = client.post("/api/auth/register", json=credentials).json()
    client.headers["X-CSRF-Token"] = first["csrf_token"]
    log_complaint(client)

    second = client.post("/api/auth/register", json={"email": "other@example.com", "password": "another good pw"}).json()
    client.headers["X-CSRF-Token"] = second["csrf_token"]
    assert second["id"] != first["id"]
    assert client.get("/api/complaints").json() == []


def test_registering_needs_the_csrf_token_when_a_session_exists(client, credentials):
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/register", json=credentials).status_code == 403
