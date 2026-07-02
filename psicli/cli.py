"""PSI command line entrypoint."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from typing import Any

from . import __version__
from .auth import (
    CredentialError,
    conventional_requirements,
    configure_missing_api_keys,
    format_missing_requirements,
    parse_key_values,
    resolve_api_keys,
)
from .launch import LaunchError, load_launch_api_key_requirements, load_launch_app

LOG_LEVELS = {"critical", "debug", "error", "info", "trace", "warning"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="psi", description="PSI user CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    launch = subcommands.add_parser(
        "launch",
        help="Launch a PSI package or entrypoint as a FastAPI service",
    )
    launch.add_argument("target", help="Package path, psi.toml path, or module:attribute")
    launch.add_argument("--resource", help="Launch a specific resource, e.g. services.api")
    launch.add_argument("--store", help="SSSN store root for channel packages")
    launch.add_argument("--host", default="127.0.0.1")
    launch.add_argument("--port", type=int)
    launch.add_argument("--log-level", default="info")
    launch.add_argument(
        "--env-file",
        default=".env.local",
        help="Local env file to read for required API keys",
    )
    launch.add_argument(
        "--credentials",
        choices=("auto", "keyring", "env"),
        default="auto",
        help="Where interactive setup should store missing keys",
    )
    launch.add_argument(
        "--no-keyring",
        action="store_true",
        help="Do not read API keys from the OS keyring",
    )
    launch.add_argument(
        "--skip-key-check",
        action="store_true",
        help="Start without checking package-declared API key requirements",
    )

    inspect_cmd = subcommands.add_parser(
        "inspect",
        help="Resolve what psi launch would serve",
    )
    inspect_cmd.add_argument("target", help="Package path, psi.toml path, or module:attribute")
    inspect_cmd.add_argument("--resource", help="Inspect a specific resource")
    inspect_cmd.add_argument("--store", help="SSSN store root for channel packages")
    inspect_cmd.add_argument("--json", action="store_true")
    inspect_cmd.add_argument(
        "--env-file",
        default=".env.local",
        help="Local env file to read for required API keys",
    )
    inspect_cmd.add_argument(
        "--no-keyring",
        action="store_true",
        help="Do not read API keys from the OS keyring",
    )

    init = subcommands.add_parser(
        "init",
        help="Guide local credential setup for launching a PSI package",
    )
    init.add_argument(
        "target",
        nargs="?",
        help="Package path, psi.toml path, or module:attribute entrypoint",
    )
    init.add_argument("--resource", help="Set up a specific package resource")
    init.add_argument(
        "--credentials",
        choices=("auto", "keyring", "env"),
        default="auto",
        help="Store entered keys in the OS keyring or a local env file",
    )
    init.add_argument(
        "--env-file",
        default=".env.local",
        help="Local env file used when --credentials env is selected",
    )
    init.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=value",
        help="Provide a key non-interactively",
    )
    init.add_argument(
        "--show-conventions",
        action="store_true",
        help="Print common provider API key names",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        return _init_or_error(parser, args)

    if args.command == "inspect":
        requirements, resolution = _resolve_requirements_for_command(
            parser,
            args.target,
            resource=args.resource,
            env_file=args.env_file,
            use_keyring=not args.no_keyring,
        )
        app = _load_or_error(parser, args.target, resource=args.resource, store=args.store)
        payload = {
            "label": app.label,
            "kind": app.kind,
            "port": app.port,
            "routes": _route_paths(app.app),
            "api_keys": resolution.public_payload(),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"{payload['label']} ({payload['kind']})")
            print(f"port: {payload['port']}")
            if requirements:
                print("api keys:")
                for status in resolution.statuses:
                    marker = "ready" if status.ready else "missing"
                    detail = (
                        f" - {status.requirement.description}"
                        if status.requirement.description
                        else ""
                    )
                    print(f"  {status.requirement.name}: {marker}{detail}")
            for route in payload["routes"]:
                print(route)
        return 0

    if args.command == "launch":
        try:
            host = _serve_host(args.host)
            port = _serve_port(args.port) if args.port is not None else None
            log_level = _serve_log_level(args.log_level)
        except ValueError as exc:
            parser.error(str(exc))
        if not args.skip_key_check:
            _ensure_launch_keys(parser, args)
        app = _load_or_error(parser, args.target, resource=args.resource, store=args.store)
        import uvicorn

        uvicorn.run(app.app, host=host, port=port or app.port, log_level=log_level)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _init_or_error(parser: argparse.ArgumentParser, args: Any) -> int:
    try:
        provided = parse_key_values(args.set)
        if args.show_conventions:
            for requirement in conventional_requirements():
                print(f"{requirement.name}: {requirement.description}")
            if args.target is None:
                return 0
        if args.target is None:
            print("Run `psi init PACKAGE` to configure keys declared by a package.")
            print("Use `psi init --show-conventions` to list common provider names.")
            return 0
        requirements, resolution = _resolve_requirements_for_command(
            parser,
            args.target,
            resource=args.resource,
            env_file=args.env_file,
            use_keyring=True,
        )
        if not requirements:
            print("No API key requirements declared for this launch target.")
            return 0
        missing = list(resolution.missing)
        requirement_by_name = {requirement.name: requirement for requirement in requirements}
        for key in provided:
            if key not in requirement_by_name:
                print(f"warning: {key} is not declared by this package")
        provided_for_missing = {
            key: value for key, value in provided.items() if key in {requirement.name for requirement in missing}
        }
        provided_declared = {
            key: value for key, value in provided.items() if key in requirement_by_name
        }
        still_prompt = [
            requirement
            for requirement in missing
            if requirement.name not in provided_for_missing
        ]
        if not missing and not provided:
            print("All required API keys are already available.")
            return 0
        if still_prompt and not sys.stdin.isatty():
            parser.error(
                "missing required API key(s):\n"
                f"{format_missing_requirements(still_prompt)}\n\n"
                "Use --set NAME=value for non-interactive setup."
            )
        requirements_to_configure = [
            *still_prompt,
            *[
                requirement_by_name[key]
                for key in provided_declared
                if key not in {requirement.name for requirement in still_prompt}
            ],
        ]
        backend = configure_missing_api_keys(
            requirements_to_configure,
            credentials=args.credentials,
            env_file=args.env_file,
            provided=provided_declared,
        )
        print(f"Configured {len(requirements_to_configure)} API key(s) via {backend}.")
        return 0
    except (CredentialError, ImportError, LaunchError, OSError, ValueError) as exc:
        parser.error(str(exc))
        raise


def _ensure_launch_keys(parser: argparse.ArgumentParser, args: Any) -> None:
    requirements, resolution = _resolve_requirements_for_command(
        parser,
        args.target,
        resource=args.resource,
        env_file=args.env_file,
        use_keyring=not args.no_keyring,
    )
    if not requirements or resolution.ok:
        return
    if sys.stdin.isatty():
        try:
            backend = configure_missing_api_keys(
                resolution.missing,
                credentials=args.credentials,
                env_file=args.env_file,
            )
            print(f"Configured {len(resolution.missing)} API key(s) via {backend}.")
            resolution = resolve_api_keys(
                requirements,
                env_file=args.env_file,
                use_keyring=not args.no_keyring,
            )
        except CredentialError as exc:
            parser.error(str(exc))
    if not resolution.ok:
        parser.error(
            "missing required API key(s):\n"
            f"{format_missing_requirements(resolution.missing)}\n\n"
            f"Run `psi init {args.target}` or set the missing names in your environment."
        )


def _resolve_requirements_for_command(
    parser: argparse.ArgumentParser,
    target: str,
    *,
    resource: str | None,
    env_file: str,
    use_keyring: bool,
) -> tuple[Any, Any]:
    try:
        requirements = load_launch_api_key_requirements(target, resource=resource)
        resolution = resolve_api_keys(
            requirements,
            env_file=env_file,
            use_keyring=use_keyring,
        )
    except (CredentialError, ImportError, LaunchError, OSError, ValueError) as exc:
        parser.error(str(exc))
        raise
    return requirements, resolution


def _load_or_error(
    parser: argparse.ArgumentParser,
    target: str,
    *,
    resource: str | None,
    store: str | None,
) -> Any:
    try:
        return load_launch_app(target, resource=resource, store=store)
    except (ImportError, LaunchError, OSError, ValueError, AttributeError, TypeError) as exc:
        parser.error(str(exc))
        raise


def _route_paths(app: Any) -> list[str]:
    routes = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path:
            prefix = ",".join(sorted(methods or []))
            routes.append(f"{prefix} {path}" if prefix else str(path))
    return sorted(routes)


def _serve_host(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("launch host must be a non-empty string")
    host = value
    if any(ch.isspace() for ch in host) or "/" in host or "\\" in host:
        raise ValueError("launch host must be a host name or address, not a URL or path")
    if ":" in host:
        try:
            ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("launch host must be a host name or address, not host:port") from exc
    return host


def _serve_port(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not (1 <= value <= 65535)
    ):
        raise ValueError("launch port must be an integer between 1 and 65535")
    return value


def _serve_log_level(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ch.isspace() for ch in value)
    ):
        raise ValueError(_log_level_error())
    log_level = value.lower()
    if log_level not in LOG_LEVELS:
        raise ValueError(_log_level_error())
    return log_level


def _log_level_error() -> str:
    return "launch log level must be one of: critical, debug, error, info, trace, warning"
