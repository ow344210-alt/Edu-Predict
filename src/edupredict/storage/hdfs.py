"""HDFS access layer for EduPredict.

The document requires HDFS as the system of record for large educational
datasets. Hadoop is integrated through its native ``hdfs dfs`` command line
client, which keeps the dependency footprint at zero and works with the
Hadoop distribution that is already installed on the host.

Only a *probe* and a *contract* are implemented in Phase 1. No data is written
and no dataset is created.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..errors import HdfsUnavailableError

__all__ = ["HdfsProbeResult", "HdfsClient", "HadoopCliClient"]


@dataclass(frozen=True)
class HdfsProbeResult:
    """Outcome of an HDFS availability check."""

    available: bool
    reason: str
    namenode_uri: str
    client_path: str | None = None
    java_home: str | None = None
    base_path: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
            "namenode_uri": self.namenode_uri,
            "client_path": self.client_path,
            "java_home": self.java_home,
            "base_path": self.base_path,
        }


@runtime_checkable
class HdfsClient(Protocol):
    """Contract every HDFS backend must satisfy (implemented in later phases)."""

    def probe(self) -> HdfsProbeResult: ...


class HadoopCliClient:
    """Thin, dependency-free wrapper around the ``hdfs dfs`` CLI."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._cfg = settings.hdfs
        # JAVA_HOME is a hard requirement of the Hadoop shell scripts; the
        # process environment is the single source of truth for the JDK path.
        self._java_home = os.environ.get("JAVA_HOME", "")

    # -- helpers ---------------------------------------------------------- #
    def _executable(self) -> str | None:
        """Resolve the HDFS client, preferring the configured Hadoop home."""
        if self._cfg.hadoop_home:
            candidate = self._resolve_from_hadoop_home(self._cfg.hadoop_home)
            if candidate:
                return candidate
        return shutil.which(self._cfg.cli)

    @staticmethod
    def _resolve_from_hadoop_home(hadoop_home: str) -> str | None:
        suffix = "hdfs.cmd" if os.name == "nt" else "hdfs"
        candidate = os.path.join(hadoop_home, "bin", suffix)
        return candidate if os.path.isfile(candidate) else None

    def _java_ok(self) -> bool:
        """Hadoop's shell scripts refuse to run without a usable JAVA_HOME."""
        java_home = self._java_home
        if not java_home:
            return False
        suffix = "java.exe" if os.name == "nt" else "java"
        return os.path.isfile(os.path.join(java_home, "bin", suffix))

    def _hadoop_root(self) -> str | None:
        """Best-effort HADOOP_HOME, derived from the client location if unset."""
        if self._cfg.hadoop_home:
            return self._cfg.hadoop_home
        env_home = os.environ.get("HADOOP_HOME", "")
        if env_home:
            return env_home
        client = self._executable()
        if client:
            # .../<hadoop>/bin/hdfs.cmd  ->  .../<hadoop>
            return os.path.dirname(os.path.dirname(os.path.abspath(client)))
        return None

    def _winutils(self) -> str | None:
        """Locate winutils.exe, which Hadoop on Windows requires at runtime."""
        if os.name != "nt":
            return None
        root = self._hadoop_root()
        if not root:
            return None
        for candidate in (
            os.path.join(root, "bin", "winutils.exe"),
            os.path.join(root, "winutils.exe"),
        ):
            if os.path.isfile(candidate):
                return candidate
        return None

    def _run(self, args: list[str], timeout: int) -> tuple[int, str, str]:
        executable = self._executable()
        if executable is None:
            raise HdfsUnavailableError(
                f"HDFS client {self._cfg.cli!r} not found on PATH and not found in "
                f"HADOOP_HOME={self._cfg.hadoop_home or '<unset>'}"
            )
        env = os.environ.copy()
        if self._cfg.hadoop_home:
            env["HADOOP_HOME"] = self._cfg.hadoop_home
        if self._java_home:
            env["JAVA_HOME"] = self._java_home
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [executable, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HdfsUnavailableError(
                f"HDFS command timed out after {timeout}s: {' '.join(args)}"
            ) from exc
        except OSError as exc:
            raise HdfsUnavailableError(f"Cannot execute HDFS client: {exc}") from exc
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    # -- public API ------------------------------------------------------- #
    @staticmethod
    def _summarise(stderr: str, max_lines: int = 3) -> str:
        """Reduce a Java stack trace to its first meaningful lines.

        Hadoop failures on Windows routinely print dozens of stack frames. The
        health report has to stay readable, so keep the head of the message and
        note how much was elided.
        """
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        if not lines:
            return "HDFS client failed with no diagnostic output"
        head = " | ".join(lines[:max_lines])
        if len(lines) > max_lines:
            head += f" (+{len(lines) - max_lines} more lines)"
        return head

    def probe(self) -> HdfsProbeResult:
        """Check whether HDFS can actually be used. Never raises."""
        if not self._cfg.enabled:
            return HdfsProbeResult(
                False, "HDFS is disabled in configuration", self._cfg.namenode_uri
            )

        client = self._executable()
        if client is None:
            return HdfsProbeResult(
                False,
                f"Hadoop HDFS client ({self._cfg.cli}) not found. Install Hadoop and set "
                "HADOOP_HOME or add it to PATH.",
                self._cfg.namenode_uri,
            )
        if not self._java_ok():
            return HdfsProbeResult(
                False,
                "JAVA_HOME is missing or invalid; the Hadoop client cannot start. "
                f"(JAVA_HOME={self._java_home or '<unset>'})",
                self._cfg.namenode_uri,
                client_path=client,
                java_home=self._java_home or None,
            )
        if os.name == "nt" and self._winutils() is None:
            root = self._hadoop_root() or "<HADOOP_HOME>"
            return HdfsProbeResult(
                False,
                "Hadoop on Windows requires winutils.exe, which was not found under "
                f"{root}. Copy it from the official Hadoop Windows build into "
                f"{os.path.join(root, 'bin')} before HDFS can be used.",
                self._cfg.namenode_uri,
                client_path=client,
                java_home=self._java_home or None,
            )

        try:
            code, out, err = self._run(["dfs", "-ls", self._cfg.base_path.rstrip("/")],
                                       self._cfg.probe_timeout_seconds)
        except HdfsUnavailableError as exc:
            return HdfsProbeResult(False, str(exc), self._cfg.namenode_uri,
                                   client_path=client, java_home=self._java_home or None)

        if code != 0:
            reason = err or out or f"`hdfs dfs -ls` exited with code {code}"
            # A missing directory is not an outage; the NameNode answered.
            lowered = reason.lower()
            if "does not exist" in lowered or "no such file" in lowered:
                reason = f"NameNode reachable; base path {self._cfg.base_path} not created yet"
            else:
                reason = self._summarise(reason)
            return HdfsProbeResult(False, reason, self._cfg.namenode_uri,
                                   client_path=client, java_home=self._java_home or None,
                                   base_path=self._cfg.base_path)

        return HdfsProbeResult(
            True,
            f"NameNode reachable; {self._cfg.base_path} present",
            self._cfg.namenode_uri,
            client_path=client,
            java_home=self._java_home or None,
            base_path=self._cfg.base_path,
        )
