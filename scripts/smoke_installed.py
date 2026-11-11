# SPDX-License-Identifier: MIT OR Apache-2.0
"""Smoke-test an installed Arras: version, doctor, and the dev host serving the console.

Run it with the interpreter of a fresh virtualenv that has the wheel installed, outside the
checkout, for example:

    /tmp/v/bin/python -I scripts/smoke_installed.py --version 0.8.2 --examples examples/catalog

It is also the quickstart of the README: `arras --version`, `arras doctor`, `arras devhost`.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _arras() -> str:
    exe = Path(sys.executable).parent / ("arras.exe" if sys.platform == "win32" else "arras")
    if not exe.exists():
        raise SystemExit(f"no arras launcher next to {sys.executable}")
    return str(exe)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read()


def _check_devhost(arras: str, examples: Path | None) -> None:
    port = _free_port()
    command = [arras, "devhost", "--port", str(port)]
    if examples is not None:
        command += [
            "--module",
            str(examples / "catalog.umf.json"),
            "--seed",
            str(examples / "seed.json"),
        ]
    host = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                status, _ = _get(f"{base}/api/people")
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if host.poll() is not None or time.monotonic() > deadline:
                    output = host.stdout.read() if host.stdout else ""
                    raise SystemExit(f"devhost did not come up:\n{output}") from None
                time.sleep(0.5)
        if status != 200:
            raise SystemExit(f"/api/people answered {status}")
        status, body = _get(f"{base}/")
        if status != 200 or b"<html" not in body.lower():
            raise SystemExit(f"/ did not serve the console (status {status})")
        print("devhost ok: / and /api/people answer 200")
    finally:
        host.terminate()
        try:
            host.wait(timeout=10)
        except subprocess.TimeoutExpired:
            host.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="the version the wheel must report")
    parser.add_argument("--examples", type=Path, help="examples/catalog directory to serve")
    args = parser.parse_args()
    arras = _arras()

    out = subprocess.run([arras, "--version"], capture_output=True, text=True, check=True)
    if out.stdout.strip() != f"arras {args.version}":
        raise SystemExit(f"arras --version printed {out.stdout.strip()!r}, wanted {args.version}")
    print("version ok:", out.stdout.strip())

    doctor = subprocess.run([arras, "doctor"], capture_output=True, text=True)
    report = json.loads(doctor.stdout)
    if doctor.returncode != 0 or report.get("ok") is not True:
        raise SystemExit(f"arras doctor failed:\n{doctor.stdout}\n{doctor.stderr}")
    print("doctor ok")

    _check_devhost(arras, args.examples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
