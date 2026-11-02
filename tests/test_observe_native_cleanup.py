from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup is POSIX-specific")
def test_owned_group_kills_surviving_descendant_after_leader_exits(
    tmp_path: Path,
) -> None:
    namespace: dict[str, Any] = {"__name__": "observer_test"}
    script_path = Path(__file__).parents[1] / ".github/scripts/observe_native_cleanup.py"
    source = compile(script_path.read_bytes(), str(script_path), "exec")
    exec(source, namespace)
    terminate_owned_group = namespace["_terminate_owned_group"]

    ready = tmp_path / "descendant-ready"
    child_code = (
        "import pathlib,signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); "
        "time.sleep(60)"
    )
    leader_code = (
        "import pathlib,subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL)\n"
        "deadline=time.monotonic()+5\n"
        f"while not pathlib.Path({str(ready)!r}).exists():\n"
        " if time.monotonic() >= deadline: raise SystemExit(2)\n"
        " time.sleep(0.01)\n"
    )
    leader = subprocess.Popen(
        [sys.executable, "-c", leader_code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert leader.wait(timeout=10) == 0
        assert ready.is_file()
        os.killpg(leader.pid, 0)

        assert terminate_owned_group(leader) is True
        with pytest.raises(ProcessLookupError):
            os.killpg(leader.pid, 0)
    finally:
        try:
            os.killpg(leader.pid, 9)
        except ProcessLookupError:
            pass
