"""Authentication and role-based authorization.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx, Functional Requirements):

    "Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts.
     Define access controls to restrict data access based on user roles and
     responsibilities."

This package is framework-free on purpose: only ``edupredict.web`` knows that
Flask exists, which keeps the documented "dependencies point downward only" rule
intact. The Flask-facing guards and routes are in:

* ``edupredict.web.auth_guards`` - ``login_required``, ``roles_required``, CSRF
* ``edupredict.web.auth_routes``  - ``/login``, ``/logout``, ``/dashboard``

IMPLEMENTATION DECISIONS: ADR-0009 (authentication), ADR-0010 (SQLite store).
"""

from .passwords import hash_password, needs_rehash, verify_password
from .permissions import (
    PERMISSION_SCOPE_NOTE,
    REGISTRY,
    Permission,
    PermissionRegistry,
    permissions_for,
)
from .roles import Role
from .service import SESSION_USER_KEY, AuthenticationService, LoginResult
from .users import User, UserStore, SqliteUserStore, build_user_store

__all__ = [
    "Role",
    "User",
    "UserStore",
    "SqliteUserStore",
    "build_user_store",
    "AuthenticationService",
    "LoginResult",
    "SESSION_USER_KEY",
    "hash_password",
    "verify_password",
    "needs_rehash",
    "Permission",
    "PermissionRegistry",
    "REGISTRY",
    "PERMISSION_SCOPE_NOTE",
    "permissions_for",
]