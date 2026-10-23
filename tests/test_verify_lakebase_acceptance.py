# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest


def _load_tool(name: str, filename: str) -> Any:
    tools_path = Path(__file__).parents[1] / "tools"
    path = tools_path / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(tools_path))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


gate = _load_tool("lakebase_acceptance", "_lakebase_acceptance.py")
cli = _load_tool("lakebase_acceptance_cli", "verify_lakebase_acceptance.py")


def _target() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "lakebase",
        "auth_profile": "native-password",
        "target_id": "test-target",
        "provider_resource_id": "resource-123",
        "endpoint": {
            "host": "lakebase.test.invalid",
            "port": 5432,
            "database": "arras_lakebase_acceptance",
            "sslmode": "verify-full",
        },
        "expected": dict(gate.EXPECTED),
        "resources": {
            "database": "arras_lakebase_acceptance",
            "installation_schema": "truss",
            "ordinary_role_names": [
                "arras_acceptance_registrar",
                "arras_acceptance_writer",
                "arras_acceptance_reader",
                "arras_acceptance_denied",
            ],
            "tolerated_grantees": ["lakebase_operator"],
            "generated_installation_role_count": 2,
            "module_access": {
                "document_id": "arras-lakebase-qualification-v1",
                "source_sha256": gate.HARNESS_MODULE_SHA256,
                "reader_role": "arras_lakebase_reader",
                "writer_role": "arras_lakebase_writer",
                "auditor_role": "arras_lakebase_auditor",
            },
        },
        "requested_cases": list(gate.FULL_MANAGED_CASES),
    }


def _fixture() -> bytes:
    return (
        b"def build_sources(target):\n    raise RuntimeError('no service fixture')\n"
        b"def observe_provider():\n    return {}\n"
        b"def cleanup_owned():\n    return []\n"
        b"def observe_native(connection):\n    return {}\n"
    )


def _input_files(tmp_path: Path) -> tuple[Path, Path, Path, Path, str]:
    target_path = tmp_path / "target.json"
    fixture_path = tmp_path / "fixture.py"
    authorization_path = tmp_path / "authorization.json"
    output_path = tmp_path / "receipt.json"
    target_raw = (json.dumps(_target(), sort_keys=True) + "\n").encode()
    fixture_raw = _fixture()
    target_path.write_bytes(target_raw)
    fixture_path.write_bytes(fixture_raw)
    authorization = {
        "schema_version": 1,
        "auth_profile": "native-password",
        "authorized_module_access": _target()["resources"]["module_access"],
        "target_sha256": hashlib.sha256(target_raw).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture_raw).hexdigest(),
        "request_reference": "test-only-no-authorization",
        "authorized_resource_id": "resource-123",
        "authorized_database": "arras_lakebase_acceptance",
        "authorized_schema": "truss",
        "authorized_ordinary_roles": [
            "arras_acceptance_registrar",
            "arras_acceptance_writer",
            "arras_acceptance_reader",
            "arras_acceptance_denied",
        ],
        "allow_generated_installation_roles": True,
        "allowed_operations": sorted(gate.OPERATIONS),
        "allowed_cases": list(gate.FULL_MANAGED_CASES),
    }
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    return (
        target_path,
        authorization_path,
        fixture_path,
        output_path,
        hashlib.sha256(fixture_raw).hexdigest(),
    )


def _validate(tmp_path: Path, scope: str = "full-managed") -> Any:
    target, auth, fixture, output, digest = _input_files(tmp_path)
    return gate.validate_inputs(target, auth, fixture, digest, output, scope=scope)


def test_exact_closed_inputs_admit_only_the_requested_scope_without_importing_fixture(
    tmp_path: Path,
) -> None:
    inputs = _validate(tmp_path)
    assert inputs.required_cases == gate.FULL_MANAGED_CASES
    assert inputs.scope == "full-managed"
    assert inputs.fixture_bytes == _fixture()
    assert (
        inputs.target_sha256 == hashlib.sha256((tmp_path / "target.json").read_bytes()).hexdigest()
    )
    assert not (tmp_path / "receipt.json").exists()


def test_cli_default_writes_blocked_not_run_without_importing_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target, auth, fixture, output, digest = _input_files(tmp_path)

    def unexpected_fixture_import(*_args: object) -> NoReturn:
        pytest.fail("default invocation must not import the fixture")

    monkeypatch.setattr(cli, "load_trusted_fixture", unexpected_fixture_import)
    result = cli.main(
        [
            "--target-json",
            str(target),
            "--authorization-json",
            str(auth),
            "--fixture",
            str(fixture),
            "--fixture-sha256",
            digest,
            "--output-json",
            str(output),
        ]
    )
    assert result == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "arras.lakebase-qualification/1"
    assert report["status"] == "blocked"
    assert report["managed_gate"] == "not_run"
    assert [case["case"] for case in report["cases"]] == list(gate.FULL_MANAGED_CASES)
    assert {case["status"] for case in report["cases"]} == {"not_run"}
    assert "blocked" in capsys.readouterr().out


def test_missing_one_control_does_not_reject_other_authorized_cases(tmp_path: Path) -> None:
    target, auth, fixture, output, digest = _input_files(tmp_path)
    authorization = json.loads(auth.read_text(encoding="utf-8"))
    authorization["allowed_operations"].remove("restart")
    auth.write_text(json.dumps(authorization), encoding="utf-8")
    inputs = gate.validate_inputs(target, auth, fixture, digest, output, scope="full-managed")
    assert inputs.required_cases == gate.FULL_MANAGED_CASES
    assert "restart" not in inputs.authorization["allowed_operations"]


mutations: list[Callable[[dict[str, Any]], object]] = [
    lambda target: target.update(provider="postgresql"),
    lambda target: target["expected"].update(postgres_version_num="180005"),
    lambda target: target["expected"].update(truss_wheel_sha256="0" * 64),
    lambda target: target["resources"].update(installation_schema="scratch"),
    lambda target: target["resources"].update(generated_installation_role_count=1),
    lambda target: target.update(requested_cases=list(gate.BASELINE_CASES)),
    lambda target: target.update(unknown_target_field=True),
]


@pytest.mark.parametrize("mutation", mutations)
def test_target_mismatch_refuses_before_any_fixture_import_or_output(
    tmp_path: Path, mutation: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_path, auth_path, fixture_path, output_path, digest = _input_files(tmp_path)
    target = _target()
    mutation(target)
    target_path.write_text(json.dumps(target), encoding="utf-8")

    def unexpected_fixture_import(*_args: object) -> NoReturn:
        pytest.fail("fixture imported")

    monkeypatch.setattr(gate, "load_trusted_fixture", unexpected_fixture_import)
    with pytest.raises(gate.AdmissionError):
        gate.validate_inputs(
            target_path, auth_path, fixture_path, digest, output_path, scope="full-managed"
        )
    assert not output_path.exists()


def test_authorization_digest_and_fixed_role_boundary_are_exact(tmp_path: Path) -> None:
    target, auth_path, fixture, output, digest = _input_files(tmp_path)
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization["authorized_resource_id"] = "another-resource"
    auth_path.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(gate.AdmissionError, match="provider resource mismatch"):
        gate.validate_inputs(target, auth_path, fixture, digest, output, scope="baseline")


def test_module_access_role_custody_is_closed_and_bound_by_authorization(tmp_path: Path) -> None:
    target, auth_path, fixture, output, digest = _input_files(tmp_path)
    value = _target()
    value["resources"]["module_access"]["reader_role"] = value["resources"]["ordinary_role_names"][
        0
    ]
    target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(gate.AdmissionError, match="distinct from actors"):
        gate.validate_inputs(target, auth_path, fixture, digest, output, scope="baseline")

    target.write_text(json.dumps(_target()), encoding="utf-8")
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization["authorized_module_access"]["writer_role"] = "arras_other_writer"
    auth_path.write_text(json.dumps(authorization), encoding="utf-8")
    target.write_text(json.dumps(_target(), sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(gate.AdmissionError, match="module access mismatch"):
        gate.validate_inputs(target, auth_path, fixture, digest, output, scope="baseline")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":1,"x":NaN}',
        b"\xff",
    ],
)
def test_strict_json_rejects_ambiguous_or_non_json_values(raw: bytes) -> None:
    with pytest.raises(gate.AdmissionError):
        gate._strict_json(raw, "target")


def test_receipt_publication_never_overwrites_a_concurrent_path(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("owner-created sentinel", encoding="utf-8")
    with pytest.raises(FileExistsError):
        gate.write_receipt(output, {"status": "blocked"})
    assert output.read_text(encoding="utf-8") == "owner-created sentinel"


def test_input_symlink_and_hardlink_aliases_refuse(tmp_path: Path) -> None:
    target, auth, fixture, output, digest = _input_files(tmp_path)
    alias = tmp_path / "target-link.json"
    alias.symlink_to(target)
    with pytest.raises(gate.AdmissionError):
        gate.validate_inputs(alias, auth, fixture, digest, output, scope="baseline")

    hardlink = tmp_path / "target-hardlink.json"
    os.link(target, hardlink)
    with pytest.raises(gate.AdmissionError, match="aliases"):
        gate.validate_inputs(target, auth, fixture, digest, hardlink, scope="baseline")


def test_bounded_input_reader_refuses_fifo_without_waiting_for_a_writer(tmp_path: Path) -> None:
    fifo = tmp_path / "target.pipe"
    os.mkfifo(fifo)
    with pytest.raises(gate.AdmissionError, match="bounded regular file"):
        gate._regular_file(fifo, maximum=1024, label="target")


def test_fixture_executes_only_exact_admitted_bytes_and_never_receives_verdict_authority(
    tmp_path: Path,
) -> None:
    target, auth, fixture, output, digest = _input_files(tmp_path)
    inputs = gate.validate_inputs(target, auth, fixture, digest, output, scope="baseline")
    module = gate.load_trusted_fixture(inputs, fixture)
    assert callable(module.build_sources)
    assert callable(module.observe_provider)
    assert callable(module.cleanup_owned)
    assert callable(module.observe_native)
    assert callable(module.cleanup_owned)
    assert not hasattr(module, "case_results")
    fixture.write_text("raise RuntimeError('replacement')\n", encoding="utf-8")
    # Loading uses the exact bytes captured during admission, not a mutable path reread.
    reloaded = gate.load_trusted_fixture(inputs, fixture)
    assert callable(reloaded.build_sources)
    corrupted = dataclasses.replace(inputs, fixture_bytes=inputs.fixture_bytes + b"# changed")
    with pytest.raises(gate.AdmissionError, match="changed after admission"):
        gate.load_trusted_fixture(corrupted, fixture)


def _operation_result_with_partial_success(inputs: Any) -> dict[str, Any]:
    cases = [
        {
            "case": case,
            "status": "passed" if case == "LB-PERSON" else "blocked",
            "code": "write_roundtrip_verified" if case == "LB-PERSON" else "control_unavailable",
        }
        for case in inputs.required_cases
        if case != "LB-ADMISSION"
    ]
    return {
        "cases": cases,
        "observed": {
            "artifacts": {
                "truss_version": "0.0.49",
                "truss_wheel_sha256": None,
                "native_manifest_sha256": None,
                "migration_manifest_sha256": None,
                "evidence_codes": [],
            },
            "preconditions": {
                "truss_schema_absent": False,
                "status_reason": "not_configured",
                "status_detail": "not_installed",
            },
            "operations": {
                "installation_ran": True,
                "registration": "passed",
                "access_configuration": "passed",
                "write": "passed",
                "read": "passed",
                "denial": "passed",
                "refreshed_connection": "blocked",
            },
            "acl": {
                "snapshot_before_sha256": None,
                "snapshot_after_sha256": None,
                "intended_memberships_match": None,
            },
            "strict_probe": {
                "outcome": "not_run",
                "object_class": None,
                "phase": None,
                "selected_role_sha256": None,
                "role_selected": None,
                "caller_state_unchanged": None,
                "native_state_unchanged": None,
            },
        },
        "cleanup": {
            "status": "blocked",
            "resources": [
                {
                    "resource_kind": "role",
                    "name_or_opaque_id": hashlib.sha256(b"arras_role_created").hexdigest(),
                    "removed": False,
                }
            ],
            "independent_absence": {
                "truss_schema_absent": None,
                "generated_roles_absent": None,
            },
        },
        "module_document_sha256": gate.HARNESS_MODULE_SHA256,
    }


def test_projection_failure_preserves_partial_execution_and_cleanup_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target, authorization, fixture, output, digest = _input_files(tmp_path)
    inputs = gate.validate_inputs(
        target, authorization, fixture, digest, output, scope="full-managed"
    )
    operation_result = _operation_result_with_partial_success(inputs)

    def fail_projection(_inputs: Any, **_kwargs: Any) -> Any:
        raise gate.AdmissionError("deliberate projection control")

    monkeypatch.setattr(cli, "_execution_receipt", fail_projection)
    context = {
        "provider": {"resource_id": "resource-123", "observation_sha256": "a" * 64},
        "installer": {"role_sha256": "b" * 64},
        "role_facts": {},
        "provenance": {},
        "toolkit": "0.0.49",
        "weft": "0.4.51",
        "truss_status": type("Status", (), {"available": False})(),
        "operation_result": operation_result,
    }
    receipt = cli._execution_or_partial_failure(inputs, **context)
    assert receipt["status"] == "failed"
    assert receipt["managed_gate"] == "failed"
    assert next(row for row in receipt["cases"] if row["case"] == "LB-PERSON")["status"] == "passed"
    assert receipt["cleanup"]["status"] == "blocked"
    assert receipt["cleanup"]["resources"][0]["removed"] is False
    assert {row["status"] for row in receipt["cases"]} != {"not_run"}

    def partial_gate(_inputs: Any, _path: Path) -> dict[str, Any]:
        return cli._execution_or_partial_failure(inputs, **context)

    monkeypatch.setattr(cli, "_run_fixture_gate", partial_gate)
    code = cli.main(
        [
            "--target-json",
            str(target),
            "--authorization-json",
            str(authorization),
            "--fixture",
            str(fixture),
            "--fixture-sha256",
            digest,
            "--output-json",
            str(output),
            "--execute",
        ]
    )
    assert code == 1
    published = json.loads(output.read_text(encoding="utf-8"))
    assert published["status"] == "failed"
    assert (
        next(row for row in published["cases"] if row["case"] == "LB-PERSON")["status"] == "passed"
    )
    assert published["cleanup"]["status"] == "blocked"


@pytest.mark.parametrize("value", ["TLSv1.3\nsecret-host", "TLSv1.3\x00", "bad"])
def test_tls_protocol_observation_rejects_unsafe_tokens(value: str) -> None:
    with pytest.raises(cli.AdmissionError, match="safe token"):
        cli._tls_token(value, "protocol", r"TLSv[0-9]+\.[0-9]+", 16)


@pytest.mark.parametrize("value", ["TLS_AES_256_GCM_SHA384", "ECDHE-RSA-AES256-GCM-SHA384"])
def test_tls_cipher_observation_preserves_safe_driver_value(value: str) -> None:
    assert cli._tls_token(value, "cipher", r"[A-Za-z0-9_.+-]+", 128) == value
