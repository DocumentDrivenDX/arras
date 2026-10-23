# SPDX-License-Identifier: MIT OR Apache-2.0
"""Offline controls for the installed action verifier's bounded input gates."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import importlib.util
import io
import sys
import types
import zipfile
from email.message import Message
from pathlib import Path
from typing import Any, Protocol

import pytest

_TOOL = Path(__file__).parents[1] / "tools" / "verify_umf_actions.py"
sys.path.insert(0, str(_TOOL.parent))
_SPEC = importlib.util.spec_from_file_location("verify_umf_actions", _TOOL)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
_COHORTS = importlib.import_module("_umf_sdk_cohorts")

_PROBE_PATH = _TOOL.with_name("_umf_actions_probe.py")
_PROBE_SPEC = importlib.util.spec_from_file_location("umf_actions_probe", _PROBE_PATH)
assert _PROBE_SPEC is not None and _PROBE_SPEC.loader is not None
_PROBE = importlib.util.module_from_spec(_PROBE_SPEC)
sys.modules[_PROBE_SPEC.name] = _PROBE
_PROBE_SPEC.loader.exec_module(_PROBE)


class _SDKCohort(Protocol):
    cohort_id: str
    distribution_version: str
    document_version: str
    platform: str
    machine: str
    filename: str
    url: str
    sha256: str


def _wheel(
    path: Path,
    name: str,
    version: str,
    filename: str,
    *,
    package_prefix: str | None = None,
) -> Path:
    dist = filename.removesuffix(".whl").replace("-", "_", 1) + ".dist-info"
    metadata = f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
    if name == "arras":
        metadata += (
            "Requires-Dist: graphql-core>=3.3,<3.4\n"
            "Requires-Dist: umf-core @ https://github.com/DocumentDrivenDX/umf/releases/download/"
            "umf-v0.5.4/umf_core-0.10.0-py3-none-any.whl#sha256="
            '49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9 ; extra == "umf"\n'
        )
    payload = {
        f"{dist}/METADATA": metadata.encode(),
        f"{(package_prefix or name.replace('-', '_'))}/__init__.py": b"# installed\n",
    }
    record_rows: list[list[str]] = []
    for member, data in payload.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record_rows.append([member, f"sha256={digest}", str(len(data))])
    record_name = f"{dist}/RECORD"
    record_rows.append([record_name, "", ""])
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(record_rows)
    payload[record_name] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in payload.items():
            archive.writestr(member, data)
    return path


def _valid_probe() -> dict[str, Any]:
    controls = {
        "arras_payload_record_parity",
        "umf_payload_record_parity",
        "imports_from_fresh_environment",
        "generated_client_apply_validate_vectors",
        "public_registration_and_import",
        "validate_has_no_public_state_change",
        "apply_and_read_at_least",
        "allowed_value_rejected_without_effect",
        "no_op_and_replay_stable",
        "current_access_denial_without_effect",
        "uncertain_response_not_retried",
        "corpus_reference_and_empty_registry_139",
    }
    names = {key: True for key in controls}
    digest = "a" * 64
    distribution = {
        "name": "arras",
        "version": "0.6.0",
        "payload_files": 1,
        "payload_sha256": digest,
        "record_matches": 1,
        "resource_files": 0,
        "resource_manifest_sha256": digest,
        "native_files": 0,
        "native_manifest_sha256": digest,
    }
    sdk = {**distribution, "name": "umf-core", "version": "0.10.0"}
    return {
        "status": "passed",
        "skipped": 0,
        "arras_wheel_sha256": "b" * 64,
        "umf_wheel_sha256": "c" * 64,
        "source_sha256": _MODULE._FIXTURE_HASHES["source.json"],
        "vectors_sha256": _MODULE._FIXTURE_HASHES["vectors.json"],
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
        "installed": {"arras": distribution, "umf_core": sdk},
        "generated_client_sha256": "d" * 64,
        "controls": names,
        "corpus": {"cases": 139, "reference_matches": 139, "empty_registry_matches": 139},
    }


def _validate_probe(probe: dict[str, Any]) -> dict[str, Any]:
    return _MODULE._validate_probe(
        probe,
        arras_sha="b" * 64,
        arras_version="0.6.0",
        sdk_sha="c" * 64,
        sdk_version="0.10.0",
    )


def test_wheel_metadata_checks_both_distribution_identities(tmp_path: Path) -> None:
    arras = _wheel(
        tmp_path / "arras-0.6.0-py3-none-any.whl", "arras", "0.6.0", "arras-0.6.0-py3-none-any.whl"
    )
    sdk = _wheel(
        tmp_path / "umf_core-0.10.0-cp311-abi3-macosx_11_0_arm64.whl",
        "umf-core",
        "0.10.0",
        "umf_core-0.10.0-cp311-abi3-macosx_11_0_arm64.whl",
    )
    assert _MODULE._metadata(arras, "arras")[0]["Version"] == "0.6.0"
    assert _MODULE._metadata(sdk, "umf-core")[0]["Name"] == "umf-core"
    with pytest.raises(_MODULE.VerificationError, match="unexpected-distribution"):
        _MODULE._metadata(sdk, "arras")


def test_sdk_distribution_uses_official_umf_import_package_prefix(tmp_path: Path) -> None:
    sdk = _wheel(
        tmp_path / "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        "umf-core",
        "0.10.1",
        "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
        package_prefix="umf",
    )

    payload, _record = _PROBE._wheel_payload(sdk, "umf-core")

    assert "umf/__init__.py" in payload


def test_wheel_payload_rejects_wrong_or_unknown_distribution_namespace(
    tmp_path: Path,
) -> None:
    wrong = _wheel(
        tmp_path / "wrong-namespace.whl",
        "umf-core",
        "0.10.1",
        "umf_core-0.10.1-cp311-abi3-macosx_11_0_arm64.whl",
    )
    with pytest.raises(_PROBE.ProbeError, match="package-payload-empty"):
        _PROBE._wheel_payload(wrong, "umf-core")

    known = _wheel(
        tmp_path / "known-namespace.whl",
        "arras",
        "0.6.0",
        "arras-0.6.0-py3-none-any.whl",
    )
    with pytest.raises(_PROBE.ProbeError, match="distribution-unsupported"):
        _PROBE._wheel_payload(known, "other-distribution")


def _install_import_path_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, outside_module: bool = False
) -> tuple[Path, Path, Path, Path]:
    working = tmp_path / "probe-cwd"
    prefix = working / "venv"
    site = prefix / "lib/python3.11/site-packages"
    stdlib = tmp_path / "stdlib"
    base = tmp_path / "base-python"
    working.mkdir()
    site.mkdir(parents=True)
    stdlib.mkdir()
    module_paths = {
        "arras": site / "arras/__init__.py",
        "umf": site / "umf/__init__.py",
        "umf.action_runtime": site / "umf/action_runtime.py",
        "umf.rust_codegen": (
            tmp_path / "source-checkout/umf/rust_codegen.py"
            if outside_module
            else site / "umf/rust_codegen.py"
        ),
    }

    def fake_import_module(name: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(__file__=str(module_paths[name]))

    def fake_get_paths() -> dict[str, str]:
        return {"purelib": str(site), "stdlib": str(stdlib), "platstdlib": str(stdlib)}

    def fake_get_config_var(_name: str) -> str:
        return "3.11"

    monkeypatch.setattr(_PROBE.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(_PROBE.sysconfig, "get_paths", fake_get_paths)
    monkeypatch.setattr(_PROBE.sysconfig, "get_config_var", fake_get_config_var)
    monkeypatch.setattr(
        _PROBE,
        "sys",
        types.SimpleNamespace(
            prefix=str(prefix),
            base_prefix=str(base),
            path=[str(site), str(stdlib), str(stdlib / "lib-dynload")],
        ),
    )
    monkeypatch.setattr(Path, "cwd", lambda: working)
    config = prefix / "pyvenv.cfg"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("include-system-site-packages = false\n", encoding="utf-8")
    return working, prefix, site, stdlib


def test_import_origins_inside_fresh_venv_under_probe_cwd_are_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_import_path_fixture(monkeypatch, tmp_path)

    origins = _PROBE._trusted_imports()

    assert origins == {
        "arras": "arras/__init__.py",
        "umf": "umf/__init__.py",
        "umf.action_runtime": "umf/action_runtime.py",
        "umf.rust_codegen": "umf/rust_codegen.py",
    }


def test_import_origin_outside_fresh_venv_checkout_path_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_import_path_fixture(monkeypatch, tmp_path, outside_module=True)

    with pytest.raises(_PROBE.ProbeError, match="module-origin-outside-fresh-site"):
        _PROBE._trusted_imports()


def test_checkout_import_path_outside_fresh_venv_or_stdlib_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _working, _prefix, _site, _stdlib = _install_import_path_fixture(monkeypatch, tmp_path)
    _PROBE.sys.path.append(str(tmp_path / "source-checkout"))

    with pytest.raises(_PROBE.ProbeError, match="external-import-path"):
        _PROBE._trusted_imports()


def test_public_extra_pin_rejects_malformed_shadow_dependency() -> None:
    metadata = Message()
    metadata["Requires-Dist"] = (
        "umf-core @ https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/"
        "umf_core-0.10.0-py3-none-any.whl#sha256="
        '49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9 ; extra == "umf"'
    )
    metadata["Requires-Dist"] = "umf-core>=0.10"
    with pytest.raises(ValueError, match="closed direct reference"):
        _COHORTS.select_sdk_cohort(metadata, platform="darwin", machine="arm64")


def _synthetic_cohorts() -> tuple[_SDKCohort, _SDKCohort]:
    return (
        _COHORTS.SDKCohort(
            "synthetic-linux",
            "0.10.1",
            "0.10.0",
            "linux",
            "x86_64",
            "umf_core-0.10.1-cp311-abi3-manylinux.whl",
            "https://github.com/example/umf/releases/download/test/"
            "umf_core-0.10.1-cp311-abi3-manylinux.whl",
            "1" * 64,
        ),
        _COHORTS.SDKCohort(
            "synthetic-darwin",
            "0.10.1",
            "0.10.0",
            "darwin",
            "arm64",
            "umf_core-0.10.1-cp311-abi3-macosx.whl",
            "https://github.com/example/umf/releases/download/test/"
            "umf_core-0.10.1-cp311-abi3-macosx.whl",
            "2" * 64,
        ),
    )


def _cohort_metadata(*cohorts: _SDKCohort) -> Message:
    metadata = Message()
    for row in cohorts:
        metadata["Requires-Dist"] = (
            f"umf-core @ {row.url}#sha256={row.sha256} ; extra == 'umf' and "
            f'platform_machine == "{row.machine}" and sys_platform == "{row.platform}"'
        )
    return metadata


@pytest.mark.parametrize(
    ("platform", "machine", "cohort_id"),
    [("linux", "x86_64", "synthetic-linux"), ("darwin", "arm64", "synthetic-darwin")],
)
def test_selector_accepts_only_matching_registered_platform_cohort(
    platform: str, machine: str, cohort_id: str
) -> None:
    selected = _COHORTS.select_sdk_cohort(
        _cohort_metadata(*_synthetic_cohorts()),
        platform=platform,
        machine=machine,
        registry=_synthetic_cohorts(),
    )
    assert selected.cohort_id == cohort_id
    assert selected.document_version == "0.10.0"


def test_selector_keeps_historical_pure_record_closed() -> None:
    metadata = Message()
    metadata["Requires-Dist"] = (
        "umf-core @ https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/"
        "umf_core-0.10.0-py3-none-any.whl#sha256="
        "49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9 ; extra == 'umf'"
    )
    selected = _COHORTS.select_sdk_cohort(metadata, platform="darwin", machine="arm64")
    assert selected.cohort_id == "umf-core-0.10.0-py3-none-any"
    assert selected.distribution_version == selected.document_version == "0.10.0"


@pytest.mark.parametrize(
    "extra_line",
    [
        "umf-core>=0.10.1 ; extra == 'umf'",
        "umf-core @ https://github.com/example/umf/releases/download/test/x.whl#sha256="
        + "1" * 64
        + " ; extra == 'umf' and python_version == '3.11'",
    ],
)
def test_selector_rejects_unknown_or_unqualified_declarations(extra_line: str) -> None:
    metadata = _cohort_metadata(*_synthetic_cohorts())
    metadata["Requires-Dist"] = extra_line
    with pytest.raises(ValueError):
        _COHORTS.select_sdk_cohort(
            metadata,
            platform="darwin",
            machine="arm64",
            registry=_synthetic_cohorts(),
        )


@pytest.mark.parametrize("alias", ["umf.core", "umf___core"])
def test_selector_rejects_pep503_normalized_shadow_names(alias: str) -> None:
    metadata = _cohort_metadata(*_synthetic_cohorts())
    metadata["Requires-Dist"] = f"{alias}>=0.10.1 ; extra == 'umf'"
    with pytest.raises(ValueError, match="closed direct reference"):
        _COHORTS.select_sdk_cohort(
            metadata,
            platform="darwin",
            machine="arm64",
            registry=_synthetic_cohorts(),
        )


def test_selector_does_not_casefold_marker_values() -> None:
    metadata = _cohort_metadata(*_synthetic_cohorts())
    declarations = metadata.get_all("Requires-Dist")
    assert declarations is not None and declarations
    metadata.replace_header(
        "Requires-Dist",
        declarations[0].replace('sys_platform == "linux"', 'sys_platform == "LINUX"'),
    )
    with pytest.raises(ValueError, match="marker atom is not supported"):
        _COHORTS.select_sdk_cohort(
            metadata,
            platform="darwin",
            machine="arm64",
            registry=_synthetic_cohorts(),
        )


def test_selector_rejects_overlapping_declarations_and_unsupported_hosts() -> None:
    first, second = _synthetic_cohorts()
    overlapping = (
        first,
        _COHORTS.SDKCohort(
            "synthetic-overlap",
            second.distribution_version,
            second.document_version,
            "linux",
            "x86_64",
            "umf_core-0.10.1-cp311-abi3-manylinux2.whl",
            "https://github.com/example/umf/releases/download/test/"
            "umf_core-0.10.1-cp311-abi3-manylinux2.whl",
            "3" * 64,
        ),
    )
    with pytest.raises(ValueError, match="overlap"):
        _COHORTS.select_sdk_cohort(
            _cohort_metadata(*overlapping),
            platform="linux",
            machine="x86_64",
            registry=overlapping,
        )
    with pytest.raises(ValueError, match="host platform is unsupported"):
        _COHORTS.select_sdk_cohort(
            _cohort_metadata(*_synthetic_cohorts()),
            platform="win32",
            machine="amd64",
            registry=_synthetic_cohorts(),
        )


def test_probe_schema_is_closed_and_binds_expected_artifacts() -> None:
    probe = _valid_probe()
    safe = _validate_probe(probe)
    assert safe["corpus"]["cases"] == 139
    assert safe["controls"]["uncertain_response_not_retried"] is True
    probe["raw_exception"] = "/private/path/token"
    with pytest.raises(_MODULE.VerificationError, match="probe-result-shape-invalid"):
        _validate_probe(probe)


def test_probe_rejects_false_success_control_after_commit_path() -> None:
    probe = _valid_probe()
    probe["controls"]["uncertain_response_not_retried"] = False
    with pytest.raises(_MODULE.VerificationError, match="control-inventory-or-corpus-incomplete"):
        _validate_probe(probe)


def test_probe_rejects_malformed_receipt_after_commit_control() -> None:
    probe = _valid_probe()
    probe["post_commit_diagnostic"] = "/private/tmp/raw-output"
    with pytest.raises(_MODULE.VerificationError, match="probe-result-shape-invalid"):
        _validate_probe(probe)


@pytest.mark.parametrize(
    "origin",
    ["/private/tmp/arras/__init__.py", "arras/../secret.py", "other/arras/__init__.py"],
)
def test_probe_rejects_non_environment_import_origins(origin: str) -> None:
    probe = _valid_probe()
    probe["origins"]["arras"] = origin
    with pytest.raises(_MODULE.VerificationError, match="probe-result-shape-invalid"):
        _validate_probe(probe)


def test_probe_rejects_arbitrary_external_import_alias() -> None:
    assert not _PROBE._trusted_sys_path_entry(
        Path("/private/tmp/shared-lib"),
        Path("/private/tmp/fresh-venv"),
        {Path("/usr/lib/python3.11")},
    )
    assert _PROBE._trusted_sys_path_entry(
        Path("/usr/lib/python3.11"), Path("/private/tmp/fresh-venv"), {Path("/usr/lib/python3.11")}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("skipped", 1), ("arras_wheel_sha256", "0" * 64), ("status", "passed-with-skips")],
)
def test_probe_refuses_skip_and_artifact_substitution(field: str, value: object) -> None:
    probe = _valid_probe()
    probe[field] = value
    with pytest.raises(_MODULE.VerificationError):
        _validate_probe(probe)


@pytest.mark.parametrize(
    ("distribution", "version"),
    [("arras", "0.6.1"), ("umf_core", "0.10.1")],
)
def test_probe_binds_installed_versions_to_selected_artifacts(
    distribution: str, version: str
) -> None:
    probe = _valid_probe()
    probe["installed"][distribution]["version"] = version
    with pytest.raises(_MODULE.VerificationError, match="control-inventory-or-corpus-incomplete"):
        _validate_probe(probe)


def test_receipt_publication_does_not_replace_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    target.write_bytes(b"preserve me")
    with pytest.raises(FileExistsError):
        _MODULE._write_receipt(target, {"status": "passed"})
    assert target.read_bytes() == b"preserve me"


def test_member_gate_rejects_path_escape() -> None:
    with pytest.raises(_MODULE.VerificationError, match="unsafe-member-path"):
        _MODULE._member("../escape.py")


def test_candidate_result_can_never_satisfy_public_gate(tmp_path: Path) -> None:
    gate = _MODULE._gate_fields(tmp_path / "candidate.whl", "c" * 64)
    assert gate == {
        "public_gate": False,
        "mode": "local-candidate",
        "candidate_override": {"sha256": "c" * 64, "public_gate": False},
    }
    with pytest.raises(_MODULE.VerificationError, match="candidate-digest-missing"):
        _MODULE._gate_fields(tmp_path / "candidate.whl", None)


def test_generated_client_digest_binds_file_contents() -> None:
    original = _PROBE._generated_manifest_sha([("actions.py", b"class Actions: pass\n")])
    changed = _PROBE._generated_manifest_sha([("actions.py", b"class Actions: fail\n")])
    assert original != changed
    assert original == _PROBE._generated_manifest_sha([("actions.py", b"class Actions: pass\n")])


def test_validation_result_requires_explicit_valid_true() -> None:
    runtime = types.ModuleType("actions_binding._runtime")
    runtime.__dict__["ValidationResult"] = type("ValidationResult", (), {"valid": True})
    sys.modules[runtime.__name__] = runtime
    generated = types.ModuleType("actions_binding")
    assert _PROBE._is_valid_validation_result(runtime.ValidationResult(), generated.__name__)
    assert not _PROBE._is_valid_validation_result(
        type("Claimed", (), {"valid": True})(), generated.__name__
    )
    assert not _PROBE._is_valid_validation_result(
        type("Wrong", (), {"valid": 1})(), generated.__name__
    )


def test_generated_actions_wrap_the_public_session_in_sync_client() -> None:
    class SyncClient:
        def __init__(self, session: object) -> None:
            self.session = session

    class SyncActions:
        def __init__(self, client: SyncClient) -> None:
            if type(client) is not SyncClient:
                raise TypeError("generated actions require SyncClient")
            self.client = client

    generated = types.SimpleNamespace(SyncClient=SyncClient, SyncActions=SyncActions)
    session = object()
    actions = _PROBE._sync_actions(session, generated)
    assert type(actions) is SyncActions
    assert type(actions.client) is SyncClient
    assert actions.client.session is session


def test_noop_requires_empty_receipt_counts_and_replay_content() -> None:
    class Receipt:
        status = "committed"
        created: tuple[object, ...] = ()
        changed: tuple[object, ...] = ()
        counts = {"created": 0, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0}

    receipt = Receipt()
    assert _PROBE._is_noop_receipt(receipt)
    receipt.counts = {"created": 1, "updated": 0, "deleted": 0, "linked": 0, "unlinked": 0}
    assert not _PROBE._is_noop_receipt(receipt)


def test_requirement_check_reports_historical_sdk_as_not_action_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wheel = _wheel(
        tmp_path / "arras-0.6.0-py3-none-any.whl",
        "arras",
        "0.6.0",
        "arras-0.6.0-py3-none-any.whl",
    )
    assert _MODULE.main(["--wheel", str(wheel), "--check-requirement"]) == 0
    assert capsys.readouterr().out.strip() == "false"
