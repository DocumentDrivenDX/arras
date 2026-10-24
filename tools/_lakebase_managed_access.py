# SPDX-License-Identifier: MIT OR Apache-2.0
"""Caller custody and selected-access checks using public APIs."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import (
    DOCUMENT_ID as _DOCUMENT_ID,
)
from _lakebase_managed_common import (
    MODULE as _MODULE,
)
from _lakebase_managed_common import (
    QUERY as _QUERY,
)
from _lakebase_managed_common import (
    Blocked as _Blocked,
)
from _lakebase_managed_common import (
    Failed as _Failed,
)
from _lakebase_managed_common import (
    allowed as _allowed,
)
from _lakebase_managed_common import (
    digest as _digest,
)
from _lakebase_managed_native import _observer_snapshot
from _lakebase_managed_public import _insert_probe, _public_host, _query_probe
from _lakebase_person import _safe_state_facts


def _person_membership_summary(baseline_observed: Any) -> dict[str, Any]:
    person = baseline_observed.get("person") if type(baseline_observed) is dict else None
    if type(person) is not dict or person.get("schema_version") != 1:
        raise _Blocked("person_membership_observation_unavailable")
    membership = person.get("membership_control")
    state = person.get("state")
    if type(membership) is not dict or set(membership) != {
        "revoke_operation_sha256",
        "restore_operation_sha256",
        "revoked_membership_sha256",
        "restored_membership_sha256",
        "fresh_connection_denied",
        "existing_session_denied",
        "restoration_verified",
    }:
        raise _Blocked("person_membership_observation_invalid")
    if type(state) is not dict or set(state) != {
        "before_sha256",
        "after_sha256",
        "unchanged",
        "sequence_allocations",
    }:
        raise _Blocked("person_state_observation_invalid")
    try:
        state = _safe_state_facts(state)
    except ValueError as exc:
        raise _Blocked("person_state_observation_invalid") from exc
    for key in (
        "revoke_operation_sha256",
        "restore_operation_sha256",
        "revoked_membership_sha256",
        "restored_membership_sha256",
    ):
        _digest(membership[key], "person_membership_digest_invalid")
    for key in ("before_sha256", "after_sha256"):
        _digest(state[key], "person_state_digest_invalid")
    if (
        any(
            type(membership[key]) is not bool or membership[key] is not True
            for key in (
                "fresh_connection_denied",
                "existing_session_denied",
                "restoration_verified",
            )
        )
        or membership["revoked_membership_sha256"] != membership["restored_membership_sha256"]
        or state["unchanged"] is not True
        or state["before_sha256"] != state["after_sha256"]
    ):
        raise _Failed("person_membership_lifecycle_postcondition_failed")
    return {
        "person_lifecycle_facts_available": True,
        "person_membership_lifecycle_verified": True,
        "person_revoke_operation_sha256": membership["revoke_operation_sha256"],
        "person_restore_operation_sha256": membership["restore_operation_sha256"],
        "person_memberships_sha256": membership["revoked_membership_sha256"],
        "person_state_sha256": state["before_sha256"],
    }


def _caller_state(connection: Any, temp: str) -> tuple[tuple[Any, ...], list[Any]]:
    identity = tuple(
        connection.execute(
            "SELECT session_user, current_user, current_setting('role'), "
            "current_setting('search_path'), current_setting('statement_timeout'), "
            "current_setting('lock_timeout'), current_setting('transaction_isolation'), "
            "current_setting('transaction_read_only')"
        ).fetchone()
    )
    return identity, connection.execute(f'SELECT marker FROM "{temp}"').fetchall()


def _query_on_caller_transaction(connection: Any) -> tuple[tuple[Any, ...], str]:
    from truss import (
        CatalogRuntimeConfiguration,
        Ok,
        adopt_psycopg_host,
        create_reference_assembly,
    )

    host = adopt_psycopg_host(connection, statement_timeout_ms=10_000, operation_timeout_ms=30_000)
    try:
        transaction = host.adopt_transaction(access_mode="read_write")
        if not isinstance(transaction, Ok):
            failure = getattr(transaction, "error", None)
            code = getattr(failure, "code", "unknown")
            message = getattr(failure, "message", "unavailable")
            raise _Blocked(f"caller_transaction_adoption_refused:{code}:{message}")
        assembled = create_reference_assembly(CatalogRuntimeConfiguration(), host)
        if not isinstance(assembled, Ok):
            raise _Blocked("truss_assembly_unavailable")
        assembly = assembled.value
        result = assembly.query_in_transaction(
            transaction.value,
            sql=_QUERY,
            document_ids=(_DOCUMENT_ID,),
            maximum_rows=100,
            maximum_scan_rows=1000,
            maximum_bytes=262_144,
        )
        if not isinstance(result, Ok) or type(result.value).__name__ != "QueryRows":
            raise _Failed("caller_public_read_failed")
        rows = tuple(getattr(result.value, "rows", ()))
        refusal = assembly.query_in_transaction(
            transaction.value,
            sql="SELECT p.unqualified_column FROM lakebase_qualification.Probe p LIMIT 1",
            document_ids=(_DOCUMENT_ID,),
            maximum_rows=1,
            maximum_scan_rows=1,
            maximum_bytes=4096,
        )
        if not isinstance(refusal, Ok) or type(refusal.value).__name__ != "QueryRefused":
            raise _Failed("caller_public_refusal_not_observed")
        return rows, type(refusal.value).__name__
    finally:
        if host.detach() is not True:
            raise _Failed("caller_host_detach_failed")


def _acl_rows(
    sources: Mapping[str, Any], ordinary: tuple[str, ...], module_access: Mapping[str, Any]
) -> tuple[list[Any], list[Any], list[Any]]:
    installer = sources.get("installer_connection_source")
    if not callable(installer):
        raise _Blocked("installer_observer_unavailable")
    role_names = tuple(
        dict.fromkeys(
            [
                *ordinary,
                module_access["reader_role"],
                module_access["writer_role"],
                *([module_access["auditor_role"]] if module_access.get("auditor_role") else []),
            ]
        )
    )
    with installer() as connection:
        roles = connection.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolreplication, "
            "rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
            (list(role_names),),
        ).fetchall()
        memberships = connection.execute(
            "SELECT member.rolname, role.rolname, "
            "pg_catalog.pg_has_role(member.oid, role.oid, 'USAGE'), "
            "pg_catalog.pg_has_role(member.oid, role.oid, 'SET'), "
            "role.rolsuper, role.rolcreaterole, role.rolcreatedb, role.rolreplication, "
            "role.rolbypassrls, "
            "EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m "
            "WHERE m.member=member.oid AND m.roleid=role.oid) "
            "FROM pg_catalog.pg_roles member CROSS JOIN pg_catalog.pg_roles role "
            "WHERE member.rolname=ANY(%s) AND role.rolname=ANY(%s) "
            "ORDER BY member.rolname, role.rolname",
            (list(ordinary), list(role_names)),
        ).fetchall()
        grants = connection.execute(
            "SELECT grantee, table_schema, table_name, privilege_type, is_grantable "
            "FROM information_schema.role_table_grants WHERE grantee=ANY(%s) "
            "ORDER BY grantee, table_schema, table_name, privilege_type",
            (list(ordinary),),
        ).fetchall()
    return roles, memberships, grants


def _validate_acl_rows(
    roles: list[Any],
    memberships: list[Any],
    grants: list[Any],
    ordinary: tuple[str, ...],
    module_access: Mapping[str, Any],
) -> list[Any]:
    role_names = tuple(
        dict.fromkeys(
            [
                *ordinary,
                module_access["reader_role"],
                module_access["writer_role"],
                *([module_access["auditor_role"]] if module_access.get("auditor_role") else []),
            ]
        )
    )
    valid_roles = len(roles) == len(role_names) and all(
        type(row) in {tuple, list}
        and len(row) == 7
        and type(row[0]) is str
        and all(type(flag) is bool for flag in row[1:])
        for row in roles
    )
    valid_memberships = len(memberships) == len(ordinary) * len(role_names) and all(
        type(row) in {tuple, list}
        and len(row) == 10
        and all(type(value) is str for value in row[:2])
        and all(type(flag) is bool for flag in row[2:])
        for row in memberships
    )
    valid_grants = all(
        type(row) in {tuple, list}
        and len(row) == 5
        and all(type(value) is str for value in row[:4])
        and row[4] in {"YES", "NO"}
        for row in grants
    )
    if not (valid_roles and valid_memberships and valid_grants):
        raise _Blocked("native_acl_snapshot_invalid")
    ordinary_roles = [row for row in roles if row[0] in ordinary]
    if any(row[1] is not True or any(row[2:]) for row in ordinary_roles):
        raise _Failed("ordinary_principal_has_elevated_role_attributes")
    if any((row[2] or row[3]) and any(row[4:9]) for row in memberships):
        raise _Failed("ordinary_principal_can_reach_elevated_role")
    return ordinary_roles


def _run_custody(
    inputs: Any, sources: Mapping[str, Any], principals: Mapping[str, Any]
) -> dict[str, Any]:
    _allowed(inputs, "LB-CUSTODY")
    source = sources.get("person_connection_source")
    if not callable(source):
        raise _Blocked("person_connection_source_unavailable")
    writer = principals.get("writer")
    if writer is None:
        raise _Blocked("writer_principal_unavailable")
    before = _observer_snapshot(sources)
    with source(writer) as connection:
        if (
            getattr(connection, "autocommit", None) is True
            or int(connection.info.transaction_status) != 0
        ):
            raise _Blocked("caller_connection_not_idle")
        temp = "arras_custody_" + uuid.uuid4().hex[:12]
        connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE")
        # Truss admission requires a finite, nonzero caller statement timeout.
        # Keep it caller-owned and bounded while proving the outer transaction
        # survives public Truss work and savepoint rollback.
        connection.execute("SET LOCAL statement_timeout = '2000ms'")
        connection.execute(f'CREATE TEMPORARY TABLE "{temp}" (marker text NOT NULL)')
        connection.execute(f'INSERT INTO "{temp}" VALUES (%s)', ("caller-owned-prework",))
        connection.execute("SAVEPOINT arras_lakebase_custody")
        pre_identity, prework = _caller_state(connection, temp)
        valid_rows, refusal_name = _query_on_caller_transaction(connection)
        post_identity, after_work = _caller_state(connection, temp)
        if prework != after_work or pre_identity != post_identity:
            raise _Failed("caller_state_changed")
        connection.execute("ROLLBACK TO SAVEPOINT arras_lakebase_custody")
        if connection.execute(f'SELECT marker FROM "{temp}"').fetchall() != prework:
            raise _Failed("caller_savepoint_not_recoverable")
        connection.rollback()
    after = _observer_snapshot(sources)
    if before["sha256"] != after["sha256"]:
        raise _Failed("native_state_changed")
    return {
        "caller_identity_sha256": hashlib.sha256(
            json.dumps(pre_identity, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
        "caller_prework_count": len(prework),
        "caller_savepoint_restored": True,
        "public_query_row_count": len(valid_rows),
        "public_refusal_type": refusal_name,
        "native_before_sha256": before["sha256"],
        "native_after_sha256": after["sha256"],
    }


def _run_acl(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
    baseline_observed: Any,
) -> dict[str, Any]:
    _allowed(inputs, "LB-ACL")
    person_summary = _person_membership_summary(baseline_observed)
    before = _observer_snapshot(sources)
    module_access = inputs.target["resources"]["module_access"]
    ordinary = tuple(inputs.target["resources"]["ordinary_role_names"])
    writer, reader, denied, registrar = (
        principals.get("writer"),
        principals.get("reader"),
        principals.get("denied"),
        principals.get("registrar"),
    )
    if any(person is None for person in (writer, reader, denied, registrar)):
        raise _Blocked("authorized_principals_unavailable")
    from arras.errors import Invalid, Refused

    host = _public_host(backend, registrar)
    code = "acl-" + uuid.uuid4().hex[:20]
    try:
        _insert_probe(
            host,
            writer,
            "selected-writer",
            code=code,
            key="lakebase-acl-" + uuid.uuid4().hex,
        )
        rows = _query_probe(backend, reader)
        if not any(
            row.get("code") == code and row.get("value") == "selected-writer" for row in rows
        ):
            raise _Failed("selected_writer_readback_failed")
        try:
            backend.document(denied, _MODULE)
        except (Invalid, Refused):
            denied_refused = True
        else:
            raise _Failed("denied_principal_catalog_read_succeeded")
    except (_Blocked, _Failed):
        raise
    except Exception:
        raise _Failed("public_acl_operations_failed") from None

    role_facts, member_facts, grants = _acl_rows(sources, ordinary, module_access)
    ordinary_roles = _validate_acl_rows(role_facts, member_facts, grants, ordinary, module_access)
    after = _observer_snapshot(sources)
    before_acl = hashlib.sha256(
        json.dumps(
            {
                "roles": before["roles"],
                "memberships": before["memberships"],
                "database_acl": before["database_acl"],
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    after_acl = hashlib.sha256(
        json.dumps(
            {
                "roles": after["roles"],
                "memberships": after["memberships"],
                "database_acl": after["database_acl"],
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    if before_acl != after_acl:
        raise _Failed("native_acl_changed_during_probe")
    return {
        "before_acl_sha256": before_acl,
        "after_acl_sha256": after_acl,
        "ordinary_actor_count": len(ordinary_roles),
        "membership_fact_count": len(member_facts),
        "ordinary_object_grant_count": len(grants),
        "denied_catalog_refused": denied_refused,
        "selected_public_write_readback": True,
        **person_summary,
    }
