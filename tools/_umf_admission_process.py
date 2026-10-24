"""Bounded subprocess and temporary-environment operations for the UMF verifier."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

_E = TypeVar("_E", bound=BaseException)


def environment(base: dict[str, str], temp: Path, *, public_index: str) -> dict[str, str]:
    clean = {
        key: value
        for key, value in base.items()
        if not key.startswith(("PIP_", "UV_", "PYTHON", "LD_", "DYLD_"))
        and key not in ("VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV")
    }
    clean.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_INDEX_URL": public_index,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_CACHE_DIR": str(temp / "pip-cache"),
            "PYTHONPATH": "",
            "PYTHONNOUSERSITE": "1",
        }
    )
    return clean


def _write_private_failure(
    env: dict[str, str],
    stage: str,
    command: list[str],
    *,
    returncode: int | None,
    timed_out: bool,
    stdout: object,
    stderr: object,
    error_type: str | None,
) -> None:
    location = env.get("ARRAS_PRIVATE_DIAGNOSTICS")
    if not location:
        return
    try:
        directory = Path(location)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)

        def bounded(value: object) -> str | None:
            if value is None:
                return None
            if isinstance(value, bytes):
                text = value.decode("utf-8", errors="replace")
            else:
                text = str(value)
            return text[:1_000_000]

        record = {
            "stage": stage,
            "command": command,
            "returncode": returncode,
            "timed_out": timed_out,
            "error_type": error_type,
            "stdout": bounded(stdout),
            "stderr": bounded(stderr),
        }
        (directory / f"{stage}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        return


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    stage: str,
    error_type: Callable[..., _E],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _write_private_failure(
            env,
            stage,
            command,
            returncode=None,
            timed_out=isinstance(error, subprocess.TimeoutExpired),
            stdout=getattr(error, "stdout", None),
            stderr=getattr(error, "stderr", None),
            error_type=type(error).__name__,
        )
        raise error_type(stage, "command-unavailable-or-timeout") from error
    if result.returncode:
        _write_private_failure(
            env,
            stage,
            command,
            returncode=result.returncode,
            timed_out=False,
            stdout=result.stdout,
            stderr=result.stderr,
            error_type=None,
        )
        raise error_type(stage, f"command-exit-{result.returncode}")
    return result


def json_from(
    result: subprocess.CompletedProcess[str], stage: str, *, error_type: Callable[..., _E]
) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise error_type(stage, "probe-did-not-return-json") from error
    if not isinstance(value, dict):
        raise error_type(stage, "probe-result-not-object")
    return cast(dict[str, Any], value)


def remove_owned_temp(path: Path, *, error_type: Callable[..., _E]) -> None:
    try:
        shutil.rmtree(path)
    except OSError as error:
        failure = error_type("cleanup", "owned-temp-cleanup-failed")
        details = getattr(failure, "details", None)
        if isinstance(details, dict):
            details["private_workspace"] = str(path)
        raise failure from error
    if path.exists():
        failure = error_type("cleanup", "owned-temp-cleanup-failed")
        details = getattr(failure, "details", None)
        if isinstance(details, dict):
            details["private_workspace"] = str(path)
        raise failure


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def python_identity(
    python: Path,
    cwd: Path,
    env: dict[str, str],
    *,
    error_type: Callable[..., _E],
    run_timeout: int,
) -> dict[str, Any]:
    script = "import json,platform,sys; print(json.dumps({'version':sys.version.split()[0],'implementation':platform.python_implementation(),'platform':sys.platform,'machine':platform.machine()}))"
    result = run(
        [str(python), "-I", "-c", script],
        cwd=cwd,
        env=env,
        stage="python-version",
        error_type=error_type,
        timeout=run_timeout,
    )
    return json_from(result, "python-version", error_type=error_type)


def fixture_paths(repository: Path) -> tuple[Path, Path]:
    return (
        repository / "tests/fixtures/umf-core-reference/current-conformance.json",
        repository / "tests/fixtures/umf-core-metadata/primary-string-record.json",
    )


def source_hashes(driver: Path, probe: Path, selector: Path) -> tuple[str, str, str]:
    driver_hash, probe_hash, selector_hash = (
        hashlib.sha256(path.read_bytes()).hexdigest() for path in (driver, probe, selector)
    )
    return driver_hash, probe_hash, selector_hash
