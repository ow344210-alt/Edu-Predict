"""Command line entry point behaviour."""

from __future__ import annotations

import json

from edupredict.__main__ import main


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert "EduPredict" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_check_command_runs(capsys):
    assert main(["check"]) == 0
    out = capsys.readouterr().out
    assert "overall:" in out
    assert "hdfs" in out and "impala" in out


def test_check_command_json(capsys):
    assert main(["check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["app"] == "EduPredict"
    assert isinstance(payload["components"], list)


def test_bad_config_exits_with_failure(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("[app]\nport = 'not-a-number'\n", encoding="utf-8")
    assert main(["--config", str(bad), "check"]) == 1
    assert "configuration error" in capsys.readouterr().err


def test_log_level_override_is_applied(capsys):
    assert main(["--log-level", "ERROR", "check"]) == 0
    assert "overall:" in capsys.readouterr().out
