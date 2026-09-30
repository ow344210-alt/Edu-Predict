"""The four documented user roles.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx, Functional Requirements):

    "User Authentication and Authorization:
     Implement a secure authentication system for users with different roles,
     such as administrators, teachers, students, and analysts.
     Define access controls to restrict data access based on user roles and
     responsibilities."

IMPLEMENTATION DECISION (ADR-0009):

* Exactly four roles exist, matching the four named in the document:
  Administrator, Teacher, Student, Analyst. No additional role is created.
* A role is a plain :class:`enum.Enum` whose *value* is the stable,
  lower-case token stored in the database and compared in code. The
  human-readable *label* is presentation only and is never persisted, so
  renaming a label can never invalidate stored accounts.
* ``Role`` never imports Flask. The module is pure domain, so it can be
  reused by batch jobs and later modules that have no web context.

Detailed role permissions are not specified in the source document and will be
defined when the corresponding functional modules are implemented.
"""

from __future__ import annotations

from enum import Enum

from ..errors import UnknownRoleError

__all__ = ["Role"]


class Role(str, Enum):
    """A documented EduPredict user role.

    Inherits from :class:`str` so a role can be compared to, and serialised as,
    its own string value without an explicit ``.value`` at every call site.
    """

    ADMINISTRATOR = "administrator"
    TEACHER = "teacher"
    STUDENT = "student"
    ANALYST = "analyst"

    @property
    def label(self) -> str:
        """Human-readable name, e.g. ``"Administrator"``. Presentation only."""
        return _LABELS[self]

    @classmethod
    def parse(cls, value: object) -> "Role":
        """Convert user input or a stored value into a :class:`Role`.

        Accepts the member, its value, or its label, case-insensitively, so the
        CLI, the database and the templates all accept the same spellings.

        Raises:
            UnknownRoleError: if ``value`` does not name one of the four roles.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            candidate = value.strip().lower()
            for member in cls:
                if candidate in (member.value, member.label.lower()):
                    return member
        # Note: ``Role`` also inherits ``str``, so ``Role.values()`` would resolve
        # to ``str.values`` and fail. The list is built from iteration instead.
        valid = ", ".join(member.value for member in cls)
        raise UnknownRoleError(f"Unknown role {value!r}. Valid roles: {valid}")

    @classmethod
    def choices(cls) -> tuple[str, ...]:
        """Every valid role value, for CLI help text and form rendering."""
        return tuple(member.value for member in cls)


_LABELS: dict["Role", str] = {
    Role.ADMINISTRATOR: "Administrator",
    Role.TEACHER: "Teacher",
    Role.STUDENT: "Student",
    Role.ANALYST: "Analyst",
}