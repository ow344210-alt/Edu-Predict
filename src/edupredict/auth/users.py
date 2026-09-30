"""User records and the persistence boundary for authentication.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx):

    "Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts."

IMPLEMENTATION DECISION (ADR-0010):

The document names no database for authentication, so the simplest persistent
mechanism that fits the current architecture is used: **SQLite through the
Python standard library** (:mod:`sqlite3`).

Why SQLite:

* It ships with CPython - no new dependency, consistent with Phase 1.
* It is a real transactional database, so accounts survive a restart and a
  partially written insert cannot corrupt the store.
* It is a single file, which keeps this eProject easy to run and to submit.

MongoDB appears in the document's software list, but the document never states
that it stores users, so it is deliberately **not** introduced here.

Swapping the backend later is a matter of implementing :class:`UserStore`; no
caller imports :class:`SqliteUserStore` directly except
:func:`build_user_store`.

Passwords are stored only as salted scrypt hashes - see
:mod:`edupredict.auth.passwords`.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..errors import UserAlreadyExistsError
from .passwords import MIN_PASSWORD_LENGTH, hash_password
from .roles import Role

__all__ = [
    "User",
    "UserStore",
    "SqliteUserStore",
    "build_user_store",
    "USERNAME_PATTERN",
    "USERNAME_MAX_LENGTH",
    "normalise_username",
]

#: Usernames are restricted to characters that are safe in a URL path and easy
#: to type. This is an allow-list, so an unexpected character is rejected rather
#: than silently stripped.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

USERNAME_MAX_LENGTH = 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class User:
    """An EduPredict account.

    ``password_hash`` is present because the login path needs it, but it is
    never rendered into a template, a response body or a log line. The web
    layer exposes :meth:`public` when it needs to display a user.
    """

    id: int
    username: str
    password_hash: str
    role: Role
    created_at: str

    @property
    def role_label(self) -> str:
        return self.role.label

    def public(self) -> dict[str, object]:
        """A representation safe to display - deliberately excludes the hash."""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "role_label": self.role.label,
            "created_at": self.created_at,
        }


def normalise_username(raw: object) -> str:
    """Validate a username and return it in its stored form.

    Surrounding whitespace is removed, then the value is checked against
    :data:`USERNAME_PATTERN`. Anything else raises, so malformed input never
    reaches the database.
    """
    username = str(raw).strip()
    if not USERNAME_PATTERN.match(username):
        raise ValueError(
            "Username must be 3-64 characters long and may contain only "
            "letters, digits, dot, underscore and hyphen, starting with a "
            "letter or digit."
        )
    return username


@runtime_checkable
class UserStore(Protocol):
    """Persistence contract for accounts.

    Implemented by :class:`SqliteUserStore`. Later phases may add a server-backed
    store without changing any caller.
    """

    def get_by_username(self, username: str) -> User | None: ...

    def get_by_id(self, user_id: int) -> User | None: ...

    def create(self, username: str, password: str, role: Role) -> User: ...

    def count(self) -> int: ...

    def list_all(self) -> list[User]: ...


class SqliteUserStore:
    """SQLite-backed :class:`UserStore` using the standard library only.

    The schema is created on first use, so pointing the store at a fresh path is
    enough to provision a new environment - no migration step is required.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    # -- internals ---------------------------------------------------------- #
    def _connect(self) -> sqlite3.Connection:
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        # Enforce the declared foreign keys and keep writes durable.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(_SCHEMA)
        return connection

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        # A role that is not one of the four documented roles means the store
        # was tampered with or written by a newer version; fail loudly rather
        # than silently downgrading the account.
        role = Role.parse(row["role"])
        return User(
            id=int(row["id"]),
            username=row["username"],
            password_hash=row["password_hash"],
            role=role,
            created_at=row["created_at"],
        )

    # -- UserStore ---------------------------------------------------------- #
    def get_by_username(self, username: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role, created_at "
                "FROM users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_by_id(self, user_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role, created_at "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def create(self, username: str, password: str, role: Role) -> User:
        clean = normalise_username(username)
        role = Role.parse(role)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
            )
        digest = hash_password(password)
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (clean, digest, role.value, created_at),
                )
                user_id = int(cursor.lastrowid or 0)
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExistsError(f"Username {clean!r} is already taken.") from exc
        user = self.get_by_id(user_id)
        if user is None:  # pragma: no cover - only reachable if the row vanished
            raise RuntimeError("User was inserted but could not be read back.")
        return user

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"])

    def list_all(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, username, password_hash, role, created_at "
                "FROM users ORDER BY id"
            ).fetchall()
        return [self._row_to_user(row) for row in rows]


def build_user_store(database_path: str | Path) -> UserStore:
    """Return the configured user store.

    The single place that decides which backend is in use.
    """
    return SqliteUserStore(database_path)