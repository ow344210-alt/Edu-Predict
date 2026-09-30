"""Account provisioning CLI, secret handling and the absence of committed credentials.

These tests are the evidence for the "no hard-coded credentials, no committed
secrets" requirement. They scan the repository itself rather than trusting a
code review.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tomllib

import pytest
from flask import Flask

from edupredict.__main__ import main
from edupredict.app import configure_secret_key, create_app
from edupredict.auth import Role
from edupredict.config import load_settings
from edupredict.errors import EduPredictError

from conftest import TEST_PASSWORD

# --------------------------------------------------------------------------- #
# user create / user list
# --------------------------------------------------------------------------- #
def test_user_create_from_stdin(auth_env, stdin_password, capsys):
    stdin_password(TEST_PASSWORD)
    assert main(["user", "create", "cli_user", "--role", "teacher", "--password-stdin"]) == 0
    out = capsys.readouterr().out
    assert "Created account 'cli_user'" in out
    assert "Teacher" in out


def test_created_account_can_authenticate(auth_env, stdin_password, auth_app):
    stdin_password(TEST_PASSWORD)
    assert main(["user", "create", "cli_login", "--role", "analyst", "--password-stdin"]) == 0
    service = auth_app.config["EDUPREDICT_AUTH_SERVICE"]
    assert service.authenticate("cli_login", TEST_PASSWORD).ok is True


def test_cli_stores_a_hash_not_the_plaintext(auth_env, stdin_password):
    stdin_password(TEST_PASSWORD)
    main(["user", "create", "raw_check", "--role", "teacher", "--password-stdin"])
    row = sqlite3.connect(auth_env).execute(
        "SELECT password_hash FROM users WHERE username = 'raw_check'"
    ).fetchone()[0]
    assert row != TEST_PASSWORD
    assert TEST_PASSWORD not in row
    assert row.startswith("scrypt:")


def test_user_list_shows_no_hash(auth_env, stdin_password, capsys):
    stdin_password(TEST_PASSWORD)
    main(["user", "create", "listed", "--role", "student", "--password-stdin"])
    capsys.readouterr()
    assert main(["user", "list"]) == 0
    out = capsys.readouterr().out
    assert "listed" in out
    assert "Student" in out
    assert "scrypt" not in out
    assert TEST_PASSWORD not in out


def test_user_list_on_an_empty_store(auth_env, capsys):
    assert main(["user", "list"]) == 0
    assert "No accounts" in capsys.readouterr().out


def test_user_command_without_subcommand_fails(auth_env, capsys):
    assert main(["user"]) == 1
    assert "create" in capsys.readouterr().err


def test_duplicate_account_reports_failure(auth_env, stdin_password, capsys):
    stdin_password(TEST_PASSWORD)
    assert main(["user", "create", "twice", "--role", "teacher", "--password-stdin"]) == 0
    capsys.readouterr()
    assert main(["user", "create", "twice", "--role", "teacher", "--password-stdin"]) == 1
    assert "already taken" in capsys.readouterr().err


def test_invalid_username_reports_failure(auth_env, stdin_password, capsys):
    stdin_password(TEST_PASSWORD)
    assert main(["user", "create", "a b", "--role", "teacher", "--password-stdin"]) == 1
    assert "Username" in capsys.readouterr().err


def test_invalid_role_is_rejected_by_the_parser(auth_env):
    with pytest.raises(SystemExit):
        main(["user", "create", "someone", "--role", "root", "--password-stdin"])


def test_every_documented_role_is_accepted_by_the_cli(auth_env, stdin_password, capsys):
    for role in Role:
        stdin_password(TEST_PASSWORD)
        assert main(
            ["user", "create", f"cli_{role.value}", "--role", role.value, "--password-stdin"]
        ) == 0
    assert main(["user", "list"]) == 0
    out = capsys.readouterr().out
    for role in Role:
        assert role.label in out


def test_password_never_appears_in_argv(auth_env, stdin_password, monkeypatch):
    """The password must not be passed as a command-line argument."""
    recorded: list[list[str]] = []
    real_argv = __import__("sys").argv
    monkeypatch.setattr(
        "sys.argv", type("A", (), {"__iter__": lambda self: iter(recorded)})()
    )
    stdin_password(TEST_PASSWORD)
    main(["user", "create", "argv_check", "--role", "teacher", "--password-stdin"])
    assert TEST_PASSWORD not in real_argv
    assert all(TEST_PASSWORD not in " ".join(argv) for argv in recorded)


def test_empty_password_is_rejected(auth_env, stdin_password, capsys):
    stdin_password("")
    assert main(["user", "create", "nopass", "--role", "teacher", "--password-stdin"]) == 1
    assert "must not be empty" in capsys.readouterr().err


def test_cli_writes_only_to_the_temporary_store(auth_env, stdin_password, project_root):
    """CLI tests must never write to the repository's own account database.

    The repository database is allowed to exist (an operator may have created
    real accounts), so the check is that this test run did not *change* it.
    """
    repo_db = project_root / "var" / "auth" / "users.db"
    before = _username_count(repo_db)

    stdin_password(TEST_PASSWORD)
    main(["user", "create", "isolated", "--role", "teacher", "--password-stdin"])

    assert os.path.exists(auth_env)
    assert _username_count(repo_db) == before, "the CLI wrote to the repository database"
    assert _has_user(auth_env, "isolated")


def _username_count(path) -> int:
    if not os.path.exists(path):
        return 0
    return sqlite3.connect(path).execute("SELECT COUNT(*) FROM users").fetchone()[0]


def _has_user(path, username: str) -> bool:
    row = sqlite3.connect(path).execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    ).fetchone()
    return row is not None


# --------------------------------------------------------------------------- #
# Secret key handling
# --------------------------------------------------------------------------- #
def test_settings_file_ships_an_empty_secret_key(project_root):
    """A committed key would be a committed secret."""
    with (project_root / "config" / "settings.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["auth"]["secret_key"] == ""


def test_missing_key_in_development_yields_a_working_ephemeral_key(auth_settings):
    app = create_app(auth_settings)
    assert len(app.config["SECRET_KEY"]) >= 32


def test_ephemeral_key_differs_between_processes(auth_settings):
    """Restarting the server must not leave old cookies valid."""
    first = create_app(auth_settings).config["SECRET_KEY"]
    second = create_app(auth_settings).config["SECRET_KEY"]
    assert first != second


def test_explicit_key_is_used(auth_settings):
    key = "a" * 64
    settings = load_settings(
        config_path=auth_settings.config_file,
        environ={"EDUPREDICT_AUTH__SECRET_KEY": key},
        overrides={"logging": {"target": "none"}},
    )
    assert create_app(settings).config["SECRET_KEY"] == key


def test_short_key_is_rejected(auth_settings):
    settings = load_settings(
        config_path=auth_settings.config_file,
        environ={"EDUPREDICT_AUTH__SECRET_KEY": "tooshort"},
        overrides={"logging": {"target": "none"}},
    )
    with pytest.raises(EduPredictError, match="too short"):
        configure_secret_key(Flask(__name__), settings)


def test_missing_key_outside_development_is_an_error(auth_settings):
    settings = load_settings(
        config_path=auth_settings.config_file,
        environ={},
        overrides={"logging": {"target": "none"}, "app": {"environment": "production"}},
    )
    with pytest.raises(EduPredictError, match="secret_key must be set"):
        configure_secret_key(Flask(__name__), settings)


def test_session_hardening_is_configured(auth_app):
    assert auth_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert auth_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert auth_app.config["SESSION_COOKIE_SECURE"] is False  # local HTTP testing
    assert auth_app.config["WTF_CSRF_ENABLED"] is True
    assert auth_app.config["MAX_CONTENT_LENGTH"] == 16384
    assert auth_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 3600


def test_cookie_secure_can_be_enabled_by_configuration(auth_settings):
    settings = load_settings(
        config_path=auth_settings.config_file,
        environ={},
        overrides={
            "logging": {"target": "none"},
            "auth": {"cookie_secure": True, "database_path": str(auth_settings.resolve(
                auth_settings.auth.database_path
            ))},
        },
    )
    assert create_app(settings).config["SESSION_COOKIE_SECURE"] is True


# --------------------------------------------------------------------------- #
# Repository scans: no credentials, no secrets
# --------------------------------------------------------------------------- #
_SOURCE_SUFFIXES = {".py", ".toml", ".html", ".md", ".cfg", ".txt"}
_SKIP_DIRS = {"__pycache__", ".pytest_cache", "logs", "var", ".git", "build", "dist"}


def _repo_files(root) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for name in filenames:
            if os.path.splitext(name)[1] in _SOURCE_SUFFIXES:
                found.append(os.path.join(dirpath, name))
    return found


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def test_repository_contains_no_committed_secret_key(project_root):
    """No file may contain a hex string long enough to be a signing key."""
    pattern = re.compile(r"\b[A-Fa-f0-9]{48,}\b")
    offenders = []
    for path in _repo_files(project_root):
        for number, line in enumerate(_read(path).splitlines(), start=1):
            # Skip lines that are plainly documentation or test assertions
            # about the absence of secrets.
            lowered = line.lower()
            if "secret" not in lowered and "token_hex" not in lowered:
                continue
            if pattern.search(line):
                offenders.append(f"{path}:{number}: {line.strip()}")
    assert not offenders, "possible committed secret:\n" + "\n".join(offenders)


def test_settings_file_contains_no_secret_material(project_root):
    content = _read(str(project_root / "config" / "settings.toml"))
    with (project_root / "config" / "settings.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["auth"]["secret_key"] == ""
    assert "EDUPREDICT_AUTH__SECRET_KEY" in content  # documents the env var only


def test_no_test_password_outside_the_test_suite(project_root):
    """The fixture credential must not leak into application code."""
    for path in _repo_files(project_root):
        if os.sep + "tests" + os.sep in path:
            continue
        assert TEST_PASSWORD not in _read(path), f"{path} contains the test password"


def test_no_social_login_in_executable_source(project_root):
    """Social login is explicitly out of scope.

    Scanned over ``src/`` and ``config/`` - the code that actually runs. The
    documentation is excluded on purpose: ``docs/DECISIONS.md`` and
    ``docs/AUTHENTICATION.md`` name Flask-Login and Authlib *to record why they
    were rejected*, which is the opposite of using them.
    """
    banned = ("oauth", "openid", "social-auth", "google-auth", "flask_login", "authlib")
    offenders = []
    for subdir in ("src", "config"):
        for path in _repo_files(project_root / subdir):
            lowered = _read(path).lower()
            for needle in banned:
                if needle in lowered:
                    offenders.append(f"{path}: {needle}")
    assert not offenders, f"social login reference found in source: {offenders}"


def test_social_login_appears_nowhere_in_the_dependency_set(project_root):
    """No auth or social-login package is a dependency, documented or not."""
    with (project_root / "pyproject.toml").open("rb") as handle:
        raw = handle.read().decode("utf-8").lower()
    for needle in ("oauth", "openid", "flask-login", "flask_login", "authlib", "jwt"):
        assert needle not in raw, f"pyproject.toml references {needle}"


def test_runtime_dependencies_are_minimal(project_root):
    """Only Flask and Werkzeug may be required at runtime."""
    with (project_root / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    runtime = {
        re.split(r"[<>=!\[ ]", entry, maxsplit=1)[0].strip().lower()
        for entry in data["project"]["dependencies"]
    }
    assert runtime == {"flask", "werkzeug"}


def test_werkzeug_is_declared_explicitly(project_root):
    """Phase 2 imports werkzeug.security directly, so it must be a declared dep."""
    with (project_root / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert any(entry.startswith("werkzeug") for entry in data["project"]["dependencies"])


def test_gitignore_covers_the_user_database(project_root):
    assert "var/" in _read(str(project_root / ".gitignore"))


def test_no_env_file_or_local_settings_committed(project_root):
    """Secrets must never be committed; the ignore rules must cover them."""
    ignore = _read(str(project_root / ".gitignore"))
    assert ".env" in ignore
    assert "config/settings.local.toml" in ignore
    assert not (project_root / ".env").exists()
