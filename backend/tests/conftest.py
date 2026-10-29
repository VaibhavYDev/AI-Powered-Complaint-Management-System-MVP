import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["GROQ_API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient

from app import main as app_main

# The suite never reaches the network: the startup model probe is disabled so CI needs no
# credentials and no outbound access.
app_main.resolve_model = lambda: None
app = app_main.app
from app.schemas import ComplaintData, RiskAssessment

RISK = RiskAssessment(
    severity_class="III",
    severity_reason="Cosmetic defect.",
    immediate_actions=["Retain sample"],
    recommended_follow_up=["Review batch record"],
    confidence=0.8,
)
DRAFT = ComplaintData.model_validate(
    {
        "complainant": {"name": "Rahul Sharma"},
        "product": {"product_name": "Paracetamol 500 mg Tablets", "batch_number": "PCM24031"},
        "complaint": {"defect_category": "physical_defect", "sample_available": True, "complaint_received_date": "2026-09-16"},
    }
)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.auth import ai_limiter, session_limiter

    ai_limiter._hits.clear()
    session_limiter._hits.clear()


def sign_in(c: TestClient) -> dict:
    """Give the client an anonymous workspace and the CSRF token that goes with it."""
    identity = c.post("/api/auth/anonymous").json()
    c.headers["X-CSRF-Token"] = identity["csrf_token"]
    return identity


@pytest.fixture
def guest():
    """A client with no session at all."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client():
    with TestClient(app) as c:
        sign_in(c)
        yield c


@pytest.fixture
def other_client():
    """A second, unrelated workspace."""
    with TestClient(app) as c:
        sign_in(c)
        yield c


@pytest.fixture
def fake_graph(monkeypatch):
    """Replace the LangGraph run with a scripted result (or exception) so the HTTP
    layer can be tested without Groq."""

    def install(result):
        def run(text, source, existing=None):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr("app.api.complaints.run_copilot", run)

    return install
