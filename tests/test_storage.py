"""Infrastructure probes must report real state and never raise."""

from __future__ import annotations

from edupredict.config import load_settings
from edupredict.health import Status
from edupredict.storage import HadoopCliClient, ImpalaClient


def test_hdfs_probe_never_raises_and_reports_reason(project_root):
    settings = load_settings(
        config_path=project_root / "config" / "settings.toml", environ={}
    )
    result = HadoopCliClient(settings).probe()
    assert isinstance(result.available, bool)
    assert result.reason, "an unavailable component must always explain itself"
    assert result.namenode_uri == settings.hdfs.namenode_uri
    assert "available" in result.as_dict()


def test_hdfs_probe_reports_disabled(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text("[hdfs]\nenabled = false\n", encoding="utf-8")
    result = HadoopCliClient(load_settings(config_path=cfg, environ={})).probe()
    assert result.available is False
    assert "disabled" in result.reason.lower()


def test_impala_probe_never_raises(project_root):
    settings = load_settings(
        config_path=project_root / "config" / "settings.toml", environ={}
    )
    result = ImpalaClient(settings).probe()
    assert isinstance(result.available, bool)
    assert result.reason
    assert result.host == settings.impala.host
    assert result.port == settings.impala.port


def test_impala_probe_reports_disabled(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text("[impala]\nenabled = false\n", encoding="utf-8")
    result = ImpalaClient(load_settings(config_path=cfg, environ={})).probe()
    assert result.available is False
    assert "disabled" in result.reason.lower()


def test_missing_java_is_reported_not_hidden(project_root, monkeypatch):
    """A broken JAVA_HOME must be surfaced, never silently treated as healthy."""
    monkeypatch.setenv("JAVA_HOME", r"C:\nonexistent\jdk")
    settings = load_settings(
        config_path=project_root / "config" / "settings.toml", environ={}
    )
    result = HadoopCliClient(settings).probe()
    if result.client_path is not None:  # client found, but Java is missing
        assert result.available is False
        assert "JAVA_HOME" in result.reason


def test_hdfs_probe_result_status_enum_is_shared():
    assert Status.OK.value == "ok"
    assert Status.UNAVAILABLE.value == "unavailable"


def test_summarise_collapses_java_stack_traces():
    stderr = "\n".join(
        ["2026-01-01 WARN Shell: Did not find winutils.exe",
         "java.io.FileNotFoundException: Could not locate Hadoop executable",
         "see https://cwiki.apache.org/confluence/display/HADOOP2/WindowsProblems",
         "\tat org.apache.hadoop.util.Shell.getQualifiedBinInner(Shell.java:673)",
         "\tat org.apache.hadoop.util.Shell.getQualifiedBin(Shell.java:646)"]
    )
    summary = HadoopCliClient._summarise(stderr)
    assert "winutils.exe" in summary
    assert summary.count("|") == 2
    assert "+2 more lines" in summary
    assert "at org.apache" not in summary


def test_summarise_handles_empty_output():
    assert HadoopCliClient._summarise("   \n  ") == "HDFS client failed with no diagnostic output"


def test_missing_winutils_is_reported_clearly(project_root, monkeypatch):
    """On Windows a missing winutils.exe must be named explicitly, not hidden."""
    import os

    if os.name != "nt":
        return
    monkeypatch.setenv("JAVA_HOME", str(project_root))  # has no bin/java.exe
    monkeypatch.setenv("HADOOP_HOME", str(project_root))
    settings = load_settings(
        config_path=project_root / "config" / "settings.toml", environ={}
    )
    client = HadoopCliClient(settings)
    monkeypatch.setattr(client, "_executable", lambda: r"C:\hadoop\bin\hdfs.cmd")
    monkeypatch.setattr(client, "_java_ok", lambda: True)
    monkeypatch.setattr(client, "_hadoop_root", lambda: r"C:\hadoop")
    result = client.probe()
    assert result.available is False
    assert "winutils" in result.reason
