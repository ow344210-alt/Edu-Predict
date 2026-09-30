"""Web surface: landing page, health endpoint, error handling."""

from __future__ import annotations

import pytest

from edupredict.health import Status
from edupredict.storage import HadoopCliClient, ImpalaClient


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "EduPredict" in body
    assert "System health" in body


def test_health_endpoint_returns_json(client):
    response = client.get("/health")
    # 200 when every component is up, 503 when Hadoop/Impala are missing.
    assert response.status_code in (200, 503)
    payload = response.get_json()
    assert payload["app"] == "EduPredict"
    assert payload["status"] in {"ok", "warn", "unavailable", "error"}
    assert any(c["name"] == "hdfs" for c in payload["components"])


def test_health_status_code_matches_payload(client):
    response = client.get("/health")
    payload = response.get_json()
    expected = 200 if payload["status"] == "ok" else 503
    assert response.status_code == expected


def test_unknown_route_returns_json_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not Found"


def test_unhandled_error_is_not_leaked(monkeypatch, app):
    from edupredict.web import routes

    def boom() -> str:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(routes, "build_health_report", boom)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = app.test_client().get("/health")
    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert "secret internal detail" not in body
    assert response.get_json()["error"] == "InternalServerError"


def test_app_registers_expected_blueprints(app):
    assert "web" in app.blueprints
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/" in rules and "/health" in rules


def test_clients_are_wired_into_app_config(app):
    assert isinstance(app.config["EDUPREDICT_HDFS_CLIENT"], HadoopCliClient)
    assert isinstance(app.config["EDUPREDICT_IMPALA_CLIENT"], ImpalaClient)
    assert app.config["EDUPREDICT_SETTINGS"] is not None


@pytest.mark.parametrize("path", ["/", "/health"])
def test_pages_do_not_error(client, path):
    assert client.get(path).status_code in (200, 503)
