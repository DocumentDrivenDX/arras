# SPDX-License-Identifier: MIT OR Apache-2.0
"""Executed controls for the trusted-to-public release asset comparison."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
HELPER = ROOT / ".github/scripts/verify_public_release_assets.py"
VERSION = "0.5.0"
WHEEL = f"arras-{VERSION}-py3-none-any.whl"
NPM = f"documentdrivendx-arras-ui-{VERSION}.tgz"
ASSETS = {
    WHEEL,
    f"arras-{VERSION}.tar.gz",
    NPM,
    "distribution-verification.json",
    "doctor-installed.json",
    "native-qualification.json",
    "native-cohort-binding.json",
    "native-cohort.json",
    "ui-qualification.json",
    "consumer-qualification.json",
    "release-evidence.json",
    "acceptance-inventory-neutral-theme.json",
    "acceptance-resources-neutral-theme.json",
    "playwright-summary-neutral-theme.json",
    "native-find-links.html",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def make_wheel(npm: bytes) -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr(f"arras/ui/npm/{NPM}", npm)
        archive.writestr("arras/__init__.py", "")
    return result.getvalue()


def build_trusted(
    path: Path, *, npm: bytes | None = None, embedded_npm: bytes | None = None
) -> tuple[str, str]:
    path.mkdir(parents=True)
    npm = b"package archive" if npm is None else npm
    wheel_bytes = make_wheel(npm if embedded_npm is None else embedded_npm)
    (path / WHEEL).write_bytes(wheel_bytes)
    (path / f"arras-{VERSION}.tar.gz").write_bytes(b"source archive")
    (path / NPM).write_bytes(npm)
    for name in ASSETS - {WHEEL, f"arras-{VERSION}.tar.gz", NPM, "release-evidence.json"}:
        (path / name).write_bytes(f"fixture:{name}".encode())
    (path / "release-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "passed",
                "version": VERSION,
                "arras_wheel": {"filename": WHEEL, "sha256": sha(wheel_bytes)},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sums = "".join(f"{sha((path / name).read_bytes())}  {name}\n" for name in sorted(ASSETS))
    (path / "SHA256SUMS").write_text(sums, encoding="ascii")
    return sha(wheel_bytes), sha(sums.encode())


def args(
    phase: str, trusted: Path, public: Path, output: Path, wheel_sha: str, sums_sha: str
) -> list[str]:
    return [
        str(HELPER),
        phase,
        "--trusted-dir",
        str(trusted),
        "--public-dir",
        str(public),
        "--expected-version",
        VERSION,
        "--expected-wheel",
        WHEEL,
        "--expected-wheel-sha256",
        wheel_sha,
        "--expected-sums-sha256",
        sums_sha,
        "--output",
        str(output),
    ]


def call_helper(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_plan_and_verify_require_exact_trusted_public_bytes(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    public = tmp_path / "public"
    wheel_sha, sums_sha = build_trusted(trusted)
    public.mkdir()
    shutil.copyfile(trusted / "SHA256SUMS", public / "SHA256SUMS")
    plan = tmp_path / "plan.txt"
    result = call_helper(*args("plan", trusted, public, plan, wheel_sha, sums_sha))
    assert result.returncode == 0, result.stderr
    assert set(plan.read_text(encoding="ascii").splitlines()) == ASSETS

    for name in ASSETS:
        shutil.copyfile(trusted / name, public / name)
    receipt = tmp_path / "receipt.json"
    result = call_helper(*args("verify", trusted, public, receipt, wheel_sha, sums_sha))
    assert result.returncode == 0, result.stderr
    value = json.loads(receipt.read_text(encoding="utf-8"))
    assert value["status"] == "passed" and value["npm_matches_wheel_payload"] is True
    assert value["wheel"] == {"filename": WHEEL, "sha256": wheel_sha}


@pytest.mark.parametrize(
    "change",
    [
        "asset",
        "replace-sums-and-assets",
        "wrong-wheel",
        "missing",
        "duplicate",
        "duplicate-sum",
        "traversal",
        "unsafe",
    ],
)
def test_public_mismatch_is_refused(tmp_path: Path, change: str) -> None:
    trusted = tmp_path / "trusted"
    public = tmp_path / "public"
    wheel_sha, sums_sha = build_trusted(trusted)
    public.mkdir()
    for name in ASSETS | {"SHA256SUMS"}:
        shutil.copyfile(trusted / name, public / name)
    output = tmp_path / "receipt.json"
    if change == "asset":
        (public / f"arras-{VERSION}.tar.gz").write_bytes(b"tampered")
    elif change == "replace-sums-and-assets":
        (public / "native-find-links.html").write_bytes(b"replacement")
        sums = "".join(f"{sha((public / name).read_bytes())}  {name}\n" for name in sorted(ASSETS))
        (public / "SHA256SUMS").write_text(sums, encoding="ascii")
    elif change == "wrong-wheel":
        wheel_sha = "0" * 64 if wheel_sha != "0" * 64 else "1" * 64
    elif change == "missing":
        (public / "ui-qualification.json").unlink()
    elif change == "duplicate":
        (public / "extra.json").write_text("{}", encoding="utf-8")
    elif change == "duplicate-sum":
        sums = (public / "SHA256SUMS").read_text(encoding="ascii")
        with (public / "SHA256SUMS").open("a", encoding="ascii") as stream:
            stream.write(sums.splitlines()[0] + "\n")
    elif change == "traversal":
        (public / "SHA256SUMS").write_text(
            (public / "SHA256SUMS")
            .read_text(encoding="ascii")
            .replace(f"  {NPM}\n", "  ../outside.tgz\n"),
            encoding="ascii",
        )
    else:
        (public / "unsafe.json").symlink_to(trusted / "native-find-links.html")
    result = call_helper(*args("verify", trusted, public, output, wheel_sha, sums_sha))
    assert result.returncode != 0
    assert not output.exists()


def test_wheel_embedded_npm_must_match_public_npm(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    public = tmp_path / "public"
    wheel_sha, sums_sha = build_trusted(trusted, npm=b"published npm", embedded_npm=b"wheel npm")
    public.mkdir()
    for name in ASSETS | {"SHA256SUMS"}:
        shutil.copyfile(trusted / name, public / name)
    (public / NPM).write_bytes(b"other package")
    receipt = tmp_path / "receipt.json"
    result = call_helper(*args("verify", trusted, public, receipt, wheel_sha, sums_sha))
    assert result.returncode != 0
    assert not receipt.exists()


def test_public_inventory_rejects_hard_link_aliases(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    public = tmp_path / "public"
    wheel_sha, sums_sha = build_trusted(trusted)
    public.mkdir()
    for name in ASSETS | {"SHA256SUMS"}:
        if name != "ui-qualification.json":
            shutil.copyfile(trusted / name, public / name)
    os.link(public / "native-cohort.json", public / "ui-qualification.json")
    receipt = tmp_path / "receipt.json"
    result = call_helper(*args("verify", trusted, public, receipt, wheel_sha, sums_sha))
    assert result.returncode != 0
    assert not receipt.exists()


def test_public_directory_cannot_be_the_trusted_stage(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    wheel_sha, sums_sha = build_trusted(trusted)
    result = call_helper(
        *args("verify", trusted, trusted, tmp_path / "receipt.json", wheel_sha, sums_sha)
    )
    assert result.returncode != 0
    assert not (tmp_path / "receipt.json").exists()


def _actual_public_download_block() -> str:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    marker = "      - name: Download and verify anonymous public release assets\n"
    assert workflow.count(marker) == 1
    content = workflow.split(marker, 1)[1].split("      - ", 1)[0]
    run_marker = "        run: |\n"
    assert content.count(run_marker) == 1
    content = content.split(run_marker, 1)[1]
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("      - ") or line.startswith("  #"):
            break
        if not line.strip():
            lines.append("")
            continue
        assert line.startswith("          "), line
        lines.append(line[10:])
    script = textwrap.dedent("\n".join(lines))
    return script


def _run_actual_download(
    tmp_path: Path,
    trusted: Path,
    public_source: Path,
    wheel_sha: str,
    sums_sha: str,
) -> subprocess.CompletedProcess[str]:
    public_download = tmp_path / "public-download"
    public_download.mkdir()
    (tmp_path / "artifacts").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "output=\nurl=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in --output) output="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac\n'
        "done\n"
        "name=${url##*/}\n"
        'cp "$PUBLIC_SOURCE/$name" "$output"\n',
        encoding="utf-8",
    )
    curl.chmod(0o755)
    (bin_dir / "python").symlink_to(sys.executable)
    scripts = tmp_path / ".github/scripts"
    scripts.mkdir(parents=True)
    (scripts / HELPER.name).symlink_to(HELPER)
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "PUBLIC_SOURCE": str(public_source),
            "TRUSTED_RELEASE_ASSETS": str(trusted),
            "PUBLIC_RELEASE_ASSETS": str(public_download),
            "RELEASE_URL": "https://github.example/releases/v0.5.0",
            "EXPECTED_VERSION": VERSION,
            "EXPECTED_WHEEL": WHEEL,
            "EXPECTED_WHEEL_SHA256": wheel_sha,
            "EXPECTED_SUMS_SHA256": sums_sha,
            "RUNNER_TEMP": str(tmp_path),
        }
    )
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _actual_public_download_block()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_actual_workflow_download_block_uses_plan_and_public_comparison(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted"
    wheel_sha, sums_sha = build_trusted(trusted)
    public_source = tmp_path / "public-source"
    public_source.mkdir()
    for name in ASSETS | {"SHA256SUMS"}:
        shutil.copyfile(trusted / name, public_source / name)
    result = _run_actual_download(tmp_path, trusted, public_source, wheel_sha, sums_sha)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((tmp_path / "artifacts/public-input-verification.json").read_text())
    assert receipt["status"] == "passed"


@pytest.mark.parametrize(
    "change",
    [
        "asset",
        "replacement-pair",
        "wrong-wheel",
        "missing",
        "duplicate",
        "unsafe",
        "npm-mismatch",
    ],
)
def test_actual_workflow_download_block_fails_before_receipt_on_bad_public_inputs(
    tmp_path: Path, change: str
) -> None:
    trusted = tmp_path / "trusted"
    wheel_sha, sums_sha = build_trusted(trusted, embedded_npm=b"wheel npm", npm=b"published npm")
    public_source = tmp_path / "public-source"
    public_source.mkdir()
    for name in ASSETS | {"SHA256SUMS"}:
        shutil.copyfile(trusted / name, public_source / name)
    if change == "asset":
        (public_source / "native-find-links.html").write_bytes(b"changed after checksum download")
    elif change == "replacement-pair":
        (public_source / "native-find-links.html").write_bytes(b"coherent replacement")
        sums = "".join(
            f"{sha((public_source / name).read_bytes())}  {name}\n" for name in sorted(ASSETS)
        )
        (public_source / "SHA256SUMS").write_text(sums, encoding="ascii")
    elif change == "wrong-wheel":
        wheel_sha = "0" * 64 if wheel_sha != "0" * 64 else "1" * 64
    elif change == "missing":
        (public_source / NPM).unlink()
    elif change in {"duplicate", "unsafe"}:
        sums_path = trusted / "SHA256SUMS"
        sums = sums_path.read_text(encoding="ascii")
        if change == "duplicate":
            sums += sums.splitlines()[0] + "\n"
        else:
            sums = sums.replace(f"  {NPM}\n", "  ../outside.tgz\n")
        sums_path.write_text(sums, encoding="ascii")
        (public_source / "SHA256SUMS").write_text(sums, encoding="ascii")
        sums_sha = sha(sums.encode())
    # The trusted stage has a coherent digest inventory, but the public wheel/npm pair is invalid.
    result = _run_actual_download(tmp_path, trusted, public_source, wheel_sha, sums_sha)
    assert result.returncode != 0
    assert not (tmp_path / "artifacts/public-input-verification.json").exists()
