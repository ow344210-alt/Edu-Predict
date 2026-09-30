"""Exception hierarchy for EduPredict.

Every error raised by the project derives from :class:`EduPredictError` so the
application can convert failures into consistent HTTP responses instead of
leaking tracebacks to the end user (NFR: Data Security / error handling).
"""

from __future__ import annotations

__all__ = [
    "EduPredictError",
    "ConfigurationError",
    "InfrastructureError",
    "HdfsUnavailableError",
    "ImpalaUnavailableError",
    "NotImplementedYetError",
    "AuthenticationError",
    "AuthorizationError",
    "AccountLockedError",
    "UnknownRoleError",
    "UserAlreadyExistsError",
]


class EduPredictError(Exception):
    """Base class for all EduPredict errors."""


class ConfigurationError(EduPredictError):
    """Raised when configuration is missing, malformed or invalid."""


class InfrastructureError(EduPredictError):
    """Base class for failures of an external infrastructure component."""


class HdfsUnavailableError(InfrastructureError):
    """Raised when HDFS cannot be reached or the Hadoop client is unusable."""


class ImpalaUnavailableError(InfrastructureError):
    """Raised when the Impala server cannot be reached."""


class NotImplementedYetError(EduPredictError):
    """Raised when a module reserved for a later phase is called too early."""


# --------------------------------------------------------------------------- #
# Authentication / authorization (Phase 2)
# --------------------------------------------------------------------------- #
class AuthenticationError(EduPredictError):
    """Raised when a credential cannot be established or verified.

    Covers malformed password hashes, invalid usernames and roles, and accounts
    that are locked out after repeated failed logins.
    """


class AuthorizationError(EduPredictError):
    """Raised when an authenticated user is not permitted to perform an action."""


class AccountLockedError(AuthenticationError):
    """Raised when an account is temporarily locked out after failed logins."""


class UnknownRoleError(AuthenticationError):
    """Raised when a role string does not match one of the four documented roles."""


class UserAlreadyExistsError(AuthenticationError):
    """Raised when creating an account whose username is already taken."""
