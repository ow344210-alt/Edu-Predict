"""Configuration loading: defaults, file layer, environment layer, errors."""

from __future__ import annotations

import pytest

from edupredict.config import Settings, load_settings
from edupredict.errors import ConfigurationError

VALID_TOML = """
[app]
name = "EduPredict"
environment = "testing"
port = 5050
debug = true

[hdfs]
enabled = false
base_path = "/user/test"
"""


def test_defaults_without_file(tmp_path):
    empty = tmp_path / "settings.toml"
    empty.write_text("", encoding="utf-8")
    settings = load_settings(config_path=empty, environ={})
    assert isinstance(settings, Settings)
    assert settings.app.name == "EduPredict"
    assert settings.app.port == 5000
    assert settings.hdfs.enabled is True
    assert settings.impala.port == 21050


def test_missing_explicit_file_raises(tmp_path):
    with pytest.raises(ConfigurationError, match="not found"):
        load_settings(config_path=tmp_path / "nope.toml", environ={})


def test_invalid_toml_raises(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[app\nport = 1", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid TOML"):
        load_settings(config_path=bad, environ={})


def test_unknown_option_raises(tmp_path):
    bad = tmp_path / "unknown.toml"
    bad.write_text("[app]\nnot_a_real_option = 1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Unknown option"):
        load_settings(config_path=bad, environ={})


def test_unknown_section_raises(tmp_path):
    """A typo'd section name must not be silently ignored."""
    bad = tmp_path / "unknown.toml"
    bad.write_text("[nonsense]\nx = 1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Unknown section"):
        load_settings(config_path=bad, environ={})


def test_wrong_type_raises(tmp_path):
    bad = tmp_path / "wrongtype.toml"
    bad.write_text("[app]\nport = 'abc'\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Expected an integer"):
        load_settings(config_path=bad, environ={})


def test_file_values_are_applied_and_typed(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text(VALID_TOML, encoding="utf-8")
    settings = load_settings(config_path=cfg, environ={})
    assert settings.app.environment == "testing"
    assert settings.app.port == 5050
    assert settings.app.debug is True
    assert settings.hdfs.enabled is False
    assert settings.hdfs.base_path == "/user/test"
    # untouched keys keep their defaults
    assert settings.app.host == "127.0.0.1"


def test_env_overrides_file(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text(VALID_TOML, encoding="utf-8")
    settings = load_settings(
        config_path=cfg,
        environ={"EDUPREDICT_APP__PORT": "7000", "EDUPREDICT_HDFS__ENABLED": "false"},
    )
    assert settings.app.port == 7000
    assert settings.hdfs.enabled is False


def test_explicit_overrides_beat_environment(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text(VALID_TOML, encoding="utf-8")
    settings = load_settings(
        config_path=cfg,
        environ={"EDUPREDICT_APP__PORT": "7000"},
        overrides={"app": {"port": 9000}},
    )
    assert settings.app.port == 9000


def test_malformed_env_variable_raises(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text("", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="must use the form"):
        load_settings(config_path=cfg, environ={"EDUPREDICT_PORT": "1"})


def test_env_variable_unknown_section_raises(tmp_path):
    cfg = tmp_path / "settings.toml"
    cfg.write_text("", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unknown section"):
        load_settings(config_path=cfg, environ={"EDUPREDICT_NOPE__A": "1"})


def test_resolve_paths_against_project_root(project_root):
    settings = load_settings(config_path=project_root / "config" / "settings.toml", environ={})
    resolved = settings.resolve("logs/x.log")
    assert resolved.is_absolute()
    assert resolved == project_root / "logs" / "x.log"
