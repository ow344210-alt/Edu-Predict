"""The authentication service - credential checking and role-aware sessions.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx, Functional Requirements):

    "Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts.
     Define access controls to restrict data access based on user roles and
     responsibilities."

IMPLEMENTATION DECISIONS (ADR-0009 / ADR-0011):

* Credential checking lives here, not in a view, so the same code can later back
  a CLI or a batch job. This module does not import Flask.
* A failed login returns the same result whether the username is unknown or the
  password is wrong, and the comparison is done against a dummy hash when the
  username is unknown, so the endpoint cannot be used to discover valid
  usernames.
* The session cookie stores only the numeric user id. The role is re-read from
  the store on every request, so a role change takes effect immediately and no
  password material is ever held in a cookie the browser can read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .passwords import DUMMY_HASH_SOURCE, hash_password, verify_password
from .roles import Role
from .users import User, UserStore, normalise_username

__all__ = ["AuthenticationService", "LoginResult", "SESSION_USER_KEY"]

#: Key used inside the Flask session cookie. A plain integer id - never a
#: password, hash, or role value.
SESSION_USER_KEY = "uid"

#: Hashed once at import time; used only to equalise response timing.
_DUMMY_HASH = hash_password(DUMMY_HASH_SOURCE)


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Outcome of a login attempt.

    ``user`` is ``None`` when authentication failed. The two failure reasons are
    deliberately merged so the caller cannot leak which one occurred.
    """

    user: User | None

    @property
    def ok(self) -> bool:
        return self.user is not None


class AuthenticationService:
    """Verifies credentials against a :class:`~edupredict.auth.users.UserStore`."""

    def __init__(self, store: UserStore, *, max_failures: int = 5, window_seconds: int = 300) -> None:
        self._store = store
        self._max_failures = max(1, int(max_failures))
        self._window_seconds = max(1, int(window_seconds))
        # username -> list of failure timestamps still inside the window.
        self._failures: dict[str, list[float]] = {}

    # -- public API --------------------------------------------------------- #
    def authenticate(self, username: str, password: str) -> LoginResult:
        """Check ``username``/``password``.

        Returns a :class:`LoginResult` whose ``user`` is ``None`` on any failure.
        Records failures so repeated wrong passwords for one account can be
        detected by the caller.
        """
        try:
            candidate = normalise_username(username)
        except ValueError:
            # An invalid username still costs a hash comparison, so the timing
            # matches the "unknown user" path.
            verify_password(_DUMMY_HASH, password or "")
            return LoginResult(None)

        user = self._store.get_by_username(candidate)
        if user is None:
            verify_password(_DUMMY_HASH, password or "")
            return LoginResult(None)

        if not verify_password(user.password_hash, password or ""):
            return LoginResult(None)

        self._clear_failures(candidate)
        return LoginResult(user)

    def record_failure(self, username: str, password: str) -> None:
        """Note a failed attempt for ``username``."""
        try:
            key = normalise_username(username)
        except ValueError:
            return
        now = time.monotonic()
        history = [t for t in self._failures.get(key, []) if now - t < self._window_seconds]
        history.append(now)
        self._failures[key] = history

    def _clear_failures(self, username: str) -> None:
        self._failures.pop(username, None)

    def failure_count(self, username: str) -> int:
        """Number of recent failures recorded for ``username``."""
        try:
            key = normalise_username(username)
        except ValueError:
            return 0
        now = time.monotonic()
        return sum(1 for t in self._failures.get(key, []) if now - t < self._window_seconds)

    def is_locked(self, username: str) -> bool:
        return self.failure_count(username) >= self._max_failures

    # -- provisioning ------------------------------------------------------- #
    def create_user(self, username: str, password: str, role: Role | str) -> User:
        """Create an account. Used by the CLI, never by a browser request."""
        return self._store.create(username, password, Role.parse(role))