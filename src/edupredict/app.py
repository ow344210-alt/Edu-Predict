"""Application factory and process bootstrap for EduPredict.

``create_app`` wires configuration, logging, error handling and the web layer
together. It is the single place that knows how a running EduPredict process is
assembled, and it is safe to import without side effects.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, Mapping

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .web.responses import wants_html

from . import APP_NAME, __version__
from .auth import AuthenticationService, build_user_store
from .config import AuthSettings, Settings, load_settings
from .errors import EduPredictError
from .logging_setup import get_logger, setup_logging
from .storage import HadoopCliClient, ImpalaClient
from .web import auth_bp, web_bp
from .web.auth_guards import csrf_token

__all__ = ["create_app", "run", "configure_secret_key"]

logger = get_logger(__name__)

#: Environments where an ephemeral signing key is acceptable. Anywhere else a
#: missing key is a configuration error, because sessions would silently stop
#: working across restarts.
_EPHEMERAL_KEY_ENVIRONMENTS = frozenset({"development", "testing", "local"})


def configure_secret_key(app: Flask, settings: Settings) -> None:
    """Install the session signing key and harden the session cookie.

    The key is read from ``[auth] secret_key`` and is expected to arrive through
    the environment (``EDUPREDICT_AUTH__SECRET_KEY``) rather than the committed
    settings file. When it is absent a random key is generated for development
    so cookies are still signed, and a warning is logged.
    """
    auth: AuthSettings = settings.auth
    secret_key = auth.secret_key.strip()

    if secret_key:
        if len(secret_key) < 32:
            raise EduPredictError(
                "[auth] secret_key is too short to be safe. Use at least 32 "
                "characters, e.g. python -c \"import secrets; "
                "print(secrets.token_hex(32))\"."
            )
        app.config["SECRET_KEY"] = secret_key
    else:
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        if settings.app.environment.lower() in _EPHEMERAL_KEY_ENVIRONMENTS:
            logger.warning(
                "No [auth] secret_key configured - using an ephemeral random key. "
                "Sessions will be invalidated when the process restarts. Set "
                "EDUPREDICT_AUTH__SECRET_KEY before deploying."
            )
        else:
            raise EduPredictError(
                f"[auth] secret_key must be set when app.environment is "
                f"{settings.app.environment!r}. Set the environment variable "
                "EDUPREDICT_AUTH__SECRET_KEY."
            )

    # Session hardening. HttpOnly blocks JavaScript access to the cookie;
    # SameSite=Lax blocks the cookie on cross-site POSTs (CSRF); Secure is
    # enabled through configuration for any HTTPS deployment.
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=auth.cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=auth.session_lifetime_minutes),
        MAX_CONTENT_LENGTH=auth.max_content_length,
        WTF_CSRF_ENABLED=auth.csrf_protection,
    )


def create_app(
    settings: Settings | None = None,
    config_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> Flask:
    """Build and configure the Flask application.

    Args:
        settings: pre-loaded settings. Loaded from disk when omitted.
        config_overrides: highest-precedence configuration, e.g. from CLI flags.
    """
    settings = settings or load_settings(overrides=config_overrides)
    setup_logging(settings)

    app = Flask(__name__, instance_relative_config=False, template_folder="web/templates")
    app.config["EDUPREDICT_SETTINGS"] = settings
    app.config["EDUPREDICT_HDFS_CLIENT"] = HadoopCliClient(settings)
    app.config["EDUPREDICT_IMPALA_CLIENT"] = ImpalaClient(settings)
    app.config["JSON_SORT_KEYS"] = False

    # Authentication wiring (Phase 2). The store is created lazily-by-use and
    # the schema is created on first access, so a fresh checkout works without
    # a migration step.
    user_store = build_user_store(settings.resolve(settings.auth.database_path))
    app.config["EDUPREDICT_USER_STORE"] = user_store
    app.config["EDUPREDICT_AUTH_SERVICE"] = AuthenticationService(
        user_store,
        max_failures=settings.auth.max_login_failures,
        window_seconds=settings.auth.lockout_seconds,
    )

    configure_secret_key(app, settings)

    # Expose the CSRF helper to templates so every form can embed a token
    # without each view having to pass it through the render context.
    app.jinja_env.globals["csrf_token"] = csrf_token

    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    _register_error_handlers(app)

    logger.info(
        "%s v%s starting (environment=%s, config=%s)",
        APP_NAME,
        __version__,
        settings.app.environment,
        settings.config_file or "<defaults>",
    )
    return app


def _register_error_handlers(app: Flask) -> None:
    """Convert every error into a consistent JSON payload (no stack leakage)."""

    @app.errorhandler(EduPredictError)
    def _handle_domain_error(exc: EduPredictError):
        logger.exception("EduPredict error: %s", exc)
        return jsonify({"error": type(exc).__name__, "message": str(exc)}), 500

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc: HTTPException):
        # Browsers get a readable page; API and monitoring clients get JSON.
        # The status code is preserved in both cases, so 401/403 remain
        # machine-detectable.
        if exc.code in (401, 403) and wants_html():
            return (
                render_template(
                    "error.html",
                    app_name=APP_NAME,
                    status_code=exc.code,
                    title=exc.name,
                    message=exc.description,
                ),
                exc.code,
            )
        return jsonify({"error": exc.name, "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return (
            jsonify(
                {
                    "error": "InternalServerError",
                    "message": "An unexpected internal error occurred.",
                }
            ),
            500,
        )


def run(settings: Settings | None = None) -> None:
    """Start the development server and block until interrupted."""
    settings = settings or load_settings()
    app = create_app(settings)
    logger.info("Listening on http://%s:%s", settings.app.host, settings.app.port)
    app.run(host=settings.app.host, port=settings.app.port, debug=settings.app.debug)
