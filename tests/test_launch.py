from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from psicli import load_launch_app
from psicli.cli import main


def test_launch_tactic_package_as_fastapi(tmp_path: Path):
    package = _write_package(
        tmp_path,
        primary="tactics.echo",
        body="""
[tactics.echo]
entry = "demo.tactics:Echo"
""",
    )
    _write(package / "demo" / "tactics.py", _echo_tactic_source())

    resolved = load_launch_app(package)
    assert resolved.kind == "tactic"
    client = TestClient(resolved.app)
    response = client.post("/run", json={"input": {"message": "hello"}})

    assert response.status_code == 200
    assert response.json()["output"] == {"echo": {"message": "hello"}}


def test_launch_service_package_falls_back_to_declared_tactic(tmp_path: Path):
    package = _write_package(
        tmp_path,
        primary="services.api",
        body="""
[tactics.echo]
entry = "demo.tactics:Echo"

[services.api]
entry = "demo.services:create_app"
tactic = "echo"
transport = "fastapi"

[services.api.metadata]
port = 8123
""",
    )
    _write(package / "demo" / "tactics.py", _echo_tactic_source())
    _write(package / "demo" / "services.py", "def create_app():\n    return {'fixture': True}\n")

    resolved = load_launch_app(package)
    assert resolved.kind == "service"
    assert resolved.port == 8123
    client = TestClient(resolved.app)
    response = client.post("/run", json={"input": "hi"})

    assert response.status_code == 200
    assert response.json()["output"] == {"echo": "hi"}


def test_launch_channel_package_creates_store_api(tmp_path: Path):
    package = _write_package(
        tmp_path,
        kind="channel",
        primary="channels.events",
        body="""
[channels.events]
schema = "psi://demo/events/schemas/event"
form = "log"
description = "Input events."
""",
    )

    resolved = load_launch_app(package, store=tmp_path / "store")
    assert resolved.kind == "channel"
    client = TestClient(resolved.app)
    response = client.get("/channels")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "events"


def test_launch_service_payload_as_fastapi_run_endpoint(tmp_path: Path):
    package = _write_package(
        tmp_path,
        kind="app",
        primary="services.api",
        body="""
[services.api]
entry = "demo.services:create_app"
transport = "fastapi"
""",
    )
    _write(package / "demo" / "services.py", "def create_app():\n    return {'service': 'demo'}\n")

    resolved = load_launch_app(package)
    client = TestClient(resolved.app)
    response = client.post("/run", json={"input": {"task": "ping"}})

    assert response.status_code == 200
    assert response.json()["output"] == {"service": "demo"}
    assert response.json()["input"] == {"task": "ping"}


def test_launch_direct_fastapi_entrypoint(tmp_path: Path, monkeypatch):
    module = tmp_path / "direct.py"
    module.write_text(
        """
from fastapi import FastAPI


def create_app():
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    resolved = load_launch_app("direct:create_app")
    client = TestClient(resolved.app)

    assert client.get("/health").json() == {"ok": True}


def test_inspect_cli_reports_launch_surface(tmp_path: Path, capsys):
    package = _write_package(
        tmp_path,
        primary="tactics.echo",
        body="""
[tactics.echo]
entry = "demo.tactics:Echo"
""",
    )
    _write(package / "demo" / "tactics.py", _echo_tactic_source())

    assert main(["inspect", str(package)]) == 0
    out = capsys.readouterr().out

    assert "demo/launch-demo:tactics.echo" in out
    assert "POST /run" in out


def _write_package(
    tmp_path: Path,
    *,
    body: str,
    primary: str,
    kind: str = "tactic",
) -> Path:
    package = tmp_path / "launch-demo"
    package.mkdir()
    module = package / "demo"
    module.mkdir()
    _write(module / "__init__.py", "")
    _write(
        package / "psi.toml",
        f"""
[package]
psi_version = "0.1"
org = "demo"
name = "launch-demo"
version = "0.1.0"
kind = "{kind}"
primary = "{primary}"
description = "Launch fixture."
{body}
""".lstrip(),
    )
    return package


def _write(path: Path, text: str) -> None:
    path.write_text(text.lstrip(), encoding="utf-8")


def _echo_tactic_source() -> str:
    return """
class Echo:
    def run(self, input_value, *, context=None):
        return {"echo": input_value}
"""
