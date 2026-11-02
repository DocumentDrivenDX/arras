# SPDX-License-Identifier: MIT OR Apache-2.0
"""Native identity and required-extension inventory checks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_common import allowed as _allowed
from _lakebase_managed_common import digest as _digest

_MP06_RUNTIME_MANIFEST_SHA256 = "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4"
_MP06_SOURCE_INVENTORY_SHA256 = "efba54c9ceb99137e11b7a2a95ebbb232dcde119f0cac63ecf19edafd7125b75"
_MP06_REQUIREMENTS_SHA256 = "841579af03e375d1bafa1e6a19dc483d9d5ab096fe9a75fd36d834dfb48ee894"
_MP06_WHEEL_SHA256 = "7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00"
_MP06_MIGRATION_MANIFEST_SHA256 = "4c6baf0282e3d0b5492f070c9c07d89ff0c9a819e748f3820f60b11c1f51c7aa"
_MP06_REQUIRED_EXTENSIONS = frozenset({("plpgsql", "1.0")})
_MP06_ROUTINE_LANGUAGES = frozenset({("plpgsql", "plpgsql", "1.0", 341), ("sql", None, None, 32)})
_MP06_EXTENSION_MEMBERS = frozenset(
    {
        ("plpgsql", "1.0", "pg_proc", "function plpgsql_call_handler()", "e"),
        ("plpgsql", "1.0", "pg_proc", "function plpgsql_inline_handler(internal)", "e"),
        ("plpgsql", "1.0", "pg_proc", "function plpgsql_validator(oid)", "e"),
        ("plpgsql", "1.0", "pg_language", "language plpgsql", "e"),
    }
)
_MP06_EXTENSION_CALLABLES = frozenset(
    {
        ("plpgsql", "plpgsql_call_handler()"),
        ("plpgsql", "plpgsql_inline_handler(internal)"),
        ("plpgsql", "plpgsql_validator(oid)"),
    }
)


def _run_mp03(
    inputs: Any,
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, "MP-03")
    source = sources.get("installer_connection_source")
    if not callable(source):
        raise _Blocked("installer_observer_unavailable")
    ordered_roles = tuple(inputs.target["resources"]["ordinary_role_names"])
    ordinary = set(ordered_roles)
    with source() as connection:
        roles = connection.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, "
            "rolinherit, rolreplication, rolbypassrls, rolconnlimit "
            "FROM pg_catalog.pg_roles ORDER BY rolname"
        ).fetchall()
        memberships = connection.execute(
            "SELECT member.rolname, role.rolname, m.admin_option, m.inherit_option, m.set_option "
            "FROM pg_catalog.pg_auth_members AS m "
            "JOIN pg_catalog.pg_roles AS member ON member.oid=m.member "
            "JOIN pg_catalog.pg_roles AS role ON role.oid=m.roleid "
            "ORDER BY member.rolname, role.rolname"
        ).fetchall()
        effective_memberships = connection.execute(
            "SELECT member.rolname, role.rolname, "
            "pg_catalog.pg_has_role(member.oid, role.oid, 'USAGE'), "
            "pg_catalog.pg_has_role(member.oid, role.oid, 'SET'), "
            "role.rolsuper, role.rolcreaterole, role.rolcreatedb, "
            "role.rolreplication, role.rolbypassrls "
            "FROM pg_catalog.pg_roles AS member CROSS JOIN pg_catalog.pg_roles AS role "
            "WHERE member.rolname = ANY(%s) "
            "AND member.rolname <> role.rolname "
            "AND (pg_catalog.pg_has_role(member.oid, role.oid, 'USAGE') "
            "OR pg_catalog.pg_has_role(member.oid, role.oid, 'SET')) "
            "ORDER BY member.rolname, role.rolname",
            (sorted(ordinary),),
        ).fetchall()
        privileges = connection.execute(
            "SELECT grantee, table_schema, table_name, privilege_type "
            "FROM information_schema.role_table_grants WHERE table_schema='truss' "
            "ORDER BY grantee, table_schema, table_name, privilege_type"
        ).fetchall()
    actor_roles = [row for row in roles if row[0] in ordinary]
    if len(actor_roles) != len(ordinary) or any(
        type(row) not in {tuple, list}
        or len(row) != 9
        or type(row[0]) is not str
        or any(type(flag) is not bool for flag in row[1:8])
        or type(row[8]) is not int
        for row in actor_roles
    ):
        raise _Failed("ordinary_role_attributes_mismatch")
    if any(
        row[1] is not True or any(row[index] for index in (2, 3, 4, 6, 7)) for row in actor_roles
    ):
        raise _Failed("ordinary_role_has_elevated_attributes")
    actor_memberships = [row for row in memberships if row[0] in ordinary]
    if any(
        type(row) not in {tuple, list}
        or len(row) != 5
        or type(row[0]) is not str
        or type(row[1]) is not str
        or any(type(flag) is not bool for flag in row[2:])
        for row in actor_memberships
    ):
        raise _Blocked("direct_membership_snapshot_invalid")
    if any(
        type(row) not in {tuple, list}
        or len(row) != 9
        or any(type(value) is not str for value in row[:2])
        or any(type(value) is not bool for value in row[2:])
        for row in effective_memberships
    ):
        raise _Blocked("effective_membership_snapshot_invalid")
    elevated_memberships = [
        row for row in effective_memberships if (row[2] or row[3]) and any(row[4:])
    ]
    if elevated_memberships:
        raise _Failed("ordinary_actor_can_set_elevated_role")
    allowed_count, denied_refused = _exercise_role_queries(ordered_roles, principals, backend)
    payload = {
        "roles": actor_roles,
        "memberships": actor_memberships,
        "effective_memberships": effective_memberships,
        "privileges": privileges,
        "allowed_query_row_count": allowed_count,
        "allowed_query_succeeded": True,
        "ordinary_attributes_safe": True,
        "elevated_membership_count": len(elevated_memberships),
        "denied_catalog_refused": denied_refused,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "ordinary_role_count": len(actor_roles),
        "direct_membership_count": len(actor_memberships),
        "effective_membership_count": len(effective_memberships),
        "elevated_membership_count": len(elevated_memberships),
        "truss_table_privilege_count": len(privileges),
        "allowed_query_row_count": allowed_count,
        "allowed_query_succeeded": True,
        "ordinary_attributes_safe": True,
        "denied_catalog_refused": denied_refused,
        "snapshot_sha256": digest,
    }


def _exercise_role_queries(
    ordered_roles: tuple[str, ...], principals: Mapping[str, Any], backend: Any
) -> tuple[int, bool]:
    labels = ("registrar", "writer", "reader", "denied")
    if len(ordered_roles) != len(labels) or any(
        principals.get(label) is None or principals[label].user != role
        for label, role in zip(labels, ordered_roles, strict=True)
    ):
        raise _Blocked("ordinary_principal_role_binding_unavailable")
    from _lakebase_managed_public import _query_probe

    from arras.errors import Invalid, Refused

    try:
        allowed_count = len(_query_probe(backend, principals["reader"]))
    except Exception:
        raise _Failed("ordinary_reader_query_failed") from None
    try:
        backend.document(principals["denied"], "lakebase_qualification")
    except (Invalid, Refused):
        return allowed_count, True
    except Exception:
        raise _Failed("ordinary_denied_query_failed_unexpectedly") from None
    raise _Failed("ordinary_denied_catalog_read_succeeded")


def _extension_contract(
    inputs: Any, controls: Mapping[str, Any]
) -> tuple[str, str, str, frozenset[tuple[str, str]]]:
    expected_package = inputs.target["expected"]
    if any(
        expected_package.get(key) != value
        for key, value in (
            ("truss_version", "0.0.50"),
            ("truss_wheel_sha256", _MP06_WHEEL_SHA256),
            ("native_manifest_sha256", _MP06_RUNTIME_MANIFEST_SHA256),
            ("migration_manifest_sha256", _MP06_MIGRATION_MANIFEST_SHA256),
        )
    ):
        raise _Failed("extension_requirement_package_tuple_mismatch")
    provenance = controls.get("required_extension_provenance")
    if not callable(provenance):
        raise _Blocked("required_extension_observation_unavailable")
    try:
        contract = provenance()
    except Exception:
        raise _Failed("required_extension_provenance_failed") from None
    if type(contract) is not dict or set(contract) != {
        "runtime_manifest_sha256",
        "source_inventory_sha256",
        "required_extensions",
    }:
        raise _Blocked("required_extension_provenance_invalid")
    runtime_hash = _digest(contract["runtime_manifest_sha256"], "runtime_manifest_unavailable")
    source_hash = _digest(contract["source_inventory_sha256"], "extension_inventory_unavailable")
    if runtime_hash != _MP06_RUNTIME_MANIFEST_SHA256:
        raise _Failed("runtime_manifest_provenance_mismatch")
    if source_hash != _MP06_SOURCE_INVENTORY_SHA256:
        raise _Failed("required_extension_inventory_provenance_mismatch")
    required = contract["required_extensions"]
    if type(required) not in {tuple, list}:
        raise _Blocked("required_extension_inventory_invalid")
    expected: set[tuple[str, str]] = set()
    for item in required:
        if (
            type(item) is not dict
            or set(item) != {"name", "version"}
            or type(item["name"]) is not str
            or not item["name"]
            or type(item["version"]) is not str
            or not item["version"]
        ):
            raise _Blocked("required_extension_inventory_invalid")
        expected.add((item["name"], item["version"]))
    if len(expected) != len(required):
        raise _Blocked("required_extension_inventory_duplicate")
    if expected != _MP06_REQUIRED_EXTENSIONS:
        raise _Failed("required_extension_declaration_mismatch")
    return runtime_hash, source_hash, _MP06_REQUIREMENTS_SHA256, _MP06_REQUIRED_EXTENSIONS


def _read_extension_inventory(
    source: Any,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    if not callable(source):
        raise _Blocked("required_extension_observation_unavailable")
    with source() as connection:
        installed = connection.execute(
            "SELECT e.extname, e.extversion, n.nspname FROM pg_catalog.pg_extension AS e "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid=e.extnamespace ORDER BY e.extname"
        ).fetchall()
        dependencies = connection.execute(
            "SELECT e.extname, e.extversion, d.classid::regclass::text, "
            "pg_catalog.pg_describe_object(d.classid, d.objid, d.objsubid), d.deptype "
            "FROM pg_catalog.pg_depend AS d "
            "JOIN pg_catalog.pg_extension AS e ON d.refclassid='pg_extension'::regclass "
            "AND d.refobjid=e.oid ORDER BY e.extname, d.classid::regclass::text, d.objid, "
            "d.refclassid::regclass::text, d.refobjid, d.deptype"
        ).fetchall()
        callables = connection.execute(
            "SELECT e.extname, p.oid::regprocedure::text, p.oid "
            "FROM pg_catalog.pg_extension AS e "
            "JOIN pg_catalog.pg_depend AS d ON d.refclassid='pg_extension'::regclass AND d.refobjid=e.oid "
            "JOIN pg_catalog.pg_proc AS p ON d.classid='pg_proc'::regclass AND d.objid=p.oid "
            "ORDER BY e.extname,p.oid::regprocedure::text"
        ).fetchall()
        routine_languages = connection.execute(
            "SELECT l.lanname, e.extname, e.extversion, count(*) "
            "FROM pg_catalog.pg_proc AS p "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid=p.pronamespace "
            "JOIN pg_catalog.pg_language AS l ON l.oid=p.prolang "
            "LEFT JOIN pg_catalog.pg_depend AS d "
            "ON d.classid='pg_catalog.pg_language'::regclass AND d.objid=l.oid "
            "AND d.objsubid=0 AND d.refclassid='pg_catalog.pg_extension'::regclass "
            "AND d.deptype='e' "
            "LEFT JOIN pg_catalog.pg_extension AS e ON e.oid=d.refobjid "
            "WHERE n.nspname='truss' "
            "GROUP BY l.lanname, e.extname, e.extversion "
            "ORDER BY l.lanname, e.extname, e.extversion"
        ).fetchall()
    return installed, dependencies, callables, routine_languages


def _ordinary_extension_privileges(
    funcs: list[Any], sources: Mapping[str, Any], principals: Mapping[str, Any]
) -> tuple[set[tuple[str, str, str, bool]], set[tuple[str, bool]]]:
    person_source = sources.get("person_connection_source")
    if not callable(person_source):
        raise _Blocked("ordinary_extension_connection_unavailable")
    facts: set[tuple[str, str, str, bool]] = set()
    language_facts: set[tuple[str, bool]] = set()
    for label in ("registrar", "writer", "reader", "denied"):
        principal = principals.get(label)
        if principal is None:
            raise _Blocked("ordinary_extension_principal_unavailable")
        with person_source(principal) as connection:
            language_usage = connection.execute(
                "SELECT pg_catalog.has_language_privilege(current_user, %s, 'USAGE')",
                ("plpgsql",),
            ).fetchone()
            if (
                type(language_usage) not in {tuple, list}
                or len(language_usage) != 1
                or type(language_usage[0]) is not bool
            ):
                raise _Blocked("ordinary_language_privilege_unavailable")
            language_facts.add((label, language_usage[0]))
            for row in funcs:
                if type(row) not in {tuple, list} or len(row) != 3:
                    raise _Blocked("extension_callable_inventory_invalid")
                name, signature, oid = row
                if type(name) is not str or type(signature) is not str or type(oid) is not int:
                    raise _Blocked("extension_callable_inventory_invalid")
                privilege = connection.execute(
                    "SELECT pg_catalog.has_function_privilege(current_user, %s, 'EXECUTE')",
                    (oid,),
                ).fetchone()
                if (
                    type(privilege) not in {tuple, list}
                    or len(privilege) != 1
                    or type(privilege[0]) is not bool
                ):
                    raise _Blocked("ordinary_extension_privilege_unavailable")
                facts.add((label, name, signature, privilege[0]))
    if len(facts) != len(funcs) * 4:
        raise _Blocked("ordinary_extension_privilege_inventory_incomplete")
    if len(language_facts) != 4:
        raise _Blocked("ordinary_language_privilege_inventory_incomplete")
    return facts, language_facts


def _run_mp06(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
) -> dict[str, Any]:
    _allowed(inputs, "MP-06")
    runtime_hash, source_hash, requirements_hash, expected = _extension_contract(inputs, controls)
    installed, dependencies, callables, routine_languages = _read_extension_inventory(
        sources.get("installer_connection_source")
    )
    if any(
        type(row) not in {tuple, list}
        or len(row) != 3
        or any(type(value) is not str for value in row)
        for row in installed
    ):
        raise _Blocked("installed_extension_inventory_invalid")
    actual = {(row[0], row[1]) for row in installed}
    if not expected.issubset(actual):
        raise _Failed("required_extension_missing_or_wrong_version")
    if ("plpgsql", "1.0", "pg_catalog") not in installed:
        raise _Failed("required_extension_schema_mismatch")
    if any(
        type(row) not in {tuple, list}
        or len(row) != 5
        or any(type(value) is not str for value in row)
        for row in dependencies
    ):
        raise _Blocked("extension_member_inventory_invalid")
    if any(
        type(row) not in {tuple, list}
        or len(row) != 3
        or type(row[0]) is not str
        or type(row[1]) is not str
        or type(row[2]) is not int
        for row in callables
    ):
        raise _Blocked("extension_callable_inventory_invalid")
    names = {name for name, _ in expected}
    deps = [row for row in dependencies if row[0] in names]
    funcs = [row for row in callables if row[0] in names]
    if len(routine_languages) != len(_MP06_ROUTINE_LANGUAGES) or any(
        type(row) not in {tuple, list}
        or len(row) != 4
        or type(row[0]) is not str
        or any(value is not None and type(value) is not str for value in row[1:3])
        or type(row[3]) is not int
        for row in routine_languages
    ):
        raise _Blocked("runtime_routine_language_inventory_invalid")
    routine_language_facts = {tuple(row) for row in routine_languages}
    if routine_language_facts != _MP06_ROUTINE_LANGUAGES:
        raise _Failed("runtime_routine_language_inventory_mismatch")
    member_facts = {tuple(row) for row in deps if type(row) in {tuple, list} and len(row) == 5}
    if len(member_facts) != len(deps) or member_facts != _MP06_EXTENSION_MEMBERS:
        raise _Failed("required_extension_member_inventory_mismatch")
    callable_facts = {
        (row[0], row[1])
        for row in funcs
        if type(row) in {tuple, list}
        and len(row) == 3
        and type(row[0]) is str
        and type(row[1]) is str
        and type(row[2]) is int
    }
    if len(callable_facts) != len(funcs) or callable_facts != _MP06_EXTENSION_CALLABLES:
        raise _Failed("required_extension_callable_inventory_mismatch")
    ordinary_execute, language_usage = _ordinary_extension_privileges(funcs, sources, principals)
    digest = hashlib.sha256(
        json.dumps(
            {
                "installed": [row for row in installed if row[0] in names],
                "members": sorted(member_facts),
                "callables": sorted(callable_facts),
                "routine_languages": sorted(routine_language_facts),
                "ordinary_execute": sorted(ordinary_execute),
                "ordinary_language_usage": sorted(language_usage),
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "runtime_manifest_sha256": runtime_hash,
        "source_inventory_sha256": source_hash,
        "requirements_declaration_sha256": requirements_hash,
        "required_extension_count": len(expected),
        "dependency_count": len(deps),
        "callable_count": len(funcs),
        "ordinary_execute_count": sum(row[3] is True for row in ordinary_execute),
        "ordinary_language_usage_count": sum(row[1] is True for row in language_usage),
        "ordinary_principal_count": len(language_usage),
        "bounded_vacuous_inventory": False,
        "observed_extensions_sha256": digest,
    }
