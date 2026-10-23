# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded target, authorization, and fixture admission for Lakebase qualification."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 1_048_576
MAX_FIXTURE_BYTES = 262_144
MAX_TARGET_TEXT = 512
HARNESS_MODULE_SHA256 = "0d9c4bd6c390803483937200812e838d45734e0e0ab7925374d88aceb767f16f"
CASE_IDS = (
    "LB-ADMISSION",
    "LB-INSTALL",
    "LB-PERSON",
    "LB-CUSTODY",
    "LB-SETTLEMENT",
    "LB-ACL",
    "MP-01",
    "MP-02",
    "MP-03",
    "MP-04",
    "MP-05",
    "MP-06",
)
PERSON_LABELS = ("registrar", "writer", "reader", "denied")
BASELINE_CASES = CASE_IDS[:6]
FULL_MANAGED_CASES = CASE_IDS
OPERATIONS = frozenset(
    {
        "read",
        "install",
        "configure",
        "apply",
        "feed",
        "refresh",
        "restart",
        "fault",
        "cleanup",
        "provision_module_roles",
        "prepare_owned_access_roles",
        "grant_owned_memberships",
        "revoke_owned_memberships",
        "expire_owned_login",
    }
)
EXPECTED = {
    "postgres_version_num": "180006",
    "truss_version": "0.0.49",
    "truss_wheel_sha256": "7ea14b2787f02cbeec9ad99d835adbcc30c684fd5be8e0765a1d8198b50e7182",
    "native_manifest_sha256": "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4",
    "migration_manifest_sha256": "96addcdb95523f478d8f50b0b47198e47a860680c7400dd359711930e837e535",
    "weft_version": "0.4.51",
}
TARGET_KEYS = {
    "schema_version",
    "provider",
    "target_id",
    "provider_resource_id",
    "endpoint",
    "expected",
    "resources",
    "requested_cases",
    "auth_profile",
}
AUTH_KEYS = {
    "schema_version",
    "target_sha256",
    "fixture_sha256",
    "request_reference",
    "authorized_resource_id",
    "authorized_database",
    "authorized_schema",
    "authorized_ordinary_roles",
    "allow_generated_installation_roles",
    "allowed_operations",
    "allowed_cases",
    "auth_profile",
    "authorized_module_access",
}
AUTH_PROFILES = frozenset({"native-password", "human-oauth", "nonhuman-oauth"})
MIXED_AUTH_PROFILE = "mixed"
TARGET_V2_KEYS = TARGET_KEYS | {"actor_auth_profiles", "human_actor"}
AUTH_V2_KEYS = AUTH_KEYS | {"actor_auth_profiles", "human_actor"}


def actor_auth_profiles(target: dict[str, Any]) -> dict[str, str]:
    """Return the exact effective profile for each ordinary role, including legacy v1 targets."""
    if target.get("schema_version") == 1:
        return {label: target["auth_profile"] for label in PERSON_LABELS}
    value = target.get("actor_auth_profiles")
    if type(value) is not dict:
        raise AdmissionError("target actor authentication profiles are missing")
    return dict(value)


class AdmissionError(ValueError):
    """A safe, bounded refusal before fixture execution or service access."""


@dataclass(frozen=True)
class Inputs:
    target: dict[str, Any]
    authorization: dict[str, Any]
    target_sha256: str
    authorization_sha256: str
    fixture_sha256: str
    fixture_bytes: bytes
    required_cases: tuple[str, ...]
    scope: str


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AdmissionError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_constant(_: str) -> None:
    raise AdmissionError("non-JSON numeric constant")


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except AdmissionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AdmissionError(f"{label} is not bounded UTF-8 JSON") from None
    if type(value) is not dict:
        raise AdmissionError(f"{label} must be a JSON object")
    return value


def _regular_file(path: Path, *, maximum: int, label: str) -> bytes:
    try:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts[1:-1]:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise AdmissionError(f"{label} path contains a symlink")
        descriptor = os.open(absolute, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise AdmissionError(f"{label} must be a bounded regular file")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                raw = stream.read(maximum + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except AdmissionError:
        raise
    except OSError:
        raise AdmissionError(f"{label} is unavailable") from None
    if len(raw) > maximum:
        raise AdmissionError(f"{label} exceeds its size bound")
    return raw


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise AdmissionError(f"{label} has an unexpected field set")


def _text(value: object, label: str, *, maximum: int = MAX_TARGET_TEXT) -> str:
    if type(value) is not str or not value:
        raise AdmissionError(f"{label} is not a bounded nonempty string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise AdmissionError(f"{label} is not valid UTF-8 text") from None
    if len(encoded) > maximum:
        raise AdmissionError(f"{label} is not a bounded nonempty string")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise AdmissionError(f"{label} contains a control character")
    return value


def _names(value: object, label: str, *, maximum: int = 32) -> tuple[str, ...]:
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise AdmissionError(f"{label} must be a nonempty bounded list")
    names = tuple(_text(item, label, maximum=63) for item in value)
    if len(set(names)) != len(names) or any("\x00" in name for name in names):
        raise AdmissionError(f"{label} must contain unique literal names")
    return names


def _sha(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AdmissionError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _case_set(value: object, label: str) -> tuple[str, ...]:
    cases = _names(value, label, maximum=len(CASE_IDS))
    if any(case not in CASE_IDS for case in cases):
        raise AdmissionError(f"{label} contains an unknown case")
    return cases


def _validate_target_identity(value: dict[str, Any]) -> dict[str, Any]:
    schema_version = value["schema_version"]
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise AdmissionError("target schema_version must be integer 1 or 2")
    if value["provider"] != "lakebase":
        raise AdmissionError("target provider must be lakebase")
    _validate_target_auth_profile(value, schema_version)
    for key in ("target_id", "provider_resource_id"):
        _text(value[key], f"target {key}")
        if "REPLACE" in value[key] or "PENDING" in value[key]:
            raise AdmissionError(f"target {key} is an example placeholder")
    endpoint = value["endpoint"]
    if type(endpoint) is not dict:
        raise AdmissionError("target endpoint must be an object")
    _exact_keys(endpoint, {"host", "port", "database", "sslmode"}, "endpoint")
    _text(endpoint["host"], "target endpoint host")
    _text(endpoint["database"], "target endpoint database")
    if type(endpoint["port"]) is not int or not 1 <= endpoint["port"] <= 65535:
        raise AdmissionError("target endpoint port is invalid")
    if endpoint["sslmode"] != "verify-full":
        raise AdmissionError("target endpoint must require verify-full TLS")
    expected = value["expected"]
    if type(expected) is not dict:
        raise AdmissionError("target expected tuple must be an object")
    _exact_keys(expected, set(EXPECTED), "target expected tuple")
    for key, wanted in EXPECTED.items():
        if expected[key] != wanted:
            raise AdmissionError(f"target expected {key} differs from the frozen cohort")
    _sha(expected["truss_wheel_sha256"], "target Truss wheel digest")
    return endpoint


def _validate_target_auth_profile(value: dict[str, Any], schema_version: int) -> None:
    if schema_version == 1:
        if value["auth_profile"] not in AUTH_PROFILES:
            raise AdmissionError("target auth_profile is not a supported authentication profile")
        return
    profiles = value["actor_auth_profiles"]
    if (
        value["auth_profile"] != MIXED_AUTH_PROFILE
        or type(profiles) is not dict
        or set(profiles) != set(PERSON_LABELS)
    ):
        raise AdmissionError("target schema 2 must bind mixed authentication for all four roles")
    if any(
        type(profile) is not str or profile not in AUTH_PROFILES for profile in profiles.values()
    ):
        raise AdmissionError("target actor authentication profile is unsupported")
    if value["human_actor"] != "writer" or profiles["writer"] != "human-oauth":
        raise AdmissionError("target must bind the required human OAuth writer")


def _validate_target_resources(
    resources: object, endpoint: dict[str, Any], value: dict[str, Any]
) -> None:
    if type(resources) is not dict:
        raise AdmissionError("target resources must be an object")
    _exact_keys(
        resources,
        {
            "database",
            "installation_schema",
            "ordinary_role_names",
            "tolerated_grantees",
            "generated_installation_role_count",
            "module_access",
        },
        "target resources",
    )
    if resources["database"] != endpoint["database"] or resources["installation_schema"] != "truss":
        raise AdmissionError(
            "target resource database/schema does not match the fixed Truss boundary"
        )
    ordinary = _names(resources["ordinary_role_names"], "ordinary role names")
    if len(ordinary) != len(PERSON_LABELS):
        raise AdmissionError("target must bind the four fixed ordinary-person roles")
    tolerated = resources["tolerated_grantees"]
    if type(tolerated) is not list or len(tolerated) > 32:
        raise AdmissionError("tolerated grantees must be a bounded list")
    if any(type(name) is not str for name in tolerated):
        raise AdmissionError("tolerated grantees must be unique literal names")
    try:
        for name in tolerated:
            _text(name, "tolerated grantee", maximum=63)
    except AdmissionError:
        raise AdmissionError("tolerated grantees must be bounded literal names") from None
    if len(set(tolerated)) != len(tolerated):
        raise AdmissionError("tolerated grantees must be unique literal names")
    if set(ordinary) & set(tolerated):
        raise AdmissionError("ordinary roles cannot also be tolerated grantees")
    if (
        type(resources["generated_installation_role_count"]) is not int
        or resources["generated_installation_role_count"] != 2
    ):
        raise AdmissionError(
            "exactly two generated installation roles must be in the authorized scope"
        )
    module_access = resources["module_access"]
    if type(module_access) is not dict:
        raise AdmissionError("module access must bind exact owned role names")
    module_keys = {"document_id", "source_sha256", "reader_role", "writer_role"}
    if "auditor_role" in module_access:
        module_keys.add("auditor_role")
    _exact_keys(module_access, module_keys, "module access")
    if module_access["document_id"] != "arras-lakebase-qualification-v1":
        raise AdmissionError("module access document id differs from the fixed harness document")
    _sha(module_access["source_sha256"], "module source digest")
    if module_access["source_sha256"] != HARNESS_MODULE_SHA256:
        raise AdmissionError("module source digest differs from the fixed harness document")
    module_roles = tuple(
        _text(module_access[name], f"module access {name}", maximum=63)
        for name in (
            "reader_role",
            "writer_role",
            *(("auditor_role",) if "auditor_role" in module_access else ()),
        )
    )
    if len(set(module_roles)) != len(module_roles) or set(module_roles) & (
        set(ordinary) | set(tolerated)
    ):
        raise AdmissionError("module roles must be distinct from actors and tolerated grantees")


def _validate_target(value: dict[str, Any]) -> None:
    if type(value.get("schema_version")) is int and value["schema_version"] == 2:
        _exact_keys(value, TARGET_V2_KEYS, "target")
    else:
        _exact_keys(value, TARGET_KEYS, "target")
    endpoint = _validate_target_identity(value)
    _validate_target_resources(value["resources"], endpoint, value)
    requested = _case_set(value["requested_cases"], "requested cases")
    if not set(BASELINE_CASES).issubset(requested):
        raise AdmissionError("target must request every fixed baseline case")


def _validate_authorization(
    value: dict[str, Any], target: dict[str, Any], target_sha: str, fixture_sha: str
) -> None:
    schema_version = target["schema_version"]
    _exact_keys(value, AUTH_V2_KEYS if schema_version == 2 else AUTH_KEYS, "authorization")
    if type(value["schema_version"]) is not int or value["schema_version"] != schema_version:
        raise AdmissionError("authorization schema_version differs from target")
    if _sha(value["target_sha256"], "authorized target digest") != target_sha:
        raise AdmissionError("authorization target digest mismatch")
    if _sha(value["fixture_sha256"], "authorized fixture digest") != fixture_sha:
        raise AdmissionError("authorization fixture digest mismatch")
    _validate_authorization_auth_profile(value, target, schema_version)
    _text(value["request_reference"], "authorization request reference")
    if value["authorized_resource_id"] != target["provider_resource_id"]:
        raise AdmissionError("authorization provider resource mismatch")
    if value["authorized_database"] != target["resources"]["database"]:
        raise AdmissionError("authorization database mismatch")
    if value["authorized_schema"] != "truss":
        raise AdmissionError("authorization must cover the fixed truss schema")
    if _names(value["authorized_ordinary_roles"], "authorized ordinary roles") != tuple(
        target["resources"]["ordinary_role_names"]
    ):
        raise AdmissionError("authorization ordinary roles mismatch")
    if value["authorized_module_access"] != target["resources"]["module_access"]:
        raise AdmissionError("authorization module access mismatch")
    if (
        type(value["allow_generated_installation_roles"]) is not bool
        or not value["allow_generated_installation_roles"]
    ):
        raise AdmissionError("authorization must explicitly allow the two generated Truss roles")
    operations = _names(value["allowed_operations"], "allowed operations", maximum=len(OPERATIONS))
    if not set(operations) <= OPERATIONS:
        raise AdmissionError("authorization contains an unknown operation")
    allowed_cases = _case_set(value["allowed_cases"], "authorized cases")
    requested = set(target["requested_cases"])
    if not requested <= set(allowed_cases):
        raise AdmissionError("authorization does not cover every requested case")
    if not {"read", "cleanup"} <= set(operations):
        raise AdmissionError("authorization lacks required read/cleanup operations")


def _validate_authorization_auth_profile(
    value: dict[str, Any], target: dict[str, Any], schema_version: int
) -> None:
    if value["auth_profile"] != target["auth_profile"]:
        raise AdmissionError("authorization auth_profile mismatch")
    if schema_version == 1:
        if value["auth_profile"] not in AUTH_PROFILES:
            raise AdmissionError("authorization auth_profile is unsupported")
    elif (
        value["auth_profile"] != MIXED_AUTH_PROFILE
        or value["human_actor"] != target["human_actor"]
        or value["actor_auth_profiles"] != target["actor_auth_profiles"]
    ):
        raise AdmissionError("authorization actor authentication profiles mismatch")


def validate_inputs(
    target_path: Path,
    authorization_path: Path,
    fixture_path: Path,
    fixture_sha256: str,
    output_path: Path,
    *,
    scope: str,
) -> Inputs:
    """Validate every input and every path alias before fixture import or output mutation."""
    if scope not in ("baseline", "full-managed"):
        raise AdmissionError("scope must be baseline or full-managed")
    paths = (target_path, authorization_path, fixture_path, output_path)
    resolved = [path.resolve(strict=False) for path in paths]
    if len(set(resolved)) != len(resolved):
        raise AdmissionError("input/output path aliases are refused")
    for left in range(len(paths)):
        for right in range(left + 1, len(paths)):
            try:
                if (
                    paths[left].exists()
                    and paths[right].exists()
                    and os.path.samefile(paths[left], paths[right])
                ):
                    raise AdmissionError("input/output hard-link aliases are refused")
            except OSError:
                raise AdmissionError("input/output alias check failed") from None
    target_raw = _regular_file(target_path, maximum=MAX_JSON_BYTES, label="target")
    auth_raw = _regular_file(authorization_path, maximum=MAX_JSON_BYTES, label="authorization")
    fixture_raw = _regular_file(fixture_path, maximum=MAX_FIXTURE_BYTES, label="fixture")
    supplied_fixture_sha = _sha(fixture_sha256, "fixture argument digest")
    target = _strict_json(target_raw, "target")
    authorization = _strict_json(auth_raw, "authorization")
    _validate_target(target)
    target_sha = hashlib.sha256(target_raw).hexdigest()
    auth_sha = hashlib.sha256(auth_raw).hexdigest()
    actual_fixture_sha = hashlib.sha256(fixture_raw).hexdigest()
    if actual_fixture_sha != supplied_fixture_sha:
        raise AdmissionError("fixture argument digest mismatch")
    _validate_authorization(authorization, target, target_sha, actual_fixture_sha)
    required = BASELINE_CASES if scope == "baseline" else FULL_MANAGED_CASES
    if not set(required).issubset(target["requested_cases"]):
        raise AdmissionError("target does not request the complete selected scope")
    if not set(required).issubset(authorization["allowed_cases"]):
        raise AdmissionError("authorization does not cover the complete selected scope")
    if not output_path.parent.exists() or not output_path.parent.is_dir():
        raise AdmissionError("output parent must already be a directory")
    current = output_path.parent
    while current != current.parent:
        if stat.S_ISLNK(current.lstat().st_mode):
            raise AdmissionError("output parent path contains a symlink")
        current = current.parent
    if output_path.exists() or output_path.is_symlink():
        raise AdmissionError("output path must be absent")
    return Inputs(
        target,
        authorization,
        target_sha,
        auth_sha,
        actual_fixture_sha,
        fixture_raw,
        tuple(required),
        scope,
    )


def load_trusted_fixture(inputs: Inputs, path: Path) -> Any:
    """Execute only the exact fixture bytes admitted by the target authorization."""
    if hashlib.sha256(inputs.fixture_bytes).hexdigest() != inputs.fixture_sha256:
        raise AdmissionError("fixture bytes changed after admission")
    import types

    module = types.ModuleType("arras_lakebase_trusted_fixture")
    module.__file__ = str(path)
    code = compile(inputs.fixture_bytes, "<authorized-lakebase-fixture>", "exec", dont_inherit=True)
    exec(code, module.__dict__)
    required = ("build_sources", "observe_provider", "cleanup_owned")
    if any(not callable(getattr(module, name, None)) for name in required):
        raise AdmissionError("trusted fixture is missing a required source or observer")
    return module


def safe_case(case: str, status: str, code: str) -> dict[str, str]:
    if case not in CASE_IDS or status not in {"passed", "failed", "blocked", "not_run"}:
        raise AdmissionError("invalid internal case result")
    if (
        not code
        or len(code) > 80
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-." for c in code)
    ):
        raise AdmissionError("case result code is not a safe token")
    return {"case": case, "status": status, "code": code}


def write_receipt(path: Path, value: dict[str, Any]) -> None:
    """Atomically create a bounded receipt without replacing a path created after admission."""
    import tempfile

    payload = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(payload) > MAX_JSON_BYTES:
        raise AdmissionError("receipt exceeds its output bound")
    fd, temporary = tempfile.mkstemp(prefix=".lakebase-receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
