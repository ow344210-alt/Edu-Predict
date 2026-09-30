"""Startup and health checks.

The document's non-functional requirements ask for monitoring of system and
data-processing health. Phase 1 implements a component health report that is
exposed by the web application and by the ``edupredict check`` command.

External infrastructure is probed for real. A component that is missing is
reported as ``unavailable`` with the reason - it is never reported as healthy.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from . import APP_NAME, __version__
from .config import Settings
from .storage import HadoopCliClient, ImpalaClient

__all__ = ["Status", "ComponentHealth", "HealthReport", "build_health_report"]


class Status(str, Enum):
    OK = "ok"
    WARN = "warn"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


#: Statuses that must not make the whole report "ok".
_DEGRADED = {Status.WARN, Status.UNAVAILABLE, Status.ERROR}


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: Status
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthReport:
    app: str
    version: str
    environment: str
    status: Status
    components: list[ComponentHealth]

    @property
    def is_healthy(self) -> bool:
        return self.status is Status.OK

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["components"] = [
            {**asdict(c), "status": c.status.value} for c in self.components
        ]
        return payload


def _config_component(settings: Settings) -> ComponentHealth:
    detail = (
        f"loaded from {settings.config_file.name}"
        if settings.config_file
        else "built-in defaults (no settings.toml found)"
    )
    return ComponentHealth(
        name="configuration",
        status=Status.OK,
        detail=detail,
        data={"config_file": str(settings.config_file) if settings.config_file else None},
    )


def _runtime_component() -> ComponentHealth:
    return ComponentHealth(
        name="runtime",
        status=Status.OK,
        detail=f"{platform.python_implementation()} {platform.python_version()} on "
        f"{platform.system()} {platform.release()}",
        data={"executable": sys.executable},
    )


def _hdfs_component(settings: Settings) -> ComponentHealth:
    result = HadoopCliClient(settings).probe()
    status = Status.OK if result.available else Status.UNAVAILABLE
    return ComponentHealth(
        name="hdfs", status=status, detail=result.reason, data=result.as_dict()
    )


def _impala_component(settings: Settings) -> ComponentHealth:
    result = ImpalaClient(settings).probe()
    status = Status.OK if result.available else Status.UNAVAILABLE
    return ComponentHealth(
        name="impala", status=status, detail=result.reason, data=result.as_dict()
    )


def _overall(components: list[ComponentHealth]) -> Status:
    if any(c.status is Status.ERROR for c in components):
        return Status.ERROR
    if any(c.status in _DEGRADED for c in components):
        return Status.WARN
    return Status.OK


def build_health_report(settings: Settings) -> HealthReport:
    """Run every component check and assemble a report."""
    components = [
        _runtime_component(),
        _config_component(settings),
        _hdfs_component(settings),
        _impala_component(settings),
    ]
    return HealthReport(
        app=APP_NAME,
        version=__version__,
        environment=settings.app.environment,
        status=_overall(components),
        components=components,
    )
