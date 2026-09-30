"""Layered configuration loading for EduPredict.

Sources, from lowest to highest precedence:

1. built-in defaults (this module)
2. ``config/settings.toml`` (or the file given via ``--config``)
3. environment variables ``EDUPREDICT_<SECTION>__<KEY>``

Parsing uses :mod:`tomllib` from the Python standard library, so no extra
dependency is required.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigurationError

__all__ = [
    "AppSettings",
    "LoggingSettings",
    "AuthSettings",
    "SecuritySettings",
    "HdfsSettings",
    "ImpalaSettings",
    "StorageSettings",
    "Settings",
    "ENV_PREFIX",
    "find_project_root",
    "default_config_path",
    "load_settings",
]

ENV_PREFIX = "EDUPREDICT_"
_SECTION_SEPARATOR = "__"


# --------------------------------------------------------------------------- #
# Settings dataclasses (also act as the source of built-in defaults)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AppSettings:
    name: str = "EduPredict"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False


@dataclass(frozen=True)
class LoggingSettings:
    level: str = "INFO"
    target: str = "both"
    file: str = "logs/edupredict.log"
    max_bytes: int = 1_048_576
    backup_count: int = 5


@dataclass(frozen=True)
class AuthSettings:
    """Authentication and authorization settings (Phase 2).

    ``secret_key`` is deliberately **empty by default** and must be supplied
    through the environment (``EDUPREDICT_AUTH__SECRET_KEY``). No real key is
    ever committed to the repository. When it is missing the application falls
    back to an ephemeral random key in a development environment, so cookies are
    still signed - they simply stop working when the process restarts.
    """

    #: SQLite file holding the accounts. Resolved against the project root.
    database_path: str = "var/auth/users.db"
    #: Signs the session cookie. Empty means "generate an ephemeral dev key".
    secret_key: str = ""
    #: Minimum session lifetime in minutes.
    session_lifetime_minutes: int = 60
    #: Reject cross-site form posts that carry no CSRF token.
    csrf_protection: bool = True
    #: Failed logins tolerated for one account before it is locked out.
    max_login_failures: int = 5
    #: Window in which those failures are counted, in seconds.
    lockout_seconds: int = 300
    #: Only accept cookies over HTTPS. Off by default for local HTTP testing.
    cookie_secure: bool = False
    #: Maximum accepted request body, guarding the login form against abuse.
    max_content_length: int = 16_384


@dataclass(frozen=True)
class HdfsSettings:
    enabled: bool = True
    namenode_uri: str = "hdfs://localhost:9000"
    hadoop_home: str = ""
    cli: str = "hdfs"
    base_path: str = "/user/edupredict"
    probe_timeout_seconds: int = 15


@dataclass(frozen=True)
class ImpalaSettings:
    enabled: bool = True
    host: str = "localhost"
    port: int = 21050
    database: str = "edupredict"
    user: str = "edupredict"
    cli: str = "impala-shell"
    probe_timeout_seconds: int = 15


@dataclass(frozen=True)
class StorageSettings:
    local_root: str = "var"


@dataclass(frozen=True)
class Settings:
    app: AppSettings = field(default_factory=AppSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    auth: AuthSettings = field(default_factory=AuthSettings)
    hdfs: HdfsSettings = field(default_factory=HdfsSettings)
    impala: ImpalaSettings = field(default_factory=ImpalaSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    project_root: Path = field(default_factory=Path.cwd)
    config_file: Path | None = None

    def resolve(self, value: str) -> Path:
        """Resolve a configured relative path against the project root."""
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path


# --------------------------------------------------------------------------- #
# Loading helpers
# --------------------------------------------------------------------------- #
def find_project_root(start: Path | None = None) -> Path:
    """Walk upwards until a ``pyproject.toml`` is found; fall back to ``start``."""
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def default_config_path(project_root: Path | None = None) -> Path:
    return (project_root or find_project_root()) / "config" / "settings.toml"


def _coerce(value: Any, reference: Any) -> Any:
    """Coerce a raw string/primitive to the type of the dataclass default.

    ``bool`` is checked first because ``bool`` is a subclass of ``int``.
    """
    if isinstance(reference, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(reference, int):
        try:
            return int(str(value).strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Expected an integer, got {value!r}"
            ) from exc
    if isinstance(reference, str):
        return str(value)
    return value


def _build_section(cls: type, data: Mapping[str, Any]) -> Any:
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigurationError(
            f"Unknown option(s) in section [{cls.__name__}]: {', '.join(sorted(unknown))}"
        )
    kwargs = {name: _coerce(data[name], known[name].default) for name in data}
    return cls(**kwargs)


def _env_overrides(environ: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Collect ``EDUPREDICT_SECTION__KEY=value`` pairs into a nested dict."""
    result: dict[str, dict[str, Any]] = {}
    section_names = {f.name for f in fields(Settings)}
    for raw_key, raw_value in environ.items():
        if not raw_key.startswith(ENV_PREFIX):
            continue
        body = raw_key[len(ENV_PREFIX) :]
        if _SECTION_SEPARATOR not in body:
            raise ConfigurationError(
                f"Environment variable {raw_key!r} must use the form "
                f"{ENV_PREFIX}<SECTION>{_SECTION_SEPARATOR}<KEY>"
            )
        section, _, key = body.partition(_SECTION_SEPARATOR)
        section = section.lower()
        if section not in section_names:
            raise ConfigurationError(
                f"Environment variable {raw_key!r} refers to unknown section "
                f"[{section}]. Known sections: {', '.join(sorted(section_names))}"
            )
        result.setdefault(section, {})[key.lower()] = raw_value
    return result


def load_settings(
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> Settings:
    """Build a :class:`Settings` instance from file, environment and defaults.

    Args:
        config_path: explicit TOML file. When omitted ``config/settings.toml``
            below the project root is used if it exists.
        environ: environment mapping (defaults to ``os.environ``).
        overrides: highest-precedence mapping, used by the command line.

    Raises:
        ConfigurationError: on unreadable, malformed or unknown configuration.
    """
    project_root = find_project_root()
    path = Path(config_path) if config_path else default_config_path(project_root)

    file_data: dict[str, Any] = {}
    if path.is_file():
        try:
            with path.open("rb") as handle:
                file_data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"Invalid TOML in {path}: {exc}") from exc
        except OSError as exc:
            raise ConfigurationError(f"Cannot read config file {path}: {exc}") from exc
    elif config_path is not None:
        raise ConfigurationError(f"Config file not found: {path}")

    # Reject unknown top-level sections so a typo cannot be silently ignored.
    section_types = {
        "app": AppSettings,
        "logging": LoggingSettings,
        "auth": AuthSettings,
        "hdfs": HdfsSettings,
        "impala": ImpalaSettings,
        "storage": StorageSettings,
    }
    unknown_sections = set(file_data) - set(section_types)
    if unknown_sections:
        raise ConfigurationError(
            f"Unknown section(s) in {path}: {', '.join(sorted(unknown_sections))}. "
            f"Known sections: {', '.join(sorted(section_types))}"
        )

    # Keys absent from a layer keep the dataclass default, so the merged
    # mapping only needs to carry what the layers actually provide.
    merged: dict[str, dict[str, Any]] = {}
    # file layer
    for section, values in file_data.items():
        merged.setdefault(section, {}).update(values if isinstance(values, dict) else {})
    # environment layer
    for section, values in _env_overrides(os.environ if environ is None else environ).items():
        merged.setdefault(section, {}).update(values)
    # explicit override layer
    for section, values in (overrides or {}).items():
        merged.setdefault(section, {}).update(values)

    built = {
        name: _build_section(cls, merged.get(name, {})) for name, cls in section_types.items()
    }
    return Settings(
        **built,
        project_root=project_root,
        config_file=path if path.is_file() else None,
    )
