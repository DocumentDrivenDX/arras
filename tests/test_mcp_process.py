# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The MCP process is disposable (twelve-factor): a termination signal ends it cleanly."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys


def test_sigterm_ends_the_process_cleanly() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "arras.mcp"],
        env={"ARRAS_DEV_SANDBOX": "1", "PATH": os.environ.get("PATH", "")},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        proc.stdin.write(json.dumps(init) + "\n")
        proc.stdin.flush()
        reply = json.loads(proc.stdout.readline())  # the frame is answered before the signal
        assert reply["id"] == 1 and "result" in reply
        proc.send_signal(signal.SIGTERM)  # stdin stays open: the loop is blocked reading
        assert proc.wait(timeout=10) == 0
        assert proc.stdout.read() == ""  # nothing but frames ever reaches stdout
        assert proc.stderr is not None and "arras.mcp: env=none" in proc.stderr.read()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_module_help_exits_before_reading_invalid_environment() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "arras.mcp", "--help"],
        env={"ARRAS_MISSPELLED": "secret", "PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0 and "usage:" in proc.stdout
    assert "MISSPELLED" not in proc.stderr and "secret" not in proc.stdout


def test_module_rejects_non_help_arguments_before_configuration() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "arras.mcp", "--token", "secret"],
        env={"ARRAS_MISSPELLED": "other-secret", "PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2 and "only --help is supported" in proc.stderr
    assert "secret" not in proc.stderr and "other-secret" not in proc.stderr


def test_process_telemetry_factory_runs_after_config_and_before_sandbox_effects(
    monkeypatch,
) -> None:
    from arras import telemetry
    from arras.distribution import DistributionConfig, TelemetryNames
    from arras.mcp import process
    from arras.mcp.config import Config

    order: list[str] = []
    selected = DistributionConfig(telemetry=TelemetryNames(log_prefix="tenant"))
    config = Config(dev_sandbox=True, distribution=selected)
    monkeypatch.setattr(process.Config, "from_env", lambda **_: order.append("config") or config)

    class FakeSandbox:
        def __init__(self) -> None:
            order.append("sandbox")
            self.arras = object()

        def seed(self):
            order.append("seed")
            return self

        def principal(self, _name: str):
            return None

    monkeypatch.setattr("arras.sandbox.Sandbox", FakeSandbox)

    class FakeServer:
        def __init__(self, *_args, telemetry_context=None, **_kwargs) -> None:
            assert telemetry_context is context
            order.append("server")

    monkeypatch.setattr(process, "McpServer", FakeServer)
    context = telemetry.TelemetryContext(selected.telemetry)

    def factory(names: TelemetryNames) -> telemetry.TelemetryContext:
        assert names == selected.telemetry
        order.append("factory")
        return context

    def serve(_frames, _out, _server) -> None:
        assert telemetry._active.get() is context
        order.append("serve")

    monkeypatch.setattr(process, "serve", serve)
    import sys

    stdout = sys.stdout
    try:
        process._run(selected, factory)
    finally:
        sys.stdout = stdout
    assert order == ["config", "factory", "sandbox", "seed", "server", "serve"]


def test_help_and_invalid_mcp_arguments_skip_telemetry_factory() -> None:
    from arras.mcp.process import main

    called: list[bool] = []

    def factory(*_args):
        called.append(True)
        raise AssertionError("factory must not run")

    try:
        main(["--help"], telemetry_factory=factory)
    except SystemExit as exc:
        assert exc.code == 0
    try:
        main(["--token", "sentinel"], telemetry_factory=factory)
    except SystemExit as exc:
        assert exc.code == 2
    assert called == []


def test_missing_matching_service_provider_refuses_before_sandbox_construction(monkeypatch) -> None:
    from arras.distribution import DistributionConfig, TelemetryNames
    from arras.mcp import process
    from arras.mcp.config import Config

    selected = DistributionConfig(telemetry=TelemetryNames(service_name="tenant-service"))
    monkeypatch.setattr(
        process.Config,
        "from_env",
        lambda **_: Config(dev_sandbox=True, distribution=selected),
    )
    effects: list[str] = []

    class FakeSandbox:
        def __init__(self) -> None:
            effects.append("sandbox")

    monkeypatch.setattr("arras.sandbox.Sandbox", FakeSandbox)
    try:
        process._run(selected)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("custom service requires a matching host provider")
    assert effects == []


def test_custom_distribution_prefixes_configuration_errors_with_printable_brand(
    monkeypatch, capsys
) -> None:
    from arras.branding import Brand
    from arras.distribution import DistributionConfig
    from arras.mcp import process
    from arras.mcp.config import ConfigError

    monkeypatch.setattr(
        process.Config,
        "from_env",
        lambda **_: (_ for _ in ()).throw(ConfigError(["TENANT_TOKEN: conflicting aliases"])),
    )
    selected = DistributionConfig(brand=Brand(name="  Tenant\nCatalog  "))
    try:
        process._run(selected)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("configuration error should stop startup")
    assert (
        capsys.readouterr().err
        == "Tenant Catalog: configuration: TENANT_TOKEN: conflicting aliases\n"
    )


def test_default_diagnostic_prefix_remains_legacy(monkeypatch, capsys) -> None:
    from arras.mcp import process
    from arras.mcp.config import ConfigError

    monkeypatch.setattr(
        process.Config,
        "from_env",
        lambda **_: (_ for _ in ()).throw(ConfigError(["ARRAS_TOKEN: malformed"])),
    )
    try:
        process._run(None)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("configuration error should stop startup")
    assert capsys.readouterr().err == "arras.mcp: configuration: ARRAS_TOKEN: malformed\n"


def test_custom_mcp_help_and_argument_error_use_brand_without_echoing_values(capsys) -> None:
    import pytest

    from arras.branding import Brand
    from arras.distribution import DistributionConfig
    from arras.mcp import launch

    selected = DistributionConfig(brand=Brand(name="Tenant Catalog"))
    with pytest.raises(SystemExit) as help_exit:
        launch(["--help"], distribution=selected)
    assert help_exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "usage: arras.mcp" in help_text
    assert "Tenant Catalog MCP stdio server" in help_text

    with pytest.raises(SystemExit) as arg_exit:
        launch(["--token", "sensitive-sentinel"], distribution=selected)
    assert arg_exit.value.code == 2
    error = capsys.readouterr().err
    assert error == "Tenant Catalog: only --help is supported\n"
    assert "sensitive-sentinel" not in error
