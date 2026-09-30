"""HTTP layer for EduPredict.

Phase 1 exposed a landing page and a machine-readable health endpoint. Phase 2
adds the authentication surface (login, logout, dashboard, role-gated admin
area) in the companion ``auth_routes`` module.

Routes for ingestion, analytics, ML, visualization, alerts and support remain
deliberately deferred to their own phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template

from ..health import build_health_report
from ..logging_setup import get_logger
from .auth_guards import current_user

__all__ = ["web_bp", "get_settings"]

logger = get_logger(__name__)

web_bp = Blueprint("web", __name__)


def get_settings():
    """Return the :class:`~edupredict.config.Settings` stored on the app."""
    settings: Any = current_app.config["EDUPREDICT_SETTINGS"]
    return settings


@dataclass(frozen=True)
class _NavItem:
    label: str
    description: str


#: Documented modules. Each one is listed so the foundation makes the target
#: architecture visible; none of them is implemented yet.
_PLANNED_MODULES: tuple[_NavItem, ...] = (
    _NavItem(
        "Authentication / Authorization",
        "Implemented - 4 roles, RBAC guards, /auth/login",
    ),
    _NavItem("Data Ingestion", "Reserved - later phase"),
    _NavItem("HDFS Storage", "Probe implemented, data pipeline reserved"),
    _NavItem("Batch Processing", "Reserved - later phase"),
    _NavItem("Real-Time Processing", "Reserved - later phase"),
    _NavItem("Analytics", "Reserved - later phase"),
    _NavItem("Machine Learning", "Reserved - later phase"),
    _NavItem("Visualization", "Reserved - later phase"),
    _NavItem("Notifications / Alerts", "Reserved - later phase"),
    _NavItem("Feedback / Support", "Reserved - later phase"),
)


@web_bp.get("/")
def index() -> str:
    settings = get_settings()
    report = build_health_report(settings)
    return render_template(
        "index.html",
        app_name=settings.app.name,
        version=report.version,
        environment=report.environment,
        status=report.status.value,
        components=report.components,
        modules=_PLANNED_MODULES,
        current_user=current_user(),
    )


@web_bp.get("/health")
def health():
    """Machine-readable health report.

    Returns HTTP 200 when every component is healthy, 503 otherwise, so the
    endpoint can be used directly by an external monitor.
    """
    report = build_health_report(get_settings())
    payload = report.as_dict()
    return jsonify(payload), (200 if report.is_healthy else 503)
