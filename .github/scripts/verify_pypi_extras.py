#!/usr/bin/env python3
"""Verify an Arras optional-extras install resolved from public PyPI bytes only."""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

PYPI_HOSTS = {"pypi.org", "files.pythonhosted.org"}
QUALIFIED_GITHUB_PINS = {
    "umf-core": {
        "version": "0.10.5",
        "assets": {
            "linux-x86_64": {
                "filename": "umf_core-0.10.5-cp311-abi3-manylinux_2_34_x86_64.whl",
                "sha256": "cf33b833ff4eaa080f459cf3c93baa7e3b4e436dab5cd7853dd748e3c220dd16",
                "release_url": "https://github.com/DocumentDrivenDX/umf/releases/download/python-v0.10.5/umf_core-0.10.5-cp311-abi3-manylinux_2_34_x86_64.whl",
            },
            "macos-arm64": {
                "filename": "umf_core-0.10.5-cp311-abi3-macosx_11_0_arm64.whl",
                "sha256": "9213ff4b87649f551abcfdff40cdb6b0d75d619260988fa8ea4fe26cac7f6788",
                "release_url": "https://github.com/DocumentDrivenDX/umf/releases/download/python-v0.10.5/umf_core-0.10.5-cp311-abi3-macosx_11_0_arm64.whl",
            },
        },
    },
    "truss-toolkit": {
        "version": "0.0.50",
        "filename": "truss_toolkit-0.0.50-py3-none-any.whl",
        "sha256": "7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00",
        "release_url": "https://github.com/DocumentDrivenDX/truss/releases/download/v0.0.50/truss_toolkit-0.0.50-py3-none-any.whl",
    },
    "weft-sql": {
        "version": "0.4.51",
        "assets": {
            "linux-aarch64": {
                "filename": "weft_sql-0.4.51-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
                "sha256": "42f846d689ace027d6bb2951f27c587660d4e5151285fe911ce7a3006d0001de",
                "release_url": "https://github.com/DocumentDrivenDX/weft/releases/download/v0.4.51/weft_sql-0.4.51-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            },
            "linux-x86_64": {
                "filename": "weft_sql-0.4.51-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
                "sha256": "a23142f12b59444138b588a8a764666b025552a14036f62d83af022153f1a0a5",
                "release_url": "https://github.com/DocumentDrivenDX/weft/releases/download/v0.4.51/weft_sql-0.4.51-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            },
            "macos-arm64": {
                "filename": "weft_sql-0.4.51-cp39-abi3-macosx_11_0_arm64.whl",
                "sha256": "e60e552f02c670b43a43111b08d26d6b415aaa9b9de42f241c37ad1d9fdd2487",
                "release_url": "https://github.com/DocumentDrivenDX/weft/releases/download/v0.4.51/weft_sql-0.4.51-cp39-abi3-macosx_11_0_arm64.whl",
            },
        },
    },
}
HISTORICAL_UMF_PIN = {
    "version": "0.10.0",
    "filename": "umf_core-0.10.0-py3-none-any.whl",
    "sha256": "49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9",
    "release_url": "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/umf_core-0.10.0-py3-none-any.whl",
}
RELEASE_UMF_PINS = {
    "0.6.3": HISTORICAL_UMF_PIN,
    "0.6.4": HISTORICAL_UMF_PIN,
    "0.6.5": HISTORICAL_UMF_PIN,
    "0.7.0": QUALIFIED_GITHUB_PINS["umf-core"],
    "0.7.1": QUALIFIED_GITHUB_PINS["umf-core"],
    "0.7.2": QUALIFIED_GITHUB_PINS["umf-core"],
    "0.7.3": QUALIFIED_GITHUB_PINS["umf-core"],
    "0.8.0": QUALIFIED_GITHUB_PINS["umf-core"],
}


class ExtrasVerificationError(ValueError):
    """The published extras install does not match its public qualified inputs."""


def qualified_pins(version: str) -> dict[str, Any]:
    if version not in RELEASE_UMF_PINS:
        raise ExtrasVerificationError("Arras release has no qualified public dependency cohort")
    return {**QUALIFIED_GITHUB_PINS, "umf-core": RELEASE_UMF_PINS[version]}


def platform_pin(pin: dict[str, Any]) -> dict[str, Any]:
    if "assets" not in pin:
        return pin
    selected = pin["assets"].get(_current_weft_platform())
    if not isinstance(selected, dict):
        raise ExtrasVerificationError("no qualified SDK artifact exists for this runner platform")
    return selected


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value is not None:
                    self.hrefs.append(value)


def _object(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ExtrasVerificationError(f"{label} must be an object")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExtrasVerificationError(f"cannot read {label}") from exc
    return _object(value, label)


def validate_qualified_index(path: Path, *, version: str = "0.7.0") -> None:
    """Require the committed find-links page to retain the qualified release pins."""
    try:
        parser = _Links()
        parser.feed(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ExtrasVerificationError("cannot read the qualified GitHub pin index") from exc
    for package, pin in qualified_pins(version).items():
        assets = pin.get("assets", {"single": pin})
        for asset in assets.values():
            matches = []
            for href in parser.hrefs:
                split = urllib.parse.urlsplit(href)
                filename = Path(urllib.parse.unquote(split.path)).name
                if filename != asset["filename"]:
                    continue
                matches.append((split, urllib.parse.parse_qs(split.fragment)))
            if len(matches) != 1:
                raise ExtrasVerificationError(
                    f"qualified index must contain one {package} asset for {asset['filename']}"
                )
            split, fragment = matches[0]
            expected = urllib.parse.urlsplit(asset["release_url"])
            if (
                split.scheme != "https"
                or split.netloc != "github.com"
                or split.path != expected.path
                or split.query
                or fragment != {"sha256": [asset["sha256"]]}
            ):
                raise ExtrasVerificationError(f"qualified GitHub pin changed for {package}")


def _current_weft_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    if system == "linux" and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if system == "linux" and machine in {"aarch64", "arm64"}:
        return "linux-aarch64"
    raise ExtrasVerificationError("no qualified Weft wheel exists for this runner platform")


def _normalized_name(value: object) -> str:
    if not isinstance(value, str):
        raise ExtrasVerificationError("pip report distribution name is malformed")
    return re.sub(r"[-_.]+", "-", value).lower()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ExtrasVerificationError(f"{label} is not a lowercase SHA-256")
    return value


def validate_pip_report(
    report: dict[str, Any], *, version: str, wheel_sha256: str
) -> dict[str, dict[str, str]]:
    """Validate every selected archive source and the qualified critical wheel hashes."""
    installs = report.get("install")
    if type(installs) is not list or not installs:
        raise ExtrasVerificationError("pip install report has no selected distributions")
    selected: dict[str, dict[str, str]] = {}
    for raw in installs:
        item = _object(raw, "pip install row")
        metadata = _object(item.get("metadata"), "pip install metadata")
        name = _normalized_name(metadata.get("name"))
        release_version = metadata.get("version")
        if not isinstance(release_version, str) or name in selected:
            raise ExtrasVerificationError("pip report has an invalid or duplicate distribution")
        download = _object(item.get("download_info"), "pip download information")
        url = download.get("url")
        if not isinstance(url, str):
            raise ExtrasVerificationError("pip report has no download URL")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in PYPI_HOSTS:
            raise ExtrasVerificationError("dependency did not download from the public PyPI index")
        archive = _object(download.get("archive_info"), "pip archive information")
        hashes = _object(archive.get("hashes"), "pip archive hashes")
        digest = _sha256(hashes.get("sha256"), f"{name} download digest")
        filename = Path(urllib.parse.unquote(parsed.path)).name
        selected[name] = {
            "version": release_version,
            "sha256": digest,
            "filename": filename,
            "origin_host": parsed.hostname or "",
        }

    expected_arras = _sha256(wheel_sha256, "expected Arras wheel digest")
    arras = selected.get("arras")
    if arras is None or arras["version"] != version or arras["sha256"] != expected_arras:
        raise ExtrasVerificationError("PyPI did not install the exact qualified Arras wheel")
    pins = qualified_pins(version)
    for name, release_pin in pins.items():
        expected_version = release_pin["version"]
        item = selected.get(name)
        if item is None or item["version"] != expected_version:
            raise ExtrasVerificationError(
                f"required extra distribution is missing or changed: {name}"
            )
        pin = platform_pin(release_pin)
        if item["filename"] != pin["filename"] or item["sha256"] != pin["sha256"]:
            raise ExtrasVerificationError(
                f"installed artifact differs from its qualified GitHub pin: {name}"
            )
    return selected


def _verify_installed_closure(version: str) -> dict[str, str]:
    installed: dict[str, str] = {}
    direct_urls: list[str] = []
    for distribution in importlib.metadata.distributions():
        name = _normalized_name(distribution.metadata.get("Name"))
        found_version = distribution.version
        if name in installed:
            raise ExtrasVerificationError("installed environment contains duplicate distributions")
        installed[name] = found_version
        if distribution.read_text("direct_url.json") is not None:
            direct_urls.append(name)
    if direct_urls:
        raise ExtrasVerificationError("installed dependency closure contains direct-URL metadata")
    expected = {
        "arras": version,
        **{name: pin["version"] for name, pin in qualified_pins(version).items()},
    }
    for name, expected_version in expected.items():
        if installed.get(name) != expected_version:
            raise ExtrasVerificationError(f"installed distribution version differs: {name}")
    return installed


def doctor_request_for_release(path: Path, version: str) -> dict[str, Any]:
    qualified_pins(version)
    request = _read_json(path, "doctor request")
    packages = _object(request.get("expected_packages"), "doctor expected packages")
    for name in ("arras", "@documentdrivendx/arras-ui"):
        if name not in packages:
            raise ExtrasVerificationError("doctor request omits the selected Arras package")
        packages[name] = version
    return request


def _run_doctor(version: str, source_request: Path) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="arras-pypi-extras-doctor-") as temporary:
        request = Path(temporary) / "request.json"
        request.write_text(json.dumps(doctor_request_for_release(source_request, version)))
        return subprocess.run(
            [sys.executable, "-I", "-m", "arras.doctor", "--request", str(request)],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )


def _smoke_imports(version: str, doctor_request: Path, umf_document: Path) -> dict[str, Any]:
    import truss
    import umf
    import weft

    import arras
    from arras.adapters.truss import require_toolkit
    from arras.adapters.truss.describe import weft_support
    from arras.umf_admission import admit_document

    if truss.__name__ != "truss" or umf.__name__ != "umf":
        raise ExtrasVerificationError("public Truss or UMF module import changed")
    if importlib.metadata.version("arras") != version:
        raise ExtrasVerificationError("imported Arras version differs")
    toolkit_version = require_toolkit()
    support = weft_support()
    if support is None or not callable(getattr(weft, "compile_json", None)):
        raise ExtrasVerificationError("qualified Weft backend is unavailable")
    try:
        corpus = json.loads(umf_document.read_text(encoding="utf-8"))
        document = next(
            case["document"] for case in corpus["cases"] if case["id"] == "schema-properties/valid"
        )
        report = admit_document(json.dumps(document, separators=(",", ":")))
    except (KeyError, OSError, StopIteration, json.JSONDecodeError) as exc:
        raise ExtrasVerificationError("official UMF document smoke could not run") from exc
    if (
        report.validation_status != "completed"
        or report.valid is not True
        or report.complete is not True
    ):
        raise ExtrasVerificationError("official UMF document smoke did not pass")

    result = _run_doctor(version, doctor_request)
    if result.returncode != 0:
        raise ExtrasVerificationError("installed Arras doctor smoke did not pass")
    try:
        doctor = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExtrasVerificationError("installed Arras doctor returned malformed output") from exc
    if doctor.get("ok") is not True or doctor.get("complete") is not True:
        raise ExtrasVerificationError("installed Arras doctor reported an incomplete result")
    if Path(arras.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[2] / "src"):
        raise ExtrasVerificationError("Arras import resolved to the source checkout")
    return {
        "arras_import": "passed",
        "truss_import": "passed",
        "weft_import": "passed",
        "toolkit_version": toolkit_version,
        "weft_support": "passed",
        "umf_distribution_version": importlib.metadata.version("umf-core"),
        "umf_document_admission": "valid_and_complete",
        "doctor": "passed",
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    validate_qualified_index(args.qualified_index, version=args.version)
    report = _read_json(args.report, "pip install report")
    selected = validate_pip_report(report, version=args.version, wheel_sha256=args.wheel_sha256)
    installed = _verify_installed_closure(args.version)
    check = subprocess.run(
        [sys.executable, "-m", "pip", "--isolated", "check"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check.returncode != 0:
        raise ExtrasVerificationError("pip check found an inconsistent installed environment")
    smoke = _smoke_imports(args.version, args.doctor_request, args.umf_document)
    return {
        "schema_version": 1,
        "status": "passed",
        "registry": "pypi",
        "install_selector": f"arras[truss,umf]=={args.version}",
        "index_scope": "https://pypi.org/simple",
        "pypi_report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "arras_wheel_sha256": _sha256(args.wheel_sha256, "expected Arras wheel digest"),
        "qualified_github_dependency_sha256": {
            name: (
                {
                    platform_name: pin["sha256"]
                    for platform_name, pin in release_pin["assets"].items()
                }
                if "assets" in release_pin
                else release_pin["sha256"]
            )
            for name, release_pin in qualified_pins(args.version).items()
        },
        "selected_distribution_count": len(selected),
        "selected_distributions": {
            name: {
                "version": row["version"],
                "sha256": row["sha256"],
                "filename": row["filename"],
                "origin_host": row["origin_host"],
            }
            for name, row in sorted(selected.items())
        },
        "installed_distributions": len(installed),
        "installed_direct_url_references": 0,
        "pip_check": "passed",
        "smoke": smoke,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--qualified-index", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--doctor-request", type=Path, required=True)
    parser.add_argument("--umf-document", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = verify(args)
        args.output_json.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (ExtrasVerificationError, OSError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Public PyPI extras verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
