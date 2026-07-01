"""PSI command line entrypoint."""

from __future__ import annotations

import argparse
import ipaddress
import json
from typing import Any

from . import __version__
from .launch import LaunchError, load_launch_app

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

    inspect_cmd = subcommands.add_parser(
        "inspect",
        help="Resolve what psi launch would serve",
    )
    inspect_cmd.add_argument("target", help="Package path, psi.toml path, or module:attribute")
    inspect_cmd.add_argument("--resource", help="Inspect a specific resource")
    inspect_cmd.add_argument("--store", help="SSSN store root for channel packages")
    inspect_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "inspect":
        app = _load_or_error(parser, args.target, resource=args.resource, store=args.store)
        payload = {
            "label": app.label,
            "kind": app.kind,
            "port": app.port,
            "routes": _route_paths(app.app),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"{payload['label']} ({payload['kind']})")
            print(f"port: {payload['port']}")
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
        app = _load_or_error(parser, args.target, resource=args.resource, store=args.store)
        import uvicorn

        uvicorn.run(app.app, host=host, port=port or app.port, log_level=log_level)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


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
