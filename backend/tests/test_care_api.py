"""Care Documentation Reliability Lab API. Fictional residents throughout."""

import pytest

from app.care.schemas import CareNote

NOTE = """[page 1]
Shift notes, 14 March 2026.
Frau Anna Keller: redness at the left heel, about 2 x 3 cm, not broken. Cream applied.
Herr Josef Brandt: walked to the dining room with a frame. No pain reported.
"""

PLAN = [{"resident": "Anna Keller", "category": "mobility", "instruction": "Assist with transfers"}]


@pytest.fixture
def fake_extract(monkeypatch):
    """Scripted model output so the API can be tested without a provider."""

    def install(note: dict):
        monkeypatch.setattr("app.api.care.extract.__wrapped__", None, raising=False)
        from app.care import checks

        def fake(source, care_plan=None):
            from app.care.schemas import CareExtraction

            parsed = CareNote.model_validate(note)
            evidence, alerts = checks.analyse(parsed, source, care_plan)
            return CareExtraction(note=parsed, evidence=evidence, alerts=alerts)

        monkeypatch.setattr("app.api.care.extract", fake)

    return install


GOOD = {
    "residents": ["Frau Anna Keller", "Herr Josef Brandt"],
    "observations": [
        {
            "resident": "Frau Anna Keller",
            "category": "wound",
            "finding": "redness at the left heel",
            "body_site": "left heel",
            "severity": "mild",
            "measurement": "2 x 3 cm",
        }
    ],
    "open_questions": [],
}

INVENTED = {
    "residents": ["Frau Anna Keller"],
    "observations": [
        {"resident": "Frau Anna Keller", "category": "wound", "finding": "open pressure ulcer grade 3"}
    ],
    "open_questions": [],
}


def analyse(client, note=NOTE, plan=PLAN):
    return client.post("/api/care", json={"note": note, "care_plan": plan})


def test_a_note_becomes_structured_observations_with_evidence(client, fake_extract):
    fake_extract(GOOD)
    body = analyse(client).json()

    assert body["status"] == "needs_review" and body["revision"] == 1
    assert body["note"]["observations"][0]["measurement"] == "2 x 3 cm"
    assert body["evidence"]["observations.0.finding"]["status"] in {"verbatim", "normalized"}
    assert body["source_text"] == NOTE


def test_a_new_wound_missing_from_the_care_plan_is_raised_for_review(client, fake_extract):
    fake_extract(GOOD)
    body = analyse(client).json()

    gaps = [a for a in body["alerts"] if a["kind"] == "not_in_care_plan"]
    assert len(gaps) == 1
    assert "wound" in gaps[0]["message"] and "Documentation may be missing" in gaps[0]["message"]


def test_an_invented_finding_blocks_approval_until_acknowledged(client, fake_extract):
    fake_extract(INVENTED)
    body = analyse(client).json()
    record_id = body["id"]
    assert any(a["kind"] == "unsupported_finding" for a in body["alerts"])

    refused = client.post(f"/api/care/{record_id}/approve", json={"revision": 1})
    assert refused.status_code == 422 and "acknowledged" in refused.json()["detail"]
    assert client.get(f"/api/care/{record_id}").json()["status"] == "needs_review"

    approved = client.post(
        f"/api/care/{record_id}/approve",
        json={"revision": 1, "acknowledged": ["unsupported_finding:0"]},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert approved.json()["acknowledged"] == ["unsupported_finding:0"]


def test_a_record_without_high_priority_alerts_approves_directly(client, fake_extract):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]
    assert client.post(f"/api/care/{record_id}/approve", json={"revision": 1}).status_code == 200


def test_export_requires_approval(client, fake_extract):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]

    assert client.get(f"/api/care/{record_id}/export").status_code == 409
    client.post(f"/api/care/{record_id}/approve", json={"revision": 1})
    exported = client.get(f"/api/care/{record_id}/export")
    assert exported.status_code == 200 and exported.json()["status"] == "approved"


def test_history_records_extraction_and_the_decision(client, fake_extract):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]
    client.post(f"/api/care/{record_id}/reject", json={"revision": 1, "note": "Wrong resident."})

    history = client.get(f"/api/care/{record_id}/history").json()
    assert [e["action"] for e in history] == ["extracted", "rejected"]
    assert history[-1]["note"] == "Wrong resident."


def test_two_reviewers_cannot_both_decide(client, fake_extract):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]

    first = client.post(f"/api/care/{record_id}/approve", json={"revision": 1})
    second = client.post(f"/api/care/{record_id}/reject", json={"revision": 1})
    assert first.status_code == 200 and second.status_code == 409
    assert client.get(f"/api/care/{record_id}").json()["status"] == "approved"


def test_a_stale_revision_is_refused(client, fake_extract):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]
    assert client.post(f"/api/care/{record_id}/approve", json={"revision": 7}).status_code == 409


@pytest.mark.parametrize("method, suffix, body", [
    ("get", "", None),
    ("post", "/approve", {"revision": 1}),
    ("post", "/reject", {"revision": 1}),
    ("get", "/history", None),
    ("get", "/export", None),
])
def test_another_workspace_cannot_reach_a_care_record(client, other_client, fake_extract, method, suffix, body):
    fake_extract(GOOD)
    record_id = analyse(client).json()["id"]

    call = getattr(other_client, method)
    response = call(f"/api/care/{record_id}{suffix}", **({"json": body} if body else {}))
    assert response.status_code == 404


def test_care_records_are_closed_to_guests(guest):
    assert guest.get("/api/care").status_code == 401
    assert guest.post("/api/care", json={"note": NOTE}).status_code == 401


def test_listing_shows_only_your_own_records(client, other_client, fake_extract):
    fake_extract(GOOD)
    mine = analyse(client).json()["id"]
    assert [r["id"] for r in client.get("/api/care").json()] == [mine]
    assert other_client.get("/api/care").json() == []


def test_an_oversized_note_is_refused(client):
    assert client.post("/api/care", json={"note": "x" * 20_001}).status_code == 422
