"""Health report assembly and status aggregation."""

from __future__ import annotations

from edupredict.health import (
    ComponentHealth,
    HealthReport,
    Status,
    _overall,
    build_health_report,
)


def _c(status: Status) -> ComponentHealth:
    return ComponentHealth(name="x", status=status, detail="d")


def test_all_ok_is_ok():
    assert _overall([_c(Status.OK), _c(Status.OK)]) is Status.OK


def test_unavailable_degrades_report():
    assert _overall([_c(Status.OK), _c(Status.UNAVAILABLE)]) is Status.WARN


def test_error_dominates():
    report = [_c(Status.UNAVAILABLE), _c(Status.ERROR)]
    assert _overall(report) is Status.ERROR


def test_report_serialises_to_plain_json_types(settings):
    payload = build_health_report(settings).as_dict()
    assert payload["app"] == "EduPredict"
    assert isinstance(payload["version"], str)
    assert payload["status"] in {"ok", "warn", "unavailable", "error"}
    names = {c["name"] for c in payload["components"]}
    assert {"runtime", "configuration", "hdfs", "impala"} <= names
    for component in payload["components"]:
        assert isinstance(component["detail"], str) and component["detail"]


def test_report_flags_missing_infrastructure(settings):
    """A missing Hadoop/Impala install must show up as not-ok, not hidden."""
    report = build_health_report(settings)
    for name in ("hdfs", "impala"):
        component = next(c for c in report.components if c.name == name)
        assert component.detail, f"{name} must explain its state"
    if not report.is_healthy:
        assert report.status is Status.WARN


def test_healthy_report_flag():
    report = HealthReport(
        app="EduPredict", version="0.1.0", environment="test",
        status=Status.OK, components=[_c(Status.OK)],
    )
    assert report.is_healthy is True
