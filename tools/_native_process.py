"""Bounded process-group execution for the native qualification tool."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

_INTERRUPT_GRACE_SECONDS = 90
_TERM_GRACE_SECONDS = 10
_REAP_GRACE_SECONDS = 5
_OUTPUT_DRAIN_GRACE_SECONDS = 15


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
        try:
            interrupt_deadline = time.monotonic() + _INTERRUPT_GRACE_SECONDS
            windows_interrupt = getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT)
            _signal_group(process, signal.SIGINT, windows_signal=windows_interrupt)
            try:
                process.communicate(timeout=_INTERRUPT_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            if not _wait_group_exit(process, max(0.0, interrupt_deadline - time.monotonic())):
                _stop_group(process)
            stdout, stderr = process.communicate(timeout=_OUTPUT_DRAIN_GRACE_SECONDS)
        except BaseException:
            try:
                _cancel_and_reap_group(process)
            except BaseException:
                pass
            raise
        raise ProcessTimeout(stdout[-2000:], stderr[-2000:], owned_postmaster_files(cwd)) from None
    except BaseException:
        try:
            _cancel_and_reap_group(process)
        except BaseException:
            # Cleanup must never replace the caller's cancellation or exception.
            pass
        raise
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _signal_group(
    process: subprocess.Popen[str], sig: int, *, windows_signal: signal.Signals
) -> None:
    if os.name == "nt":
        if process.poll() is None:
            process.send_signal(windows_signal)
    else:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass


def _stop_group(process: subprocess.Popen[str]) -> None:
    _signal_group(process, signal.SIGTERM, windows_signal=signal.SIGTERM)
    if os.name != "nt":
        if not _wait_group_exit(process, _TERM_GRACE_SECONDS):
            _force_kill_group(process)
        try:
            process.wait(timeout=_REAP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        return
    try:
        process.wait(timeout=_TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _force_kill_group(process)


def _cancel_and_reap_group(process: subprocess.Popen[str]) -> None:
    """Stop the complete owned group while preserving the cancellation exception."""
    interrupt_deadline = time.monotonic() + _INTERRUPT_GRACE_SECONDS
    try:
        _signal_group(
            process,
            signal.SIGINT,
            windows_signal=getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT),
        )
        process.communicate(timeout=_INTERRUPT_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    except BaseException:
        # A second cancellation during cleanup must not replace the original one.
        pass

    try:
        group_exited = _wait_group_exit(process, max(0.0, interrupt_deadline - time.monotonic()))
    except BaseException:
        group_exited = False
    if group_exited:
        return

    try:
        _stop_group(process)
    except BaseException:
        try:
            _force_kill_group(process)
        except BaseException:
            pass
    try:
        process.communicate(timeout=_OUTPUT_DRAIN_GRACE_SECONDS)
    except BaseException:
        try:
            _force_kill_group(process)
        except BaseException:
            pass
        try:
            process.communicate(timeout=_REAP_GRACE_SECONDS)
        except BaseException:
            try:
                process.wait(timeout=_REAP_GRACE_SECONDS)
            except BaseException:
                pass


def _force_kill_group(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            process.kill()
        except ProcessLookupError:
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=_REAP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _wait_group_exit(process: subprocess.Popen[str], timeout: float) -> bool:
    if os.name == "nt":
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
    deadline = time.monotonic() + timeout
    while _group_exists(process.pid):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))
    return True


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
