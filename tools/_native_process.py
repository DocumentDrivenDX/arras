"""Bounded process-group execution for the native qualification tool."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from pathlib import Path


class ProcessTimeout(RuntimeError):
    def __init__(self, stdout: str, stderr: str, leftovers: list[Path]) -> None:
        super().__init__("owned command timed out")
        self.stdout = stdout
        self.stderr = stderr
        self.leftovers = leftovers


def temp_parent() -> Path:
    for candidate in (Path("/private/tmp"), Path("/tmp")):
        if candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK):
            return candidate
    return Path(tempfile.gettempdir())


def owned_postmaster_files(root: Path) -> list[Path]:
    pg_root = root / "pg"
    if not pg_root.is_dir() or pg_root.is_symlink():
        return []
    return [
        path for path in pg_root.rglob("postmaster.pid") if path.is_file() and not path.is_symlink()
    ]


def run_owned(
    args: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 35 * 60
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name != "nt"),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        windows_interrupt = getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT)
        _signal_group(process, signal.SIGINT, windows_signal=windows_interrupt)
        try:
            stdout, stderr = process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            _stop_group(process)
            stdout, stderr = process.communicate(timeout=15)
        raise ProcessTimeout(stdout[-2000:], stderr[-2000:], owned_postmaster_files(cwd)) from None
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _signal_group(
    process: subprocess.Popen[str], sig: int, *, windows_signal: signal.Signals
) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(windows_signal)
    else:
        os.killpg(process.pid, sig)


def _stop_group(process: subprocess.Popen[str]) -> None:
    _signal_group(process, signal.SIGTERM, windows_signal=signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
