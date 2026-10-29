"""The process must come up and serve the interface even when its dependencies are down.

A startup that blocks on an unreachable database never binds the port, and a platform router
then holds every request open - which is indistinguishable, from outside, from an application
that simply never loads.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import main


@pytest.fixture
def broken_database(monkeypatch):
    def unreachable(*args, **kwargs):
        raise OperationalError("select 1", {}, Exception("connection refused"))

    monkeypatch.setattr(main.engine, "connect", unreachable)
    monkeypatch.setattr(main, "upgrade_to_head", unreachable)
    monkeypatch.setitem(main._schema, "ready", False)
    monkeypatch.setitem(main._schema, "error", None)
    monkeypatch.setitem(main._probe, "state", "")
    return unreachable


def test_schema_failure_is_recorded_not_raised(broken_database):
    assert main.ensure_schema() is False
    assert "OperationalError" in main._schema["error"]


def test_the_app_still_starts_and_serves_when_the_database_is_unreachable(broken_database):
    with TestClient(main.app) as client:  # lifespan runs here and must not raise
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "degraded"
        assert body["database"] == "unavailable" and body["schema"] == "pending"
        assert body["schema_error"] and "OperationalError" in body["schema_error"]


def test_readiness_is_separate_from_liveness(broken_database):
    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200  # the process is alive
        assert client.get("/api/ready").status_code == 503    # but not ready to serve


def test_the_database_probe_is_cached_briefly(monkeypatch):
    calls = {"n": 0}
    real = main.engine.connect

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(main.engine, "connect", counting)
    monkeypatch.setitem(main._probe, "state", "")
    assert main.database_state() == "ok"
    assert main.database_state() == "ok"
    assert calls["n"] == 1  # the second call is served from the cache


def test_a_healthy_app_reports_ready(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ready" and body["schema"] == "ready" and body["schema_error"] is None
    assert client.get("/api/ready").status_code == 200


def test_the_schema_is_retried_once_the_database_comes_back(monkeypatch):
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OperationalError("upgrade", {}, Exception("still waking up"))

    monkeypatch.setattr(main, "upgrade_to_head", flaky)
    monkeypatch.setitem(main._schema, "ready", False)
    monkeypatch.setitem(main._schema, "error", None)

    assert main.ensure_schema() is False
    assert main.ensure_schema() is True  # a later health check picks it up
    assert attempts["n"] == 2

    main.ensure_schema()
    assert attempts["n"] == 2  # and stops trying once it is at head


def test_postgres_urls_get_a_bounded_connect_timeout():
    from app.db import connect_args

    assert connect_args("postgresql+psycopg://u:p@host/db")["connect_timeout"] > 0
    assert connect_args("postgres://u:p@host/db")["connect_timeout"] > 0
    assert connect_args("sqlite:///x.db") == {}
