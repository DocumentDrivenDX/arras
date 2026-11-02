from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
SPEC = importlib.util.spec_from_file_location(
    "local_qualification", ROOT / ".github/scripts/local_registry_qualification.py"
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


@pytest.fixture
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, str]]:
    identity = {
        "wheel": "arras-0.6.5-py3-none-any.whl",
        "wheel_sha256": module.ASSETS["arras-0.6.5-py3-none-any.whl"],
        "npm_sha256": module.ASSETS["documentdrivendx-arras-ui-0.6.5.tgz"],
    }
    wheel_sha = identity["wheel_sha256"]
    records = {
        "installed/native-cohort-binding.json": {"status": "bound", "wheel": {"sha256": wheel_sha}},
        "installed/native-verification.json": {"status": "passed", "runtime": {"python": "3.11"}},
        "installed/umf-admission-installed.json": {
            "fixture": "delegated to existing full UMF receipt validator"
        },
        "installed/public-distribution.json": {
            "source_wheel": {"sha256": wheel_sha},
            "sdist": {"sha256": module.ASSETS["arras-0.6.5.tar.gz"]},
            "npm": {"sha256": identity["npm_sha256"]},
            "qualification": ["artifact-inspected", "installed-consumer-tested"],
        },
        "installed/public-doctor.json": {"status": "passed", "wheel": {"sha256": wheel_sha}},
        "installed/public-extension.json": {
            "arras_wheel": {"sha256": wheel_sha},
            "environment": {"dependency_mode": "fresh-public-index-resolution"},
            "qualification": "installed-artifact consumer and fixed memory corpus",
        },
        "ui/qualification-linux.json": {
            "schema": "arras.ui.downstream-qualification.v1",
            "cohort": {"wheel": {"sha256": wheel_sha}, "npm": {"sha256": identity["npm_sha256"]}},
            "routes": [
                {
                    "schema": "arras.ui.qualification-receipt.v1",
                    "route": route,
                    "surface": surface,
                    "checks": ["axe-wcag21aa", "theme-tokens", "contrast", "keyboard-focus"],
                }
                for route in ["prebuilt-page", "compiled-host"]
                for surface in ["browser", "console"]
            ],
            "acceptance_suite": {
                "status": "passed",
                "canonical": {"specCount": 17, "expectedTestCount": 205},
                "visual": {"status": "skipped-non-Darwin"},
                "projects": [
                    {
                        "name": name,
                        "expected": count,
                        "discovered": count,
                        "passed": count,
                        "failed": 0,
                        "skipped": 0,
                    }
                    for name, count in [("chromium", 132), ("schema-admin", 3), ("browser", 70)]
                ],
            },
        },
    }
    for name, value in records.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    for name in ["source/source-pytest.xml", "source/truss-pytest.xml", "downstream/consumer.xml"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"/>')

    def check_umf(value: object, **kwargs: Any) -> None:
        assert value == records["installed/umf-admission-installed.json"]
        assert kwargs["wheel_sha256"] == wheel_sha
        assert kwargs["version"] == "0.6.5"
        assert kwargs["phase"] == "public-download"

    monkeypatch.setattr(module, "validate_receipt", check_umf)
    return tmp_path, identity


def test_exact_gate_receipts_pass(evidence: tuple[Path, dict[str, str]]) -> None:
    module.validate_evidence(*evidence)


@pytest.mark.parametrize(
    "name,field,bad",
    [
        ("installed/native-cohort-binding.json", "status", "failed"),
        ("installed/native-verification.json", "status", "failed"),
        ("installed/public-distribution.json", "qualification", []),
        ("installed/public-doctor.json", "status", "failed"),
        ("installed/public-extension.json", "qualification", "source-only"),
        ("ui/qualification-linux.json", "acceptance_suite", {"status": "failed"}),
        ("ui/qualification-linux.json", "routes", []),
    ],
)
def test_semantic_failures_refuse(
    evidence: tuple[Path, dict[str, str]], name: str, field: str, bad: Any
) -> None:
    root, identity = evidence
    path = root / name
    receipt = json.loads(path.read_text())
    receipt[field] = bad
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        module.validate_evidence(root, identity)


def test_umf_failure_propagates(
    evidence: tuple[Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ValueError("UMF controls failed")

    monkeypatch.setattr(module, "validate_receipt", refuse)
    with pytest.raises(ValueError, match="UMF controls"):
        module.validate_evidence(*evidence)


def test_failed_consumer_report_refuses(evidence: tuple[Path, dict[str, str]]) -> None:
    root, identity = evidence
    (root / "downstream/consumer.xml").write_text('<testsuite tests="1" failures="1"/>')
    with pytest.raises(ValueError, match="test qualification"):
        module.validate_evidence(root, identity)


def test_missing_receipt_refuses(evidence: tuple[Path, dict[str, str]]) -> None:
    root, identity = evidence
    (root / "installed/public-doctor.json").unlink()
    with pytest.raises(FileNotFoundError):
        module.validate_evidence(root, identity)


@pytest.mark.parametrize("change", ["duplicate", "missing-check", "schema"])
def test_ui_route_coverage_refuses(evidence: tuple[Path, dict[str, str]], change: str) -> None:
    root, identity = evidence
    path = root / "ui/qualification-linux.json"
    receipt = json.loads(path.read_text())
    if change == "duplicate":
        receipt["routes"][0] = receipt["routes"][1]
    elif change == "missing-check":
        receipt["routes"][0]["checks"] = []
    else:
        receipt["routes"][0]["schema"] = "unknown"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="UI route"):
        module.validate_evidence(root, identity)


@pytest.mark.parametrize("change", ["counts", "discovery", "canonical"])
def test_ui_incomplete_campaign_refuses(evidence: tuple[Path, dict[str, str]], change: str) -> None:
    root, identity = evidence
    path = root / "ui/qualification-linux.json"
    receipt = json.loads(path.read_text())
    suite = receipt["acceptance_suite"]
    if change == "counts":
        suite["projects"][0].update(expected=1, discovered=1, passed=1)
    elif change == "discovery":
        suite["projects"][0]["discovered"] = 1
    else:
        suite["canonical"]["specCount"] = 1
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="UI"):
        module.validate_evidence(root, identity)
