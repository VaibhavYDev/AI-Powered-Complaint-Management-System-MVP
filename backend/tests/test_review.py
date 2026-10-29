"""A generated record is a suggestion until a reviewer approves it."""

import pytest

from app.schemas import Intent
from tests.conftest import DRAFT, RISK

SOURCE = "Rahul Sharma reported Paracetamol 500 mg Tablets from batch PCM24031 were chipped."
LOG_RESULT = {"intent": Intent.LOG, "draft": DRAFT, "risk": RISK, "reply": "Logged."}
EDIT_RESULT = {
    "intent": Intent.EDIT,
    "patch": {"product": {"batch_number": "PCM24099"}},
    "draft": DRAFT,
    "reply": "Updated batch number.",
}


@pytest.fixture
def logged(client, fake_graph):
    fake_graph(LOG_RESULT)
    body = client.post("/api/chat", json={"message": SOURCE}).json()
    return body["complaint_id"], body


def test_a_new_record_needs_review_and_carries_evidence(logged):
    _, body = logged
    complaint = body["complaint"]
    assert complaint["status"] == "needs_review" and complaint["revision"] == 1
    assert complaint["reviewed_at"] is None
    assert complaint["evidence"]["product.batch_number"]["status"] == "verbatim"
    assert body["review"]["quoted"] >= 1 and "product.generic_name" in body["review"]["missing"]


def test_values_absent_from_the_source_are_flagged_for_the_reviewer(client, fake_graph):
    fake_graph(LOG_RESULT)
    body = client.post("/api/chat", json={"message": "A complaint arrived today."}).json()
    # Nothing in that sentence supports the extracted names and identifiers.
    assert "product.batch_number" in body["review"]["unsupported"]
    assert body["complaint"]["evidence"]["product.batch_number"]["status"] == "unsupported"


def test_export_is_refused_until_the_record_is_approved(client, logged):
    complaint_id, _ = logged
    assert client.get(f"/api/complaints/{complaint_id}/export").status_code == 409

    client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1})
    exported = client.get(f"/api/complaints/{complaint_id}/export")
    assert exported.status_code == 200 and exported.json()["status"] == "approved"


def test_approval_records_who_and_when(client, logged):
    complaint_id, _ = logged
    approved = client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1}).json()
    assert approved["status"] == "approved" and approved["reviewed_at"] is not None

    assert client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1}).status_code == 409


def test_a_stale_revision_cannot_approve(client, logged, fake_graph):
    complaint_id, _ = logged
    fake_graph(EDIT_RESULT)
    client.post("/api/chat", json={"message": "change the batch number", "complaint_id": complaint_id})

    stale = client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1})
    assert stale.status_code == 409 and "changed since" in stale.json()["detail"]
    assert client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 2}).status_code == 200


def test_editing_an_approved_record_sends_it_back_for_review(client, logged, fake_graph):
    complaint_id, _ = logged
    client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1})

    fake_graph(EDIT_RESULT)
    edited = client.post(
        "/api/chat", json={"message": "change the batch number to PCM24099", "complaint_id": complaint_id}
    ).json()["complaint"]

    assert edited["status"] == "needs_review" and edited["revision"] == 2
    assert edited["reviewed_at"] is None
    assert edited["evidence"]["product.batch_number"]["status"] == "user_supplied"
    assert client.get(f"/api/complaints/{complaint_id}/export").status_code == 409


def test_rejection_keeps_the_record_and_its_reason(client, logged):
    complaint_id, _ = logged
    rejected = client.post(
        f"/api/complaints/{complaint_id}/reject", json={"revision": 1, "note": "Batch number not in the source."}
    ).json()
    assert rejected["status"] == "rejected"

    history = client.get(f"/api/complaints/{complaint_id}/history").json()
    assert history[-1]["action"] == "rejected"
    assert history[-1]["note"] == "Batch number not in the source."


def test_history_records_every_action_with_the_fields_it_touched(client, logged, fake_graph):
    complaint_id, _ = logged
    fake_graph(EDIT_RESULT)
    client.post("/api/chat", json={"message": "change the batch number", "complaint_id": complaint_id})
    client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 2})

    history = client.get(f"/api/complaints/{complaint_id}/history").json()
    assert [e["action"] for e in history] == ["extracted", "edited", "approved"]
    assert history[1]["changed_fields"] == ["product.batch_number"]
    assert [e["revision"] for e in history] == [1, 2, 2]
    assert all(e["actor_id"] is not None for e in history)


@pytest.mark.parametrize("method, suffix, body", [
    ("post", "/approve", {"revision": 1}),
    ("post", "/reject", {"revision": 1}),
    ("get", "/history", None),
    ("get", "/export", None),
])
def test_another_workspace_cannot_review_or_export(client, other_client, logged, method, suffix, body):
    complaint_id, _ = logged
    call = getattr(other_client, method)
    response = call(f"/api/complaints/{complaint_id}{suffix}", **({"json": body} if body else {}))
    assert response.status_code == 404


@pytest.mark.parametrize("method, suffix, body", [
    ("post", "/approve", {"revision": 1}),
    ("post", "/reject", {"revision": 1}),
    ("get", "/history", None),
    ("get", "/export", None),
])
def test_review_actions_are_closed_to_guests(guest, logged, method, suffix, body):
    complaint_id, _ = logged
    call = getattr(guest, method)
    response = call(f"/api/complaints/{complaint_id}{suffix}", **({"json": body} if body else {}))
    assert response.status_code == 401


def test_approving_needs_the_csrf_token(client, logged):
    complaint_id, _ = logged
    client.headers.pop("X-CSRF-Token")
    assert client.post(f"/api/complaints/{complaint_id}/approve", json={"revision": 1}).status_code == 403
