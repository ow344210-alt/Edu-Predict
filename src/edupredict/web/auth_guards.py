"""Flask-facing guards: authentication state, role checks and CSRF.

This module is the boundary between the framework-free ``edupredict.auth``
package and HTTP. Keeping it here preserves the architecture rule that only
``edupredict.web`` imports Flask (docs/ARCHITECTURE.md, section 2).

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx):

    "Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts.
     Define access controls to restrict data access based on user roles and
     responsibilities."
"""

from __future__ import annotations

import hmac
import secrets
from functools import wraps
from typing import Any, Callable, Iterable, ParamSpec, TypeVar
from urllib.parse import urlencode

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from ..auth import SESSION_USER_KEY, User
from ..errors import AuthorizationError
from ..logging_setup import get_logger
from .responses import wants_html

__all__ = [
    "current_user",
    "is_authenticated",
    "login_user",
    "logout_user",
    "login_required",
    "roles_required",
    "csrf_token",
    "verify_csrf",
    "safe_next_target",
    "return_path",
    "login_redirect",
]

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

#: Key holding the CSRF token inside the session cookie.
_CSRF_KEY = "csrf_token"

#: Cap on the size of an accepted post-login redirect target. Anything longer is
#: treated as hostile and replaced with the dashboard.
_MAX_NEXT_LENGTH = 256


def get_auth_service():
    """Return the :class:`AuthenticationService` wired onto the application."""
    return current_app.config["EDUPREDICT_AUTH_SERVICE"]


def get_user_store():
    """Return the :class:`UserStore` wired onto the application."""
    return current_app.config["EDUPREDICT_USER_STORE"]


# --------------------------------------------------------------------------- #
# Authentication state
# --------------------------------------------------------------------------- #
def current_user() -> User | None:
    """Return the signed-in :class:`User`, or ``None``.

    Only the numeric user id lives in the cookie. The record - including the
    role - is re-read from the store on every request, so a role change applies
    immediately and no password material is ever client-side.
    """
    if "user" in g:
        return g.user
    g.user = None
    user_id = session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    try:
        user = get_user_store().get_by_id(int(user_id))
    except (TypeError, ValueError):
        # A tampered or stale cookie: treat as signed out rather than crashing.
        session.clear()
        return None
    if user is None:
        session.clear()
        return None
    g.user = user
    return user


def is_authenticated() -> bool:
    return current_user() is not None


def login_user(user: User) -> None:
    """Start an authenticated session for ``user``."""
    session.clear()
    session[SESSION_USER_KEY] = user.id
    session.permanent = True
    # Rotating the session identifier on login is the standard mitigation for
    # session fixation.
    session[_CSRF_KEY] = secrets.token_urlsafe(32)
    g.user = user
    logger.info("Login succeeded for user %r (role=%s)", user.username, user.role.value)


def logout_user() -> None:
    """End the session, discarding all session state."""
    user = current_user()
    if user is not None:
        logger.info("Logout for user %r (role=%s)", user.username, user.role.value)
    session.clear()
    g.pop("user", None)


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def login_required(view: Callable[P, R]) -> Callable[P, R]:
    """Reject anonymous callers.

    A browser is redirected to the login form with a ``next`` hint; a machine
    client receives ``401``. The distinction keeps ``curl`` usable against the
    API without making a human click through a JSON error.
    """

    @wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if not is_authenticated():
            if wants_html():
                return login_redirect()  # type: ignore[return-value]
            abort(401, description="Authentication required.")
        return view(*args, **kwargs)

    return wrapper


def roles_required(*roles, message: str | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Restrict a view to the given roles.

    Requires authentication as well, so it is safe to apply to a route without
    also stacking :func:`login_required`.

    Args:
        *roles: the roles permitted to call the view. A user's role must be one
            of these; every other authenticated user gets ``403``.
        message: optional explanation shown to the denied user.

    Raises:
        AuthorizationError: when called without any role, which would silently
            deny everyone - a configuration mistake worth failing loudly.
    """
    if not roles:
        raise AuthorizationError("roles_required() needs at least one role.")
    allowed = frozenset(roles)
    text = message or "Your role does not have access to this page."

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @wraps(view)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            user = current_user()
            if user is None:
                if wants_html():
                    return login_redirect()  # type: ignore[return-value]
                abort(401, description="Authentication required.")
            if user.role not in allowed:
                logger.info(
                    "Access denied: user %r (role=%s) lacks any of %s for %s",
                    user.username,
                    user.role.value,
                    sorted(r.value for r in allowed),
                    request.path,
                )
                if wants_html():
                    abort(403, description=text)
                abort(403, description=text)
            return view(*args, **kwargs)

        return wrapper

    return decorator


# --------------------------------------------------------------------------- #
# CSRF protection
# --------------------------------------------------------------------------- #
def csrf_token() -> str:
    """Return the session's CSRF token, creating one if needed."""
    token = session.get(_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_KEY] = token
    return token


def verify_csrf() -> bool:
    """Check the submitted form token against the session token.

    Compared with :func:`hmac.compare_digest` so a mismatch cannot be found by
    timing the response. Returns ``True`` when protection is switched off, which
    keeps the guards simple for tests that do not exercise CSRF.
    """
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return True
    expected = session.get(_CSRF_KEY)
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not submitted:
        return False
    return hmac.compare_digest(str(expected), str(submitted))


def login_redirect() -> Any:
    """Redirect an anonymous caller to the login form, remembering the target.

    The ``next`` value is encoded explicitly rather than left to
    ``url_for``, which would escape the ``?`` of a query string and lose it.
    """
    query = urlencode({"next": return_path()})
    return redirect(f"{url_for('auth.login')}?{query}")


def return_path() -> str:
    """The current request's path, with query string, for a ``next`` hint.

    ``request.full_path`` appends a bare ``?`` even when there is no query
    string, which would produce a URL like ``/dashboard?``.
    """
    path = request.path
    if request.query_string:
        path = f"{path}?{request.query_string.decode('latin-1')}"
    return path


def safe_next_target(raw: str | None, fallback: str = "/") -> str:
    """Return a same-site redirect target.

    Guards against open-redirect abuse: only a path beginning with a single
    ``/`` and not ``//`` is accepted, so ``https://evil.example`` cannot be used
    to bounce a user off the site after login.
    """
    if not raw:
        return fallback
    candidate = str(raw).strip()
    if len(candidate) > _MAX_NEXT_LENGTH:
        return fallback
    if not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    # Control characters would allow header splitting in the Location header.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return fallback
    return candidate


def flash_errors(messages: Iterable[str]) -> None:
    """Queue messages for the next render without leaking internals."""
    for message in messages:
        flash(message)