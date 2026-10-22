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
