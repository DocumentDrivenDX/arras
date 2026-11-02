from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def _roots() -> set[str]:
    found: set[str] = set()
    for base in (Path("/private/tmp"), Path("/tmp")):
        if base.is_dir():
            for path in base.glob("arras-native-*"):
                if path.is_dir() and not path.is_symlink():
                    found.add(str(path.resolve()))
    return found


def _ps_snapshot() -> dict[int, dict[str, Any]]:
    result = subprocess.run(
        ["ps", "-ww", "-axo", "pid=,ppid=,pgid=,command="],
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    )
    rows: dict[int, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(None, 3)
        if len(parts) != 4:
            raise RuntimeError("process snapshot contains an unparseable row")
        try:
            pid, ppid, pgid = (int(part) for part in parts[:3])
        except ValueError:
            raise RuntimeError("process snapshot contains a nonnumeric identity") from None
        if pid <= 0 or ppid < 0 or pgid < 0:
            raise RuntimeError("process snapshot contains an invalid PID, PPID, or PGID")
        command = parts[3]
        rows[pid] = {
            "ppid": ppid,
            "pgid": pgid,
            "command_sha256": hashlib.sha256(command.encode("utf-8", "replace")).hexdigest(),
            "references_root": False,
        }
        rows[pid]["_command"] = command
    observer = rows.get(os.getpid())
    if observer is None or observer["ppid"] <= 0 or observer["pgid"] <= 0:
        raise RuntimeError("process snapshot is empty or does not contain the observer")
    return rows


def _owned_processes(rows: dict[int, dict[str, Any]], seeds: set[int], roots: set[str]) -> set[int]:
    owned = set(seeds)
    for pid, row in rows.items():
        command = row.pop("_command")
        references = any(root in command for root in roots)
        row["references_root"] = references
        if references:
            owned.add(pid)
    changed = True
    while changed:
        changed = False
        for pid, row in rows.items():
            if pid not in owned and row["ppid"] in owned:
                owned.add(pid)
                changed = True
    return owned


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_group_exit(proc: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        proc.poll()
        if not _process_group_exists(proc.pid):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def _terminate_owned_group(proc: subprocess.Popen[bytes] | None) -> bool:
    if proc is None:
        return True
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        if not _process_group_exists(proc.pid):
            proc.wait()
            return True
    if _wait_for_group_exit(proc, 3):
        proc.wait()
        return True
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        if not _process_group_exists(proc.pid):
            proc.wait()
            return True
    if _wait_for_group_exit(proc, 2):
        proc.wait()
        return True
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    return not _process_group_exists(proc.pid)


def _run_and_track(
    command: list[str], before: set[str], stdout_path: Path, stderr_path: Path
) -> tuple[
    subprocess.Popen[bytes] | None,
    int | None,
    str | None,
    bool | None,
    set[str],
    dict[int, dict[str, int | str]],
]:
    tracked_roots: set[str] = set()
    known: dict[int, dict[str, int | str]] = {}
    verifier: subprocess.Popen[bytes] | None = None
    verifier_exit: int | None = None
    wrapper_error: str | None = None
    group_cleanup_complete: bool | None = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            verifier = subprocess.Popen(
                command, stdout=stdout, stderr=stderr, start_new_session=True
            )
            while verifier.poll() is None:
                tracked_roots.update(_roots() - before)
                rows = _ps_snapshot()
                owned = _owned_processes(rows, {verifier.pid, *known.keys()}, tracked_roots)
                for pid in owned:
                    row = rows.get(pid)
                    if row is not None:
                        known[pid] = {
                            "pgid": row["pgid"],
                            "command_sha256": row["command_sha256"],
                        }
                time.sleep(0.25)
            verifier_exit = verifier.wait()
    except BaseException as exc:  # noqa: BLE001 - retain cleanup evidence on interruption
        wrapper_error = type(exc).__name__
        group_cleanup_complete = _terminate_owned_group(verifier)
    return (
        verifier,
        verifier_exit,
        wrapper_error,
        group_cleanup_complete,
        tracked_roots,
        known,
    )


def _final_process_observation(
    before: set[str],
    tracked_roots: set[str],
    verifier: subprocess.Popen[bytes] | None,
    known: dict[int, dict[str, int | str]],
) -> tuple[
    list[str],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str | None,
]:
    remaining_roots: list[str] = []
    remaining_owned: list[dict[str, Any]] = []
    ambiguous_owned: list[dict[str, Any]] = []
    observation_error: str | None = None
    try:
        tracked_roots.update(_roots() - before)
        final_rows = _ps_snapshot()
        seeds = {verifier.pid, *known.keys()} if verifier else set()
        owned_now = _owned_processes(final_rows, seeds, tracked_roots)
        for pid in sorted(owned_now):
            current = final_rows.get(pid)
            prior = known.get(pid)
            if current is None:
                continue
            if prior is None or current["command_sha256"] == prior["command_sha256"]:
                remaining_owned.append(
                    {
                        "pid": pid,
                        "pgid": current["pgid"],
                        "command_sha256": current["command_sha256"],
                    }
                )
            else:
                ambiguous_owned.append(
                    {
                        "pid": pid,
                        "previous_pgid": prior["pgid"],
                        "current_pgid": current["pgid"],
                        "previous_command_sha256": prior["command_sha256"],
                        "current_command_sha256": current["command_sha256"],
                    }
                )
        after = _roots()
        tracked_roots.update(after - before)
        remaining_roots = sorted(after - before)
    except BaseException as exc:  # noqa: BLE001 - keep evidence incomplete on interruption
        observation_error = type(exc).__name__
    return remaining_roots, remaining_owned, ambiguous_owned, observation_error


def _cleanup_receipt(
    before: set[str],
    tracked_roots: set[str],
    known: dict[int, dict[str, int | str]],
    verifier: subprocess.Popen[bytes] | None,
    verifier_exit: int | None,
    wrapper_error: str | None,
    group_cleanup_complete: bool | None,
    final_observation: tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], str | None],
) -> dict[str, Any]:
    remaining_roots, remaining_owned, ambiguous_owned, observation_error = final_observation
    passed = (
        wrapper_error is None
        and observation_error is None
        and group_cleanup_complete is not False
        and not remaining_roots
        and not remaining_owned
        and not ambiguous_owned
    )
    return {
        "schema": "arras.native-independent-cleanup/3",
        "status": "passed" if passed else "incomplete",
        "verifier_pid": verifier.pid if verifier else None,
        "verifier_exit_code": verifier_exit,
        "wrapper_error_type": wrapper_error,
        "owned_process_group_cleanup_complete": group_cleanup_complete,
        "process_observation_error_type": observation_error,
        "native_temp_roots_before": sorted(before),
        "native_temp_roots_observed": sorted(tracked_roots),
        "native_temp_roots_remaining": remaining_roots,
        "known_owned_processes": [{"pid": pid, **known[pid]} for pid in sorted(known)],
        "owned_processes_remaining": remaining_owned,
        "owned_process_identity_ambiguous": ambiguous_owned,
    }


def observe(
    command: list[str], output: Path, stdout_path: Path, stderr_path: Path
) -> dict[str, Any]:
    before = _roots()
    (
        verifier,
        verifier_exit,
        wrapper_error,
        group_cleanup_complete,
        tracked_roots,
        known,
    ) = _run_and_track(command, before, stdout_path, stderr_path)
    final_observation = _final_process_observation(before, tracked_roots, verifier, known)
    receipt = _cleanup_receipt(
        before,
        tracked_roots,
        known,
        verifier,
        verifier_exit,
        wrapper_error,
        group_cleanup_complete,
        final_observation,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"verifier_exit_code": verifier_exit, "cleanup_status": receipt["status"]},
            sort_keys=True,
        )
    )
    if wrapper_error is not None:
        raise SystemExit(1)
    if verifier_exit:
        raise SystemExit(verifier_exit)
    if receipt["status"] != "passed":
        raise SystemExit(1)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("verifier command is required after --")
    observe(command, args.output_json, args.stdout, args.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
