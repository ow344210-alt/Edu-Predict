"""Role-based access control.

SOURCE REQUIREMENT (docs/Big Data-EduPredict.docx, Functional Requirements):

    "Define access controls to restrict data access based on user roles and
     responsibilities."

IMPLEMENTATION DECISION (ADR-0009):

The document requires that access be restricted by role, but it does not
enumerate what each role may do. Rather than invent a permission matrix that no
requirement supports, this module provides the *mechanism* - a permission
registry plus role guards - and leaves the *content* empty:

    Detailed role permissions are not specified in the source document and will
    be defined when the corresponding functional modules are implemented.

Each phase that implements a documented functional module (analytics, ML,
visualization, ...) is expected to define its own permission names here. Until
then, the only enforced access control is role membership itself, which *is*
documented.

No Flask import: the web-layer decorators live in ``edupredict.web.auth_guards``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import AuthorizationError
from .roles import Role

__all__ = [
    "Permission",
    "PermissionRegistry",
    "REGISTRY",
    "PERMISSION_SCOPE_NOTE",
    "all_permissions",
    "permissions_for",
]


PERMISSION_SCOPE_NOTE = (
    "Detailed role permissions are not specified in the source document and will "
    "be defined when the corresponding functional modules are implemented."
)


@dataclass(frozen=True, slots=True)
class Permission:
    """A named capability and the roles allowed to use it."""

    name: str
    description: str
    #: Roles permitted to exercise the permission. Empty means "not yet
    #: defined" - it deliberately does NOT mean "nobody", so an undefined
    #: permission cannot accidentally deny every user.
    roles: frozenset[Role] = field(default_factory=frozenset)

    def allows(self, role: Role) -> bool:
        return role in self.roles


class PermissionRegistry:
    """Registry of permissions and the roles that hold them."""

    def __init__(self) -> None:
        self._permissions: dict[str, Permission] = {}

    def define(self, name: str, description: str, roles: tuple[Role, ...] = ()) -> Permission:
        """Register (or replace) a permission.

        Intended to be called by later phases as each documented module lands.
        """
        permission = Permission(name=name, description=description, roles=frozenset(roles))
        self._permissions[name] = permission
        return permission

    def get(self, name: str) -> Permission | None:
        return self._permissions.get(name)

    def clear(self) -> None:
        """Drop every permission. Used by tests to isolate the registry."""
        self._permissions.clear()

    def all(self) -> tuple[Permission, ...]:
        return tuple(self._permissions.values())

    def for_role(self, role: Role) -> frozenset[str]:
        """Names of the permissions held by ``role``."""
        return frozenset(p.name for p in self._permissions.values() if p.allows(role))

    def check(self, role: Role, name: str) -> bool:
        """Return ``True`` when ``role`` holds ``name``.

        An unknown permission raises, because silently returning ``False`` would
        hide a typo in a guard and deny access without explanation.
        """
        permission = self._permissions.get(name)
        if permission is None:
            raise AuthorizationError(f"Permission {name!r} is not defined.")
        return permission.allows(role)


#: Process-wide registry. Empty by design - see :data:`PERMISSION_SCOPE_NOTE`.
REGISTRY = PermissionRegistry()


def all_permissions() -> tuple[Permission, ...]:
    return REGISTRY.all()


def permissions_for(role: Role) -> frozenset[str]:
    return REGISTRY.for_role(role)