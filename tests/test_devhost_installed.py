# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev host's default UI: a source checkout's `ui/dist`, else the build the wheel carries."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from arras import devhost
from arras.devhost import DevHost, seed_demo
from arras.sandbox import Sandbox

PAGE = "<!doctype html><html><head><title>Wheel</title></head><body>wheel page</body></html>"


def wheel_static(tmp_path: Path) -> Path:
    static = tmp_path / "wheel-static"
    (static / "assets").mkdir(parents=True)
    (static / "embed.html").write_text(PAGE)
    (static / "assets" / "app.js").write_text("export {}")
    return static


def host_for(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **kw) -> DevHost:
    monkeypatch.setattr(devhost, "STATIC", wheel_static(tmp_path))
    return DevHost(seed_demo(Sandbox().seed()), port=0, **kw)


def test_without_a_source_build_the_default_is_the_wheels_static_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(devhost, "DEFAULT_UI", tmp_path / "no-ui" / "dist")
    host = host_for(monkeypatch, tmp_path, ui_dir=devhost.DEFAULT_UI)
    status, ctype, body = host.static("/")
    assert status == 200 and ctype.startswith("text/html")
    assert b"<title>Arras</title>" in body and b"not built" not in body
    assert host.static("/assets/app.js")[0] == 200
    assert host.static("/browse/catalog")[0] == 200  # a route of the app gets the page
    assert host.static("/assets/missing.js", fallback=False)[0] == 404


def test_a_source_build_wins_over_the_wheels_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dist = tmp_path / "ui-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Source</title>")
    monkeypatch.setattr(devhost, "DEFAULT_UI", dist)
    host = host_for(monkeypatch, tmp_path, ui_dir=dist)
    assert host.ui == dist and b"<title>Arras</title>" in host.static("/")[2]


def test_an_explicit_ui_directory_is_served_as_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(devhost, "DEFAULT_UI", tmp_path / "no-ui" / "dist")
    empty = tmp_path / "empty"
    empty.mkdir()
    host = host_for(monkeypatch, tmp_path, ui_dir=empty)
    assert host.ui == empty and b"not built" in host.static("/")[2]


def test_the_parser_defaults_to_the_default_ui() -> None:
    assert devhost._parser().parse_args([]).ui == devhost.DEFAULT_UI


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(
    shutil.which("uv") is None or not os.environ.get("ARRAS_WHEEL"),
    reason="set ARRAS_WHEEL to a wheel built after `npm run build:wheel` in ui/; CI does",
)
def test_the_installed_wheel_serves_its_own_page(tmp_path: Path) -> None:
    """Install the built wheel into a clean venv and fetch the page from the installed dev host."""
    wheel = Path(os.environ["ARRAS_WHEEL"])
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True)
    python = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), f"{wheel}[devhost]"],
        check=True,
        capture_output=True,
        timeout=600,
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV"))}
    port = _free_port()
    proc = subprocess.Popen(
        [str(python), "-m", "arras.devhost", "--port", str(port)],
        cwd=tmp_path,  # not the checkout: there is no ui/dist beside the installed package
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(base + "/", timeout=5) as response:
                    page = response.read().decode()
                break
            except (urllib.error.URLError, ConnectionError):
                assert proc.poll() is None and time.monotonic() < deadline, "dev host did not start"
                time.sleep(0.2)
        assert "not built" not in page
        assert "<title>Arras</title>" in page and 'type="module"' in page
        src = page.split('src="', 1)[1].split('"', 1)[0]
        with urllib.request.urlopen(f"{base}/{src.lstrip('./')}", timeout=5) as asset:
            assert asset.status == 200 and asset.headers["content-type"].startswith(
                "text/javascript"
            )
            # Finish the request before asking the host to shut down gracefully.
            assert asset.read()
    finally:
        proc.terminate()
        try:
            output, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
            print(output)
            raise
        print(output)
