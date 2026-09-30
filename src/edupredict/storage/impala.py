"""Impala connectivity layer for EduPredict.

Impala is listed in the document's software requirements and is the natural
SQL engine for querying the data held in HDFS. In Phase 1 only an
*availability probe* is implemented so the health endpoint can report the real
state of the environment instead of pretending the server is reachable.

The final integration method (impala-shell for exploration vs. the Impala
daemon protocol / ODBC for production) is an open decision recorded as
ADR-0004 in ``docs/DECISIONS.md``.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from dataclasses import dataclass

from ..errors import ImpalaUnavailableError

__all__ = ["ImpalaProbeResult", "ImpalaClient"]


@dataclass(frozen=True)
class ImpalaProbeResult:
    """Outcome of an Impala availability check."""

    available: bool
    reason: str
    host: str
    port: int
    database: str
    shell_path: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "shell_path": self.shell_path,
        }


class ImpalaClient:
    """Dependency-free Impala availability check (Phase 1)."""

    def __init__(self, settings) -> None:
        self._cfg = settings.impala

    def _shell(self) -> str | None:
        return shutil.which(self._cfg.cli)

    def _tcp_open(self, timeout: float) -> bool:
        try:
            with socket.create_connection((self._cfg.host, self._cfg.port), timeout=timeout):
                return True
        except OSError:
            return False

    def probe(self) -> ImpalaProbeResult:
        """Check Impala availability. Never raises."""
        if not self._cfg.enabled:
            return ImpalaProbeResult(
                False, "Impala is disabled in configuration",
                self._cfg.host, self._cfg.port, self._cfg.database,
            )

        shell = self._shell()
        timeout = float(self._cfg.probe_timeout_seconds)

        if shell is None:
            return ImpalaProbeResult(
                False,
                f"Impala shell ({self._cfg.cli}) not found on PATH. Install the Impala "
                "server tools before the analytics phase.",
                self._cfg.host, self._cfg.port, self._cfg.database,
            )

        if not self._tcp_open(timeout):
            return ImpalaProbeResult(
                False,
                f"Impala daemon not accepting connections on "
                f"{self._cfg.host}:{self._cfg.port}.",
                self._cfg.host, self._cfg.port, self._cfg.database, shell_path=shell,
            )

        query = f"SHOW DATABASES LIKE '{self._cfg.database}';"
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [shell, "-q", query, "--host=" + self._cfg.host,
                 f"--port={self._cfg.port}", "--user=" + self._cfg.user],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
                shell=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return ImpalaProbeResult(
                False, f"impala-shell could not be executed: {exc}",
                self._cfg.host, self._cfg.port, self._cfg.database, shell_path=shell,
            )

        if proc.returncode != 0:
            reason = (proc.stderr or proc.stdout or "unknown error").strip()
            return ImpalaProbeResult(
                False, f"impala-shell failed: {reason}",
                self._cfg.host, self._cfg.port, self._cfg.database, shell_path=shell,
            )

        return ImpalaProbeResult(
            True, f"Impala reachable; database {self._cfg.database!r} verified",
            self._cfg.host, self._cfg.port, self._cfg.database, shell_path=shell,
        )
