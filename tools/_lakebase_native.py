# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded native observation and strict-install helpers for the Lakebase harness."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_CALLER_IDENTITY_SQL = (
    "SELECT session_user, current_user, current_setting('role'), "
    "current_setting('search_path'), current_setting('statement_timeout'), "
    "current_setting('transaction_isolation'), current_setting('transaction_read_only')"
)


def _digest_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="strict")).hexdigest()


def _artifact_facts() -> dict[str, Any]:
    """Read installed artifact evidence, never substituting the expected release tuple."""
    try:
        distribution = importlib.metadata.distribution("truss-toolkit")
        version = distribution.version if type(distribution.version) is str else None
        direct_url = distribution.read_text("direct_url.json")
        wheel_sha256: str | None = None
        if direct_url is not None and len(direct_url) <= 16_384:
            decoded = json.loads(direct_url)
            archive = decoded.get("archive_info") if type(decoded) is dict else None
            hashes = archive.get("hashes") if type(archive) is dict else None
            candidate = hashes.get("sha256") if type(hashes) is dict else None
            if (
                type(candidate) is str
                and len(candidate) == 64
                and all(char in "0123456789abcdef" for char in candidate)
            ):
                wheel_sha256 = candidate
        from importlib.resources import files

        package = files("truss")
        native_bytes = package.joinpath("_catalog_runtime", "manifest.json").read_bytes()
        migration_bytes = package.joinpath("_migrations", "manifest.json").read_bytes()
        native_digest = hashlib.sha256(native_bytes).hexdigest()
        migration_digest = hashlib.sha256(migration_bytes).hexdigest()
        evidence: list[str] = []
        if wheel_sha256 is None:
            evidence.append("wheel_archive_digest_unavailable")
        return {
            "truss_version": version,
            "truss_wheel_sha256": wheel_sha256,
            "native_manifest_sha256": native_digest,
            "migration_manifest_sha256": migration_digest,
            "evidence_codes": evidence,
        }
    except Exception:
        return {
            "truss_version": None,
            "truss_wheel_sha256": None,
            "native_manifest_sha256": None,
            "migration_manifest_sha256": None,
            "evidence_codes": ["installed_artifact_observation_unavailable"],
        }


def _role_acl_snapshot(
    connection: Any,
    actors: tuple[str, ...],
    roles: tuple[str, ...],
    expected_direct: frozenset[tuple[str, str]],
) -> tuple[str, bool]:
    rows = connection.execute(
        "SELECT member.rolname, role.rolname, "
        "pg_catalog.pg_has_role(member.oid, role.oid, 'USAGE'), "
        "pg_catalog.pg_has_role(member.oid, role.oid, 'SET'), "
        "EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m "
        "WHERE m.member = member.oid AND m.roleid = role.oid) "
        "FROM pg_catalog.pg_roles AS member CROSS JOIN pg_catalog.pg_roles AS role "
        "WHERE member.rolname = ANY(%s) AND role.rolname = ANY(%s) "
        "ORDER BY member.rolname, role.rolname",
        (list(actors), list(roles)),
    ).fetchall()
    facts: list[tuple[str, str, bool, bool, bool]] = []
    for row in rows:
        if type(row) not in (tuple, list) or len(row) != 5:
            raise ValueError("ACL observation shape")
        member, role, effective, settable, direct = row
        if (
            type(member) is not str
            or type(role) is not str
            or any(type(flag) is not bool for flag in (effective, settable, direct))
        ):
            raise ValueError("ACL observation types")
        facts.append((member, role, effective, settable, direct))
    expected_pairs = {
        (member, role) for member, role, *_ in facts if (member, role) in expected_direct
    }
    actual_direct = {(member, role) for member, role, _, _, direct in facts if direct}
    actual_effective = {(member, role) for member, role, effective, _, _ in facts if effective}
    actual_settable = {(member, role) for member, role, _, settable, _ in facts if settable}
    success = (
        len(facts) == len(actors) * len(roles)
        and expected_pairs == expected_direct
        and actual_direct == expected_direct
        and actual_effective == expected_direct
        and not actual_settable
    )
    digest = hashlib.sha256(
        json.dumps(facts, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    return digest, success


def _role_attributes(
    connection: Any, roles: tuple[str, ...]
) -> dict[str, tuple[bool, bool, bool, bool]]:
    rows = connection.execute(
        "SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb "
        "FROM pg_catalog.pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
        (list(roles),),
    ).fetchall()
    result: dict[str, tuple[bool, bool, bool, bool]] = {}
    for row in rows:
        if type(row) not in (tuple, list) or len(row) != 5:
            raise ValueError("role observation shape")
        name, *flags = row
        if type(name) is not str or any(type(flag) is not bool for flag in flags):
            raise ValueError("role observation types")
        result[name] = (flags[0], flags[1], flags[2], flags[3])
    return result


@dataclass(frozen=True)
class _StrictProbe:
    outcome: str
    object_class: str | None
    phase: str | None
    selected_role_sha256: str | None
    role_selected: bool | None
    caller_state_unchanged: bool | None
    native_state_unchanged: bool | None
    owner_role: str | None = None
    registrar_role: str | None = None


@dataclass(frozen=True)
class _ClassifiedStrictResult:
    outcome: str
    object_class: str | None = None
    phase: str | None = None
    selected_role_sha256: str | None = None
    role_selected: bool | None = None
    owner_role: str | None = None
    registrar_role: str | None = None
    commit_unexpected_success: bool = False


def _native_install_snapshot(connection: Any) -> tuple[bool, str]:
    schema_exists = connection.execute(
        "SELECT pg_catalog.to_regnamespace('truss') IS NOT NULL"
    ).fetchone()
    if (
        type(schema_exists) not in (tuple, list)
        or len(schema_exists) != 1
        or type(schema_exists[0]) is not bool
    ):
        raise ValueError("namespace observation shape")
    roles = connection.execute(
        "SELECT oid, rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, "
        "rolinherit, rolreplication, rolbypassrls, rolconnlimit "
        "FROM pg_catalog.pg_roles "
        "ORDER BY oid"
    ).fetchall()
    role_facts: list[tuple[Any, ...]] = []
    for row in roles:
        if (
            type(row) not in (tuple, list)
            or len(row) != 10
            or type(row[0]) is not int
            or type(row[1]) is not str
            or any(type(flag) is not bool for flag in row[2:9])
            or type(row[9]) is not int
        ):
            raise ValueError("role observation shape")
        role_facts.append(tuple(row))
    memberships = connection.execute(
        "SELECT member.oid, role.oid, m.admin_option, m.inherit_option, m.set_option "
        "FROM pg_catalog.pg_auth_members AS m "
        "JOIN pg_catalog.pg_roles AS member ON member.oid = m.member "
        "JOIN pg_catalog.pg_roles AS role ON role.oid = m.roleid "
        "ORDER BY member.oid, role.oid",
    ).fetchall()
    for row in memberships:
        if (
            type(row) not in (tuple, list)
            or len(row) != 5
            or type(row[0]) is not int
            or type(row[1]) is not int
            or any(type(flag) is not bool for flag in row[2:])
        ):
            raise ValueError("membership observation shape")
    namespaces = connection.execute(
        "SELECT oid, nspname, nspowner, nspacl::text FROM pg_catalog.pg_namespace ORDER BY oid"
    ).fetchall()
    namespace_facts: list[tuple[int, str, int, str | None]] = []
    for row in namespaces:
        if (
            type(row) not in (tuple, list)
            or len(row) != 4
            or type(row[0]) is not int
            or type(row[1]) is not str
            or type(row[2]) is not int
            or (row[3] is not None and type(row[3]) is not str)
        ):
            raise ValueError("namespace ACL observation shape")
        namespace_facts.append(tuple(row))
    database_acl = connection.execute(
        "SELECT oid, datname, datdba, datacl::text "
        "FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database()"
    ).fetchall()
    if (
        type(database_acl) not in (tuple, list)
        or len(database_acl) != 1
        or type(database_acl[0]) not in (tuple, list)
        or len(database_acl[0]) != 4
        or type(database_acl[0][0]) is not int
        or type(database_acl[0][1]) is not str
        or type(database_acl[0][2]) is not int
        or (database_acl[0][3] is not None and type(database_acl[0][3]) is not str)
    ):
        raise ValueError("database ACL observation shape")
    digest = hashlib.sha256(
        json.dumps(
            {
                "roles": role_facts,
                "memberships": memberships,
                "namespace_acls": namespace_facts,
                "database_acl": database_acl[0],
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    return schema_exists[0], digest


def _classify_strict_result(
    result: Any, selected: tuple[str, ...], refusal_type: type, pending_type: type
) -> _ClassifiedStrictResult:
    value = result.value if type(result).__name__ == "Ok" else None
    if type(result).__name__ == "Error":
        value = result.error
    if isinstance(value, refusal_type) and value.code == "third_party_grant":
        role_name = value.role_name if type(value.role_name) is str else None
        return _ClassifiedStrictResult(
            "typed_refusal",
            object_class=_safe_enum(
                value.object_class, {"schema", "relation", "sequence", "routine", "type", "column"}
            ),
            phase=_safe_enum(value.phase, {"pre_ownership", "post_installation"}),
            selected_role_sha256=_digest_name(role_name) if role_name else None,
            role_selected=role_name in selected if role_name else None,
        )
    if isinstance(value, refusal_type):
        return _ClassifiedStrictResult("other_refusal")
    if type(result).__name__ == "Ok" and isinstance(value, pending_type):
        return _ClassifiedStrictResult(
            "unexpected_success",
            owner_role=getattr(value, "owner_role", None),
            registrar_role=getattr(value, "registrar_role", None),
            commit_unexpected_success=True,
        )
    return _ClassifiedStrictResult("other_refusal")


def _invoke_strict_install(host: Any, selected: tuple[str, ...]) -> _ClassifiedStrictResult:
    from truss import (
        CatalogRuntimeConfiguration,
        InstallRefused,
        PendingCatalogInstallation,
        create_reference_assembly,
    )

    adopted = host.adopt_transaction(access_mode="read_write")
    if type(adopted).__name__ != "Ok":
        return _ClassifiedStrictResult("other_refusal")
    assembly = create_reference_assembly(CatalogRuntimeConfiguration(), host)
    if type(assembly).__name__ != "Ok":
        return _ClassifiedStrictResult("other_refusal")
    result = assembly.value.install_in_transaction(adopted.value, tolerated_grantees=())
    return _classify_strict_result(result, selected, InstallRefused, PendingCatalogInstallation)


def _discard_connection(connection: Any) -> None:
    close_connection = getattr(connection, "close", None)
    if callable(close_connection):
        try:
            close_connection()
        except Exception:
            pass


def _strict_install_attempt(
    connection: Any,
    selected: tuple[str, ...],
    temp_name: str,
    prior_work: list[Any],
    caller_identity: Any,
) -> _StrictProbe:
    from truss import adopt_psycopg_host

    host = None
    connection_usable = True
    caller_unchanged = None
    classified = _ClassifiedStrictResult("other_refusal")
    try:
        host = adopt_psycopg_host(
            connection, statement_timeout_ms=10_000, operation_timeout_ms=30_000
        )
        classified = _invoke_strict_install(host, selected)
        detached = host.detach()
        host = None
        if detached is not True:
            connection_usable = False
            _discard_connection(connection)
            return _strict_probe_from_classification(classified, None, None)
        after_work = connection.execute(f'SELECT value FROM "{temp_name}"').fetchall()
        after_identity = connection.execute(_CALLER_IDENTITY_SQL).fetchone()
        caller_unchanged = after_work == prior_work and after_identity == caller_identity
        if classified.commit_unexpected_success:
            connection.commit()
    finally:
        if host is not None:
            try:
                connection_usable = host.detach() is True
            except BaseException:
                _discard_connection(connection)
                raise
            if not connection_usable:
                _discard_connection(connection)
        if connection_usable and not classified.commit_unexpected_success:
            connection.rollback()
    return _strict_probe_from_classification(classified, caller_unchanged, None)


def _strict_probe_from_classification(
    classified: _ClassifiedStrictResult,
    caller_unchanged: bool | None,
    native_unchanged: bool | None,
) -> _StrictProbe:
    return _StrictProbe(
        classified.outcome,
        classified.object_class,
        classified.phase,
        classified.selected_role_sha256,
        classified.role_selected,
        caller_unchanged,
        native_unchanged,
        classified.owner_role,
        classified.registrar_role,
    )


def _safe_enum(value: object, allowed: set[str]) -> str | None:
    return value if type(value) is str and value in allowed else None


def _strict_default_probe(sources: Mapping[str, Any], selected: tuple[str, ...]) -> _StrictProbe:
    """Ask public Truss once with the strict empty policy and prove rollback containment."""
    with sources["installer_connection_source"]() as observer:
        before_native = _native_install_snapshot(observer)
    if before_native[0]:
        return _StrictProbe("not_run", None, None, None, None, None, None)
    with sources["installer_connection_source"]() as connection:
        autocommit = getattr(connection, "autocommit", None)
        connection_info = getattr(connection, "info", None)
        transaction_status = getattr(connection_info, "transaction_status", None)
        if type(autocommit) is not bool or transaction_status != 0:
            return _StrictProbe("not_run", None, None, None, None, None, None)
        if autocommit:
            connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE")
        else:
            connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ WRITE")
        connection.execute("SET LOCAL statement_timeout = '10000ms'")
        caller_identity = connection.execute(_CALLER_IDENTITY_SQL).fetchone()
        temp_name = f"arras_probe_{uuid.uuid4().hex}"
        connection.execute(f'CREATE TEMP TABLE "{temp_name}" (value text)')
        connection.execute(f'INSERT INTO "{temp_name}" VALUES (%s)', ("retain",))
        prior_work = connection.execute(f'SELECT value FROM "{temp_name}"').fetchall()
        attempt = _strict_install_attempt(
            connection, selected, temp_name, prior_work, caller_identity
        )
    try:
        with sources["installer_connection_source"]() as observer:
            after_native = _native_install_snapshot(observer)
        native_unchanged = before_native == after_native and after_native[0] is False
    except Exception:
        native_unchanged = None
    return _StrictProbe(
        attempt.outcome,
        attempt.object_class,
        attempt.phase,
        attempt.selected_role_sha256,
        attempt.role_selected,
        attempt.caller_state_unchanged,
        native_unchanged,
        attempt.owner_role,
        attempt.registrar_role,
    )
