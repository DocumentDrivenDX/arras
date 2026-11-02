# SPDX-License-Identifier: MIT OR Apache-2.0
"""Complete bounded read-only snapshots of Truss-owned native storage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked

_MAX_RELATIONS = 512
_MAX_ROWS = 100_000
_MAX_BYTES = 16_777_216


def _relation_rows(connection: Any) -> tuple[tuple[Any, ...], ...]:
    rows = connection.execute(
        "SELECT c.relname, c.relkind, c.relpersistence, c.relispartition, "
        "pg_catalog.pg_get_userbyid(c.relowner) "
        "FROM pg_catalog.pg_class AS c "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace "
        "WHERE n.nspname='truss' "
        "ORDER BY c.relname"
    ).fetchall()
    if type(rows) not in {list, tuple} or len(rows) > _MAX_RELATIONS:
        raise _Blocked("native_relation_inventory_unbounded")
    return tuple(rows)


def _partition_ancestors(
    connection: Any, relation_rows: tuple[tuple[Any, ...], ...]
) -> dict[str, tuple[str, ...]]:
    """Read the bounded in-schema inheritance graph once and resolve table ancestry."""
    relation_kinds: dict[str, str] = {}
    for row in relation_rows:
        if (
            type(row) not in {tuple, list}
            or len(row) != 5
            or type(row[0]) is not str
            or row[1] not in {"r", "p", "S", "i", "I"}
            or row[0] in relation_kinds
        ):
            raise _Blocked("native_relation_inventory_shape_invalid")
        relation_kinds[row[0]] = row[1]

    edges = connection.execute(
        "SELECT parent_ns.nspname, parent.relname, parent.relkind, "
        "child_ns.nspname, child.relname, child.relkind "
        "FROM pg_catalog.pg_inherits AS i "
        "JOIN pg_catalog.pg_class AS parent ON parent.oid=i.inhparent "
        "JOIN pg_catalog.pg_namespace AS parent_ns ON parent_ns.oid=parent.relnamespace "
        "JOIN pg_catalog.pg_class AS child ON child.oid=i.inhrelid "
        "JOIN pg_catalog.pg_namespace AS child_ns ON child_ns.oid=child.relnamespace "
        "WHERE parent_ns.nspname='truss' OR child_ns.nspname='truss' "
        "ORDER BY parent_ns.nspname, parent.relname, child_ns.nspname, child.relname"
    ).fetchall()
    if type(edges) not in {tuple, list} or len(edges) > _MAX_RELATIONS * 2:
        raise _Blocked("native_partition_inventory_unavailable")

    parents: dict[str, set[str]] = {}
    for edge in edges:
        if (
            type(edge) not in {tuple, list}
            or len(edge) != 6
            or any(type(edge[index]) is not str for index in (0, 1, 2, 3, 4, 5))
        ):
            raise _Blocked("native_partition_inventory_shape_invalid")
        parent_schema, parent_name, parent_kind, child_schema, child_name, child_kind = edge
        if parent_schema != "truss" or child_schema != "truss":
            raise _Blocked("native_external_partition_not_inventoryable")
        if (
            relation_kinds.get(parent_name) != parent_kind
            or relation_kinds.get(child_name) != child_kind
        ):
            raise _Blocked("native_partition_inventory_shape_invalid")
        if parent_kind in {"r", "p"} and child_kind in {"r", "p"}:
            parents.setdefault(child_name, set()).add(parent_name)
        elif parent_kind not in {"i", "I"} or child_kind not in {"i", "I"}:
            raise _Blocked("native_partition_inventory_shape_invalid")

    resolved: dict[str, frozenset[str]] = {}
    visiting: set[str] = set()

    def ancestors(name: str) -> frozenset[str]:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise _Blocked("native_partition_inventory_shape_invalid")
        visiting.add(name)
        found: set[str] = set()
        for parent in parents.get(name, ()):
            found.add(parent)
            found.update(ancestors(parent))
        visiting.remove(name)
        resolved[name] = frozenset(found)
        return resolved[name]

    return {
        name: tuple(sorted(ancestors(name)))
        for name, kind in relation_kinds.items()
        if kind in {"r", "p"} and parents.get(name)
    }


def _columns(connection: Any, name: str) -> tuple[tuple[Any, ...], ...]:
    rows = connection.execute(
        "SELECT a.attnum, a.attname, t.typname, a.atttypmod, "
        "COALESCE(coll.collname,''), a.attnotnull "
        "FROM pg_catalog.pg_attribute AS a "
        "JOIN pg_catalog.pg_class AS c ON c.oid=a.attrelid "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace "
        "JOIN pg_catalog.pg_type AS t ON t.oid=a.atttypid "
        "LEFT JOIN pg_catalog.pg_collation AS coll ON coll.oid=a.attcollation "
        "WHERE n.nspname='truss' AND c.relname=%s "
        "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
        (name,),
    ).fetchall()
    if type(rows) not in {list, tuple}:
        raise _Blocked("native_column_inventory_unavailable")
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if (
            type(row) not in {list, tuple}
            or len(row) != 6
            or type(row[0]) is not int
            or any(type(value) is not str for value in (row[1], row[2], row[4]))
            or type(row[3]) is not int
            or type(row[5]) is not bool
        ):
            raise _Blocked("native_column_inventory_shape_invalid")
        normalized.append(tuple(row))
    return tuple(normalized)


def _relation_header(connection: Any, row: Any) -> dict[str, Any]:
    if (
        type(row) not in {list, tuple}
        or len(row) != 5
        or type(row[0]) is not str
        or row[1] not in {"r", "p", "S", "i", "I"}
        or row[2] not in {"p", "u", "t"}
        or type(row[3]) is not bool
        or type(row[4]) is not str
    ):
        raise _Blocked("native_relation_inventory_shape_invalid")
    name, kind, persistence, is_partition, owner = row
    return {
        "name": name,
        "kind": kind,
        "persistence": persistence,
        "partition": is_partition,
        "owner": owner,
        "columns": _columns(connection, name),
    }


def _sequence_fact(connection: Any, item: dict[str, Any]) -> dict[str, Any]:
    quoted = '"truss"."' + item["name"].replace('"', '""') + '"'
    row = connection.execute(f"SELECT last_value, is_called FROM {quoted}").fetchone()
    if (
        type(row) not in {list, tuple}
        or len(row) != 2
        or type(row[0]) is not int
        or type(row[1]) is not bool
    ):
        raise _Blocked("native_sequence_state_unavailable")
    definition = connection.execute(
        "SELECT s.seqstart, s.seqincrement, s.seqmin, s.seqmax, s.seqcache, "
        "s.seqcycle, t.typname "
        "FROM pg_catalog.pg_sequence AS s "
        "JOIN pg_catalog.pg_class AS c ON c.oid=s.seqrelid "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace "
        "JOIN pg_catalog.pg_type AS t ON t.oid=s.seqtypid "
        "WHERE n.nspname='truss' AND c.relname=%s",
        (item["name"],),
    ).fetchone()
    if (
        type(definition) not in {list, tuple}
        or len(definition) != 7
        or any(type(value) is not int for value in definition[:5])
        or type(definition[5]) is not bool
        or type(definition[6]) is not str
    ):
        raise _Blocked("native_sequence_definition_unavailable")
    item["sequence_state"] = tuple(row)
    item["sequence_definition"] = tuple(definition)
    return item


def _index_fact(connection: Any, item: dict[str, Any]) -> dict[str, Any]:
    row = connection.execute(
        "SELECT pg_catalog.pg_get_indexdef(c.oid) "
        "FROM pg_catalog.pg_class AS c "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace "
        "WHERE n.nspname='truss' AND c.relname=%s",
        (item["name"],),
    ).fetchone()
    if type(row) not in {list, tuple} or len(row) != 1 or type(row[0]) is not str:
        raise _Blocked("native_index_definition_unavailable")
    item["index_definition"] = row[0]
    return item


def _table_rows(connection: Any, item: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    quoted = '"truss"."' + item["name"].replace('"', '""') + '"'
    count_row = connection.execute(f"SELECT count(*) FROM {quoted}").fetchone()
    if (
        type(count_row) not in {list, tuple}
        or len(count_row) != 1
        or type(count_row[0]) is not int
        or count_row[0] > _MAX_ROWS
    ):
        raise _Blocked("native_row_inventory_unbounded")
    rows = connection.execute(
        f"SELECT pg_catalog.row_to_json(r)::text FROM {quoted} AS r"
    ).fetchall()
    if type(rows) not in {list, tuple} or len(rows) != count_row[0]:
        raise _Blocked("native_row_count_mismatch")
    serialized: list[str] = []
    byte_count = 0
    for row in rows:
        if type(row) not in {list, tuple} or len(row) != 1 or type(row[0]) is not str:
            raise _Blocked("native_row_serialization_invalid")
        serialized.append(row[0])
        byte_count += len(row[0].encode("utf-8", errors="strict"))
    serialized.sort()
    item["row_count"] = count_row[0]
    item["rows"] = tuple(serialized)
    return item, count_row[0], byte_count


def _relation_fact(
    connection: Any, row: Any, partition_ancestors: tuple[str, ...] = ()
) -> tuple[dict[str, Any], int, int]:
    item = _relation_header(connection, row)
    kind = item["kind"]
    if partition_ancestors:
        item["partition_ancestors"] = partition_ancestors
    if kind == "S":
        return _sequence_fact(connection, item), 0, 0
    if kind in {"i", "I"}:
        return _index_fact(connection, item), 0, 0
    if kind == "p":
        # Parent definitions are captured once; leaf table rows are enumerated
        # through relkind r so partitioned contents are not double-counted.
        item["partition_parent"] = True
        return item, 0, 0
    return _table_rows(connection, item)


def _relations(
    connection: Any,
    relation_rows: tuple[tuple[Any, ...], ...],
    partition_ancestors: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[dict[str, Any], ...], int]:
    result: list[dict[str, Any]] = []
    rows_seen = 0
    bytes_seen = 0
    for relation in relation_rows:
        item, count, byte_count = _relation_fact(
            connection, relation, partition_ancestors.get(relation[0], ())
        )
        result.append(item)
        rows_seen += count
        bytes_seen += byte_count
        if rows_seen > _MAX_ROWS or bytes_seen > _MAX_BYTES:
            raise _Blocked("native_inventory_exceeds_bound")
    return tuple(result), rows_seen


def _global_facts(connection: Any) -> dict[str, Any]:
    extensions = connection.execute(
        "SELECT e.extname, e.extversion, n.nspname, "
        "pg_catalog.pg_get_userbyid(e.extowner) "
        "FROM pg_catalog.pg_extension AS e "
        "JOIN pg_catalog.pg_namespace AS n ON n.oid=e.extnamespace ORDER BY e.extname"
    ).fetchall()
    roles = connection.execute(
        "SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolcreaterole, r.rolcreatedb, "
        "r.rolinherit, r.rolreplication, r.rolbypassrls, r.rolconnlimit "
        "FROM pg_catalog.pg_roles AS r ORDER BY r.rolname"
    ).fetchall()
    memberships = connection.execute(
        "SELECT member.rolname, role.rolname, m.admin_option, m.inherit_option, m.set_option "
        "FROM pg_catalog.pg_auth_members AS m "
        "JOIN pg_catalog.pg_roles AS member ON member.oid=m.member "
        "JOIN pg_catalog.pg_roles AS role ON role.oid=m.roleid "
        "ORDER BY member.rolname, role.rolname"
    ).fetchall()
    database = connection.execute(
        "SELECT datname, datacl::text FROM pg_catalog.pg_database "
        "WHERE datname=pg_catalog.current_database()"
    ).fetchone()
    if not all(type(rows) in {list, tuple} for rows in (extensions, roles, memberships)):
        raise _Blocked("native_global_inventory_unavailable")
    if type(database) not in {list, tuple} or len(database) != 2:
        raise _Blocked("native_database_acl_unavailable")
    return {
        "extensions": tuple(tuple(row) for row in extensions),
        "roles": tuple(tuple(row) for row in roles),
        "memberships": tuple(tuple(row) for row in memberships),
        "database_acl": tuple(database),
    }


def _native_inventory(connection: Any) -> dict[str, Any]:
    """Capture complete installed-schema relations in a bounded read-only snapshot.

    Rows stay in memory for independent before/after comparisons. The safe
    observation projection exposes only digests and counts, never row values.
    """
    if getattr(connection, "autocommit", None) is True:
        raise _Blocked("observer_autocommit_enabled")
    if int(connection.info.transaction_status) != 0:
        raise _Blocked("observer_connection_not_idle")
    try:
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        relation_rows = _relation_rows(connection)
        partition_ancestors = _partition_ancestors(connection, relation_rows)
        relations, row_count = _relations(connection, relation_rows, partition_ancestors)
        payload = {"relations": relations, **_global_facts(connection), "row_count": row_count}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return {**payload, "sha256": digest}
    finally:
        try:
            connection.rollback()
        except Exception:
            pass


def _observer_snapshot(sources: Mapping[str, Any]) -> dict[str, Any]:
    source = sources.get("installer_connection_source")
    if not callable(source):
        raise _Blocked("installer_observer_unavailable")
    try:
        with source() as connection:
            return _native_inventory(connection)
    except _Blocked:
        raise
    except Exception:
        raise _Blocked("native_inventory_observation_unavailable") from None
