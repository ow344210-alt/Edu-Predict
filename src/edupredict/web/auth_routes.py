"""Authentication and authorization routes.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx):

    "Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts.
     Define access controls to restrict data access based on user roles and
     responsibilities."

This is the minimum surface the requirement needs:

* ``GET  /login``  - sign-in form
* ``POST /login``  - credential check (CSRF protected)
* ``POST /logout`` - end the session (CSRF protected)
* ``GET  /dashboard``  - authenticated landing page, role aware
* ``GET  /admin``      - Administrator-only page proving the role boundary

No dashboard, analytics or prediction content is invented here; the pages state
which modules arrive in later phases.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth import PERMISSION_SCOPE_NOTE, Role
from ..auth.permissions import permissions_for
from ..logging_setup import get_logger
from .auth_guards import (
    current_user,
    get_auth_service,
    get_user_store,
    login_required,
    login_user,
    logout_user,
    roles_required,
    safe_next_target,
    verify_csrf,
)

__all__ = ["auth_bp"]

logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

#: One message for every failed sign-in, so the form never reveals whether a
#: username exists.
_INVALID_CREDENTIALS = "Incorrect username or password."

#: What each documented role is described as, straight from the requirement that
#: roles differ by "role and responsibilities". No capability is asserted.
_ROLE_PURPOSE: dict[Role, str] = {
    Role.ADMINISTRATOR: "Administers the system and its accounts.",
    Role.TEACHER: "Views the teaching side of the platform.",
    Role.STUDENT: "Views their own side of the platform.",
    Role.ANALYST: "Works with the analytical outputs of the platform.",
}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign in.

    GET renders the form; POST verifies the credentials. The password is never
    logged and never echoed back into the form.
    """
    if current_user() is not None:
        return redirect(url_for("auth.dashboard"))

    service = get_auth_service()
    username = ""
    locked = False

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        csrf_ok = verify_csrf()
        # Remote address only - never the submitted password.
        logger.info(
            "Login attempt for %r from %s", username or "<empty>", request.remote_addr
        )

        if not csrf_ok:
            logger.warning("Login rejected: CSRF token missing or invalid")
            flash("Your session expired. Please try again.", "error")
        elif service.is_locked(username):
            locked = True
            logger.warning("Login rejected: account %r is temporarily locked", username)
            flash(
                "Too many failed attempts. Please wait before trying again.", "error"
            )
        else:
            result = service.authenticate(username, password)
            if result.ok and result.user is not None:
                login_user(result.user)
                target = safe_next_target(
                    request.args.get("next") or request.form.get("next"),
                    url_for("auth.dashboard"),
                )
                return redirect(target)
            service.record_failure(username, password)
            logger.info("Login failed for user %r", username or "<empty>")
            flash(_INVALID_CREDENTIALS, "error")
            if service.is_locked(username):
                locked = True

    return render_template(
        "login.html",
        app_name=current_app.config["EDUPREDICT_SETTINGS"].app.name,
        username=username,
        locked=locked,
        next_target=safe_next_target(
            request.args.get("next") or request.form.get("next"),
            url_for("auth.dashboard"),
        ),
    )


@auth_bp.post("/logout")
def logout():
    """End the authenticated session.

    POST-only: a state change reachable by a plain ``GET`` would let a third
    party sign a user out with an image tag.
    """
    if not verify_csrf():
        logger.warning("Logout rejected: CSRF token missing or invalid")
        flash("Your session expired. Please try again.", "error")
        return redirect(url_for("auth.dashboard"))
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("web.index"))


@auth_bp.get("/dashboard")
@login_required
def dashboard():
    """Authenticated landing page.

    Shows who is signed in and what their role is. It contains no statistics,
    predictions or dataset information - those belong to later phases.
    """
    user = current_user()
    assert user is not None  # guaranteed by @login_required
    return render_template(
        "dashboard.html",
        app_name=current_app.config["EDUPREDICT_SETTINGS"].app.name,
        user=user,
        purpose=_ROLE_PURPOSE.get(user.role, ""),
        held_permissions=sorted(permissions_for(user.role)),
        permission_note=PERMISSION_SCOPE_NOTE,
    )


@auth_bp.get("/admin")
@roles_required(Role.ADMINISTRATOR)
def admin():
    """Administrator-only page.

    Exists to demonstrate and test that the role boundary is actually enforced:
    a Teacher, Student or Analyst who requests this URL receives ``403``.

    It lists accounts because an administrator must be able to see who exists,
    and deliberately shows no credential material.
    """
    accounts = get_user_store().list_all()
    logger.info("Administrator account list requested by %r", current_user().username)  # type: ignore[union-attr]
    return render_template(
        "admin.html",
        app_name=current_app.config["EDUPREDICT_SETTINGS"].app.name,
        accounts=[account.public() for account in accounts],
        roles=Role,
        permission_note=PERMISSION_SCOPE_NOTE,
    )