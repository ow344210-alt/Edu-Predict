"""Web layer package.

``web`` is the only part of EduPredict that imports Flask; the domain packages
below it stay framework-free (docs/ARCHITECTURE.md, section 2).
"""

from .auth_routes import auth_bp
from .routes import web_bp

__all__ = ["web_bp", "auth_bp"]
