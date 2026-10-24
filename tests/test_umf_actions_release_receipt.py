# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
import zipfile
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
_PATH = ROOT / ".github/scripts/_umf_actions_receipt.py"
_SPEC = importlib.util.spec_from_file_location("umf_actions_release_receipt", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
_SELECTOR_PATH = ROOT / "tools/_umf_sdk_cohorts.py"
_SELECTOR_SPEC = importlib.util.spec_from_file_location(
    "action_receipt_cohort_selector", _SELECTOR_PATH
)
assert _SELECTOR_SPEC is not None and _SELECTOR_SPEC.loader is not None
_SELECTOR = importlib.util.module_from_spec(_SELECTOR_SPEC)
sys.modules[_SELECTOR_SPEC.name] = _SELECTOR
_SELECTOR_SPEC.loader.exec_module(_SELECTOR)

_DIGEST = "a" * 64
_COHORT = SimpleNamespace(
    cohort_id="umf-core-0.10.1-cp311-abi3-macosx_11_0_arm64",
    distribution_version="0.10.1",
    document_version="0.10.0",
    platform="darwin",
    machine="arm64",
    filename="umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
    url="https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.6.0/umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
    sha256="b" * 64,
    supports_single_set=True,
)


def _wheel(
    path: Path, *, declared_url: str | None = None, declared_sha: str | None = None
) -> tuple[str, str]:
    url = declared_url or _COHORT.url
    digest = declared_sha or _COHORT.sha256
    metadata = (
        "Metadata-Version: 2.3\n"
        "Name: arras\n"
        "Version: 0.6.0\n"
        "Requires-Dist: umf-core @ "
        + url
        + "#sha256="
        + digest
        + "; extra == 'umf' and sys_platform == 'darwin' and platform_machine == 'arm64'\n\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("arras-0.6.0.dist-info/METADATA", metadata)
    return path.name, hashlib.sha256(path.read_bytes()).hexdigest()


def _distribution(name: str, version: str) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "payload_files": 3,
        "payload_sha256": "c" * 64,
        "record_matches": 3,
        "resource_files": 9 if name == "umf-core" else 0,
        "resource_manifest_sha256": "d" * 64,
        "native_files": 1 if name == "umf-core" else 0,
        "native_manifest_sha256": "e" * 64,
    }


def _receipt(
    wheel: Path, *, declared_url: str | None = None, declared_sha: str | None = None
) -> dict[str, Any]:
    wheel_name, wheel_sha = _wheel(wheel, declared_url=declared_url, declared_sha=declared_sha)
    cohort = {
        key: getattr(_COHORT, key)
        for key in (
            "cohort_id",
            "distribution_version",
            "document_version",
            "platform",
            "machine",
            "filename",
            "url",
            "sha256",
            "supports_single_set",
        )
    }
    return {
        "schema": _MODULE.SCHEMA,
        "status": "passed",
        "public_gate": True,
        "mode": "public-extra",
        "candidate_override": None,
        "arras_wheel": {"filename": wheel_name, "version": "0.6.0", "sha256": wheel_sha},
        "umf": {
            "public_extra": cohort,
            "installed": {"filename": _COHORT.filename, "sha256": _COHORT.sha256},
            "candidate_override": None,
        },
        "fixtures": dict(_MODULE._FIXTURES),
        "tool_sha256": hashlib.sha256(
            (ROOT / "tools/verify_umf_actions.py").read_bytes()
        ).hexdigest(),
        "probe_sha256": hashlib.sha256(
            (ROOT / "tools/_umf_actions_probe.py").read_bytes()
        ).hexdigest(),
        "selector_sha256": hashlib.sha256(
            (ROOT / "tools/_umf_sdk_cohorts.py").read_bytes()
        ).hexdigest(),
        "runtime": {
            "python": "3.11.9",
            "platform": "darwin",
            "machine": "arm64",
            "implementation": "CPython",
        },
        "origins": {
            "arras": "arras/__init__.py",
            "umf": "umf/__init__.py",
            "umf.action_runtime": "umf/action_runtime.py",
            "umf.rust_codegen": "umf/rust_codegen.py",
        },
        "installed": {
            "arras": _distribution("arras", "0.6.0"),
            "umf_core": _distribution("umf-core", "0.10.1"),
        },
        "generated_client_sha256": "f" * 64,
        "controls": {key: True for key in _MODULE._CONTROLS},
        "corpus": {"cases": 139, "reference_matches": 139, "empty_registry_matches": 139},
        "cleanup": {"completed": True, "fresh_venvs": 1, "shared_site_packages": False},
        "qualification_phase": "release-build",
    }


def _select_only_candidate(metadata: object, *, platform: str, machine: str) -> Any:
    return _SELECTOR.select_sdk_cohort(
        metadata, platform=platform, machine=machine, registry=(_COHORT,)
    )


def _fake_cohort_loader(_repository: Path) -> SimpleNamespace:
    return SimpleNamespace(
        select_sdk_cohort=_select_only_candidate,
        single_set_capability=_single_set_capability,
    )


def _single_set_capability(_metadata: object) -> bool:
    return True


def _real_select(metadata: object, *, platform: str, machine: str) -> Any:
    return _SELECTOR.select_sdk_cohort(
        metadata, platform=platform, machine=machine, registry=(_COHORT,)
    )


def _real_capability(metadata: object) -> bool:
    return _SELECTOR.single_set_capability(metadata, registry=(_COHORT,))


def _real_cohort_loader(_repository: Path) -> SimpleNamespace:
    return SimpleNamespace(select_sdk_cohort=_real_select, single_set_capability=_real_capability)


def _bad_public_gate(row: dict[str, Any]) -> None:
    row["public_gate"] = False


def _candidate_mode(row: dict[str, Any]) -> None:
    row["mode"] = "local-candidate"


def _candidate_override(row: dict[str, Any]) -> None:
    row["candidate_override"] = {"sha256": "0" * 64, "public_gate": False}


def _false_control(row: dict[str, Any]) -> None:
    row["controls"]["apply_and_read_at_least"] = False


def _wrong_corpus_count(row: dict[str, Any]) -> None:
    row["corpus"]["empty_registry_matches"] = 138


def _incomplete_cleanup(row: dict[str, Any]) -> None:
    row["cleanup"]["completed"] = False


def _wrong_runtime(row: dict[str, Any]) -> None:
    row["runtime"]["machine"] = "x86_64"


def _raw_diagnostic(row: dict[str, Any]) -> None:
    row["extra_diagnostic"] = "/private/secret/path"


def _zero_sdk_resources(row: dict[str, Any]) -> None:
    row["installed"]["umf_core"]["resource_files"] = 0


def _zero_sdk_native_files(row: dict[str, Any]) -> None:
    row["installed"]["umf_core"]["native_files"] = 0


def _boolean_sdk_resource_count(row: dict[str, Any]) -> None:
    row["installed"]["umf_core"]["resource_files"] = True


def _numeric_capability(row: dict[str, Any]) -> None:
    row["umf"]["public_extra"]["supports_single_set"] = 1


_INVALID_RECEIPT_MUTATIONS: list[Callable[[dict[str, Any]], None]] = [
    _bad_public_gate,
    _candidate_mode,
    _candidate_override,
    _false_control,
    _wrong_corpus_count,
    _incomplete_cleanup,
    _wrong_runtime,
    _raw_diagnostic,
    _zero_sdk_resources,
    _zero_sdk_native_files,
    _boolean_sdk_resource_count,
    _numeric_capability,
]


def _validate(value: object, wheel: Path) -> dict[str, Any]:
    wheel_name, wheel_sha = wheel.name, hashlib.sha256(wheel.read_bytes()).hexdigest()
    return _MODULE.validate_receipt(
        value,
        version="0.6.0",
        wheel_name=wheel_name,
        wheel_sha256=wheel_sha,
        wheel_path=wheel,
        phase="release-build",
        repository=ROOT,
    )


def test_release_projection_requires_public_action_capable_selected_cohort(tmp_path: Path) -> None:
    wheel = tmp_path / "arras-0.6.0-py3-none-any.whl"
    _wheel(wheel)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_MODULE, "_cohorts", _fake_cohort_loader)
    try:
        receipt = _receipt(wheel)
        projection = _validate(receipt, wheel)
        assert projection["schema"] == "arras.umf-actions-public-qualification/1"
        assert projection["qualification_phase"] == "release-build"
        assert "origins" not in projection
        assert "public_gate" not in projection
        assert projection["umf_wheel"]["document_version"] == "0.10.0"
    finally:
        monkeypatch.undo()


def test_release_receipt_binds_real_selector_to_wheel_pin_and_runtime(tmp_path: Path) -> None:
    wheel = tmp_path / "arras-0.6.0-py3-none-any.whl"
    _wheel(wheel)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_MODULE, "_cohorts", _real_cohort_loader)
    try:
        _validate(_receipt(wheel), wheel)
        wrong_pin = tmp_path / "arras-0.6.0-wrong-pin.whl"
        _wheel(wrong_pin, declared_sha="0" * 64)
        with pytest.raises(_MODULE.ActionReceiptError):
            _validate(_receipt(wrong_pin, declared_sha="0" * 64), wrong_pin)
        wrong_url = tmp_path / "arras-0.6.0-wrong-url.whl"
        _wheel(
            wrong_url,
            declared_url=_COHORT.url.replace("/umf-v0.6.0/", "/umf-v0.6.1/"),
        )
        with pytest.raises(_MODULE.ActionReceiptError):
            _validate(
                _receipt(
                    wrong_url,
                    declared_url=_COHORT.url.replace("/umf-v0.6.0/", "/umf-v0.6.1/"),
                ),
                wrong_url,
            )
        wrong_host = _receipt(wheel)
        wrong_host["runtime"]["machine"] = "x86_64"
        with pytest.raises(_MODULE.ActionReceiptError):
            _validate(wrong_host, wheel)
    finally:
        monkeypatch.undo()


def test_selector_rejects_mixed_action_capability_declarations() -> None:
    linux = SimpleNamespace(
        cohort_id="umf-core-0.10.1-linux",
        distribution_version="0.10.1",
        document_version="0.10.0",
        platform="linux",
        machine="x86_64",
        filename="umf_core-0.10.1-cp311-abi3-manylinux.whl",
        url="https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.6.0/umf_core-0.10.1-cp311-abi3-manylinux.whl",
        sha256="9" * 64,
        supports_single_set=False,
    )
    metadata = Message()
    for cohort in (_COHORT, linux):
        metadata.add_header(
            "Requires-Dist",
            f"umf-core @ {cohort.url}#sha256={cohort.sha256} ; extra == 'umf' and "
            f"sys_platform == '{cohort.platform}' and platform_machine == '{cohort.machine}'",
        )
    with pytest.raises(ValueError, match="disagree on action capability"):
        _SELECTOR.single_set_capability(metadata, registry=(_COHORT, linux))


@pytest.mark.parametrize(
    "mutation",
    _INVALID_RECEIPT_MUTATIONS,
)
def test_release_projection_rejects_unqualified_or_malformed_raw_receipt(
    tmp_path: Path, mutation: Any
) -> None:
    wheel = tmp_path / "arras-0.6.0-py3-none-any.whl"
    _wheel(wheel)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_MODULE, "_cohorts", _fake_cohort_loader)
    try:
        receipt = _receipt(wheel)
        mutation(receipt)
        with pytest.raises(_MODULE.ActionReceiptError):
            _validate(receipt, wheel)
    finally:
        monkeypatch.undo()


def test_public_projection_is_bound_to_phase_and_arras_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "arras-0.6.0-py3-none-any.whl"
    _wheel(wheel)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_MODULE, "_cohorts", _fake_cohort_loader)
    try:
        projection = _validate(_receipt(wheel), wheel)
        checked = _MODULE.validate_public_projection(
            projection,
            version="0.6.0",
            wheel_name=wheel.name,
            wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
            phase="release-build",
            wheel_path=wheel,
            repository=ROOT,
        )
        assert checked["status"] == "passed"
        correct_wheel_sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with pytest.raises(_MODULE.ActionReceiptError):
            _MODULE.validate_public_projection(
                projection,
                version="0.6.0",
                wheel_name=wheel.name,
                wheel_sha256=correct_wheel_sha,
                phase="public-download",
                wheel_path=wheel,
                repository=ROOT,
            )
        with pytest.raises(_MODULE.ActionReceiptError):
            _MODULE.validate_public_projection(
                projection,
                version="0.6.0",
                wheel_name=wheel.name,
                wheel_sha256="0" * 64,
                phase="release-build",
                wheel_path=wheel,
                repository=ROOT,
            )
        with pytest.raises(_MODULE.ActionReceiptError):
            _MODULE.validate_public_projection(
                projection,
                version="0.6.0",
                wheel_name=wheel.name,
                wheel_sha256="0" * 64,
                phase="public-download",
                wheel_path=wheel,
                repository=ROOT,
            )
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize(
    ("field", "value"),
    [("resource_files", 0), ("native_files", 0), ("resource_files", True)],
)
def test_public_projection_requires_positive_typed_sdk_payload_counts(
    tmp_path: Path, field: str, value: object
) -> None:
    wheel = tmp_path / "arras-0.6.0-py3-none-any.whl"
    _wheel(wheel)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_MODULE, "_cohorts", _fake_cohort_loader)
    try:
        projection = _validate(_receipt(wheel), wheel)
        corrupted = copy.deepcopy(projection)
        corrupted["installed"]["umf_core"][field] = value
        with pytest.raises(_MODULE.ActionReceiptError):
            _MODULE.validate_public_projection(
                corrupted,
                version="0.6.0",
                wheel_name=wheel.name,
                wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
                phase="release-build",
                wheel_path=wheel,
                repository=ROOT,
            )
    finally:
        monkeypatch.undo()
