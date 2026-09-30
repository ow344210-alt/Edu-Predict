"""Role model, password hashing, the user store and the login service.

These are the unit-level guarantees behind the document's requirement for a
"secure authentication system" (docs/Big Data-EduPredict.docx).
"""

from __future__ import annotations

import sqlite3

import pytest

from edupredict.auth import (
    PERMISSION_SCOPE_NOTE,
    REGISTRY,
    AuthenticationService,
    Role,
    SqliteUserStore,
    UserStore,
    build_user_store,
    hash_password,
    verify_password,
)
from edupredict.auth.passwords import DUMMY_HASH_SOURCE, MIN_PASSWORD_LENGTH, needs_rehash
from edupredict.auth.permissions import Permission, PermissionRegistry
from edupredict.auth.service import LoginResult
from edupredict.auth.users import normalise_username
from edupredict.errors import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    EduPredictError,
    UnknownRoleError,
    UserAlreadyExistsError,
)

from conftest import TEST_PASSWORD

DOCUMENTED_ROLES = ("administrator", "teacher", "student", "analyst")


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #
def test_exactly_four_roles_exist():
    """The document names four roles; no more and no fewer are permitted."""
    assert [role.value for role in Role] == list(DOCUMENTED_ROLES)
    assert len(Role) == 4


def test_role_labels_match_the_document():
    assert [role.label for role in Role] == [
        "Administrator",
        "Teacher",
        "Student",
        "Analyst",
    ]


@pytest.mark.parametrize("raw", ["administrator", "Administrator", "ADMINISTRATOR", " Administrator "])
def test_role_parse_accepts_value_and_label(raw):
    assert Role.parse(raw) is Role.ADMINISTRATOR


def test_role_parse_is_case_and_space_insensitive_for_every_role():
    for role in Role:
        assert Role.parse(role.label) is role
        assert Role.parse(role.value.upper()) is role


@pytest.mark.parametrize("raw", ["root", "superuser", "moderator", "", "guest", None, 7])
def test_role_parse_rejects_anything_else(raw):
    with pytest.raises(UnknownRoleError):
        Role.parse(raw)


def test_unknown_role_error_is_a_domain_error():
    assert issubclass(UnknownRoleError, AuthenticationError)
    assert issubclass(UnknownRoleError, EduPredictError)
    assert issubclass(AccountLockedError, AuthenticationError)


def test_role_values_are_stable_storage_tokens():
    """The stored token must not change if a display label is reworded."""
    assert Role.ADMINISTRATOR.value == "administrator"
    assert Role.TEACHER.value == "teacher"
    assert Role.STUDENT.value == "student"
    assert Role.ANALYST.value == "analyst"


def test_role_choices_matches_members():
    assert Role.choices() == DOCUMENTED_ROLES


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def test_password_is_never_stored_in_plaintext():
    digest = hash_password("CorrectHorseBatteryStaple")
    assert "CorrectHorseBatteryStaple" not in digest
    assert digest != "CorrectHorseBatteryStaple"


def test_hash_uses_a_salted_algorithm():
    """Two hashes of the same password must differ, i.e. a random salt is used."""
    assert hash_password("same-password") != hash_password("same-password")


def test_hash_records_the_algorithm_and_parameters():
    """Werkzeug 3.x defaults to scrypt, a memory-hard KDF."""
    digest = hash_password("another-password")
    assert "scrypt:" in digest
    assert needs_rehash(digest) is False


def test_verify_accepts_the_correct_password():
    assert verify_password(hash_password("s3cret-value"), "s3cret-value") is True


def test_verify_rejects_the_wrong_password():
    assert verify_password(hash_password("s3cret-value"), "s3cret-value-typo") is False


@pytest.mark.parametrize("stored", ["", "not-a-hash", None, 12345])
def test_verify_never_raises_on_a_damaged_hash(stored):
    """A corrupt row must fail the login, not crash the endpoint."""
    assert verify_password(stored, "any-password") is False


def test_dummy_hash_source_is_not_a_password():
    """The timing equaliser is a constant, not a credential."""
    assert DUMMY_HASH_SOURCE and DUMMY_HASH_SOURCE != TEST_PASSWORD
    assert verify_password(hash_password(DUMMY_HASH_SOURCE), TEST_PASSWORD) is False


# --------------------------------------------------------------------------- #
# User store
# --------------------------------------------------------------------------- #
def test_store_satisfies_the_protocol(user_store):
    assert isinstance(user_store, UserStore)


def test_create_persists_the_account(user_store):
    user = user_store.create("ada", TEST_PASSWORD, Role.TEACHER)
    assert user.id > 0
    assert user.username == "ada"
    assert user.role is Role.TEACHER
    assert user.password_hash != TEST_PASSWORD
    assert user.created_at


def test_account_survives_a_reopen_of_the_file(auth_settings):
    """Persistence is the point of using SQLite rather than a dict."""
    path = auth_settings.resolve(auth_settings.auth.database_path)
    SqliteUserStore(path).create("grace", TEST_PASSWORD, Role.ANALYST)
    assert SqliteUserStore(path).get_by_username("grace") is not None


@pytest.mark.parametrize("role", list(Role))
def test_store_round_trips_every_role(user_store, role):
    user = user_store.create(f"u{role.value}", TEST_PASSWORD, role)
    assert user_store.get_by_username(user.username).role is role


def test_lookup_is_case_insensitive(user_store):
    user_store.create("Alice", TEST_PASSWORD, Role.STUDENT)
    assert user_store.get_by_username("alice") is not None
    assert user_store.get_by_username("ALICE") is not None


def test_duplicate_username_is_rejected(user_store):
    user_store.create("dup", TEST_PASSWORD, Role.TEACHER)
    with pytest.raises(UserAlreadyExistsError):
        user_store.create("DUP", TEST_PASSWORD, Role.STUDENT)


def test_duplicate_is_rejected_case_insensitively(user_store):
    user_store.create("dup2", TEST_PASSWORD, Role.TEACHER)
    with pytest.raises(UserAlreadyExistsError):
        user_store.create("DUP2", TEST_PASSWORD, Role.STUDENT)


def test_get_by_id_returns_none_for_unknown_id(user_store):
    assert user_store.get_by_id(9999) is None


def test_get_by_username_returns_none_for_unknown_user(user_store):
    assert user_store.get_by_username("nobody") is None


def test_short_password_is_rejected(user_store):
    with pytest.raises(ValueError, match="at least"):
        user_store.create("shorty", "a" * (MIN_PASSWORD_LENGTH - 1), Role.STUDENT)


def test_invalid_role_is_rejected_at_creation(user_store):
    with pytest.raises(UnknownRoleError):
        user_store.create("wrongrole", TEST_PASSWORD, "superuser")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw", ["", "  ", "ab", "has space", "drop;table", "a" * 65, "-leading", "sym$bol"]
)
def test_invalid_usernames_are_rejected(raw):
    with pytest.raises(ValueError):
        normalise_username(raw)


def test_valid_usernames_are_normalised():
    assert normalise_username("  bob.smith_1 ") == "bob.smith_1"


def test_count_and_list_all(user_store):
    assert user_store.count() == 0
    user_store.create("first", TEST_PASSWORD, Role.TEACHER)
    user_store.create("second", TEST_PASSWORD, Role.STUDENT)
    assert user_store.count() == 2
    assert [u.username for u in user_store.list_all()] == ["first", "second"]


def test_stored_hash_is_verifiable_from_the_database(user_store):
    user = user_store.create("verify-me", TEST_PASSWORD, Role.ANALYST)
    raw = sqlite3.connect(user_store.database_path).execute(
        "SELECT password_hash FROM users WHERE username = ?", ("verify-me",)
    ).fetchone()[0]
    assert raw == user.password_hash
    assert TEST_PASSWORD not in raw
    assert verify_password(raw, TEST_PASSWORD) is True


def test_user_public_view_excludes_the_hash(user_store):
    public = user_store.create("safe", TEST_PASSWORD, Role.TEACHER).public()
    assert "password_hash" not in public
    assert "password" not in " ".join(public)
    assert public["role"] == "teacher"
    assert public["role_label"] == "Teacher"


def test_unknown_role_in_the_database_is_rejected_loudly(user_store):
    """A tampered role must not silently degrade into an unprivileged account."""
    user_store.create("tamper", TEST_PASSWORD, Role.TEACHER)
    connection = sqlite3.connect(user_store.database_path)
    connection.execute("UPDATE users SET role = 'root' WHERE username = 'tamper'")
    connection.commit()
    connection.close()
    with pytest.raises(UnknownRoleError):
        user_store.get_by_username("tamper")


def test_build_user_store_returns_the_sqlite_implementation(tmp_path):
    assert isinstance(build_user_store(tmp_path / "x.db"), SqliteUserStore)


# --------------------------------------------------------------------------- #
# Authentication service
# --------------------------------------------------------------------------- #
def test_valid_credentials_authenticate(user_store):
    user_store.create("valid", TEST_PASSWORD, Role.TEACHER)
    result = AuthenticationService(user_store).authenticate("valid", TEST_PASSWORD)
    assert isinstance(result, LoginResult)
    assert result.ok and result.user is not None
    assert result.user.username == "valid"


def test_wrong_password_fails(user_store):
    user_store.create("valid", TEST_PASSWORD, Role.TEACHER)
    assert AuthenticationService(user_store).authenticate("valid", "wrong").ok is False


def test_unknown_user_fails(user_store):
    assert AuthenticationService(user_store).authenticate("ghost", TEST_PASSWORD).ok is False


def test_invalid_username_shape_fails_without_raising(user_store):
    assert AuthenticationService(user_store).authenticate("a", TEST_PASSWORD).ok is False


def test_username_is_trimmed_before_verification(user_store):
    user_store.create("pad", TEST_PASSWORD, Role.STUDENT)
    assert AuthenticationService(user_store).authenticate("  pad  ", TEST_PASSWORD).ok


def test_empty_password_fails(user_store):
    user_store.create("empty", TEST_PASSWORD, Role.STUDENT)
    assert AuthenticationService(user_store).authenticate("empty", "").ok is False


def test_repeated_failures_lock_the_account(user_store):
    user_store.create("lockme", TEST_PASSWORD, Role.TEACHER)
    service = AuthenticationService(user_store, max_failures=3, window_seconds=300)
    for _ in range(3):
        service.authenticate("lockme", "wrong")
        service.record_failure("lockme", "wrong")
    assert service.failure_count("lockme") == 3
    assert service.is_locked("lockme") is True


def test_successful_login_clears_the_failure_count(user_store):
    user_store.create("reset", TEST_PASSWORD, Role.STUDENT)
    service = AuthenticationService(user_store, max_failures=5, window_seconds=300)
    service.record_failure("reset", "wrong")
    service.record_failure("reset", "wrong")
    assert service.failure_count("reset") == 2
    assert service.authenticate("reset", TEST_PASSWORD).ok
    assert service.failure_count("reset") == 0


def test_failures_outside_the_window_are_discarded(user_store, monkeypatch):
    """Old failures age out, so a lockout cannot become permanent."""
    import edupredict.auth.service as service_module

    clock = {"now": 1000.0}
    monkeypatch.setattr(service_module.time, "monotonic", lambda: clock["now"])

    user_store.create("aging", TEST_PASSWORD, Role.TEACHER)
    service = AuthenticationService(user_store, max_failures=2, window_seconds=300)
    service.record_failure("aging", "wrong")
    assert service.failure_count("aging") == 1

    clock["now"] += 301  # just past the window
    assert service.failure_count("aging") == 0
    assert service.is_locked("aging") is False


def test_lockout_window_is_clamped_to_a_positive_value(user_store):
    """A zero or negative window must not disable the lockout entirely."""
    user_store.create("clamped", TEST_PASSWORD, Role.TEACHER)
    service = AuthenticationService(user_store, max_failures=1, window_seconds=0)
    service.record_failure("clamped", "wrong")
    assert service.failure_count("clamped") == 1
    assert service.is_locked("clamped") is True


def test_create_user_through_the_service(user_store):
    user = AuthenticationService(user_store).create_user("svc", TEST_PASSWORD, "Student")
    assert user.role is Role.STUDENT


# --------------------------------------------------------------------------- #
# Permission registry
# --------------------------------------------------------------------------- #
def test_registry_ships_empty_so_no_permission_is_invented():
    """The document does not define per-role permissions, so none are preloaded."""
    assert REGISTRY.all() == ()
    assert PERMISSION_SCOPE_NOTE == (
        "Detailed role permissions are not specified in the source document and "
        "will be defined when the corresponding functional modules are implemented."
    )


def test_a_later_phase_can_define_a_permission():
    registry = PermissionRegistry()
    registry.define("analytics.view", "View analytics outputs", (Role.ANALYST, Role.TEACHER))
    assert registry.for_role(Role.ANALYST) == frozenset({"analytics.view"})
    assert registry.for_role(Role.STUDENT) == frozenset()
    assert registry.check(Role.TEACHER, "analytics.view") is True
    assert registry.check(Role.STUDENT, "analytics.view") is False


def test_undefined_permission_raises_rather_than_denying_silently():
    with pytest.raises(AuthorizationError):
        REGISTRY.check(Role.TEACHER, "does.not.exist")


def test_permission_without_roles_is_unassigned_not_denied_for_everyone():
    """An empty role set means 'not yet defined', which must be visible."""
    permission = Permission(name="p", description="d")
    assert permission.roles == frozenset()
    assert permission.allows(Role.ADMINISTRATOR) is False
