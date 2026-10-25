# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run the separately authorized Lakebase acceptance harness.

Input validation is offline and completes before the selected fixture is imported. Without
``--execute`` the command emits a blocked, not-run receipt and does not import the fixture or
load PostgreSQL/Truss. Service execution requires the explicit owner-provided target,
authorization, and fixture inputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

from _lakebase_acceptance import (
    EXPECTED,
    PERSON_LABELS,
    AdmissionError,
    Inputs,
    actor_auth_profiles,
    load_trusted_fixture,
    safe_case,
    validate_inputs,
    write_receipt,
)
from _lakebase_person import safe_person_observations
from _lakebase_receipts import _safe_operation_observations, validate_managed_case_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-json", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--fixture-sha256", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--scope", choices=("baseline", "full-managed"), default="full-managed")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="permit the authorized fixture to run after all offline gates pass",
    )
    return parser


def _not_run_cases(inputs: Inputs, reason: str) -> list[dict[str, str]]:
    return [safe_case(case, "not_run", reason) for case in inputs.required_cases]


def _operation_case_rows(inputs: Inputs, operation_result: dict[str, Any]) -> list[dict[str, str]]:
    operation_cases = operation_result["cases"]
    if type(operation_cases) is not list:
        raise AdmissionError("operation runner case results must be a list")
    expected = [case for case in inputs.required_cases if case != "LB-ADMISSION"]
    if len(operation_cases) != len(expected):
        raise AdmissionError("operation runner omitted a required case result")
    rows = [safe_case("LB-ADMISSION", "passed", "identity_tls_server_match")]
    for expected_case, row in zip(expected, operation_cases, strict=True):
        if type(row) is not dict or set(row) != {"case", "status", "code"}:
            raise AdmissionError("operation runner returned an invalid case row")
        rows.append(safe_case(row["case"], row["status"], row["code"]))
        if rows[-1]["case"] != expected_case:
            raise AdmissionError("operation runner case order differs from the fixed inventory")
    return rows


def _validate_strict_install_evidence(
    inputs: Inputs, observed: dict[str, Any], rows: list[dict[str, str]]
) -> None:
    strict_probe = observed["strict_probe"]
    tolerated = inputs.target["resources"]["tolerated_grantees"]
    allowed_hashes = {hashlib.sha256(role.encode("utf-8")).hexdigest() for role in tolerated}
    selected_hash = strict_probe["selected_role_sha256"]
    if selected_hash is not None and strict_probe["role_selected"] is not (
        selected_hash in allowed_hashes
    ):
        raise AdmissionError("strict install role match differs from the authorized selected role")
    if selected_hash is None and strict_probe["role_selected"] is True:
        raise AdmissionError("strict install role match lacks a bounded selected-role digest")
    install = next((row for row in rows if row["case"] == "LB-INSTALL"), None)
    if (
        install is not None
        and install["status"] == "passed"
        and (
            strict_probe["outcome"] != "typed_refusal"
            or strict_probe["role_selected"] is not True
            or selected_hash is None
            or strict_probe["caller_state_unchanged"] is not True
            or strict_probe["native_state_unchanged"] is not True
            or observed["operations"]["installation_ran"] is not True
        )
    ):
        raise AdmissionError(
            "install case lacks the exact strict-refusal and selected-install evidence"
        )


def _validate_cleanup(inputs: Inputs, cleanup: object) -> dict[str, Any]:
    if type(cleanup) is not dict or set(cleanup) != {"status", "resources", "independent_absence"}:
        raise AdmissionError("operation runner cleanup facts have an unexpected shape")
    if type(cleanup["status"]) is not str or cleanup["status"] not in {
        "passed",
        "blocked",
        "failed",
    }:
        raise AdmissionError("operation runner cleanup status is invalid")
    if type(cleanup["resources"]) is not list:
        raise AdmissionError("operation runner cleanup resources must be a list")
    identities: set[tuple[str, str]] = set()
    for item in cleanup["resources"]:
        if type(item) is not dict or set(item) != {"resource_kind", "name_or_opaque_id", "removed"}:
            raise AdmissionError("operation runner cleanup entry has an unexpected shape")
        if type(item["resource_kind"]) is not str or type(item["name_or_opaque_id"]) is not str:
            raise AdmissionError("operation runner cleanup resource identity is invalid")
        if type(item["removed"]) is not bool or item["resource_kind"] not in {"schema", "role"}:
            raise AdmissionError("operation runner cleanup fact is outside the owned scope")
        _require_digest(item["name_or_opaque_id"], "cleanup resource identity")
        identity = (item["resource_kind"], item["name_or_opaque_id"])
        if identity in identities:
            raise AdmissionError("operation runner cleanup resource set contains duplicates")
        identities.add(identity)
    expected_schema = hashlib.sha256(
        inputs.target["resources"]["installation_schema"].encode("utf-8")
    ).hexdigest()
    access = inputs.target["resources"]["module_access"]
    roles = ("reader_role", "writer_role", *(("auditor_role",) if "auditor_role" in access else ()))
    expected_groups = {hashlib.sha256(access[key].encode("utf-8")).hexdigest() for key in roles}
    schemas = {item for item in identities if item[0] == "schema"}
    role_hashes = {digest for kind, digest in identities if kind == "role"}
    provided_groups = role_hashes & expected_groups
    if (
        len(identities) > 1 + len(expected_groups) + 2
        or any(item != ("schema", expected_schema) for item in schemas)
        or len(role_hashes - expected_groups) > 2
        or cleanup["status"] == "passed"
        and (
            schemas != {("schema", expected_schema)}
            or provided_groups not in (set(), expected_groups)
            or len(role_hashes) != len(provided_groups) + 2
        )
    ):
        raise AdmissionError(
            "operation runner cleanup set differs from the exact owned resource scope"
        )
    absence = cleanup["independent_absence"]
    if type(absence) is not dict or set(absence) != {
        "truss_schema_absent",
        "generated_roles_absent",
    }:
        raise AdmissionError("operation runner independent cleanup facts have an unexpected shape")
    if any(value is not None and type(value) is not bool for value in absence.values()):
        raise AdmissionError("operation runner independent cleanup fact is invalid")
    return cleanup


def _partial_execution_failure(
    inputs: Inputs,
    *,
    provider: dict[str, Any],
    installer: dict[str, Any],
    role_facts: dict[str, Any],
    provenance: dict[str, Any],
    toolkit: str,
    weft: str,
    truss_status: Any,
    operation_result: dict[str, Any],
) -> dict[str, Any]:
    receipt = _blocked_receipt(inputs, execute=True)
    try:
        rows = _operation_case_rows(inputs, operation_result)
    except Exception:
        rows = [safe_case("LB-ADMISSION", "passed", "identity_tls_server_match")]
        rows.extend(
            safe_case(case, "blocked", "execution_result_unavailable")
            for case in inputs.required_cases
            if case != "LB-ADMISSION"
        )
    managed_evidence_valid = False
    try:
        observed = _safe_operation_observations(operation_result["observed"])
        validate_managed_case_evidence(rows, observed.get("managed"))
        managed_evidence_valid = True
    except Exception:
        observed = {}
    if not managed_evidence_valid:
        managed_cases = set(inputs.required_cases) - {"LB-ADMISSION", "LB-INSTALL", "LB-PERSON"}
        rows = [
            safe_case(row["case"], "blocked", "managed_evidence_projection_failed")
            if row["case"] in managed_cases and row["status"] == "passed"
            else row
            for row in rows
        ]
    # A projection failure cannot preserve an install pass without revalidating the strict probe.
    rows = [
        safe_case(row["case"], "blocked", "receipt_projection_failed")
        if row["case"] == "LB-INSTALL" and row["status"] == "passed"
        else row
        for row in rows
    ]
    try:
        cleanup = _validate_cleanup(inputs, operation_result.get("cleanup"))
    except Exception:
        cleanup = {
            "status": "blocked",
            "resources": [],
            "independent_absence": {
                "truss_schema_absent": None,
                "generated_roles_absent": None,
            },
        }
    safe_observed = {
        "provider_resource_sha256": hashlib.sha256(
            provider["resource_id"].encode("utf-8")
        ).hexdigest(),
        "provider_observation_sha256": provider["observation_sha256"],
        "installer": installer,
        "ordinary_roles": role_facts,
        "credential_source_provenance": provenance,
        "installed_truss_version": toolkit,
        "installed_weft_version": weft,
        "truss_installed_before_run": truss_status.available,
        "module_document_sha256": inputs.target["resources"]["module_access"]["source_sha256"],
        "operations": observed,
    }
    receipt.update(
        {
            "status": "failed",
            "managed_gate": "failed" if inputs.scope == "full-managed" else "not_run",
            "authentication_profile": inputs.target["auth_profile"],
            "cases": rows,
            "observed": safe_observed,
            "cleanup": cleanup,
            "gate_blockers": ["receipt_projection_failed_after_execution"],
            "qualification_note": (
                "Execution was attempted but receipt projection failed; overall status is failed."
            ),
        }
    )
    return receipt


def _execution_or_partial_failure(
    inputs: Inputs,
    *,
    provider: dict[str, Any],
    installer: dict[str, Any],
    role_facts: dict[str, Any],
    provenance: dict[str, Any],
    toolkit: str,
    weft: str,
    truss_status: Any,
    operation_result: dict[str, Any],
) -> dict[str, Any]:
    arguments = {
        "provider": provider,
        "installer": installer,
        "role_facts": role_facts,
        "provenance": provenance,
        "toolkit": toolkit,
        "weft": weft,
        "truss_status": truss_status,
        "operation_result": operation_result,
    }
    try:
        return _execution_receipt(inputs, **arguments)
    except BaseException:
        return _partial_execution_failure(inputs, **arguments)


def _execution_receipt(
    inputs: Inputs,
    *,
    provider: dict[str, Any],
    installer: dict[str, Any],
    role_facts: dict[str, Any],
    provenance: dict[str, Any],
    toolkit: str,
    weft: str,
    truss_status: Any,
    operation_result: dict[str, Any],
) -> dict[str, Any]:
    from _lakebase_operations import HARNESS_MODULE_SHA256

    expected_keys = {"cases", "observed", "cleanup", "module_document_sha256"}
    if type(operation_result) is not dict or set(operation_result) != expected_keys:
        raise AdmissionError("operation runner returned an unexpected result shape")
    if operation_result["module_document_sha256"] != HARNESS_MODULE_SHA256:
        raise AdmissionError("operation runner module document digest mismatch")
    rows = _operation_case_rows(inputs, operation_result)
    observed = _safe_operation_observations(operation_result["observed"])
    validate_managed_case_evidence(rows, observed.get("managed"))
    person_facts = operation_result["observed"].get("person")
    person_row = next((row for row in rows if row["case"] == "LB-PERSON"), None)
    person_proof_complete = False
    if (
        inputs.target["schema_version"] == 2
        and person_row is not None
        and person_row["status"] == "passed"
    ):
        if type(person_facts) is not dict:
            raise AdmissionError("human person pass lacks closed identity lifecycle facts")
        try:
            person_facts = safe_person_observations(
                person_facts,
                target=inputs.target,
                authorization=inputs.authorization,
                provider_observation_sha256=provider["observation_sha256"],
                role_sha256_by_actor={
                    label: role_facts[label]["role_sha256"] for label in PERSON_LABELS
                },
            )
        except Exception:
            raise AdmissionError(
                "human person identity facts do not match admission evidence"
            ) from None
        person_proof_complete = True
    _validate_strict_install_evidence(inputs, observed, rows)
    cleanup = _validate_cleanup(inputs, operation_result["cleanup"])
    safe_observed = {
        "provider_resource_sha256": hashlib.sha256(
            provider["resource_id"].encode("utf-8")
        ).hexdigest(),
        "provider_observation_sha256": provider["observation_sha256"],
        "installer": installer,
        "ordinary_roles": role_facts,
        "credential_source_provenance": provenance,
        "installed_truss_version": toolkit,
        "installed_weft_version": weft,
        "truss_installed_before_run": truss_status.available,
        "module_document_sha256": HARNESS_MODULE_SHA256,
        "operations": observed,
    }
    artifact_facts = observed["artifacts"]
    artifact_provenance_complete = (
        type(artifact_facts) is dict
        and artifact_facts.get("truss_wheel_sha256")
        == inputs.target["expected"]["truss_wheel_sha256"]
        and artifact_facts.get("native_manifest_sha256")
        == inputs.target["expected"]["native_manifest_sha256"]
        and artifact_facts.get("migration_manifest_sha256")
        == inputs.target["expected"]["migration_manifest_sha256"]
    )
    case_failed = any(row["status"] == "failed" for row in rows)
    case_blocked = any(row["status"] != "passed" for row in rows)
    blockers = [] if artifact_provenance_complete else ["installed_artifact_provenance_unavailable"]
    if inputs.target["schema_version"] != 2 and inputs.target["auth_profile"] in {
        "human-oauth",
        "nonhuman-oauth",
    }:
        blockers.append("oauth_subject_evidence_unavailable")
    if inputs.target["schema_version"] == 2 and not person_proof_complete:
        blockers.append("human_writer_identity_lifecycle_unverified")
    passed = not case_failed and not case_blocked and cleanup["status"] == "passed" and not blockers
    status = (
        "passed"
        if passed
        else "failed"
        if case_failed or cleanup["status"] == "failed"
        else "blocked"
    )
    managed_gate = (
        "not_run"
        if inputs.scope == "baseline"
        else "passed"
        if passed
        else "failed"
        if status == "failed"
        else "blocked"
    )
    receipt = _blocked_receipt(inputs, execute=True)
    receipt.update(
        {
            "status": status,
            "managed_gate": managed_gate,
            "authentication_profile": inputs.target["auth_profile"],
            "cases": rows,
            "observed": safe_observed,
            "cleanup": cleanup,
            "gate_blockers": blockers,
            "qualification_note": (
                "Results are limited to the authorized target, observed artifacts, and exact selected scope."
            ),
        }
    )
    return receipt


_CASE_OPERATIONS: dict[str, frozenset[str]] = {
    "LB-ADMISSION": frozenset({"read"}),
    "LB-INSTALL": frozenset({"read", "install", "cleanup"}),
    "LB-PERSON": frozenset(
        {"read", "apply", "refresh", "revoke_owned_memberships", "expire_owned_login"}
    ),
    "LB-CUSTODY": frozenset({"read", "apply"}),
    "LB-SETTLEMENT": frozenset({"read", "apply", "fault"}),
    "LB-ACL": frozenset(
        {
            "read",
            "install",
            "configure",
            "provision_module_roles",
            "prepare_owned_access_roles",
            "grant_owned_memberships",
            "revoke_owned_memberships",
        }
    ),
    "MP-01": frozenset({"read", "apply", "feed", "refresh", "restart"}),
    "MP-02": frozenset({"read", "refresh"}),
    "MP-03": frozenset({"read", "install"}),
    "MP-04": frozenset({"read", "feed", "refresh", "restart"}),
    "MP-05": frozenset({"read", "apply", "fault"}),
    "MP-06": frozenset({"read", "install", "configure"}),
}


def _blocked_receipt(inputs: Inputs, *, execute: bool) -> dict[str, Any]:
    reason = "execution_not_requested" if not execute else "service_fixture_not_ready"
    return {
        "schema": "arras.lakebase-qualification/1",
        "status": "blocked",
        "scope": inputs.scope,
        "managed_gate": "not_run",
        "target_sha256": inputs.target_sha256,
        "authorization_sha256": inputs.authorization_sha256,
        "fixture_sha256": inputs.fixture_sha256,
        "harness_sha256": _harness_sha256(),
        "authentication_profile": "unobserved",
        "request_reference_sha256": hashlib.sha256(
            inputs.authorization["request_reference"].encode("utf-8")
        ).hexdigest(),
        "expected": dict(EXPECTED),
        "required_cases": list(inputs.required_cases),
        "cases": _not_run_cases(inputs, reason),
        "cleanup": {"status": "not_attempted"},
        "qualification_note": (
            "No managed-service result is asserted; all required cases remain not_run."
        ),
    }


def _harness_sha256() -> str:
    digest = hashlib.sha256()
    for source in (
        Path(__file__),
        Path(__file__).with_name("_lakebase_acceptance.py"),
        Path(__file__).with_name("_lakebase_operations.py"),
        Path(__file__).with_name("_lakebase_native.py"),
        Path(__file__).with_name("_lakebase_receipts.py"),
        Path(__file__).with_name("_lakebase_person.py"),
        Path(__file__).with_name("_lakebase_managed.py"),
        Path(__file__).with_name("_lakebase_managed_access.py"),
        Path(__file__).with_name("_lakebase_managed_common.py"),
        Path(__file__).with_name("_lakebase_managed_feed.py"),
        Path(__file__).with_name("_lakebase_managed_feed_carriers.py"),
        Path(__file__).with_name("_lakebase_managed_feed_cases.py"),
        Path(__file__).with_name("_lakebase_managed_feed_codec.py"),
        Path(__file__).with_name("_lakebase_managed_feed_destination.py"),
        Path(__file__).with_name("_lakebase_managed_feed_pages.py"),
        Path(__file__).with_name("_lakebase_managed_feed_probe.py"),
        Path(__file__).with_name("_lakebase_managed_feed_revisions.py"),
        Path(__file__).with_name("_lakebase_managed_identity.py"),
        Path(__file__).with_name("_lakebase_managed_lifecycle.py"),
        Path(__file__).with_name("_lakebase_managed_native.py"),
        Path(__file__).with_name("_lakebase_managed_public.py"),
    ):
        data = source.read_bytes()
        digest.update(source.name.encode("ascii"))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _admit_fixture_sources(
    inputs: Inputs, fixture_path: Path
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    module = load_trusted_fixture(inputs, fixture_path)
    # The current contract requires separate installer/person sources, a principal factory,
    # refresh callback, and provider/native factual observers. These are capabilities, not verdicts.
    try:
        sources = module.build_sources(copy.deepcopy(inputs.target))
    except Exception:
        raise AdmissionError(
            "trusted fixture could not provide authorized connection sources"
        ) from None
    required = {
        "installer_connection_source",
        "person_connection_source",
        "principal_for",
        "refresh_principal",
    }
    if type(sources) is not dict or set(sources) != required:
        raise AdmissionError("trusted fixture connection-source contract is incomplete")
    if any(not callable(sources[name]) for name in required):
        raise AdmissionError("trusted fixture connection-source contract is invalid")
    provider = module.observe_provider()
    provider_keys = {
        "provider",
        "resource_id",
        "endpoint_sha256",
        "observation_source",
        "observation_sha256",
    }
    if type(provider) is not dict or set(provider) != provider_keys:
        raise AdmissionError("provider observer returned an unexpected fact shape")
    if (
        provider["provider"] != "lakebase"
        or provider["resource_id"] != inputs.target["provider_resource_id"]
        or provider["observation_source"] != "databricks-cli"
        or provider["endpoint_sha256"] != _endpoint_sha256(inputs.target["endpoint"])
    ):
        raise AdmissionError("provider identity does not match the authorized target")
    for key in ("endpoint_sha256", "observation_sha256"):
        _require_digest(provider[key], f"provider {key}")
    if not callable(getattr(module, "credential_provenance", None)):
        raise AdmissionError("trusted fixture lacks credential-source provenance")
    provenance = {
        label: _credential_fact(
            module.credential_provenance(label),
            inputs,
            provider,
            label=label,
        )
        for label in PERSON_LABELS
    }

    return module, sources, provider, provenance


def _observe_database_admission(
    inputs: Inputs, module: Any, sources: dict[str, Any]
) -> dict[str, Any]:
    # This function is reached only after input and fixture admission. Driver imports remain below.
    try:
        with sources["installer_connection_source"]() as connection:
            installer = _observe_connection(connection, inputs.target, expected_role=None)
            if installer["role_sha256"] in {
                hashlib.sha256(role.encode("utf-8")).hexdigest()
                for role in inputs.target["resources"]["ordinary_role_names"]
            }:
                raise AdmissionError("installer session cannot reuse an ordinary person role")
            native_observer = getattr(module, "observe_native", None)
            native_facts = (
                _validate_native_facts(native_observer(connection))
                if callable(native_observer)
                else {}
            )
        role_facts: dict[str, Any] = {}
        ordinary_roles = tuple(inputs.target["resources"]["ordinary_role_names"])
        for label, role in zip(PERSON_LABELS, ordinary_roles, strict=True):
            principal = sources["principal_for"](label)
            from arras.types import Principal

            if (
                type(principal) is not Principal
                or principal.user != role
                or type(principal.token) is not str
                or not principal.token
            ):
                raise AdmissionError("ordinary principal does not match its authorized role")
            with sources["person_connection_source"](principal) as connection:
                role_facts[label] = _observe_connection(
                    connection, inputs.target, expected_role=role
                )
        toolkit = importlib.metadata.version("truss-toolkit")
        weft = importlib.metadata.version("weft-sql")
        from arras.adapters.truss import create_backend, require_toolkit

        require_toolkit()
        backend = create_backend(
            "truss",
            sources["person_connection_source"],
            sources["installer_connection_source"],
            tolerated_grantees=tuple(inputs.target["resources"]["tolerated_grantees"]),
        )
        truss_status = backend.status()
    except AdmissionError:
        raise
    except Exception:
        raise AdmissionError("authorized service admission observation failed") from None
    if toolkit != inputs.target["expected"]["truss_version"]:
        raise AdmissionError("installed Truss toolkit differs from the authorized release")
    if weft != inputs.target["expected"]["weft_version"]:
        raise AdmissionError("installed Weft differs from the authorized release")
    if truss_status.available:
        raise AdmissionError("target already contains an installation not created by this run")
    if (
        truss_status.reason != "not_configured"
        or truss_status.detail != "Truss is not installed here"
    ):
        raise AdmissionError("Truss installation state is not safely readable")

    return {
        "installer": installer,
        "native_facts": native_facts,
        "role_facts": role_facts,
        "toolkit": toolkit,
        "weft": weft,
        "truss_status": truss_status,
    }


def _run_fixture_gate(inputs: Inputs, fixture_path: Path) -> dict[str, Any]:
    """Run independent provider, TLS, PostgreSQL and ordinary-login admission checks."""
    from _lakebase_operations import HARNESS_MODULE_SHA256, run_baseline

    if inputs.target["resources"]["module_access"]["source_sha256"] != HARNESS_MODULE_SHA256:
        raise AdmissionError("module source digest differs from the fixed harness document")
    module, sources, provider, provenance = _admit_fixture_sources(inputs, fixture_path)
    observed = _observe_database_admission(inputs, module, sources)
    operation_result = run_baseline(
        inputs,
        module,
        sources,
        admission={
            "provider_observation_sha256": provider["observation_sha256"],
            "ordinary_roles": observed["role_facts"],
        },
    )
    if type(operation_result) is not dict:
        raise AdmissionError("operation runner returned an invalid result")
    base = _execution_or_partial_failure(
        inputs,
        provider=provider,
        installer=observed["installer"],
        role_facts=observed["role_facts"],
        provenance=provenance,
        toolkit=observed["toolkit"],
        weft=observed["weft"],
        truss_status=observed["truss_status"],
        operation_result=operation_result,
    )
    base["observed"]["credential_source_provenance"] = provenance
    base["observed"]["native_observer_fact_count"] = len(observed["native_facts"])
    return base


def _endpoint_sha256(endpoint: dict[str, Any]) -> str:
    wire = json.dumps(endpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(wire).hexdigest()


def _require_digest(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AdmissionError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _validate_native_facts(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise AdmissionError("native observer must return a factual object")
    if any(key in value for key in ("passed", "status", "case_results", "verdict")):
        raise AdmissionError("native observer cannot supply case verdicts")
    return value


def _tls_token(value: object, label: str, pattern: str, maximum: int) -> str:
    if (
        type(value) is not str
        or len(value) > maximum
        or re.fullmatch(pattern, value, flags=re.ASCII) is None
    ):
        raise AdmissionError(f"observed TLS {label} is not a safe token")
    return value


def _credential_fact(
    value: object,
    inputs: Inputs,
    provider: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    if label not in PERSON_LABELS:
        raise AdmissionError("credential provenance actor label is unknown")
    auth_profile = actor_auth_profiles(inputs.target)[label]
    expected_subject = {
        "native-password": "native-role",
        "human-oauth": "human",
        "nonhuman-oauth": "nonhuman",
    }.get(auth_profile)
    if expected_subject is None:
        raise AdmissionError("credential provenance actor profile is unknown")
    keys = {
        "auth_profile",
        "subject_kind",
        "subject_reference_sha256",
        "credential_source_sha256",
        "provider_observation_sha256",
    }
    if type(value) is not dict or set(value) != keys:
        raise AdmissionError("credential provenance has an unexpected fact shape")
    if value["auth_profile"] != auth_profile or value["subject_kind"] != expected_subject:
        raise AdmissionError(
            "credential provenance differs from the authorized authentication profile"
        )
    result = dict(value)
    for key in ("subject_reference_sha256", "credential_source_sha256"):
        _require_digest(result[key], f"credential provenance {key}")
    observed_provider = result["provider_observation_sha256"]
    if observed_provider is not None:
        _require_digest(observed_provider, "credential provider observation digest")
    if observed_provider is not None and observed_provider != provider["observation_sha256"]:
        raise AdmissionError("credential provenance is not bound to the provider observation")
    return {
        "auth_profile": result["auth_profile"],
        "subject_kind": result["subject_kind"],
        "subject_reference_sha256": result["subject_reference_sha256"],
        "credential_source_sha256": result["credential_source_sha256"],
        "provider_observation_sha256": result["provider_observation_sha256"],
    }


def _observe_connection(
    connection: Any, target: dict[str, Any], *, expected_role: str | None
) -> dict[str, Any]:
    endpoint = target["endpoint"]
    info = connection.info
    parameters = info.get_parameters()
    if (
        type(parameters) is not dict
        or info.host != endpoint["host"]
        or type(info.port) is not int
        or info.port != endpoint["port"]
        or info.dbname != endpoint["database"]
        or parameters.get("sslmode") != "verify-full"
        or not parameters.get("sslrootcert")
        or not connection.pgconn.ssl_in_use
    ):
        raise AdmissionError("connection did not establish the authorized verify-full TLS endpoint")
    row = connection.execute(
        "SELECT current_user, session_user, current_database(), current_setting('role'), "
        "current_setting('server_version_num'), r.rolcanlogin, r.rolsuper, r.rolcreaterole, "
        "r.rolcreatedb, r.rolbypassrls, r.rolreplication, s.ssl, s.version, s.cipher, "
        "to_regnamespace('truss') IS NULL, EXISTS (SELECT 1 FROM pg_roles elevated "
        "WHERE (elevated.rolsuper OR elevated.rolcreaterole OR elevated.rolcreatedb "
        "OR elevated.rolbypassrls) AND pg_catalog.pg_has_role(current_user, elevated.oid, 'USAGE')) "
        "FROM pg_roles AS r JOIN pg_stat_ssl AS s ON s.pid = pg_backend_pid() "
        "WHERE r.rolname = current_user"
    ).fetchone()
    if row is None or len(row) != 16:
        raise AdmissionError("connection identity or TLS session could not be observed")
    user, session_user, database, role_setting, version, *rest = row
    (
        can_login,
        superuser,
        can_create_roles,
        can_create_database,
        bypass_rls,
        can_replicate,
        ssl,
        tls_version,
        cipher,
        namespace_absent,
        effective_elevated,
    ) = rest
    tls_version = _tls_token(tls_version, "protocol", r"TLSv[0-9]+\.[0-9]+", 16)
    cipher = _tls_token(cipher, "cipher", r"[A-Za-z0-9_.+-]+", 128)
    if (
        type(user) is not str
        or user != session_user
        or database != endpoint["database"]
        or role_setting not in ("none", "")
        or version != target["expected"]["postgres_version_num"]
        or expected_role is not None
        and user != expected_role
        or ssl is not True
        or type(namespace_absent) is not bool
        or not namespace_absent
        or type(effective_elevated) is not bool
        or type(can_login) is not bool
        or type(superuser) is not bool
        or type(can_create_roles) is not bool
        or type(can_create_database) is not bool
        or type(bypass_rls) is not bool
        or type(can_replicate) is not bool
        or expected_role is not None
        and (
            superuser
            or can_create_roles
            or can_create_database
            or bypass_rls
            or can_replicate
            or effective_elevated
            or not can_login
        )
    ):
        raise AdmissionError("connection identity, server version, or TLS facts differ from target")
    return {
        "role_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
        "database_matches": True,
        "server_version_num": version,
        "ssl": ssl,
        "tls_version": tls_version,
        "tls_cipher": cipher,
        "can_login": can_login,
        "superuser": superuser,
        "can_create_roles": can_create_roles,
        "can_create_database": can_create_database,
        "can_replicate": can_replicate,
        "truss_namespace_absent_before_mutation": namespace_absent,
    }


def _admit(args: argparse.Namespace) -> Inputs:
    return validate_inputs(
        args.target_json,
        args.authorization_json,
        args.fixture,
        args.fixture_sha256,
        args.output_json,
        scope=args.scope,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs: Inputs | None = None
    try:
        inputs = _admit(args)
        if args.execute:
            receipt = _run_fixture_gate(inputs, args.fixture)
        else:
            receipt = _blocked_receipt(inputs, execute=False)
        write_receipt(args.output_json, receipt)
    except AdmissionError as exc:
        print(f"Lakebase acceptance refused: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("Lakebase acceptance could not safely write its receipt", file=sys.stderr)
        return 2
    except Exception:
        # Trusted fixture and driver exceptions can contain a DSN, server text, or private path.
        # The private owner captures detailed diagnostics separately; stdout/stderr stay bounded.
        print("Lakebase acceptance stopped on an unexpected harness failure", file=sys.stderr)
        if args.execute and inputs is not None and not args.output_json.exists():
            try:
                write_receipt(
                    args.output_json,
                    _blocked_receipt(inputs, execute=True)
                    | {"qualification_note": "Harness execution stopped; results are not_run."},
                )
            except OSError:
                pass
        return 2
    print(json.dumps({"status": receipt["status"], "scope": receipt["scope"]}, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
