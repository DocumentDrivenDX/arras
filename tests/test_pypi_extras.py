# SPDX-License-Identifier: MIT OR Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / ".github/scripts/verify_pypi_extras.py"
SPEC = importlib.util.spec_from_file_location("pypi_extras", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
extras = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extras)

VERSION = "0.6.3"
ARRAS_SHA256 = "a" * 64


def _item(
    name: str, version: str, filename: str, sha256: str, url: str | None = None
) -> dict[str, Any]:
    return {
        "metadata": {"name": name, "version": version},
        "download_info": {
            "url": url or f"https://files.pythonhosted.org/packages/test/{filename}",
            "archive_info": {"hashes": {"sha256": sha256}},
        },
    }


def _report() -> dict[str, Any]:
    pins = extras.QUALIFIED_GITHUB_PINS
    weft_pin = pins["weft-sql"]["assets"][extras._current_weft_platform()]
    return {
        "install": [
            _item("arras", VERSION, "arras.whl", ARRAS_SHA256),
            _item("umf-core", "0.10.0", pins["umf-core"]["filename"], pins["umf-core"]["sha256"]),
            _item(
                "truss-toolkit",
                "0.0.50",
                pins["truss-toolkit"]["filename"],
                pins["truss-toolkit"]["sha256"],
            ),
            _item(
                "weft-sql",
                "0.4.51",
                weft_pin["filename"],
                weft_pin["sha256"],
            ),
            _item("graphql-core", "3.3.0", "graphql_core.whl", "b" * 64),
        ]
    }


def _validate(
    report: dict[str, Any], *, wheel_sha256: str = ARRAS_SHA256
) -> dict[str, dict[str, str]]:
    return extras.validate_pip_report(report, version=VERSION, wheel_sha256=wheel_sha256)


def test_public_pypi_report_matches_arras_and_qualified_github_dependency_bytes() -> None:
    extras.validate_qualified_index(ROOT / "tools/find-links/index.html")
    result = _validate(_report())
    assert result["arras"]["sha256"] == ARRAS_SHA256
    assert result["umf-core"]["sha256"] == extras.QUALIFIED_GITHUB_PINS["umf-core"]["sha256"]
    assert (
        result["truss-toolkit"]["sha256"] == extras.QUALIFIED_GITHUB_PINS["truss-toolkit"]["sha256"]
    )
    assert (
        result["weft-sql"]["sha256"]
        == extras.QUALIFIED_GITHUB_PINS["weft-sql"]["assets"][extras._current_weft_platform()][
            "sha256"
        ]
    )


def test_macos_report_accepts_exact_qualified_weft_archive_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = extras.QUALIFIED_GITHUB_PINS["weft-sql"]["assets"]["macos-arm64"]
    report = _report()
    weft = next(row for row in report["install"] if row["metadata"]["name"] == "weft-sql")
    weft["download_info"]["url"] = f"https://files.pythonhosted.org/packages/test/{pin['filename']}"
    weft["download_info"]["archive_info"]["hashes"]["sha256"] = pin["sha256"]
    monkeypatch.setattr(extras, "_current_weft_platform", lambda: "macos-arm64")
    selected = _validate(report)
    assert selected["weft-sql"]["filename"] == pin["filename"]
    assert selected["weft-sql"]["sha256"] == pin["sha256"]

    weft["download_info"]["archive_info"]["hashes"]["sha256"] = "f" * 64
    with pytest.raises(extras.ExtrasVerificationError, match="qualified GitHub pin"):
        _validate(report)


def test_report_rejects_direct_url_source_even_when_its_bytes_match() -> None:
    report = _report()
    item = next(row for row in report["install"] if row["metadata"]["name"] == "umf-core")
    item["download_info"]["url"] = extras.QUALIFIED_GITHUB_PINS["umf-core"]["release_url"]
    with pytest.raises(extras.ExtrasVerificationError, match="public PyPI index"):
        _validate(report)


def test_report_rejects_nonstandard_pypi_endpoint_configuration() -> None:
    report = _report()
    report["install"][0]["download_info"]["url"] = (
        "https://files.pythonhosted.org:444/packages/test/arras.whl"
    )
    with pytest.raises(extras.ExtrasVerificationError, match="public PyPI index"):
        _validate(report)


def test_installed_dependency_closure_rejects_pep610_direct_url_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Distribution:
        def __init__(self, name: str, version: str, direct_url: str | None = None) -> None:
            self.metadata = {"Name": name}
            self.version = version
            self.direct_url = direct_url

        def read_text(self, filename: str) -> str | None:
            assert filename == "direct_url.json"
            return self.direct_url

    distributions = [
        Distribution("arras", VERSION),
        Distribution("truss-toolkit", "0.0.50"),
        Distribution("weft-sql", "0.4.51"),
        Distribution("umf-core", "0.10.0", '{"url":"https://example.invalid/wheel.whl"}'),
    ]
    monkeypatch.setattr(extras.importlib.metadata, "distributions", lambda: distributions)
    with pytest.raises(extras.ExtrasVerificationError, match="direct-URL metadata"):
        extras._verify_installed_closure(VERSION)


def test_report_rejects_dependency_provenance_digest_mismatch() -> None:
    report = _report()
    item = next(row for row in report["install"] if row["metadata"]["name"] == "weft-sql")
    item["download_info"]["archive_info"]["hashes"]["sha256"] = "c" * 64
    with pytest.raises(extras.ExtrasVerificationError, match="qualified GitHub pin"):
        _validate(report)


def test_report_rejects_missing_extra_dependency() -> None:
    report = _report()
    report["install"] = [row for row in report["install"] if row["metadata"]["name"] != "weft-sql"]
    with pytest.raises(extras.ExtrasVerificationError, match="missing or changed: weft-sql"):
        _validate(report)


def test_qualified_github_pin_index_refuses_digest_or_repository_drift(tmp_path: Path) -> None:
    source = (ROOT / "tools/find-links/index.html").read_text(encoding="utf-8")
    pinned = extras.QUALIFIED_GITHUB_PINS["truss-toolkit"]["sha256"]
    tampered = source.replace(pinned, "d" * 64, 1)
    index = tmp_path / "find-links.html"
    index.write_text(tampered, encoding="utf-8")
    with pytest.raises(extras.ExtrasVerificationError, match="pin changed for truss-toolkit"):
        extras.validate_qualified_index(index)

    weft_url = extras.QUALIFIED_GITHUB_PINS["weft-sql"]["assets"]["linux-x86_64"]["release_url"]
    tampered = source.replace(weft_url, weft_url.replace("github.com", "example.invalid"), 1)
    index.write_text(tampered, encoding="utf-8")
    with pytest.raises(extras.ExtrasVerificationError, match="pin changed for weft-sql"):
        extras.validate_qualified_index(index)


def test_report_rejects_changed_arras_wheel_digest() -> None:
    with pytest.raises(extras.ExtrasVerificationError, match="exact qualified Arras wheel"):
        _validate(_report(), wheel_sha256="e" * 64)


def test_publisher_installs_only_the_configured_public_index_and_verifies_post_publish() -> None:
    workflow = (ROOT / ".github/workflows/publish-registries.yml").read_text(encoding="utf-8")
    match = __import__("re").search(
        r"(?ms)^  pypi-extras-verify:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", workflow
    )
    assert match is not None
    job = match.group(1)
    assert "needs: [verify-release, pypi-publish]" in job
    assert "PIP_CONFIG_FILE: /dev/null" in job
    assert "--isolated install" in job
    assert "--index-url https://pypi.org/simple" in job
    assert "--no-cache-dir" in job
    assert "--extra-index-url" not in job and "--find-links" not in job
    assert '"arras[truss,umf]==$VERSION"' in job
    assert "verify_pypi_extras.py" in job
    assert "runner: ubuntu-latest" in job
    assert "platform: linux-x86_64" in job
    assert "runner: macos-15" in job
    assert "platform: macos-arm64" in job
    assert (
        "registry-pypi-extras-${{ needs.verify-release.outputs.version }}-${{ matrix.platform }}"
        in job
    )
