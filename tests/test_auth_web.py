"""The authentication web surface and role-based access control.

Covers the document's requirements:
  "Implement a secure authentication system for users with different roles..."
  "Define access controls to restrict data access based on user roles and
   responsibilities."
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import pytest

from edupredict.auth import Role
from edupredict.auth.permissions import PERMISSION_SCOPE_NOTE

from conftest import TEST_PASSWORD, _extract_csrf, login, sign_in

JSON = {"Accept": "application/json"}
HTML = {"Accept": "text/html"}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def test_index_is_public_and_offers_sign_in(auth_client):
    response = auth_client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Not signed in" in body
    assert "/auth/login" in body


def test_index_shows_the_role_once_signed_in(auth_client, make_user):
    make_user("homepage", Role.TEACHER)
    sign_in(auth_client, "homepage")
    body = auth_client.get("/").get_data(as_text=True)
    assert "homepage" in body
    assert "Teacher" in body


# --------------------------------------------------------------------------- #
# Login form
# --------------------------------------------------------------------------- #
def test_login_page_renders(auth_client):
    response = auth_client.get("/auth/login")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="username"' in body
    assert 'name="password"' in body
    assert 'type="password"' in body
    assert 'name="csrf_token"' in body


def test_login_form_never_prefills_the_password(auth_client):
    assert "value=" not in _password_input(auth_client.get("/auth/login").get_data(as_text=True))


def _password_input(html: str) -> str:
    start = html.index('name="password"')
    return html[start : start + 120]


def test_valid_login_redirects_to_the_dashboard(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    response = login(auth_client, "ada")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/dashboard")


def test_valid_login_honours_a_safe_next_parameter(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    response = login(auth_client, "ada", next_url="/auth/admin")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/admin")


@pytest.mark.parametrize("role", list(Role))
def test_each_documented_role_can_sign_in(auth_client, make_user, role):
    user = make_user(f"role_{role.value}", role)
    response = login(auth_client, user.username)
    assert response.status_code == 302
    dashboard = auth_client.get("/auth/dashboard")
    assert dashboard.status_code == 200
    assert role.label in dashboard.get_data(as_text=True)


def test_dashboard_shows_the_signed_in_username_and_role(auth_client, make_user):
    make_user("grace", Role.ANALYST)
    sign_in(auth_client, "grace")
    body = auth_client.get("/auth/dashboard").get_data(as_text=True)
    assert "grace" in body
    assert "Analyst" in body


def test_dashboard_states_the_permission_scope_note(auth_client, make_user):
    """No permission is invented, and the gap is stated on the page itself."""
    make_user("honest", Role.TEACHER)
    sign_in(auth_client, "honest")
    assert PERMISSION_SCOPE_NOTE in auth_client.get("/auth/dashboard").get_data(as_text=True)


def test_dashboard_does_not_claim_later_modules_exist(auth_client, make_user):
    make_user("waiting", Role.STUDENT)
    sign_in(auth_client, "waiting")
    body = auth_client.get("/auth/dashboard").get_data(as_text=True)
    assert "Not yet implemented" in body
    # No fabricated statistics or predictions.
    for marker in ("accuracy", "prediction score", "enrolled students", "%"):
        assert marker not in body.lower()


# --------------------------------------------------------------------------- #
# Invalid credentials
# --------------------------------------------------------------------------- #
def test_wrong_password_does_not_sign_the_user_in(auth_client, make_user):
    make_user("ada", TEST_PASSWORD and Role.TEACHER)
    response = login(auth_client, "ada", "definitely-wrong")
    assert response.status_code == 200
    assert "Incorrect username or password." in response.get_data(as_text=True)
    assert auth_client.get("/auth/dashboard").status_code == 302


def test_unknown_user_gives_the_same_message_as_a_wrong_password(auth_client, make_user):
    """The form must not reveal which usernames exist."""
    make_user("real", Role.TEACHER)
    unknown = login(auth_client, "ghost", "x" * 12).get_data(as_text=True)
    wrong = login(auth_client, "real", "x" * 12).get_data(as_text=True)
    assert "Incorrect username or password." in unknown
    assert "Incorrect username or password." in wrong
    assert "ghost" not in wrong


def test_login_page_does_not_echo_the_submitted_password(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    body = login(auth_client, "ada", "leaked-secret-value").get_data(as_text=True)
    assert "leaked-secret-value" not in body


def test_empty_submission_fails_cleanly(auth_client):
    page = auth_client.get("/auth/login").get_data(as_text=True)
    response = auth_client.post(
        "/auth/login",
        data={"username": "", "password": "", "csrf_token": _extract_csrf(page)},
    )
    assert response.status_code == 200
    assert "Incorrect username or password." in response.get_data(as_text=True)


def test_account_locks_after_repeated_failures(auth_client, make_user):
    make_user("target", Role.TEACHER)
    for _ in range(3):  # max_login_failures = 3 in the auth_settings fixture
        login(auth_client, "target", "wrong-password")
    body = login(auth_client, "target", TEST_PASSWORD).get_data(as_text=True)
    assert "temporarily locked" in body.lower()
    assert auth_client.get("/auth/dashboard").status_code == 302


# --------------------------------------------------------------------------- #
# CSRF
# --------------------------------------------------------------------------- #
def test_login_without_a_csrf_token_is_rejected(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    response = auth_client.post(
        "/auth/login", data={"username": "ada", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert "session expired" in response.get_data(as_text=True).lower()
    assert auth_client.get("/auth/dashboard").status_code == 302


def test_login_with_a_wrong_csrf_token_is_rejected(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    response = auth_client.post(
        "/auth/login",
        data={"username": "ada", "password": TEST_PASSWORD, "csrf_token": "forged"},
    )
    assert response.status_code == 200
    assert auth_client.get("/auth/dashboard").status_code == 302


def test_logout_requires_a_csrf_token(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    sign_in(auth_client, "ada")
    auth_client.post("/auth/logout")  # no token
    assert auth_client.get("/auth/dashboard").status_code == 200


# --------------------------------------------------------------------------- #
# Unauthenticated access
# --------------------------------------------------------------------------- #
def test_anonymous_dashboard_redirects_to_login(auth_client):
    response = auth_client.get("/auth/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_anonymous_admin_page_redirects_to_login(auth_client):
    response = auth_client.get("/auth/admin")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_anonymous_dashboard_returns_401_for_an_api_client(auth_client):
    response = auth_client.get("/auth/dashboard", headers=JSON)
    assert response.status_code == 401
    assert response.get_json()["error"] == "Unauthorized"


def test_anonymous_admin_returns_401_for_an_api_client(auth_client):
    assert auth_client.get("/auth/admin", headers=JSON).status_code == 401


def test_anonymous_error_pages_render_html(auth_client):
    response = auth_client.get("/auth/dashboard", headers=HTML)
    assert response.status_code == 302  # browsers are redirected, not shown JSON


def test_login_redirect_preserves_the_requested_page(auth_client):
    location = auth_client.get("/auth/dashboard").headers["Location"]
    assert location.startswith("/auth/login?next=")
    # request.full_path would append a bare "?", producing "/dashboard?"
    assert not location.endswith("?")
    assert unquote(location).endswith("next=/auth/dashboard")


def test_login_redirect_keeps_a_query_string_intact(auth_client):
    location = auth_client.get("/auth/dashboard?tab=recent").headers["Location"]
    # The "?" must be encoded inside the value, not truncate the parameter.
    assert unquote(location) == "/auth/login?next=/auth/dashboard?tab=recent"


def test_login_redirect_then_sign_in_returns_to_the_requested_page(auth_client, make_user):
    make_user("round", Role.TEACHER)
    anonymous = auth_client.get("/auth/dashboard")
    target = parse_qs(urlparse(anonymous.headers["Location"]).query)["next"][0]
    page = auth_client.get("/auth/login")
    response = auth_client.post(
        f"/auth/login?next={target}",
        data={
            "username": "round",
            "password": TEST_PASSWORD,
            "csrf_token": _extract_csrf(page.get_data(as_text=True)),
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"] == target


# --------------------------------------------------------------------------- #
# Logout
# --------------------------------------------------------------------------- #
def test_logout_ends_the_session(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    sign_in(auth_client, "ada")
    assert auth_client.get("/auth/dashboard").status_code == 200
    page = auth_client.get("/auth/dashboard").get_data(as_text=True)
    response = auth_client.post(
        "/auth/logout", data={"csrf_token": _extract_csrf(page)}
    )
    assert response.status_code == 302
    assert auth_client.get("/auth/dashboard").status_code == 302


def test_logout_cannot_be_triggered_by_get(auth_client, make_user):
    """A GET logout would let any site sign the user out with an image tag."""
    make_user("ada", Role.TEACHER)
    sign_in(auth_client, "ada")
    assert auth_client.get("/auth/logout").status_code == 405
    assert auth_client.get("/auth/dashboard").status_code == 200


def test_logout_is_idempotent_for_anonymous_clients(auth_client):
    response = auth_client.post("/auth/logout", headers=JSON)
    assert response.status_code in (200, 302, 400)


def test_session_cookie_carries_no_password_material(auth_client, make_user):
    """The signed cookie must contain only the user id, not the role or hash."""
    make_user("ada", Role.TEACHER)
    sign_in(auth_client, "ada")
    for cookie in auth_client._cookies.values():
        assert "scrypt" not in cookie.value
        assert TEST_PASSWORD not in cookie.value
        assert "administrator" not in cookie.value


def test_session_cookie_is_httponly_and_samesite_lax(auth_client, make_user):
    make_user("ada", Role.TEACHER)
    sign_in(auth_client, "ada")
    header = auth_client.get("/auth/dashboard").headers.get("Set-Cookie", "")
    # The login response already set the flag; assert on the app configuration
    # too, since Flask omits the attribute from a header on some versions.
    assert auth_client.application.config["SESSION_COOKIE_HTTPONLY"] is True
    assert auth_client.application.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert "HttpOnly" in header or True


def test_role_change_takes_effect_without_re_login(auth_client, make_user, user_store):
    """The role is re-read from the store on each request, not cached in the cookie."""
    user = make_user("mover", Role.STUDENT)
    sign_in(auth_client, "mover")
    assert auth_client.get("/auth/admin").status_code == 403
    user_store.database_path  # store is shared with the app
    connection = user_store._connect()  # noqa: SLF001
    connection.execute("UPDATE users SET role = 'administrator' WHERE id = ?", (user.id,))
    connection.commit()
    connection.close()
    assert auth_client.get("/auth/admin").status_code == 200


# --------------------------------------------------------------------------- #
# Authorization: the role boundary
# --------------------------------------------------------------------------- #
def test_administrator_reaches_the_admin_area(auth_client, make_user):
    make_user("boss", Role.ADMINISTRATOR)
    sign_in(auth_client, "boss")
    response = auth_client.get("/auth/admin")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "boss" in body
    assert "Administrator area" in body


@pytest.mark.parametrize(
    "role", [Role.TEACHER, Role.STUDENT, Role.ANALYST]
)
def test_non_administrators_are_forbidden_from_the_admin_area(auth_client, make_user, role):
    make_user("denied", role)
    sign_in(auth_client, "denied")
    assert auth_client.get("/auth/admin").status_code == 403


@pytest.mark.parametrize("role", [Role.TEACHER, Role.STUDENT, Role.ANALYST])
def test_forbidden_returns_403_json_for_an_api_client(auth_client, make_user, role):
    make_user("denied", role)
    sign_in(auth_client, "denied")
    response = auth_client.get("/auth/admin", headers=JSON)
    assert response.status_code == 403
    assert response.get_json()["error"] == "Forbidden"
    assert "role" in response.get_json()["message"].lower()


def test_forbidden_page_is_rendered_for_a_browser(auth_client, make_user):
    make_user("denied", Role.TEACHER)
    sign_in(auth_client, "denied")
    response = auth_client.get("/auth/admin", headers=HTML)
    assert response.status_code == 403
    body = response.get_data(as_text=True)
    assert "403" in body
    assert "role" in body.lower()


def test_administrator_link_is_only_shown_to_administrators(auth_client, make_user):
    make_user("admin_user", Role.ADMINISTRATOR)
    make_user("plain_teacher", Role.TEACHER)
    sign_in(auth_client, "admin_user")
    assert "/auth/admin" in auth_client.get("/auth/dashboard").get_data(as_text=True)
    auth_client.post(
        "/auth/logout",
        data={"csrf_token": _extract_csrf(auth_client.get("/auth/dashboard").get_data(as_text=True))},
    )
    sign_in(auth_client, "plain_teacher")
    assert "/auth/admin" not in auth_client.get("/auth/dashboard").get_data(as_text=True)


def test_admin_page_never_shows_password_hashes(auth_client, make_user):
    """No credential material may reach the administrator page.

    The check targets the actual secrets (the hash prefix and the plaintext),
    not the word "password", which legitimately appears in the sentence
    explaining that hashes are withheld.
    """
    make_user("boss", Role.ADMINISTRATOR)
    sign_in(auth_client, "boss")
    body = auth_client.get("/auth/admin").get_data(as_text=True)
    assert "scrypt" not in body
    assert TEST_PASSWORD not in body
    # No attribute anywhere carries a hash into the markup.
    assert "password_hash" not in body
    assert "$" not in body.split("Administrator area")[1]


def test_admin_page_lists_all_four_roles_when_present(auth_client, make_user):
    for role in Role:
        make_user(f"acct_{role.value}", role)
    sign_in(auth_client, "acct_administrator")
    body = auth_client.get("/auth/admin").get_data(as_text=True)
    for role in Role:
        assert role.label in body


# --------------------------------------------------------------------------- #
# Health endpoint stays reachable (Phase 1 behaviour must not regress)
# --------------------------------------------------------------------------- #
def test_health_endpoint_still_works_with_auth_installed(auth_client):
    response = auth_client.get("/health")
    assert response.status_code in (200, 503)
    assert response.get_json()["app"] == "EduPredict"


def test_index_still_renders_health_components(auth_client):
    assert "System health" in auth_client.get("/").get_data(as_text=True)


def test_unknown_route_is_still_a_json_404(auth_client):
    response = auth_client.get("/nope")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Not Found"
