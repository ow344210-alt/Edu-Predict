"""Shared pytest fixtures.

Tests must pass on a machine with or without Hadoop/Impala installed, so the
infrastructure probes are never asserted to be healthy - only that they behave
predictably and never raise.

Authentication tests need their own SQLite file, so the ``auth_app`` fixtures
below override ``[auth] database_path`` to a temporary location. The
repository's real account store is never read or written by the test suite.
"""

from __future__ import annotations

import pytest

from edupredict.app import create_app
from edupredict.auth import Role, build_user_store
from edupredict.config import Settings, load_settings


@pytest.fixture(scope="session")
def project_root():
    from edupredict.config import find_project_root

    return find_project_root()


@pytest.fixture
def settings(project_root) -> Settings:
    """Settings built from the repository's real settings.toml."""
    return load_settings(
        config_path=project_root / "config" / "settings.toml",
        environ={},
        overrides={"logging": {"target": "none"}},
    )


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Authentication fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def auth_settings(project_root, tmp_path) -> Settings:
    """Settings whose user store lives in a temporary directory."""
    return load_settings(
        config_path=project_root / "config" / "settings.toml",
        environ={},
        overrides={
            "logging": {"target": "none"},
            "auth": {
                "database_path": str(tmp_path / "users.db"),
                # Short lockout so the behaviour is testable without sleeping.
                "max_login_failures": 3,
                "lockout_seconds": 300,
            },
        },
    )


@pytest.fixture
def auth_app(auth_settings):
    application = create_app(auth_settings)
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


@pytest.fixture
def user_store(auth_settings):
    """A store bound to the same temporary database the app uses."""
    return build_user_store(auth_settings.resolve(auth_settings.auth.database_path))


#: Credentials used only inside the test suite. These are test fixtures, not
#: working accounts: the real store is a temporary file created per test.
TEST_PASSWORD = "TestPassw0rd!not-a-real-secret"


@pytest.fixture
def make_user(user_store):
    """Factory creating accounts in the temporary store."""
    created: list = []

    def _make(username: str, role: Role, password: str = TEST_PASSWORD):
        user = user_store.create(username, password, role)
        created.append(user)
        return user

    return _make


@pytest.fixture
def all_roles_user(make_user):
    """One account per documented role, so every role boundary can be tested."""

    def _create(role: Role):
        return make_user(f"user_{role.value}", role)

    return _create


@pytest.fixture
def auth_env(auth_settings, monkeypatch):
    """Point the CLI at the temporary account store.

    The ``user`` subcommand reloads settings itself, so the temporary path is
    injected through the environment - the layer with the highest precedence
    after explicit overrides. Without this, CLI tests would write to the
    repository's own ``var/auth/users.db``.
    """
    import os

    database = str(auth_settings.resolve(auth_settings.auth.database_path))
    monkeypatch.setenv("EDUPREDICT_AUTH__DATABASE_PATH", database)
    monkeypatch.setenv("EDUPREDICT_LOGGING__TARGET", "none")
    return database


@pytest.fixture
def stdin_password(monkeypatch):
    """Feed a password to ``user create --password-stdin``.

    The production path prompts on an interactive terminal, which pytest cannot
    drive, so the test exercises the equally valid stdin branch. No password
    ever appears in ``argv``.
    """

    def _feed(value: str):
        stream = type("FakeStdin", (), {"readline": staticmethod(lambda: value + "\n")})()
        monkeypatch.setattr("sys.stdin", stream)

    return _feed


def login(client, username: str, password: str = TEST_PASSWORD, next_url: str = "/auth/dashboard"):
    """Perform a real form login, including the CSRF token.

    Mirrors what a browser does, so the tests exercise the real flow rather than
    poking at the session object.
    """
    page = client.get("/auth/login", follow_redirects=False)
    token = _extract_csrf(page.get_data(as_text=True))
    return client.post(
        f"/auth/login?next={next_url}",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def _extract_csrf(html: str) -> str:
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def sign_in(client, username: str, password: str = TEST_PASSWORD):
    """Log in and return the client, asserting the sign-in succeeded."""
    response = login(client, username, password)
    assert response.status_code == 302, response.get_data(as_text=True)[:500]
    return client
