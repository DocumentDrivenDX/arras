# SPDX-License-Identifier: MIT OR Apache-2.0
"""The `arras` command delegates to the module entry points, which stay as they are."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from arras import cli

VERSION = importlib.metadata.version("arras")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False, timeout=120
    )


def test_version_and_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out == f"arras {VERSION}\n"
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert all(name in out for name in cli.SUBCOMMANDS)
    assert cli.main([]) == 2
    assert capsys.readouterr().err.startswith("usage: arras")
    assert cli.main(["bogus"]) == 2
    assert "unknown command 'bogus'" in capsys.readouterr().err


def test_each_subcommand_runs_the_modules_own_main() -> None:
    doctor, direct_doctor = run("-m", "arras.cli", "doctor"), run("-m", "arras.doctor")
    assert doctor.returncode == direct_doctor.returncode
    assert json.loads(doctor.stdout) == json.loads(direct_doctor.stdout)
    for module, command in (("arras.devhost", "devhost"), ("arras.mcp", "mcp")):
        via_cli = run("-m", "arras.cli", command, "--help")
        direct = run("-m", module, "--help")
        assert via_cli.returncode == direct.returncode == 0
        assert via_cli.stdout == direct.stdout  # the module's own parser and prog name


def test_the_script_is_declared_and_the_launcher_seams_are_intact() -> None:
    declared = [
        e for e in importlib.metadata.entry_points(group="console_scripts") if e.name == "arras"
    ]
    assert [e.value for e in declared] == ["arras.cli:run"]
    import inspect

    from arras import devhost, mcp

    assert "distribution" in inspect.signature(devhost.main).parameters
    assert "distribution" in inspect.signature(mcp.launch).parameters


@pytest.mark.skipif(
    shutil.which("uv") is None or not os.environ.get("ARRAS_WHEEL"),
    reason="set ARRAS_WHEEL to a built wheel (uv build --wheel); CI does after building one",
)
def test_the_installed_wheel_provides_the_command(tmp_path: Path) -> None:
    """Install the built wheel into a clean venv and run `arras` from there."""
    wheel = Path(os.environ["ARRAS_WHEEL"])
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True)
    python = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
        timeout=600,
    )
    arras = venv / "bin" / "arras"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}

    def installed(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(arras), *args], capture_output=True, text=True, cwd=tmp_path, env=env, timeout=120
        )

    version = installed("--version")
    assert version.returncode == 0 and version.stdout == f"arras {VERSION}\n"
    assert installed("mcp", "--help").returncode == 0
    assert "--port" in installed("devhost", "--help").stdout
    report = json.loads(installed("doctor").stdout)
    assert "diagnostics" in report
    direct = subprocess.run(
        [str(python), "-m", "arras.doctor"], capture_output=True, text=True, cwd=tmp_path, env=env
    )
    assert json.loads(direct.stdout) == report  # the module entry point is unchanged
