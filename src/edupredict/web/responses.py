"""Content negotiation helpers shared by the HTTP layer.

The document requires a user-facing website, so most failures are best answered
with an HTML page, while API/monitoring clients want JSON. ``wants_html`` keeps
that decision in one place instead of duplicating ``Accept`` parsing in every
guard.
"""

from __future__ import annotations

from flask import request

__all__ = ["wants_html"]


def wants_html() -> bool:
    """Return ``True`` when the caller prefers an HTML response.

    A request that does not state a preference at all is treated as a browser:
    the login flow is a human-facing feature, and defaulting to HTML keeps a
    plain ``curl`` on a protected page useful instead of returning raw JSON.
    """
    accept = request.accept_mimetypes
    if not accept:
        return True
    if accept.accept_json and not accept.accept_html:
        return False
    return True