"""Password hashing.

IMPLEMENTATION DECISION (ADR-0009):

Passwords are hashed with :func:`werkzeug.security.generate_password_hash`.
Werkzeug already ships as a Flask dependency, so this adds **no new third-party
package** to the project while still using a modern, salted, memory-hard key
derivation function.

Werkzeug 3.x defaults to ``scrypt`` (``scrypt:32768:8:1``), a memory-hard KDF
that is far more resistant to GPU/ASIC cracking than PBKDF2. The method is
stored inside the hash string itself, so parameters can be raised later and old
hashes keep verifying - :func:`needs_rehash` detects those.

This module never imports Flask and never logs a password.
"""

from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

__all__ = [
    "hash_password",
    "verify_password",
    "needs_rehash",
    "MIN_PASSWORD_LENGTH",
    "DUMMY_HASH_SOURCE",
]

#: Shortest password accepted when an account is created. Deliberately modest -
#: this is a student eProject, not a production identity provider.
MIN_PASSWORD_LENGTH = 8

#: A fixed, non-secret string hashed once at import time. Verifying a submitted
#: password against it keeps the response time of "unknown user" and "wrong
#: password" roughly equal, so the login form cannot be used to enumerate valid
#: usernames by timing. The value is never a real password.
DUMMY_HASH_SOURCE = "edupredict-timing-equaliser"


def hash_password(plaintext: str) -> str:
    """Return a salted hash of ``plaintext`` suitable for storage.

    The returned string embeds the algorithm and its parameters, so no
    configuration of the hashing scheme needs to be stored alongside it.
    """
    return generate_password_hash(plaintext)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    """Return ``True`` when ``plaintext`` produced ``stored_hash``.

    Never raises: a missing or corrupt hash is treated as a failed verification
    so that a damaged account row cannot crash the login endpoint.
    """
    if not isinstance(stored_hash, str) or not stored_hash:
        return False
    if not isinstance(plaintext, str) or not plaintext:
        return False
    try:
        return check_password_hash(stored_hash, plaintext)
    except Exception:
        # Any damage in a stored row (wrong type, missing "$", truncated
        # scrypt parameters) must read as "wrong password", never as a crash.
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Return ``True`` when ``stored_hash`` uses outdated hash parameters."""
    if not stored_hash:
        return True
    try:
        from werkzeug.security import _check_hash_method  # type: ignore[attr-defined]

        return _check_hash_method(stored_hash)
    except ImportError:
        # Older Werkzeug without the helper: treat a valid-looking hash as fine.
        return False
    except ValueError:
        return True