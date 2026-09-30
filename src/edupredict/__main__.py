"""EduPredict command line entry point.

Usage::

    python -m edupredict serve                 # start the web application
    python -m edupredict check                 # print the health report and exit
    python -m edupredict version               # print the version
    python -m edupredict user create <name> --role <role>
    python -m edupredict user list

``user create`` prompts for the password without echoing it, so no credential is
ever passed on the command line, stored in a shell history or committed.

After installation the same commands are available as ``edupredict <cmd>``.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import APP_NAME, __version__
from .auth import Role
from .config import load_settings
from .errors import EduPredictError
from .logging_setup import setup_logging

EXIT_OK = 0
EXIT_FAILURE = 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edupredict", description=f"{APP_NAME} control")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--config", metavar="PATH", help="path to a settings TOML file")
    parser.add_argument("--log-level", metavar="LEVEL", help="override logging level")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the web application")
    serve.add_argument("--host", help="override bind address")
    serve.add_argument("--port", type=int, help="override bind port")
    serve.add_argument("--debug", action="store_true", help="enable Flask debug mode")

    check = sub.add_parser("check", help="run configuration and component health checks")
    check.add_argument("--json", action="store_true", help="emit the report as JSON")

    sub.add_parser("version", help="print the version and exit")

    user = sub.add_parser("user", help="manage user accounts")
    user_sub = user.add_subparsers(dest="user_command")

    create = user_sub.add_parser("create", help="create an account")
    create.add_argument("username", help="login name")
    create.add_argument(
        "--role",
        required=True,
        choices=Role.choices(),
        help="documented role for the account",
    )
    # The password is read from the terminal, never from argv, so it cannot end
    # up in shell history, in a process listing or in a CI log.
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from standard input instead of prompting",
    )

    user_sub.add_parser("list", help="list accounts (never shows password hashes)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_OK

    overrides: dict[str, dict[str, object]] = {}
    if args.log_level:
        overrides["logging"] = {"level": args.log_level}
    if args.command == "serve":
        app_overrides: dict[str, object] = {}
        if args.host:
            app_overrides["host"] = args.host
        if args.port:
            app_overrides["port"] = args.port
        if args.debug:
            app_overrides["debug"] = True
        if app_overrides:
            overrides["app"] = app_overrides

    try:
        settings = load_settings(config_path=args.config, overrides=overrides or None)
    except EduPredictError as exc:
        print(f"{APP_NAME}: configuration error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    setup_logging(settings)

    if args.command == "version":
        print(f"{APP_NAME} {__version__}")
        return EXIT_OK

    if args.command == "check":
        return _run_check(settings, as_json=args.json)

    if args.command == "user":
        return _run_user_command(args, settings)

    from .app import run  # imported late so `check` never starts a server

    try:
        run(settings)
    except KeyboardInterrupt:
        print("\nShutdown requested.", file=sys.stderr)
    return EXIT_OK


def _run_user_command(args, settings) -> int:
    """Create and list accounts.

    Accounts are provisioned from the command line rather than over HTTP, so
    creating a user needs no pre-existing account and no credential is ever
    hard-coded in the repository.
    """
    from .auth import AuthenticationService, build_user_store

    if args.user_command is None:
        print("usage: edupredict user {create,list}", file=sys.stderr)
        return EXIT_FAILURE

    store = build_user_store(settings.resolve(settings.auth.database_path))
    service = AuthenticationService(store)

    if args.user_command == "list":
        accounts = store.list_all()
        if not accounts:
            print("No accounts exist yet.")
            print(
                "Create one with: "
                f"{APP_NAME.lower()} user create <username> --role <role>"
            )
            return EXIT_OK
        width = max(len(a.username) for a in accounts)
        print(f"{'ID':>4}  {'USERNAME':<{width}}  {'ROLE':<14}  CREATED")
        for account in accounts:
            print(
                f"{account.id:>4}  {account.username:<{width}}  "
                f"{account.role_label:<14}  {account.created_at}"
            )
        return EXIT_OK

    if args.user_command == "create":
        password = _read_password(args.password_stdin)
        if password is None:
            return EXIT_FAILURE
        try:
            user = service.create_user(args.username, password, Role.parse(args.role))
        except (ValueError, EduPredictError) as exc:
            # Covers an invalid username, a short password, an unknown role and
            # a duplicate account - all reported as a message, never a traceback.
            print(f"{APP_NAME}: {exc}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"Created account {user.username!r} with role {user.role_label}.")
        print(f"Stored in {store.database_path}")
        return EXIT_OK

    return EXIT_FAILURE


def _read_password(from_stdin: bool) -> str | None:
    """Obtain a password without echoing it and without putting it in argv."""
    import getpass

    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        try:
            password = getpass.getpass("Password: ")
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - interactive only
            print(file=sys.stderr)
            return None
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return None
    if not password:
        print("Password must not be empty.", file=sys.stderr)
        return None
    return password


def _run_check(settings, as_json: bool) -> int:
    from .health import Status, build_health_report

    report = build_health_report(settings)
    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"{report.app} {report.version} - {report.environment}")
        print(f"overall: {report.status.value}\n")
        for component in report.components:
            print(f"  [{component.status.value:>11}] {component.name}")
            print(f"                 {component.detail}")
    return EXIT_OK if report.status is not Status.ERROR else EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
