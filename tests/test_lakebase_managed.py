# SPDX-License-Identifier: MIT OR Apache-2.0
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "lakebase_managed_test_module", TOOLS / "_lakebase_managed.py"
)
assert SPEC is not None and SPEC.loader is not None
managed = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = managed
SPEC.loader.exec_module(managed)
NATIVE_SPEC = importlib.util.spec_from_file_location(
    "lakebase_managed_native_test_module", TOOLS / "_lakebase_managed_native.py"
)
assert NATIVE_SPEC is not None and NATIVE_SPEC.loader is not None
native = importlib.util.module_from_spec(NATIVE_SPEC)
sys.modules[NATIVE_SPEC.name] = native
NATIVE_SPEC.loader.exec_module(native)
LIFECYCLE_SPEC = importlib.util.spec_from_file_location(
    "lakebase_managed_lifecycle_test_module", TOOLS / "_lakebase_managed_lifecycle.py"
)
assert LIFECYCLE_SPEC is not None and LIFECYCLE_SPEC.loader is not None
lifecycle = importlib.util.module_from_spec(LIFECYCLE_SPEC)
sys.modules[LIFECYCLE_SPEC.name] = lifecycle
LIFECYCLE_SPEC.loader.exec_module(lifecycle)
access = importlib.import_module("_lakebase_managed_access")


@pytest.fixture(scope="module")
def managed_local_cluster() -> Any:
    from test_truss_harness import Cluster, available

    reason = available()
    if reason is not None:
        if os.environ.get("ARRAS_REQUIRE_TRUSS") == "1":
            pytest.fail(f"ARRAS_REQUIRE_TRUSS=1 and the Truss harness cannot run: {reason}")
        pytest.skip(reason)
    cluster = Cluster()
    try:
        yield cluster
    finally:
        cluster.close()


@contextmanager
def _local_managed_world(cluster: Any) -> Any:
    operations = importlib.import_module("_lakebase_operations")

    from arras.adapters.truss import ModuleAccess
    from arras.core import Arras
    from arras.model import Placement

    with cluster.bare_database() as bare:
        reader_role = bare.role("arras_native_reader")
        writer_role = bare.role("arras_native_writer")
        access = ModuleAccess(
            document_id="arras-lakebase-qualification-v1",
            reader_role=reader_role,
            writer_role=writer_role,
        )
        backend = bare.backend(module_access={"lakebase_qualification": access})
        installed = backend.migrate()
        registrar = bare.person("arras_native_registrar", installed.registrar_role, reader_role)
        writer = bare.person("arras_native_writer_person", reader_role, writer_role)
        reader = bare.person("arras_native_reader_person", reader_role)
        denied = bare.person("arras_native_denied")
        principals = {
            "registrar": registrar,
            "writer": writer,
            "reader": reader,
            "denied": denied,
        }
        host = Arras.start(
            {"truss": backend},
            expected=("truss",),
            admin=registrar,
            default_placement=Placement("truss"),
        )
        harness_document: Any = operations.HARNESS_MODULE_DOCUMENT
        host.session(registrar).registry().register(harness_document)
        backend.configure_access(("lakebase_qualification",))
        sources = {
            "person_connection_source": bare.connection_source,
            "installer_connection_source": bare.installing_connection,
        }
        yield bare, access, backend, principals, sources, host


class _SQLiteFeedDestination:
    """Test-owned durable sink for the selected native feed envelope."""

    def __init__(self, path: Path, destination_id: str, *, replay_mode: str | None = None) -> None:
        self.path = path
        self.destination_id = destination_id
        self.replay_mode = replay_mode
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> _SQLiteFeedDestination:
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS feed_record "
            "(destination TEXT NOT NULL, page_sha TEXT NOT NULL, request_sha TEXT NOT NULL, "
            "publication TEXT NOT NULL, content BLOB NOT NULL, semantic_sha TEXT NOT NULL, "
            "semantic_content BLOB NOT NULL, "
            "receipt BLOB NOT NULL, "
            "PRIMARY KEY(destination, publication))"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS feed_fact "
            "(destination TEXT NOT NULL, publication TEXT NOT NULL, kind TEXT NOT NULL, "
            "writer_xid TEXT, sequence INTEGER, profile TEXT NOT NULL, fact_sha TEXT NOT NULL, "
            "semantic BLOB NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS feed_entity "
            "(destination TEXT NOT NULL, publication TEXT NOT NULL, source_epoch TEXT NOT NULL, "
            "writer_xid TEXT NOT NULL, sequence INTEGER NOT NULL, entity_kind TEXT NOT NULL, "
            "entity_id INTEGER NOT NULL, entity_type INTEGER NOT NULL, document_id TEXT NOT NULL, "
            "module_id TEXT NOT NULL, definition_pin TEXT NOT NULL, record_version INTEGER NOT NULL, "
            "catalog_revision INTEGER NOT NULL, properties BLOB NOT NULL, retained BLOB NOT NULL, "
            "event_sha TEXT NOT NULL, PRIMARY KEY(destination, publication, entity_kind, entity_id))"
        )
        self.connection.commit()
        return self

    def __exit__(self, *_: Any) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def snapshot(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
        assert self.connection is not None
        rows = self.connection.execute(
            "SELECT page_sha, request_sha, publication, content, semantic_sha, semantic_content, receipt "
            "FROM feed_record WHERE destination=? ORDER BY publication",
            (self.destination_id,),
        ).fetchall()
        facts = self.connection.execute(
            "SELECT publication, kind, writer_xid, sequence, profile, fact_sha, semantic "
            "FROM feed_fact WHERE destination=? ORDER BY publication, kind, sequence",
            (self.destination_id,),
        ).fetchall()
        entities = self.connection.execute(
            "SELECT publication, source_epoch, writer_xid, sequence, entity_kind, entity_id, "
            "entity_type, document_id, module_id, definition_pin, record_version, "
            "catalog_revision, properties, retained, event_sha FROM feed_entity "
            "WHERE destination=? ORDER BY publication, entity_kind, entity_id",
            (self.destination_id,),
        ).fetchall()
        return {
            "records": tuple(tuple(row[:6]) for row in rows),
            "receipts": tuple((row[6],) for row in rows),
            "facts": tuple(tuple(row) for row in facts),
            "entities": tuple(tuple(row) for row in entities),
        }

    def apply_page(
        self,
        *,
        page_content: bytes,
        page_sha256: str,
        request_sha256: str,
        publication_id: str,
        semantic_page: Mapping[str, Any],
    ) -> bytes:
        assert self.connection is not None
        if hashlib.sha256(page_content).hexdigest() != page_sha256:
            raise ValueError("feed page digest mismatch")
        raw_payload: Any = json.loads(page_content)
        if type(raw_payload) is not dict:
            raise ValueError("unknown native feed payload shape")
        payload = cast(dict[str, Any], raw_payload)
        if set(payload) != {
            "interfaceVersion",
            "prior",
            "next",
            "writerXid",
            "configuration",
            "catalogPrerequisites",
            "revisions",
            "changes",
            "sources",
            "reservations",
        }:
            raise ValueError("unknown native feed payload shape")
        if payload["interfaceVersion"] != "truss-native-feed/0.1":
            raise ValueError("unsupported native feed payload version")
        if type(semantic_page) is not dict:
            raise ValueError("unsupported semantic feed projection")
        semantic = cast(dict[str, Any], semantic_page)
        if (
            semantic.get("interfaceVersion") != "arras-mp04-semantic-replica/1"
            or semantic.get("sourcePageSha256") != page_sha256
            or type(semantic.get("semanticSha256")) is not str
        ):
            raise ValueError("unsupported semantic feed projection")
        semantic_without_digest: dict[str, Any] = dict(semantic)
        semantic_body_sha256 = semantic_without_digest.pop("semanticSha256")
        semantic_body_bytes = json.dumps(
            semantic_without_digest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        if hashlib.sha256(semantic_body_bytes).hexdigest() != semantic_body_sha256:
            raise ValueError("semantic feed digest mismatch")
        semantic_page_bytes = json.dumps(
            semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        semantic_page_sha256 = hashlib.sha256(semantic_page_bytes).hexdigest()
        facts_value = semantic.get("facts")
        entities_value = semantic.get("entities")
        if type(facts_value) is not list or type(entities_value) is not list:
            raise ValueError("semantic feed rows unavailable")
        facts = cast(list[dict[str, Any]], facts_value)
        entities = cast(list[dict[str, Any]], entities_value)
        receipt = json.dumps(
            {
                "pageSha256": page_sha256,
                "requestSha256": request_sha256,
                "publicationId": publication_id,
                "semanticPageSha256": semantic_page_sha256,
                "semanticBodySha256": semantic_body_sha256,
                "factCount": len(facts),
                "entityCount": len(entities),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        existing = self.connection.execute(
            "SELECT page_sha, request_sha, content, semantic_sha, semantic_content, receipt "
            "FROM feed_record WHERE destination=? AND publication=?",
            (self.destination_id, publication_id),
        ).fetchone()
        if existing is not None:
            expected_existing = (
                page_sha256,
                request_sha256,
                page_content,
                semantic_page_sha256,
                semantic_page_bytes,
                receipt,
            )
            if tuple(existing) != expected_existing:
                raise ValueError("feed destination replay does not match original publication")
            if self.replay_mode == "changed_receipt":
                return receipt + b"changed"
            if self.replay_mode == "duplicate_fact":
                self.connection.execute(
                    "INSERT INTO feed_fact SELECT * FROM feed_fact "
                    "WHERE destination=? AND publication=? LIMIT 1",
                    (self.destination_id, publication_id),
                )
                self.connection.commit()
            return receipt
        self.connection.execute(
            "INSERT INTO feed_record VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(destination, publication) DO NOTHING",
            (
                self.destination_id,
                page_sha256,
                request_sha256,
                publication_id,
                page_content,
                semantic_page_sha256,
                semantic_page_bytes,
                receipt,
            ),
        )
        for fact in facts:
            self.connection.execute(
                "INSERT INTO feed_fact VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.destination_id,
                    publication_id,
                    fact["kind"],
                    fact["writer_xid"],
                    fact["sequence"],
                    fact["profile"],
                    fact["sha256"],
                    json.dumps(
                        fact["semantic"],
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode(),
                ),
            )
        for entity in entities:
            self.connection.execute(
                "INSERT INTO feed_entity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.destination_id,
                    publication_id,
                    entity["source_epoch"],
                    entity["writer_xid"],
                    entity["sequence"],
                    entity["entity_kind"],
                    entity["entity_id"],
                    entity["entity_type"],
                    entity["document_id"],
                    entity["module_id"],
                    entity["definition_pin"],
                    entity["record_version"],
                    entity["catalog_revision"],
                    json.dumps(
                        entity["properties"], sort_keys=True, separators=(",", ":")
                    ).encode(),
                    json.dumps(entity["retained"], sort_keys=True, separators=(",", ":")).encode(),
                    entity["event_sha256"],
                ),
            )
        self.connection.commit()
        return receipt


def _dryrun_delta_summary(before: Any, after: Any, approved: Any) -> dict[str, Any]:
    person = importlib.import_module("_lakebase_person")

    before_sequences: dict[str, tuple[int, bool]] = person._sequence_states(before["relations"])
    after_sequences: dict[str, tuple[int, bool]] = person._sequence_states(after["relations"])
    changed_sequences = sorted(
        name for name, state in before_sequences.items() if after_sequences[name] != state
    )
    before_relations = {row["name"]: row for row in before["relations"]}
    after_relations = {row["name"]: row for row in after["relations"]}
    changed_relations: list[tuple[str, int, int, bool]] = []
    for name in sorted(set(before_relations) | set(after_relations)):
        old = before_relations.get(name)
        new = after_relations.get(name)
        if old != new:
            old_rows = old.get("rows", ()) if old else ()
            new_rows = new.get("rows", ()) if new else ()
            changed_relations.append(
                (
                    name,
                    old.get("row_count", 0) if old else 0,
                    new.get("row_count", 0) if new else 0,
                    hashlib.sha256(json.dumps(old_rows, separators=(",", ":")).encode()).hexdigest()
                    != hashlib.sha256(
                        json.dumps(new_rows, separators=(",", ":")).encode()
                    ).hexdigest(),
                )
            )
    normalized: frozenset[str] = frozenset((*approved, *changed_sequences))
    return {
        "changed_sequences": changed_sequences,
        "changed_relations": changed_relations,
        "durable_equal_approved": person._durable_snapshot_sha256(before, approved)
        == person._durable_snapshot_sha256(after, approved),
        "durable_equal_observed": person._durable_snapshot_sha256(before, normalized)
        == person._durable_snapshot_sha256(after, normalized),
    }


def _capture_local_extensions(sources: Any) -> None:
    producer_path = os.environ.get("ARRAS_EXTENSION_CAPTURE_PRODUCER")
    capture_dir = os.environ.get("ARRAS_EXTENSION_CAPTURE_DIR")
    wheel_path = os.environ.get("ARRAS_PUBLIC49_WHEEL")
    if any(value is not None for value in (producer_path, capture_dir, wheel_path)):
        assert all(value is not None for value in (producer_path, capture_dir, wheel_path))
        producer_spec = importlib.util.spec_from_file_location(
            "truss_extension_requirement_capture", cast(str, producer_path)
        )
        assert producer_spec is not None and producer_spec.loader is not None
        producer = importlib.util.module_from_spec(producer_spec)
        producer_spec.loader.exec_module(producer)
        with sources["installer_connection_source"]() as connection:
            connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            result = producer.capture(
                connection,
                output_dir=Path(cast(str, capture_dir)),
                wheel_path=Path(cast(str, wheel_path)),
            )
            connection.rollback()
        print(f"source-bound local extension capture: {result}")


def _validate_dryrun_inventory(writer: Any, sources: Any, draft: dict[str, str]) -> None:
    person = importlib.import_module("_lakebase_person")

    artifacts = {
        "truss_version": "0.0.50",
        "truss_wheel_sha256": "7b0483bb0c624c98515cf38ec30bbbf1ca43c1250e8880e5d00d520b4b7eec00",
        "native_manifest_sha256": "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4",
        "migration_manifest_sha256": "4c6baf0282e3d0b5492f070c9c07d89ff0c9a819e748f3820f60b11c1f51c7aa",
    }
    context: dict[str, Any] = {
        "inputs": SimpleNamespace(target={"expected": artifacts}),
        "baseline_observed": {"artifacts": artifacts},
        "sources": sources,
        "sequence_deltas": [],
    }
    before = native._observer_snapshot(sources)
    validation = writer.validate("lakebase_qualification.CreateProbe", draft)
    after = native._observer_snapshot(sources)
    approved: frozenset[str] = person._approved_validation_sequences(context)
    validation_succeeded = validation.ok is True
    validation_effect_count = len(validation.effects)
    assert validation_succeeded, "public validation did not succeed"
    assert validation_effect_count == 1, "public validation returned an unexpected effect count"
    delta = _dryrun_delta_summary(before, after, approved)
    print(f"native dry-run sequence allocations: {delta['changed_sequences']}")
    print(f"native dry-run relation deltas: {delta['changed_relations']}")
    print(
        f"native dry-run durable equality: {delta['durable_equal_approved']}/{delta['durable_equal_observed']}"
    )
    _capture_local_extensions(sources)
    snapshot_pair_ok: bool = person._record_snapshot_pair(
        context, before, after, allowed_sequence_advances=approved
    )
    assert snapshot_pair_ok is True, "validated dry-run changed unapproved native state"
    print(f"native dry-run sequence delta receipt: {context['sequence_deltas']}")


class InventoryConnection:
    """A deterministic PostgreSQL response fixture for the exact inventory query bundle."""

    autocommit = False

    def __init__(self) -> None:
        self.info = SimpleNamespace(transaction_status=0)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self._last = ""

    def execute(self, statement: str, params: Any = None) -> InventoryConnection:
        self.sql.append(statement)
        self.params.append(params)
        self._last = statement
        self.info.transaction_status = (
            2 if statement.startswith("BEGIN") else self.info.transaction_status
        )
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        sql = self._last
        if "FROM pg_catalog.pg_class AS c" in sql:
            return [("records", "r", "p", False, "truss_owner")]
        if "FROM pg_catalog.pg_attribute AS a" in sql:
            return [(1, "id", "text", -1, "", True), (2, "payload", "jsonb", -1, "", True)]
        if "FROM pg_catalog.pg_sequence AS s" in sql:
            return []
        if "row_to_json(r)::text" in sql:
            return [('{"id":"record-1","payload":{"opaque":"secret"}}',)]
        if (
            "FROM pg_catalog.pg_extension AS e" in sql
            and "pg_depend" not in sql
            and "pg_proc" not in sql
        ):
            return [("plpgsql", "1.0", "pg_catalog", "postgres")]
        if "FROM pg_catalog.pg_roles AS r" in sql:
            return [("arr_test", True, False, False, False, True, False, False, -1)]
        if "FROM pg_catalog.pg_auth_members AS m" in sql:
            return []
        raise AssertionError(f"unexpected inventory query: {sql}")

    def fetchone(self) -> tuple[Any, ...]:
        sql = self._last
        if "pg_catalog.pg_inherits" in sql:
            return (0,)
        if "SELECT count(*)" in sql:
            return (1,)
        if "pg_database" in sql:
            return ("testdb", None)
        if "pg_get_serial_sequence" in sql:
            return (None,)
        if "SELECT last_value, is_called FROM" in sql:
            return (1, False)
        raise AssertionError(f"unexpected inventory query: {sql}")

    def rollback(self) -> None:
        self.info.transaction_status = 0


def test_native_inventory_reads_complete_relation_without_limit_and_returns_only_digest_for_projection() -> (
    None
):
    connection = InventoryConnection()
    inventory = native._native_inventory(connection)

    inventory_row_count_valid = inventory["row_count"] == 1
    inventory_payload_exact = inventory["relations"][0]["rows"] == (
        '{"id":"record-1","payload":{"opaque":"secret"}}',
    )
    inventory_digest_valid = len(inventory["sha256"]) == 64
    assert inventory_row_count_valid, "native inventory row count mismatch"
    assert inventory_payload_exact, "native inventory did not retain exact row bytes"
    assert inventory_digest_valid, "native inventory digest missing"
    assert any("SELECT count(*)" in sql for sql in connection.sql)
    assert any("row_to_json(r)::text" in sql and "LIMIT" not in sql for sql in connection.sql)
    assert connection.info.transaction_status == 0


def test_native_inventory_uses_identifier_quoting_for_discovered_relation_name() -> None:
    class QuotedNameConnection(InventoryConnection):
        def fetchall(self) -> list[tuple[Any, ...]]:
            if "FROM pg_catalog.pg_class AS c" in self._last:
                return [('odd"name', "r", "p", False, "truss_owner")]
            return super().fetchall()

    connection = QuotedNameConnection()
    native._native_inventory(connection)
    assert any('FROM "truss"."odd""name" AS r' in sql for sql in connection.sql)


def test_native_inventory_fails_closed_on_unhandled_relation_kinds() -> None:
    class ViewConnection(InventoryConnection):
        def fetchall(self) -> list[tuple[Any, ...]]:
            if "FROM pg_catalog.pg_class AS c" in self._last:
                return [("unexpected_view", "v", "p", False, "truss_owner")]
            return super().fetchall()

    with pytest.raises(managed._Blocked, match="native_relation_inventory_shape_invalid"):
        native._native_inventory(ViewConnection())


def test_native_inventory_refuses_partition_children_outside_observed_schema() -> None:
    class ExternalPartitionConnection(InventoryConnection):
        def fetchone(self) -> tuple[Any, ...]:
            if "pg_catalog.pg_inherits" in self._last:
                return (1,)
            return super().fetchone()

    with pytest.raises(managed._Blocked, match="native_external_partition_not_inventoryable"):
        native._native_inventory(ExternalPartitionConnection())


def test_sequence_state_allowance_preserves_sequence_definition() -> None:
    class SequenceConnection:
        def __init__(self) -> None:
            self._last = ""

        def execute(self, statement: str, params: Any = None) -> SequenceConnection:
            del params
            self._last = statement
            return self

        def fetchone(self) -> tuple[Any, ...]:
            if "SELECT last_value, is_called" in self._last:
                return (100, True)
            return (1, 1, 1, 9_223_372_036_854_775_807, 1, False, "int8")

    sequence = native._sequence_fact(
        SequenceConnection(),
        {"name": "request_receipt_row_seq", "kind": "S"},
    )
    assert sequence["sequence_definition"] == (
        1,
        1,
        1,
        9_223_372_036_854_775_807,
        1,
        False,
        "int8",
    )

    person = importlib.import_module("_lakebase_person")
    before = {
        "relations": (
            {
                **sequence,
                "sequence_state": (100, True),
            },
        ),
        "sha256": "a" * 64,
    }
    state_only = {
        "relations": (
            {
                **sequence,
                "sequence_state": (101, True),
            },
        ),
        "sha256": "b" * 64,
    }
    changed_definition = {
        "relations": (
            {
                **sequence,
                "sequence_definition": (1, 2, 1, 9_223_372_036_854_775_807, 1, False, "int8"),
                "sequence_state": (101, True),
            },
        ),
        "sha256": "c" * 64,
    }
    allowance = frozenset({"request_receipt_row_seq"})
    assert person._durable_snapshot_sha256(before, allowance) == person._durable_snapshot_sha256(
        state_only, allowance
    ), "approved sequence state advance changed durable definitions"
    assert person._durable_snapshot_sha256(before, allowance) != person._durable_snapshot_sha256(
        changed_definition, allowance
    ), "sequence definition change was hidden by allocator normalization"


def test_acl_accepts_login_only_and_rejects_either_path_to_elevated_role() -> None:
    access = importlib.import_module("_lakebase_managed_access")
    ordinary = ("ordinary_actor",)
    module_access = {"reader_role": "reader_group", "writer_role": "writer_group"}
    roles = [
        ("ordinary_actor", True, False, False, False, False, False),
        ("reader_group", False, False, False, False, False, False),
        ("writer_group", False, False, False, False, False, False),
    ]
    memberships = [
        ("ordinary_actor", role, False, False, False, False, False, False, False, False)
        for role in ("ordinary_actor", "reader_group", "writer_group")
    ]
    assert access._validate_acl_rows(roles, memberships, [], ordinary, module_access) == [roles[0]]

    elevated_usage = list(memberships)
    elevated_usage[1] = (
        "ordinary_actor",
        "reader_group",
        True,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
    )
    with pytest.raises(managed._Failed, match="can_reach_elevated_role"):
        access._validate_acl_rows(roles, elevated_usage, [], ordinary, module_access)

    no_login = list(roles)
    no_login[0] = ("ordinary_actor", False, False, False, False, False, False)
    with pytest.raises(managed._Failed, match="role_attributes"):
        access._validate_acl_rows(no_login, memberships, [], ordinary, module_access)


def test_mp01_uses_native_server_pid_on_owned_idle_tls_connection() -> None:
    endpoint = {"host": "db.example.test", "port": 5432, "database": "arras_test"}

    class Connection:
        def __init__(self) -> None:
            self.info = SimpleNamespace(
                transaction_status=0,
                backend_pid=9000,
                user="installer_role",
                host=endpoint["host"],
                port=endpoint["port"],
                dbname=endpoint["database"],
                get_parameters=lambda: {"sslmode": "verify-full", "sslrootcert": "/tmp/root.pem"},
            )
            self.pgconn = SimpleNamespace(ssl_in_use=True)
            self.autocommit = False
            self.statements: list[str] = []

        def execute(self, statement: str) -> Any:
            self.statements.append(statement)
            if statement.startswith("BEGIN"):
                assert self.info.transaction_status == 0
                self.info.transaction_status = 2
                return SimpleNamespace(fetchone=lambda: None)
            if statement.startswith("SET LOCAL"):
                assert self.info.transaction_status == 2
                return SimpleNamespace(fetchone=lambda: None)
            assert self.info.transaction_status == 2
            return SimpleNamespace(
                fetchone=lambda: (
                    2677,
                    "installer_role",
                    "installer_role",
                    "none",
                    "on",
                    "arras_test",
                    True,
                )
            )

        def rollback(self) -> None:
            self.info.transaction_status = 0

    connection = Connection()
    assert (
        lifecycle._owned_installer_server_pid(connection, {"endpoint": endpoint}, "pid_unavailable")
        == 2677
    )
    assert connection.info.backend_pid == 9000
    assert connection.info.transaction_status == 0
    assert connection.statements == [
        "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY",
        "SET LOCAL statement_timeout = '10000ms'",
        "SELECT pg_catalog.pg_backend_pid(), current_user, session_user, "
        "pg_catalog.current_setting('role'), "
        "pg_catalog.current_setting('transaction_read_only'), "
        "pg_catalog.current_database(), (SELECT ssl FROM pg_catalog.pg_stat_ssl "
        "WHERE pid=pg_catalog.pg_backend_pid())",
    ]


def test_mp01_pid_probe_preserves_fatal_error_when_rollback_also_fails() -> None:
    endpoint = {"host": "db.example.test", "port": 5432, "database": "arras_test"}
    fatal = KeyboardInterrupt("primary")

    class Connection:
        def __init__(self, *, fail_query: bool) -> None:
            self.info = SimpleNamespace(
                transaction_status=0,
                user="installer_role",
                host=endpoint["host"],
                port=endpoint["port"],
                dbname=endpoint["database"],
                get_parameters=lambda: {"sslmode": "verify-full", "sslrootcert": "/tmp/root.pem"},
            )
            self.pgconn = SimpleNamespace(ssl_in_use=True)
            self.autocommit = False
            self.fail_query = fail_query
            self.rollback_called = False

        def execute(self, statement: str) -> Any:
            if statement.startswith("BEGIN"):
                self.info.transaction_status = 2
                return SimpleNamespace(fetchone=lambda: None)
            if statement.startswith("SET LOCAL"):
                return SimpleNamespace(fetchone=lambda: None)
            if self.fail_query:
                raise fatal
            return SimpleNamespace(
                fetchone=lambda: (
                    2677,
                    "installer_role",
                    "installer_role",
                    "none",
                    "on",
                    "arras_test",
                    True,
                )
            )

        def rollback(self) -> None:
            self.rollback_called = True
            raise RuntimeError("secondary cleanup failure")

    connection = Connection(fail_query=True)
    with pytest.raises(KeyboardInterrupt) as caught:
        lifecycle._owned_installer_server_pid(connection, {"endpoint": endpoint}, "pid_unavailable")
    assert caught.value is fatal
    assert connection.rollback_called


def test_mp01_pid_probe_preserves_fatal_rollback_when_probe_error_is_ordinary() -> None:
    endpoint = {"host": "db.example.test", "port": 5432, "database": "arras_test"}
    fatal = KeyboardInterrupt("rollback cancellation")

    class Connection:
        def __init__(self) -> None:
            self.info = SimpleNamespace(
                transaction_status=0,
                user="installer_role",
                host=endpoint["host"],
                port=endpoint["port"],
                dbname=endpoint["database"],
                get_parameters=lambda: {"sslmode": "verify-full", "sslrootcert": "/tmp/root.pem"},
            )
            self.pgconn = SimpleNamespace(ssl_in_use=True)
            self.autocommit = False
            self.rollback_called = False

        def execute(self, statement: str) -> Any:
            if statement.startswith("BEGIN"):
                self.info.transaction_status = 2
                return SimpleNamespace(fetchone=lambda: None)
            if statement.startswith("SET LOCAL"):
                return SimpleNamespace(fetchone=lambda: None)
            raise RuntimeError("ordinary probe failure")

        def rollback(self) -> None:
            self.rollback_called = True
            raise fatal

    connection = Connection()
    with pytest.raises(KeyboardInterrupt) as caught:
        lifecycle._owned_installer_server_pid(connection, {"endpoint": endpoint}, "pid_unavailable")
    assert caught.value is fatal
    assert connection.rollback_called


def test_mp01_pid_probe_blocks_when_rollback_fails_without_primary_error() -> None:
    endpoint = {"host": "db.example.test", "port": 5432, "database": "arras_test"}

    class Connection:
        def __init__(self) -> None:
            self.info = SimpleNamespace(
                transaction_status=0,
                user="installer_role",
                host=endpoint["host"],
                port=endpoint["port"],
                dbname=endpoint["database"],
                get_parameters=lambda: {"sslmode": "verify-full", "sslrootcert": "/tmp/root.pem"},
            )
            self.pgconn = SimpleNamespace(ssl_in_use=True)
            self.autocommit = False

        def execute(self, statement: str) -> Any:
            if statement.startswith("BEGIN"):
                self.info.transaction_status = 2
                return SimpleNamespace(fetchone=lambda: None)
            if statement.startswith("SET LOCAL"):
                return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(
                fetchone=lambda: (
                    2677,
                    "installer_role",
                    "installer_role",
                    "none",
                    "on",
                    "arras_test",
                    True,
                )
            )

        def rollback(self) -> None:
            raise RuntimeError("cleanup")

    with pytest.raises(managed._Blocked, match="pid_unavailable"):
        lifecycle._owned_installer_server_pid(
            Connection(), {"endpoint": endpoint}, "pid_unavailable"
        )


@pytest.mark.parametrize(
    "outcome,state,pid_absent,expected",
    [
        ("invalid_transaction", "closed", True, True),
        ("invalid_transaction", "closed", False, False),
        ("transaction_unusable", "unknown", True, True),
        ("transaction_unusable", "unknown", False, False),
        ("transaction_unusable", "usable", True, False),
        ("QueryRows", "closed", True, False),
        ("other_error", "closed", True, False),
    ],
)
def test_mp02_stale_outcome_requires_independent_lease_and_pid_proof(
    outcome: str, state: str, pid_absent: bool, expected: bool
) -> None:
    assert lifecycle._stale_lease_proof_is_valid(outcome, state, pid_absent) is expected


class _Mp02PidConnection:
    def __init__(self, row: tuple[Any, ...], client_pid: int) -> None:
        self.info = SimpleNamespace(transaction_status=0, backend_pid=client_pid)
        self.row = row
        self.statements: list[str] = []
        self.rollbacks = 0

    def execute(self, statement: str) -> Any:
        self.statements.append(statement)
        if statement == "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY":
            assert self.info.transaction_status == 0
            self.info.transaction_status = 2
            return SimpleNamespace(fetchone=lambda: None)
        if statement == "SET LOCAL statement_timeout = '10000ms'":
            assert self.info.transaction_status == 2
            return SimpleNamespace(fetchone=lambda: None)
        assert statement == (
            "SELECT pg_catalog.pg_backend_pid(), current_user, session_user, "
            "pg_catalog.current_setting('transaction_read_only')"
        )
        assert self.info.transaction_status == 2
        return SimpleNamespace(fetchone=lambda: self.row)

    def rollback(self) -> None:
        self.rollbacks += 1
        self.info.transaction_status = 0


class _Mp02PidOk:
    def __init__(self, value: Any) -> None:
        self.value = value


class _Mp02PidError:
    def __init__(self) -> None:
        self.error = SimpleNamespace(code="invalid_transaction")


class QueryRows:
    pass


class _Mp02PidAssembly:
    def __init__(self, replacement: bool) -> None:
        self.replacement = replacement
        self.calls = 0

    def query_in_transaction(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        if not self.replacement or self.calls == 1:
            return _Mp02PidError()
        return _Mp02PidOk(QueryRows())


class _Mp02PidHost:
    def __init__(self, assembly: _Mp02PidAssembly, *, transaction_ok: bool = True) -> None:
        self.assembly = assembly
        self.transaction_ok = transaction_ok
        self.detached = False

    def adopt_transaction(self, *, access_mode: str) -> _Mp02PidOk | _Mp02PidError:
        assert access_mode == "read_only"
        if not self.transaction_ok:
            return _Mp02PidError()
        return _Mp02PidOk(object())

    def detach(self) -> None:
        self.detached = True


def _mp02_pid_truss_stub(
    hosts: list[_Mp02PidHost], *, transaction_ok: bool = True, assembly_ok: bool = True
) -> Any:
    stub = type(sys)("truss")
    stub.CatalogRuntimeConfiguration = type("CatalogRuntimeConfiguration", (), {})
    stub.Ok = _Mp02PidOk
    stub.Error = _Mp02PidError

    def adopt(connection: Any, **kwargs: Any) -> _Mp02PidHost:
        assert connection.info.transaction_status == 2
        assert connection.statements[:2] == [
            "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY",
            "SET LOCAL statement_timeout = '10000ms'",
        ]
        assert kwargs == {"statement_timeout_ms": 10_000, "operation_timeout_ms": 30_000}
        host = _Mp02PidHost(
            _Mp02PidAssembly(replacement=bool(hosts)), transaction_ok=transaction_ok
        )
        hosts.append(host)
        return host

    def create_reference_assembly(_config: Any, host: _Mp02PidHost) -> _Mp02PidOk | _Mp02PidError:
        if not assembly_ok:
            return _Mp02PidError()
        return _Mp02PidOk(host.assembly)

    stub.adopt_psycopg_host = adopt
    stub.create_reference_assembly = create_reference_assembly
    return stub


def _mp02_noop_allowed(*_args: Any) -> None:
    return None


def _mp02_noop_terminate(**_kwargs: Any) -> None:
    return None


def _mp02_connection_is_broken(_connection: Any) -> bool:
    return True


def _mp02_lease_state(_connection: Any) -> str:
    return "unknown"


def _mp02_native_pid_absent(_sources: Any, _target: Any, _pid: int) -> bool:
    return True


def _mp02_query_probe(_backend: Any, _principal: Any) -> list[int]:
    return [1, 2]


def test_mp02_server_pid_is_bound_to_readonly_reader_session(monkeypatch: Any) -> None:
    connections = [
        _Mp02PidConnection((2677, "reader_role", "reader_role", "on"), 9000),
        _Mp02PidConnection((2688, "reader_role", "reader_role", "on"), 9001),
    ]
    hosts: list[_Mp02PidHost] = []
    terminated: list[int] = []
    source_calls = 0

    @contextmanager
    def source(_principal: Any) -> Any:
        nonlocal source_calls
        connection = connections[source_calls]
        source_calls += 1
        try:
            yield connection
        finally:
            if connection.info.transaction_status == 2:
                connection.info.transaction_status = 0

    monkeypatch.setitem(sys.modules, "truss", _mp02_pid_truss_stub(hosts))

    def end_session(_inputs: Any, _connection: Any, _terminate: Any, pid: int) -> str:
        terminated.append(pid)
        return "a" * 64

    monkeypatch.setattr(lifecycle, "_allowed", _mp02_noop_allowed)
    monkeypatch.setattr(lifecycle, "_connection_lease_state", _mp02_lease_state)
    monkeypatch.setattr(lifecycle, "_native_server_pid_absent", _mp02_native_pid_absent)
    monkeypatch.setattr(lifecycle, "_end_session", end_session)
    monkeypatch.setattr(lifecycle, "_connection_is_broken", _mp02_connection_is_broken)
    monkeypatch.setattr(lifecycle, "_query_probe", _mp02_query_probe)
    result = lifecycle._run_session_lease(
        SimpleNamespace(
            target={"endpoint": {"host": "db.example.test", "port": 5432, "database": "arras_test"}}
        ),
        {"terminate_session": _mp02_noop_terminate},
        {"person_connection_source": source},
        {"reader": SimpleNamespace(user="reader_role", token="opaque")},
        object(),
    )
    assert terminated == [2677]
    assert result["ended_backend_pid"] == 2677
    assert connections[0].info.backend_pid == 9000
    assert connections[0].statements[:3] == [
        "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY",
        "SET LOCAL statement_timeout = '10000ms'",
        "SELECT pg_catalog.pg_backend_pid(), current_user, session_user, "
        "pg_catalog.current_setting('transaction_read_only')",
    ]
    assert all(host.detached for host in hosts)


@pytest.mark.parametrize("failure_stage", ["transaction", "assembly", "precondition"])
def test_mp02_adoption_failures_are_staged_and_cleaned_up(
    monkeypatch: Any, failure_stage: str
) -> None:
    connection = _Mp02PidConnection((2677, "reader_role", "reader_role", "on"), 9000)
    hosts: list[_Mp02PidHost] = []
    if failure_stage == "transaction":
        stub = _mp02_pid_truss_stub(hosts, transaction_ok=False)
        expected = "transaction_adoption_failed"
    elif failure_stage == "assembly":
        stub = _mp02_pid_truss_stub(hosts, assembly_ok=False)
        expected = "assembly_construction_failed"
    else:
        stub = _mp02_pid_truss_stub(hosts)
        original_execute = connection.execute

        def fail_precondition(statement: str) -> Any:
            if statement == "SET LOCAL statement_timeout = '10000ms'":
                raise RuntimeError("private diagnostic text")
            return original_execute(statement)

        connection.execute = fail_precondition
        expected = "transaction_adoption_failed"
    monkeypatch.setitem(sys.modules, "truss", stub)

    with pytest.raises(managed._Blocked, match=expected):
        lifecycle._adopt_readonly_handle(connection)
    assert connection.info.transaction_status == 0
    assert connection.rollbacks == 1
    assert all(host.detached for host in hosts)
    if failure_stage == "precondition":
        assert hosts == []


def test_mp02_invalid_session_binding_rolls_back_before_host_or_termination(
    monkeypatch: Any,
) -> None:
    connection = _Mp02PidConnection((2677, "other_role", "reader_role", "on"), 9000)
    hosts: list[_Mp02PidHost] = []
    terminated: list[int] = []

    @contextmanager
    def source(_principal: Any) -> Any:
        try:
            yield connection
        finally:
            if connection.info.transaction_status == 2:
                connection.info.transaction_status = 0

    monkeypatch.setitem(sys.modules, "truss", _mp02_pid_truss_stub(hosts))

    def unexpected_termination(*_args: Any) -> str:
        terminated.append(1)
        return "a" * 64

    monkeypatch.setattr(lifecycle, "_allowed", _mp02_noop_allowed)
    monkeypatch.setattr(lifecycle, "_end_session", unexpected_termination)
    with pytest.raises(managed._Blocked, match="backend_pid_identity_mismatch"):
        lifecycle._run_session_lease(
            SimpleNamespace(),
            {"terminate_session": _mp02_noop_terminate},
            {"person_connection_source": source},
            {"reader": SimpleNamespace(user="reader_role", token="opaque")},
            object(),
        )
    assert connection.info.transaction_status == 0
    assert hosts == []
    assert terminated == []


@pytest.mark.parametrize(
    "row,status,user",
    [
        ((True, "reader_role", "reader_role", "on"), 2, "reader_role"),
        ((0, "reader_role", "reader_role", "on"), 2, "reader_role"),
        ((-1, "reader_role", "reader_role", "on"), 2, "reader_role"),
        ((2_147_483_648, "reader_role", "reader_role", "on"), 2, "reader_role"),
        (("2677", "reader_role", "reader_role", "on"), 2, "reader_role"),
        ((2677, "other_role", "reader_role", "on"), 2, "reader_role"),
        ((2677, "reader_role", "other_role", "on"), 2, "reader_role"),
        ((2677, "reader_role", "reader_role", "off"), 2, "reader_role"),
        ((2677, "reader_role", "reader_role", "on"), 0, "reader_role"),
        ((2677, "reader_role", "reader_role", "on"), 2, ""),
    ],
)
def test_mp02_server_pid_rejects_unbound_facts(
    row: tuple[Any, ...], status: int, user: str
) -> None:
    class Connection:
        info = SimpleNamespace(transaction_status=status)

        def execute(self, _statement: str) -> Any:
            return SimpleNamespace(fetchone=lambda: row)

    with pytest.raises(managed._Blocked):
        lifecycle._readonly_server_backend_pid(Connection(), user)


def test_mp02_closed_safe_observation_requires_both_independent_proofs() -> None:
    facts = {
        "ended_backend_pid": 2677,
        "termination_operation_sha256": "a" * 64,
        "old_handle_refused": True,
        "new_session_row_count": 0,
        "old_handle_rebound": False,
        "stale_query_outcome": "transaction_unusable",
        "original_connection_state": "unknown",
        "native_pid_absent": True,
    }
    assert managed._safe_facts("MP-02", facts)["native_pid_absent"] is True
    for field, value in (
        ("native_pid_absent", False),
        ("native_pid_absent", 1),
        ("original_connection_state", "usable"),
        ("stale_query_outcome", "private_error_text"),
    ):
        invalid = dict(facts)
        invalid[field] = value
        with pytest.raises(ValueError, match="managed observation|ended-session"):
            managed._safe_facts("MP-02", invalid)


def test_fault_connection_is_bound_to_authorized_tls_actor() -> None:
    class Connection:
        def __init__(self, actor: str) -> None:
            self.info = SimpleNamespace(
                host="db.example.test",
                port=5432,
                dbname="arras_test",
                get_parameters=lambda: {
                    "sslmode": "verify-full",
                    "sslrootcert": "/tmp/root.pem",
                },
                transaction_status=0,
            )
            self.pgconn = SimpleNamespace(ssl_in_use=True)
            self.actor = actor

        def execute(self, statement: str) -> Any:
            assert "pg_stat_ssl" in statement
            self.info.transaction_status = 2
            return SimpleNamespace(
                fetchone=lambda: (
                    self.actor,
                    self.actor,
                    "none",
                    "arras_test",
                    "1234",
                    True,
                )
            )

        def rollback(self) -> None:
            self.info.transaction_status = 0

    target = {"endpoint": {"host": "db.example.test", "port": 5432, "database": "arras_test"}}
    principal = SimpleNamespace(user="authorized_writer")
    assert (
        lifecycle._verify_fault_connection(Connection(principal.user), target, principal) == "1234"
    )
    with pytest.raises(managed._Failed, match="identity_or_tls_mismatch"):
        lifecycle._verify_fault_connection(Connection("other_actor"), target, principal)

    wrong_tls = Connection(principal.user)
    wrong_tls.info.get_parameters = lambda: {"sslmode": "require", "sslrootcert": "/tmp/root.pem"}
    with pytest.raises(managed._Failed, match="endpoint_or_tls_mismatch"):
        lifecycle._verify_fault_connection(wrong_tls, target, principal)


def test_faulting_backend_binds_factory_to_exact_principal(monkeypatch: Any) -> None:
    from contextlib import contextmanager

    principal = SimpleNamespace(user="writer_role", token="opaque")
    connection = SimpleNamespace(
        info=SimpleNamespace(
            host="db.example.test",
            port=5432,
            dbname="arras_test",
            get_parameters=lambda: {
                "sslmode": "verify-full",
                "sslrootcert": "/tmp/root.pem",
            },
            transaction_status=0,
        ),
        pgconn=SimpleNamespace(ssl_in_use=True),
    )

    def execute(statement: str) -> Any:
        assert "pg_stat_ssl" in statement
        connection.info.transaction_status = 2
        return SimpleNamespace(
            fetchone=lambda: (
                principal.user,
                principal.user,
                "none",
                "arras_test",
                "1234",
                True,
            )
        )

    connection.execute = execute
    connection.rollback = lambda: setattr(connection.info, "transaction_status", 0)
    factory_calls: list[dict[str, Any]] = []
    source_calls: list[Any] = []

    def fixture_callback(**kwargs: Any) -> Callable[[Any], Any]:
        factory_calls.append(kwargs)

        def source_factory(actual_principal: Any) -> Any:
            source_calls.append(actual_principal)
            if actual_principal is not principal:
                raise managed._Blocked("fixture_principal_mismatch")

            @contextmanager
            def source() -> Any:
                yield connection

            return source()

        return source_factory

    backend = object()
    constructed: dict[str, Any] = {}

    class ModuleAccess:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    def create_backend(
        _name: str,
        person_source: Any,
        installer_source: Any,
        **kwargs: Any,
    ) -> Any:
        constructed.update(
            source=person_source,
            installer_source=installer_source,
            kwargs=kwargs,
        )
        return backend

    truss_adapter = cast(
        Any, SimpleNamespace(ModuleAccess=ModuleAccess, create_backend=create_backend)
    )
    monkeypatch.setitem(sys.modules, "arras.adapters.truss", truss_adapter)

    inputs = SimpleNamespace(
        target={
            "endpoint": {
                "host": "db.example.test",
                "port": 5432,
                "database": "arras_test",
            },
            "resources": {
                "module_access": {
                    "document_id": "arras-test",
                    "reader_role": "reader_role",
                    "writer_role": "writer_role",
                },
                "tolerated_grantees": [],
            },
        }
    )
    observed_actor: dict[str, str] = {}
    result = lifecycle._faulting_backend(
        inputs,
        {"fault_person_connection_source": fixture_callback},
        {"installer_connection_source": "installer-source"},
        {"writer": principal},
        "cut_transport_during_commit",
        request_sha256="a" * 64,
        observed_actor=observed_actor,
    )

    assert result is backend
    assert constructed["installer_source"] == "installer-source"
    with constructed["source"](principal) as yielded:
        assert yielded is connection
    assert len(factory_calls) == 1
    callback_args = factory_calls[0]
    assert callback_args == {
        "actor_label": "writer",
        "fault_mode": "cut_transport_during_commit",
        "request_sha256": "a" * 64,
        "publication_sha256": None,
        "page_sha256": None,
    }
    assert source_calls == [principal]
    assert observed_actor == {"actor": "writer_role", "actor_oid": "1234"}
    assert connection.info.transaction_status == 0
    wrong_principal = SimpleNamespace(user=principal.user, token="other")
    with pytest.raises(managed._Blocked, match="fixture_principal_mismatch"):
        with constructed["source"](wrong_principal):
            pytest.fail("the fixture must refuse a different principal object")
    assert source_calls == [principal, wrong_principal]


def test_faulting_backend_refuses_nonfactory_control_result(monkeypatch: Any) -> None:
    principal = SimpleNamespace(user="writer_role", token="opaque")
    captured: dict[str, Any] = {}

    class ModuleAccess:
        def __init__(self, **_kwargs: Any) -> None:
            pass

    def create_backend(_name: str, person_source: Any, *_args: Any, **_kwargs: Any) -> Any:
        captured["source"] = person_source
        return object()

    truss_adapter = cast(
        Any, SimpleNamespace(ModuleAccess=ModuleAccess, create_backend=create_backend)
    )
    monkeypatch.setitem(sys.modules, "arras.adapters.truss", truss_adapter)
    inputs = SimpleNamespace(
        target={
            "resources": {
                "module_access": {
                    "document_id": "arras-test",
                    "reader_role": "reader_role",
                    "writer_role": "writer_role",
                },
                "tolerated_grantees": [],
            }
        }
    )
    callback_calls: list[dict[str, Any]] = []

    def malformed_callback(**kwargs: Any) -> object:
        callback_calls.append(kwargs)
        return object()

    lifecycle._faulting_backend(
        inputs,
        {"fault_person_connection_source": malformed_callback},
        {},
        {"writer": principal},
        "cut_transport_during_commit",
    )
    with pytest.raises(managed._Blocked, match="genuine_transport_fault_control_unavailable"):
        with captured["source"](principal):
            pytest.fail("a non-callable fault source must fail before connecting")
    assert len(callback_calls) == 1
    assert callback_calls[0]["actor_label"] == "writer"


def test_original_request_receipt_binds_namespace_and_writer_context() -> None:
    request = b"lakebase_qualification.CreateProbe:stable-key"
    actor = "authorized_writer"
    actor_oid = "1234"
    installation_id = "69a219c2-c209-4df2-a184-3bc151a3bd4e"
    attempt_id = "b0bfe174-23bf-4d76-aeb9-2e07f6e52f7e"
    namespace = f"truss-person:{installation_id}:{actor_oid}".encode()
    writer_context = json.dumps(
        {
            "profile": "truss-object-group-writer/0.1",
            "attemptId": attempt_id,
            "xid": "42",
            "actorOid": actor_oid,
            "actor": actor,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    receipt_bytes = json.dumps(
        {"profile": "truss-object-group-receipt/0.1", "attemptId": attempt_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    def bytea(value: bytes) -> str:
        return "\\x" + value.hex()

    row = {
        "request_id_utf8": bytea(request),
        "namespace_identity_utf8": bytea(namespace),
        "request_sha256": bytea(hashlib.sha256(request).digest()),
        "namespace_sha256": bytea(hashlib.sha256(namespace).digest()),
        "storage_row_id": 17,
        "payload_state": "complete",
        "original_receipt_bytes": bytea(receipt_bytes),
        "expired_identity_bytes": None,
        "original_writer_context_bytes": bytea(writer_context),
        "original_writer_xid": "42",
    }
    inventory = {
        "relations": (
            {
                "name": "catalog_runtime_installation",
                "rows": (json.dumps({"installation_id": installation_id}),),
            },
            {"name": "request_receipt", "rows": (json.dumps(row, sort_keys=True),)},
            {
                "name": "runtime_object_attempt",
                "rows": (
                    json.dumps(
                        {
                            "id": attempt_id,
                            "actor_oid": 1234,
                            "writer_xid": "42",
                            "complete": True,
                            "receipt_id": 17,
                        },
                        sort_keys=True,
                    ),
                ),
            },
        )
    }
    raw, facts = lifecycle._find_exact_request_receipt(
        inventory, request, expected_actor=actor, expected_actor_oid=actor_oid
    )
    assert raw == json.dumps(row, sort_keys=True)
    assert facts["original_writer_xid"] == "42"

    with pytest.raises(managed._Failed, match="binding_invalid"):
        lifecycle._find_exact_request_receipt(
            inventory, request, expected_actor="different_actor", expected_actor_oid=actor_oid
        )

    swapped = dict(row)
    swapped["original_receipt_bytes"] = bytea(
        json.dumps(
            {
                "profile": "truss-object-group-receipt/0.1",
                "attemptId": "ab0f8f08-4f2d-4a1c-9291-978c47fcb154",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    mismatched = {
        "relations": (
            inventory["relations"][0],
            {"name": "request_receipt", "rows": (json.dumps(swapped, sort_keys=True),)},
            inventory["relations"][2],
        )
    }
    with pytest.raises(managed._Failed, match="binding_invalid"):
        lifecycle._find_exact_request_receipt(
            mismatched, request, expected_actor=actor, expected_actor_oid=actor_oid
        )


def test_fixture_controls_cannot_claim_results_or_add_undocumented_capabilities() -> None:
    def restart_compute() -> dict[str, Any]:
        return {}

    class Fixture:
        @staticmethod
        def managed_controls() -> dict[str, Any]:
            return {
                "interface_version": 1,
                "restart_compute": restart_compute,
                "passed_cases": list(managed.MANAGED_CASES),
            }

    assert managed._controls(Fixture) == {}


def test_run_managed_returns_exact_requested_cases_and_skips_controls_without_eligible_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fixture:
        calls = 0

        @classmethod
        def managed_controls(cls) -> dict[str, Any]:
            cls.calls += 1
            return {"interface_version": 1}

    inputs = SimpleNamespace(
        authorization={
            "allowed_cases": ["MP-03"],
            "allowed_operations": ["read", "install"],
        },
        required_cases=("MP-03", "LB-ACL"),
        target={
            "resources": {"ordinary_role_names": [], "module_access": {}},
            "expected": {"native_manifest_sha256": "0" * 64},
        },
    )

    def fake_run_mp03(inputs: Any, sources: Any, principals: Any, backend: Any) -> dict[str, Any]:
        return {
            "ordinary_role_count": 4,
            "direct_membership_count": 0,
            "effective_membership_count": 0,
            "elevated_membership_count": 0,
            "truss_table_privilege_count": 0,
            "allowed_query_row_count": 0,
            "allowed_query_succeeded": True,
            "ordinary_attributes_safe": True,
            "denied_catalog_refused": True,
            "snapshot_sha256": "a" * 64,
        }

    monkeypatch.setattr(managed, "_run_mp03", fake_run_mp03)
    result = managed.run_managed(
        inputs=inputs,
        fixture_module=Fixture,
        sources={},
        backend=object(),
        principals={},
        installed=object(),
        baseline_observed={},
    )
    assert [row["case"] for row in result["cases"]] == ["LB-ACL", "MP-03"]
    assert result["cases"] == [
        {"case": "LB-ACL", "status": "blocked", "code": "case_not_authorized"},
        {"case": "MP-03", "status": "passed", "code": "managed_postconditions_verified"},
    ]
    assert Fixture.calls == 0


def test_inventory_limits_fail_closed_instead_of_returning_partial_rows() -> None:
    class TruncatedConnection(InventoryConnection):
        def fetchall(self) -> list[tuple[Any, ...]]:
            if "row_to_json(r)::text" in self._last:
                return []
            return super().fetchall()

    with pytest.raises(managed._Blocked, match="native_row_count_mismatch"):
        native._native_inventory(TruncatedConnection())


def test_safe_projection_keeps_only_closed_digest_count_and_outcome_facts() -> None:
    facts = {
        "caller_identity_sha256": "a" * 64,
        "caller_prework_count": 1,
        "caller_savepoint_restored": True,
        "public_query_row_count": 0,
        "public_refusal_type": "QueryRefused",
        "native_before_sha256": "b" * 64,
        "native_after_sha256": "b" * 64,
    }
    assert managed.safe_managed_observations({"LB-CUSTODY": facts}) == {"LB-CUSTODY": facts}


def test_safe_projection_rejects_contradicted_custody_and_identity_claims() -> None:
    custody = {
        "caller_identity_sha256": "a" * 64,
        "caller_prework_count": 1,
        "caller_savepoint_restored": True,
        "public_query_row_count": 0,
        "public_refusal_type": "QueryRefused",
        "native_before_sha256": "b" * 64,
        "native_after_sha256": "b" * 64,
    }
    for key, value in (
        ("caller_savepoint_restored", False),
        ("caller_prework_count", 0),
        ("native_after_sha256", "c" * 64),
    ):
        contradicted = dict(custody)
        contradicted[key] = value
        with pytest.raises(ValueError, match="caller custody"):
            managed.safe_managed_observations({"LB-CUSTODY": contradicted})

    identity = {
        "ordinary_role_count": 4,
        "direct_membership_count": 0,
        "effective_membership_count": 0,
        "elevated_membership_count": 0,
        "truss_table_privilege_count": 0,
        "allowed_query_row_count": 0,
        "allowed_query_succeeded": True,
        "ordinary_attributes_safe": True,
        "denied_catalog_refused": True,
        "snapshot_sha256": "d" * 64,
    }
    identity["denied_catalog_refused"] = False
    with pytest.raises(ValueError, match="identity observation"):
        managed.safe_managed_observations({"MP-03": identity})


def test_safe_projection_requires_source_bound_nonvacuous_extension_evidence() -> None:
    facts = {
        "runtime_manifest_sha256": "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4",
        "source_inventory_sha256": "efba54c9ceb99137e11b7a2a95ebbb232dcde119f0cac63ecf19edafd7125b75",
        "requirements_declaration_sha256": "841579af03e375d1bafa1e6a19dc483d9d5ab096fe9a75fd36d834dfb48ee894",
        "required_extension_count": 1,
        "dependency_count": 4,
        "callable_count": 3,
        "ordinary_execute_count": 12,
        "ordinary_language_usage_count": 4,
        "ordinary_principal_count": 4,
        "bounded_vacuous_inventory": False,
        "observed_extensions_sha256": "a" * 64,
    }
    assert managed.safe_managed_observations({"MP-06": facts}) == {"MP-06": facts}
    for key, value in (
        ("bounded_vacuous_inventory", True),
        ("dependency_count", 0),
        ("requirements_declaration_sha256", "b" * 64),
    ):
        contradicted = dict(facts)
        contradicted[key] = value
        with pytest.raises(ValueError, match="extension observation"):
            managed.safe_managed_observations({"MP-06": contradicted})


def test_mp06_current_source_declaration_is_not_the_historical_database_receipt() -> None:
    identity = importlib.import_module("_lakebase_managed_identity")
    binding_path = (
        Path(__file__).parents[1]
        / "docs/helix/04-build/evidence/truss050-adoption-20261024/extension-source-binding.json"
    )
    binding_bytes = binding_path.read_bytes()
    binding = json.loads(binding_bytes)
    assert hashlib.sha256(binding_bytes).hexdigest() == (
        "7ce3846a77f705fa5d1b6cabca98cbf46dec4497a53ab652dd239e4035ee2329"
    )
    declaration = binding["extension_requirement"]
    assert declaration["public_0_0_50_source_review_sha256"] == (
        "841579af03e375d1bafa1e6a19dc483d9d5ab096fe9a75fd36d834dfb48ee894"
    )
    assert declaration["public_0_0_50_source_review_sha256"] == (identity._MP06_REQUIREMENTS_SHA256)
    assert declaration["historical_requirements_sha256"] == (
        "bedc8af0112668d1d3c4365488337610b4fb97a6e78c33b487e304449def7fc3"
    )
    assert binding["lakebase_acceptance"] == "not_run"


def test_safe_projection_requires_feed_empty_interval_drain() -> None:
    facts = {
        "consumer_id_sha256": "a" * 64,
        "feed_page_sha256": "b" * 64,
        "feed_page_count": 2,
        "transaction_page_count": 1,
        "empty_interval_drained": True,
        "source_ack_reconciled": "matched",
        "destination_receipt_sha256": "c" * 64,
        "destination_reopened_equal": True,
        "destination_replay_equal": True,
        "restart_operation_sha256": "d" * 64,
        "generation_before_sha256": "e" * 64,
        "generation_after_sha256": "f" * 64,
        "native_after_restart_sha256": "1" * 64,
    }
    assert managed.safe_managed_observations({"MP-04": facts}) == {"MP-04": facts}
    for key, value in (
        ("empty_interval_drained", False),
        ("destination_replay_equal", False),
        ("feed_page_count", 1),
        ("transaction_page_count", 2),
        ("transaction_page_count", 0),
        ("feed_page_count", 3),
    ):
        contradicted = dict(facts)
        contradicted[key] = value
        with pytest.raises(ValueError, match="feed durability"):
            managed.safe_managed_observations({"MP-04": contradicted})


def test_foreign_transaction_handle_requires_typed_refusal() -> None:
    from truss import Error, ExecutionFailure, Ok, QueryRefused, QueryUnavailable

    lifecycle = importlib.import_module("_lakebase_managed_lifecycle")
    assert lifecycle._foreign_handle_refused(
        Error(ExecutionFailure("invalid_transaction", "foreign host"))
    )
    assert not lifecycle._foreign_handle_refused(
        Error(ExecutionFailure("execution_obligation", "other failure"))
    )
    assert not lifecycle._foreign_handle_refused(Ok(QueryRefused("invalid_query")))
    assert not lifecycle._foreign_handle_refused(Ok(QueryUnavailable("resource")))
    assert not lifecycle._foreign_handle_refused(Ok(object()))


def test_ended_session_requires_no_rows_and_broken_connection() -> None:
    from truss import Error, ExecutionFailure, Ok, QueryRows

    lifecycle = importlib.import_module("_lakebase_managed_lifecycle")
    assert lifecycle._ended_session_result_has_no_rows(
        Error(ExecutionFailure("invalid_transaction", "ended session"))
    )
    assert not lifecycle._ended_session_result_has_no_rows(
        Ok(QueryRows(columns=(), rows=(), catalog_revision=1))
    )
    assert not lifecycle._ended_session_result_has_no_rows(
        Ok(QueryRows(columns=("value",), rows=(("visible",),), catalog_revision=1))
    )

    class DeadConnection:
        closed = 0
        info = SimpleNamespace(transaction_status=4)

        def execute(self, _sql: str) -> Any:
            raise OSError("connection closed")

    class LiveConnection:
        closed = 0
        info = SimpleNamespace(transaction_status=0)

        def execute(self, _sql: str) -> Any:
            return SimpleNamespace(fetchone=lambda: (1,))

    assert lifecycle._connection_is_broken(DeadConnection())
    assert not lifecycle._connection_is_broken(LiveConnection())


def test_restart_projection_requires_populated_complete_feed_drain() -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    feed = {
        "consumer_id_sha256": "a" * 64,
        "feed_page_sha256": "b" * 64,
        "feed_page_count": 2,
        "transaction_page_count": 1,
        "feed_payload_bytes": 128,
        "empty_interval_drained": True,
        "unacknowledged_replay_equal": True,
        "destination_receipt_sha256": "c" * 64,
        "source_ack_reconciled": "matched",
        "destination_reopened_equal": True,
        "destination_replay_equal": True,
    }
    managed._validate_restart_feed(feed)
    contradicted = dict(feed)
    contradicted["transaction_page_count"] = 0
    with pytest.raises(ValueError, match="restart feed postcondition"):
        managed._validate_restart_feed(contradicted)
    for invalid in (True, 0, -1, feed_module._MAX_TOTAL_FEED_BYTES + 1):
        contradicted = dict(feed)
        contradicted["feed_payload_bytes"] = invalid
        with pytest.raises(ValueError, match="restart feed postcondition"):
            managed._validate_restart_feed(contradicted)


def test_feed_delivery_payload_count_matches_restart_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    operations = importlib.import_module("_lakebase_operations")
    payload_bytes = 321
    expected_digest = operations.HARNESS_MODULE_SHA256

    def register_consumer(*_args: Any) -> None:
        return None

    def schema_binding(_sources: Any) -> dict[str, Any]:
        return {"document_sha256": expected_digest}

    def drained_pages(**_kwargs: Any) -> dict[str, Any]:
        return {
            "deliveries": [{}, {}],
            "page_sha256": "b" * 64,
            "receipt_sha256": "c" * 64,
            "payload_bytes": payload_bytes,
            "transaction_page_count": 1,
            "empty_interval_drained": True,
        }

    def open_destination(*_args: Any) -> None:
        return None

    monkeypatch.setattr(feed_module, "_register_consumer", register_consumer)
    monkeypatch.setattr(
        feed_module,
        "_load_probe_schema_binding",
        schema_binding,
    )
    monkeypatch.setattr(
        feed_module,
        "_drain_feed_pages",
        drained_pages,
    )
    facts = feed_module._feed_delivery(
        controls={"open_feed_destination": open_destination},
        sources={
            "installer_connection_source": lambda: None,
            "person_connection_source": lambda: None,
        },
        principals={"reader": object()},
        module_access={
            "reader_role": "reader_role",
            "document_id": managed._DOCUMENT_ID,
            "source_sha256": operations.HARNESS_MODULE_SHA256,
        },
        consumer_id="mp01-contract",
    )
    assert facts["feed_payload_bytes"] == payload_bytes
    managed._validate_restart_feed(facts)


def test_run_managed_rejects_one_invalid_case_without_erasing_other_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_feed = {
        "consumer_id_sha256": "a" * 64,
        "feed_page_sha256": "b" * 64,
        "feed_page_count": 2,
        "transaction_page_count": 1,
        "empty_interval_drained": True,
        "unacknowledged_replay_equal": True,
        "destination_receipt_sha256": "c" * 64,
        "source_ack_reconciled": "matched",
        "destination_reopened_equal": True,
        "destination_replay_equal": True,
    }
    mp01_facts = {
        "operation_sha256": "d" * 64,
        "generation_before_sha256": "e" * 64,
        "generation_after_sha256": "f" * 64,
        "backend_pid_changed": True,
        "public_object_count": 2,
        "native_inventory_sha256": "1" * 64,
        "feed": invalid_feed,
    }
    mp03_facts = {
        "ordinary_role_count": 4,
        "direct_membership_count": 0,
        "effective_membership_count": 0,
        "elevated_membership_count": 0,
        "truss_table_privilege_count": 4,
        "allowed_query_row_count": 1,
        "allowed_query_succeeded": True,
        "ordinary_attributes_safe": True,
        "denied_catalog_refused": True,
        "snapshot_sha256": "2" * 64,
    }
    facts_by_case = {"MP-01": mp01_facts, "MP-03": mp03_facts}

    def execute_case(case: str, *_args: Any) -> dict[str, Any]:
        return facts_by_case[case]

    monkeypatch.setattr(
        managed,
        "_execute_case",
        execute_case,
    )

    class Fixture:
        @staticmethod
        def managed_controls() -> dict[str, Any]:
            return {"interface_version": 1}

    result = managed.run_managed(
        inputs=SimpleNamespace(
            required_cases=("MP-01", "MP-03"),
            authorization={
                "allowed_cases": ["MP-01", "MP-03"],
                "allowed_operations": ["read", "apply", "feed", "refresh", "restart", "install"],
            },
        ),
        fixture_module=Fixture,
        sources={},
        backend=object(),
        principals={},
        installed=object(),
        baseline_observed={},
    )
    assert result["cases"] == [
        {"case": "MP-01", "status": "failed", "code": "managed_observation_unverified"},
        {"case": "MP-03", "status": "passed", "code": "managed_postconditions_verified"},
    ]
    assert "MP-01" not in result["observed"]
    assert result["observed"]["MP-03"] == mp03_facts


def test_feed_page_decoder_refuses_unknown_native_envelope() -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    cursor = json.dumps(
        {
            "profile": "truss-caller-asserted-feed/0.1",
            "installationId": "install",
            "sourceEpoch": "epoch",
            "consumerId": "consumer",
            "registrationId": "registration",
            "nextXid": "0",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    content = b'{"unknown":true}'
    page = SimpleNamespace(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        prior=SimpleNamespace(content=cursor),
        next=SimpleNamespace(content=cursor),
        consumer_id="consumer",
        registration_id="registration",
        writer_xid=None,
        safe_watermark_xid="0",
        outcome="empty_interval",
    )
    with pytest.raises(feed_module._Blocked, match="feed_payload_profile_unknown"):
        feed_module._decode_feed_page(
            page,
            consumer_id="consumer",
            expected_owner={"document_id": "qualification", "module_id": "lakebase_qualification"},
            expected_prior=None,
            expected_cursor_identity=None,
        )


def test_feed_drain_applies_and_reconciles_every_page_through_empty_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    identity = ("install", "epoch", "registration")
    pages = [
        SimpleNamespace(sha256="a" * 64),
        SimpleNamespace(sha256="b" * 64),
    ]
    decoded = {
        id(pages[0]): {
            "payload_bytes": 11,
            "outcome": "transaction",
            "next": b"cursor-1",
            "cursor_identity": identity,
        },
        id(pages[1]): {
            "payload_bytes": 7,
            "outcome": "empty_interval",
            "next": b"cursor-2",
            "cursor_identity": identity,
        },
    }
    read_index = 0
    applied: list[str] = []
    acknowledgements: list[str] = []
    reconciliations: list[str] = []

    def read_page(_source: Any, _reader: Any, _consumer: str) -> Any:
        nonlocal read_index
        page = pages[read_index]
        read_index += 1
        return page

    def decode_page(page: Any, **kwargs: Any) -> dict[str, Any]:
        value = decoded[id(page)]
        expected_prior = b"cursor-1" if page is pages[1] else None
        assert kwargs["expected_prior"] == expected_prior
        assert kwargs["expected_cursor_identity"] == (identity if page is pages[1] else None)
        return value

    def decode_with_canonicalizer(
        _source: Any, _reader: Any, page: Any, **kwargs: Any
    ) -> dict[str, Any]:
        return decode_page(page, **kwargs)

    def apply_page(
        _destination: Any, _destination_id: str, publication: str, page: Any, _decoded: Any
    ) -> tuple[bytes, Any, str]:
        applied.append(page.sha256)
        return (publication.encode(), {}, hashlib.sha256(page.sha256.encode()).hexdigest())

    def acknowledge(_source: Any, _reader: Any, page: Any, **_kwargs: Any) -> None:
        acknowledgements.append(page.sha256)

    def reconcile(_source: Any, _reader: Any, page: Any, **_kwargs: Any) -> None:
        reconciliations.append(page.sha256)

    def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(feed_module, "_read_page", read_page)
    monkeypatch.setattr(
        feed_module, "_decode_page_with_pg_canonicalizer", decode_with_canonicalizer
    )
    monkeypatch.setattr(feed_module, "_apply_destination", apply_page)
    monkeypatch.setattr(feed_module, "_acknowledge", acknowledge)
    monkeypatch.setattr(feed_module, "_reconcile", reconcile)
    monkeypatch.setattr(feed_module, "_destination_reopened", noop)

    result = feed_module._drain_feed_pages(
        person_source=object(),
        reader=object(),
        consumer_id="consumer",
        destination_source=object(),
        destination_id="destination",
        expected_owner={"document_id": "qualification", "module_id": "lakebase_qualification"},
    )
    assert applied == ["a" * 64, "b" * 64]
    assert acknowledgements == applied
    assert reconciliations == applied
    assert result["transaction_page_count"] == 1
    assert result["empty_interval_drained"] is True
    assert result["payload_bytes"] == 18
    assert len(result["deliveries"]) == 2


def test_feed_drain_fails_closed_when_page_bound_has_no_empty_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    page = SimpleNamespace(sha256="a" * 64)
    decoded = {
        "payload_bytes": 1,
        "outcome": "transaction",
        "next": b"cursor",
        "cursor_identity": ("install", "epoch", "registration"),
    }
    applied = 0

    def apply_page(*_args: Any) -> tuple[bytes, Any, str]:
        nonlocal applied
        applied += 1
        return b"receipt", {}, "c" * 64

    def read_page(*_args: Any) -> Any:
        return page

    def decode_with_canonicalizer(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return decoded

    def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(feed_module, "_MAX_FEED_PAGES", 2)
    monkeypatch.setattr(feed_module, "_read_page", read_page)
    monkeypatch.setattr(
        feed_module, "_decode_page_with_pg_canonicalizer", decode_with_canonicalizer
    )
    monkeypatch.setattr(feed_module, "_apply_destination", apply_page)
    monkeypatch.setattr(feed_module, "_acknowledge", noop)
    monkeypatch.setattr(feed_module, "_reconcile", noop)
    monkeypatch.setattr(feed_module, "_destination_reopened", noop)
    with pytest.raises(feed_module._Blocked, match="feed_drain_bound_exceeded"):
        feed_module._drain_feed_pages(
            person_source=object(),
            reader=object(),
            consumer_id="consumer",
            destination_source=object(),
            destination_id="destination",
            expected_owner={
                "document_id": "qualification",
                "module_id": "lakebase_qualification",
            },
        )
    assert applied == 2


def test_feed_destination_persists_semantic_page_facts_entities_and_receipt(
    tmp_path: Path,
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    cursor = {
        "profile": "truss-caller-asserted-feed/0.1",
        "installationId": "install",
        "sourceEpoch": "epoch",
        "consumerId": "consumer",
        "registrationId": "registration",
        "nextXid": "5",
    }
    content = json.dumps(
        {
            "interfaceVersion": "truss-native-feed/0.1",
            "prior": cursor,
            "next": cursor,
            "writerXid": "5",
            "configuration": {},
            "catalogPrerequisites": [],
            "revisions": [],
            "changes": [],
            "sources": [],
            "reservations": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    page_sha = hashlib.sha256(content).hexdigest()
    semantic: dict[str, Any] = {
        "interfaceVersion": "arras-mp04-semantic-replica/1",
        "consumerId": "consumer",
        "registrationId": "registration",
        "prior": cursor,
        "next": cursor,
        "priorSha256": "a" * 64,
        "nextSha256": "b" * 64,
        "outcome": "transaction",
        "writerXid": "5",
        "configuration": {},
        "facts": [],
        "entities": [],
        "sourcePageSha256": page_sha,
    }
    fact = {
        "kind": "journal",
        "writer_xid": "5",
        "sequence": 1,
        "profile": "truss-native-scalar-create/0.2",
        "sha256": "c" * 64,
        "semantic": {"journal": {"seq": 1}, "event": {"operation": "create"}},
    }
    entity = {
        "source_epoch": "epoch",
        "writer_xid": "5",
        "sequence": 1,
        "entity_kind": "object",
        "entity_id": 2,
        "entity_type": 3,
        "document_id": "qualification",
        "module_id": "lakebase_qualification",
        "definition_pin": "d" * 64,
        "record_version": 1,
        "catalog_revision": 1,
        "properties": [
            {
                "propertyId": "1",
                "definitionPin": "e" * 64,
                "value": {"kind": "string", "text": "alpha"},
            },
            {
                "propertyId": "2",
                "definitionPin": "f" * 64,
                "value": {"kind": "string", "text": "beta"},
            },
        ],
        "retained": [],
        "event_sha256": "c" * 64,
    }
    semantic["facts"] = [fact]
    semantic["entities"] = [entity]
    semantic["semanticSha256"] = hashlib.sha256(
        json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    page = SimpleNamespace(content=content, sha256=page_sha)

    def open_destination(*, destination_id: str) -> _SQLiteFeedDestination:
        return _SQLiteFeedDestination(tmp_path / "semantic-feed.sqlite3", destination_id)

    receipt, state, request_sha = feed_module._apply_destination(
        open_destination,
        "destination",
        "publication",
        page,
        {"semantic": semantic, "facts": [fact], "entities": [entity]},
    )
    assert request_sha == page_sha
    assert b'"semanticPageSha256"' in receipt
    assert len(state["records"]) == 1
    assert len(state["facts"]) == 1
    assert len(state["entities"]) == 1
    assert (
        state["records"][0][5]
        == json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    feed_module._destination_reopened(open_destination, "destination", state)

    def open_changed_receipt(*, destination_id: str) -> _SQLiteFeedDestination:
        return _SQLiteFeedDestination(
            tmp_path / "changed-receipt.sqlite3", destination_id, replay_mode="changed_receipt"
        )

    with pytest.raises(feed_module._Failed, match="feed_destination_replay_receipt_mismatch"):
        feed_module._apply_destination(
            open_changed_receipt,
            "destination",
            "publication",
            page,
            {"semantic": semantic, "facts": [fact], "entities": [entity]},
        )

    def open_duplicate_fact(*, destination_id: str) -> _SQLiteFeedDestination:
        return _SQLiteFeedDestination(
            tmp_path / "duplicate-fact.sqlite3", destination_id, replay_mode="duplicate_fact"
        )

    with pytest.raises(feed_module._Failed, match="feed_destination_replay_mutated_state"):
        feed_module._apply_destination(
            open_duplicate_fact,
            "destination",
            "publication",
            page,
            {"semantic": semantic, "facts": [fact], "entities": [entity]},
        )


def test_feed_replica_query_requires_complete_duplicate_sensitive_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    probe_module = importlib.import_module("_lakebase_managed_feed_probe")
    public_module = importlib.import_module("_lakebase_managed_public")
    entities = [
        {
            "properties": [
                {
                    "propertyId": "2",
                    "definitionPin": "b" * 64,
                    "value": {"kind": "string", "text": "first"},
                },
                {
                    "propertyId": "9",
                    "definitionPin": "a" * 64,
                    "value": {"kind": "string", "text": "alpha"},
                },
            ]
        },
        {
            "properties": [
                {
                    "propertyId": "2",
                    "definitionPin": "b" * 64,
                    "value": {"kind": "string", "text": "second"},
                },
                {
                    "propertyId": "9",
                    "definitionPin": "a" * 64,
                    "value": {"kind": "string", "text": "beta"},
                },
            ]
        },
    ]
    deliveries = [{"decoded": {"entities": entities}}]
    schema_binding = {
        "property_names": {"2": "value", "9": "code"},
        "property_order": ["2", "9"],
        "property_pins": {"2": "b" * 64, "9": "a" * 64},
    }

    def complete_rows(_backend: Any, _reader: Any) -> tuple[dict[str, str], ...]:
        return (
            {"code": "alpha", "value": "first"},
            {"code": "beta", "value": "second"},
        )

    def missing_row(_backend: Any, _reader: Any) -> tuple[dict[str, str], ...]:
        return ({"code": "alpha", "value": "first"},)

    def duplicate_row(_backend: Any, _reader: Any) -> tuple[dict[str, str], ...]:
        return (
            {"code": "alpha", "value": "first"},
            {"code": "beta", "value": "second"},
            {"code": "beta", "value": "second"},
        )

    def bound_schema(_backend: Any, _reader: Any) -> None:
        return None

    monkeypatch.setattr(probe_module, "_validate_probe_schema_binding", bound_schema)
    monkeypatch.setattr(
        public_module,
        "_query_probe",
        complete_rows,
    )
    feed_module._verify_replica_query(object(), object(), deliveries, schema_binding)

    monkeypatch.setattr(
        public_module,
        "_query_probe",
        missing_row,
    )
    with pytest.raises(feed_module._Failed, match="feed_replica_public_query_mismatch"):
        feed_module._verify_replica_query(object(), object(), deliveries, schema_binding)

    monkeypatch.setattr(
        public_module,
        "_query_probe",
        duplicate_row,
    )
    with pytest.raises(feed_module._Failed, match="feed_replica_public_query_mismatch"):
        feed_module._verify_replica_query(object(), object(), deliveries, schema_binding)

    wrong_pins = dict(schema_binding, property_pins={"2": "f" * 64, "9": "a" * 64})
    with pytest.raises(feed_module._Blocked, match="feed_probe_schema_binding_unavailable"):
        probe_module._probe_pairs_from_entities(entities, wrong_pins)

    invalid_cells: tuple[Any, ...] = (
        "alpha",
        {"kind": "integer", "text": "1"},
        {"kind": "string"},
        {"kind": "string", "text": "alpha", "extra": True},
    )
    for invalid_cell in invalid_cells:
        malformed = [
            {"properties": [dict(prop) for prop in entity["properties"]]} for entity in entities
        ]
        malformed[0]["properties"][0]["value"] = invalid_cell
        with pytest.raises(feed_module._Blocked, match="feed_probe_property_shape_unsupported"):
            probe_module._probe_pairs_from_entities(malformed, schema_binding)


def test_selected_history_carrier_preserves_only_exact_typed_string_cells() -> None:
    carriers = importlib.import_module("_lakebase_managed_feed_carriers")
    identity = {
        "id": "7",
        "typeId": "9",
        "definitionPin": "a" * 64,
        "owner": {"documentId": "qualification", "moduleId": "lakebase_qualification"},
    }
    after: dict[str, Any] = {
        "interfaceVersion": "truss-history-record/0.1.0",
        "kind": "object",
        "identity": identity,
        "recordVersion": "1",
        "catalogRevision": "1",
        "createdAt": "2026-10-23T00:00:00Z",
        "updatedAt": "2026-10-23T00:00:00Z",
        "properties": [
            {
                "propertyId": "1",
                "definitionPin": "b" * 64,
                "value": {"kind": "string", "text": "alpha"},
            },
            {
                "propertyId": "2",
                "definitionPin": "c" * 64,
                "value": {"kind": "string", "text": "beta"},
            },
        ],
        "retained": [],
        "ownership": {"state": "rootless"},
    }
    event = {"historyProfile": "truss-native-scalar-create/0.2"}
    schema_binding = {
        "revision": 1,
        "property_order": ["1", "2"],
        "property_pins": {"1": "b" * 64, "2": "c" * 64},
    }
    props = carriers._validate_history_image({"rev": 1}, after, identity, event, schema_binding)
    assert props == after["properties"]

    invalid_cells: tuple[Any, ...] = (
        "alpha",
        {"kind": "integer", "text": "1"},
        {"kind": "string"},
        {"kind": "string", "text": "alpha", "extra": True},
    )
    for invalid_cell in invalid_cells:
        malformed = dict(after)
        malformed["properties"] = [dict(prop) for prop in after["properties"]]
        malformed["properties"][0]["value"] = invalid_cell
        with pytest.raises(carriers._Blocked, match="feed_history_property_unsupported"):
            carriers._validate_history_image({"rev": 1}, malformed, identity, event, schema_binding)


def test_feed_schema_binding_uses_native_property_ids_and_pins() -> None:
    probe_module = importlib.import_module("_lakebase_managed_feed_probe")
    operations = importlib.import_module("_lakebase_operations")
    metadata = {
        "typeId": "42",
        "revision": "7",
        "typePin": "c" * 64,
        "propertyOrder": ["2", "9"],
        "propertyPins": {"2": "b" * 64, "9": "a" * 64},
        "propertyAccess": {},
        "keyCodecs": {},
    }
    document_text = operations.HARNESS_MODULE_DOCUMENT.decode("utf-8")
    document_sha256 = hashlib.sha256(document_text.encode("utf-8")).hexdigest()
    rows = [
        (
            7,
            "0.1.0",
            document_sha256,
            document_text,
            42,
            "c" * 64,
            "b" * 64,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            2,
            "value",
            "lakebase_qualification",
            "Probe.value",
            "string",
            "required",
            "one",
        ),
        (
            7,
            "0.1.0",
            document_sha256,
            document_text,
            42,
            "c" * 64,
            "a" * 64,
            json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            9,
            "code",
            "lakebase_qualification",
            "Probe.code",
            "string",
            "required",
            "one",
        ),
    ]
    binding = probe_module._normalize_probe_schema_rows(rows, operations.HARNESS_MODULE_DOCUMENT)
    assert binding["property_order"] == ["2", "9"]
    assert binding["property_names"] == {"2": "value", "9": "code"}
    assert binding["property_pins"] == {"2": "b" * 64, "9": "a" * 64}

    wrong_name = list(rows)
    wrong_name[0] = (
        *wrong_name[0][:9],
        "code",
        "lakebase_qualification",
        "Probe.code",
        *wrong_name[0][12:],
    )
    with pytest.raises(probe_module._Blocked, match="feed_probe_schema_binding_ambiguous"):
        probe_module._normalize_probe_schema_rows(wrong_name, operations.HARNESS_MODULE_DOCUMENT)

    wrong_pin_metadata = dict(metadata, propertyPins={"2": "e" * 64, "9": "a" * 64})
    wrong_pin = [
        (*row[:7], json.dumps(wrong_pin_metadata, sort_keys=True, separators=(",", ":")), *row[8:])
        for row in rows
    ]
    with pytest.raises(probe_module._Blocked, match="feed_probe_schema_property_pins_unavailable"):
        probe_module._normalize_probe_schema_rows(wrong_pin, operations.HARNESS_MODULE_DOCUMENT)

    wrong_source_pin = list(rows)
    wrong_source_pin[0] = (*wrong_source_pin[0][:6], "f" * 64, *wrong_source_pin[0][7:])
    with pytest.raises(probe_module._Blocked, match="feed_probe_schema_property_pins_unavailable"):
        probe_module._normalize_probe_schema_rows(
            wrong_source_pin, operations.HARNESS_MODULE_DOCUMENT
        )


def test_feed_configuration_requires_exact_selected_layout_object() -> None:
    feed_codec = importlib.import_module("_lakebase_managed_feed_codec")
    configuration: dict[str, Any] = {
        "releaseId": "truss-catalog-runtime/0.74-candidate",
        "releaseSha256": "288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4",
        "layoutProfile": {
            "identity": "truss-layout",
            "sha256": "cf417e0af5d37dd61fa5f39f818d2e7282a29e6c6c6ab7fc0b26dcdde99e7dec",
            "version": "1.0",
        },
        "preparationConfiguration": {},
        "settings": {},
    }
    feed_codec._validate_configuration(configuration)
    wrong_layout = dict(configuration)
    wrong_layout["layoutProfile"] = "truss-layout/1.0"
    with pytest.raises(feed_codec._Blocked, match="feed_configuration_profile_unknown"):
        feed_codec._validate_configuration(wrong_layout)


def test_feed_json_refuses_fractional_numbers_before_semantic_canonicalization() -> None:
    feed_codec = importlib.import_module("_lakebase_managed_feed_codec")
    with pytest.raises(feed_codec._Blocked, match="feed_revision_profile_unknown"):
        feed_codec._json_bytes(b'{"value":1.25}', "feed_revision_profile_unknown")


def test_owned_create_history_profile_requires_known_ownership_shape() -> None:
    feed_carriers = importlib.import_module("_lakebase_managed_feed_carriers")
    feed_carriers._validate_history_ownership({"state": "rootless"})
    feed_carriers._validate_history_ownership(
        {
            "state": "owned",
            "root": {
                "id": "1",
                "typeId": "2",
                "definitionPin": "a" * 64,
                "owner": {"documentId": "qualification", "moduleId": "lakebase_qualification"},
            },
        }
    )
    with pytest.raises(feed_carriers._Blocked, match="feed_history_ownership_unknown"):
        feed_carriers._validate_history_ownership({"state": "owned", "root": {"id": "1"}})


def test_native_history_group_digest_is_rechecked_after_outer_wrapper_rehash() -> None:
    feed_carriers = importlib.import_module("_lakebase_managed_feed_carriers")
    feed_codec = importlib.import_module("_lakebase_managed_feed_codec")
    origin = {"asserted": {"operation": "create"}, "databaseRole": "writer"}
    identity = {
        "id": "7",
        "typeId": "9",
        "definitionPin": "a" * 64,
        "owner": {"documentId": "qualification", "moduleId": "lakebase_qualification"},
    }
    event: dict[str, Any] = {
        "interfaceVersion": "truss-history-event/0.2.0-proposal",
        "sourceEpoch": "epoch",
        "historyProfile": "truss-native-owned-create/0.1",
        "xid": "42",
        "seq": "1",
        "identity": identity,
        "eventVersion": "1",
        "eventCatalogRevision": "1",
        "operation": "create",
        "after": {
            "interfaceVersion": "truss-history-record/0.1.0",
            "kind": "object",
            "identity": identity,
            "recordVersion": "1",
            "catalogRevision": "1",
            "createdAt": "2026-10-23T00:00:00Z",
            "updatedAt": "2026-10-23T00:00:00Z",
            "properties": [
                {
                    "propertyId": "1",
                    "definitionPin": "b" * 64,
                    "value": {"kind": "string", "text": "alpha"},
                },
                {
                    "propertyId": "2",
                    "definitionPin": "c" * 64,
                    "value": {"kind": "string", "text": "beta"},
                },
            ],
            "retained": [],
            "ownership": {"state": "rootless"},
        },
        "origin": origin,
        "mutationGroup": {
            "profile": "truss-history-group/0.1.0",
            "eventCount": "1",
            "orderedEventDigest": "d" * 64,
        },
    }
    origin_bytes = feed_codec._canonical(origin)
    origin_wrapper = {
        "interfaceVersion": "truss-journal-exact-bytes/0.2.0-proposal",
        "eventInterfaceVersion": "truss-history-event/0.2.0-proposal",
        "component": "origin",
        "canonicalizationProfile": feed_codec._CANONICALIZATION_PROFILE,
        "bytesBase64": base64.b64encode(origin_bytes).decode("ascii"),
        "bytesSha256": hashlib.sha256(origin_bytes).hexdigest(),
    }

    def row_for(current: dict[str, Any]) -> dict[str, Any]:
        event_bytes = feed_codec._canonical(current)
        return {
            "seq": 1,
            "at": "2026-10-23T00:00:00Z",
            "xid": "42",
            "entity_kind": "o",
            "entity_id": 7,
            "entity_type": 9,
            "ver": 1,
            "op": "create",
            "prop_id": None,
            "old_value": None,
            "new_value": {
                "interfaceVersion": "truss-journal-exact-bytes/0.2.0-proposal",
                "eventInterfaceVersion": "truss-history-event/0.2.0-proposal",
                "component": "event",
                "canonicalizationProfile": feed_codec._CANONICALIZATION_PROFILE,
                "bytesBase64": base64.b64encode(event_bytes).decode("ascii"),
                "bytesSha256": hashlib.sha256(event_bytes).hexdigest(),
            },
            "rev": 1,
            "origin": origin_wrapper,
        }

    def expected_digest(raw: bytes) -> str:
        return "d" * 64 if type(raw) is bytes else ""

    checked = feed_carriers._decode_journal(
        row_for(event),
        writer_xid="42",
        expected_source_epoch="epoch",
        expected_owner={"document_id": "qualification", "module_id": "lakebase_qualification"},
        schema_binding={
            "type_id": "9",
            "type_pin": "a" * 64,
            "revision": 1,
            "property_order": ["1", "2"],
            "property_pins": {"1": "b" * 64, "2": "c" * 64},
        },
        ordered_event_digest=expected_digest,
    )
    assert checked[0]["profile"] == "truss-native-owned-create/0.1"

    tampered_event = dict(event)
    tampered_event["mutationGroup"] = dict(event["mutationGroup"])
    tampered_event["mutationGroup"]["orderedEventDigest"] = "e" * 64
    with pytest.raises(feed_carriers._Blocked, match="feed_mutation_group_digest_mismatch"):
        feed_carriers._decode_journal(
            row_for(tampered_event),
            writer_xid="42",
            expected_source_epoch="epoch",
            expected_owner={"document_id": "qualification", "module_id": "lakebase_qualification"},
            schema_binding={
                "type_id": "9",
                "type_pin": "a" * 64,
                "revision": 1,
                "property_order": ["1", "2"],
                "property_pins": {"1": "b" * 64, "2": "c" * 64},
            },
            ordered_event_digest=expected_digest,
        )


def test_settlement_projection_requires_cut_mode_and_ordered_driver_outcome() -> None:
    facts = {
        "fault_mode": "cut_transport_during_commit",
        "transport_event_count": 4,
        "transport_phases": (
            "commit_entered",
            "transport_interrupted",
            "driver_error",
            "connection_closed",
        ),
        "public_initial_outcome_type": "CommitUnknown",
        "idempotency_retry_receipt_type": "Receipt",
        "exactly_one_public_object": True,
        "original_request_receipt_sha256": "a" * 64,
        "native_before_sha256": "b" * 64,
        "native_after_sha256": "c" * 64,
    }
    assert managed.safe_managed_observations({"LB-SETTLEMENT": facts}) == {"LB-SETTLEMENT": facts}
    facts["transport_phases"] = (
        "commit_entered",
        "driver_error",
        "transport_interrupted",
        "connection_closed",
    )
    with pytest.raises(ValueError, match="phase sequence"):
        managed.safe_managed_observations({"LB-SETTLEMENT": facts})


def test_safe_projection_preserves_internally_recovered_commit_receipt_without_claiming_unknown() -> (
    None
):
    facts = {
        "fault_mode": "cut_transport_during_commit",
        "transport_event_count": 4,
        "transport_phases": (
            "commit_entered",
            "transport_interrupted",
            "driver_error",
            "connection_closed",
        ),
        "public_initial_outcome_type": "Receipt",
        "idempotency_retry_receipt_type": "Receipt",
        "exactly_one_public_object": True,
        "original_request_receipt_sha256": "a" * 64,
        "native_before_sha256": "b" * 64,
        "native_after_sha256": "c" * 64,
    }
    projected = managed.safe_managed_observations({"LB-SETTLEMENT": facts})
    assert projected["LB-SETTLEMENT"]["public_initial_outcome_type"] == "Receipt"


def test_safe_projection_rejects_raw_inventory_or_unrecognized_person_facts() -> None:
    facts = {
        "caller_identity_sha256": "a" * 64,
        "caller_prework_count": 1,
        "caller_savepoint_restored": True,
        "public_query_row_count": 0,
        "public_refusal_type": "QueryRefused",
        "native_before_sha256": "b" * 64,
        "native_after_sha256": "b" * 64,
        "rows": ['{"reader_catalog_validator_secret":"must-not-leave-memory"}'],
    }
    with pytest.raises(ValueError, match="unexpected field set"):
        managed.safe_managed_observations({"LB-CUSTODY": facts})
    assert managed.safe_managed_observations({}) == {}


def _person_membership_observation() -> dict[str, Any]:
    return {
        "person": {
            "schema_version": 1,
            "membership_control": {
                "revoke_operation_sha256": "c622eff995323b75ed5956a44f9fef8fae89327389ae1171d5cce449fd315702",
                "restore_operation_sha256": "9b9f706c59c8db4ed7dff28b0a28410d98bf6a2e3e3ea6a4e20363eef9805173",
                "revoked_membership_sha256": "f065f5350029b67d9b994c356d3696f43a065e2d0727c3ede978282b53c37010",
                "restored_membership_sha256": "f065f5350029b67d9b994c356d3696f43a065e2d0727c3ede978282b53c37010",
                "fresh_connection_denied": True,
                "existing_session_denied": True,
                "restoration_verified": True,
            },
            "state": {
                "before_sha256": "d871f3efe5fe82bbe89be56c50a2abc28d5e0990a3eed3c86973ae54a15ad39a",
                "after_sha256": "d871f3efe5fe82bbe89be56c50a2abc28d5e0990a3eed3c86973ae54a15ad39a",
                "unchanged": True,
                "sequence_allocations": {
                    "comparison_count": 4,
                    "sha256": "46d68ca1ccbaaebe9a21c2679359a7da0228ba8ba6812e81c4411c61e73c21e2",
                },
            },
        }
    }


def test_person_membership_summary_preserves_validated_sequence_state() -> None:
    summary = access._person_membership_summary(_person_membership_observation())
    assert summary == {
        "person_lifecycle_facts_available": True,
        "person_membership_lifecycle_verified": True,
        "person_revoke_operation_sha256": "c622eff995323b75ed5956a44f9fef8fae89327389ae1171d5cce449fd315702",
        "person_restore_operation_sha256": "9b9f706c59c8db4ed7dff28b0a28410d98bf6a2e3e3ea6a4e20363eef9805173",
        "person_memberships_sha256": "f065f5350029b67d9b994c356d3696f43a065e2d0727c3ede978282b53c37010",
        "person_state_sha256": "d871f3efe5fe82bbe89be56c50a2abc28d5e0990a3eed3c86973ae54a15ad39a",
    }


_PERSON_STATE_MUTATIONS: tuple[Callable[[dict[str, Any]], object], ...] = (
    lambda state: state.pop("sequence_allocations"),
    lambda state: state["sequence_allocations"].update(comparison_count=True),
    lambda state: state["sequence_allocations"].update(comparison_count=3),
    lambda state: state["sequence_allocations"].update(sha256="x"),
    lambda state: state.update(sequence_allocations={"comparison_count": 4}),
    lambda state: state.update(unchanged=1),
)


@pytest.mark.parametrize("mutate", _PERSON_STATE_MUTATIONS)
def test_person_membership_summary_rejects_invalid_sequence_state(
    mutate: Callable[[dict[str, Any]], object],
) -> None:
    observation = _person_membership_observation()
    mutate(observation["person"]["state"])
    with pytest.raises(access._Blocked, match="person_state_observation_invalid"):
        access._person_membership_summary(observation)


@pytest.mark.parametrize(
    ("field", "value"),
    (("unchanged", False), ("after_sha256", "b" * 64)),
)
def test_person_membership_summary_fails_changed_durable_state(field: str, value: object) -> None:
    observation = _person_membership_observation()
    observation["person"]["state"][field] = value
    with pytest.raises(access._Failed, match="person_membership_lifecycle_postcondition_failed"):
        access._person_membership_summary(observation)


@pytest.mark.truss
def test_managed_custody_activation_feed_and_recovery_use_local_public_apis(
    managed_local_cluster: Any, tmp_path: Path
) -> None:
    feed_module = importlib.import_module("_lakebase_managed_feed")
    public_module = importlib.import_module("_lakebase_managed_public")
    identity_module = importlib.import_module("_lakebase_managed_identity")

    from arras.errors import Invalid, Refused

    with _local_managed_world(managed_local_cluster) as (
        _bare,
        access,
        backend,
        principals,
        sources,
        host,
    ):
        writer = host.session(principals["writer"])
        code = "native-managed-" + "a" * 12
        draft = {"code": code, "value": "local-native-public-api"}
        _validate_dryrun_inventory(writer, sources, draft)
        receipt = writer.invoke(
            "lakebase_qualification.CreateProbe",
            draft,
            idempotency_key="local-managed-" + code,
        )
        assert receipt.created == 1
        query_rows: tuple[dict[str, Any], ...] = tuple(
            public_module._query_probe(backend, principals["reader"])
        )
        assert any(
            row.get("code") == code and row.get("value") == "local-native-public-api"
            for row in query_rows
        )
        with pytest.raises((Invalid, Refused)):
            backend.document(principals["denied"], "lakebase_qualification")

        identity_inputs = SimpleNamespace(
            authorization={"allowed_cases": ["MP-03"], "allowed_operations": ["read", "install"]},
            target={
                "resources": {
                    "ordinary_role_names": tuple(
                        principals[label].user
                        for label in ("registrar", "writer", "reader", "denied")
                    )
                }
            },
        )
        identity_facts: dict[str, Any] = identity_module._run_mp03(
            identity_inputs, sources, principals, backend
        )
        assert identity_facts["ordinary_role_count"] == 4
        assert identity_facts["denied_catalog_refused"] is True

        inputs = SimpleNamespace(
            authorization={
                "allowed_cases": ["LB-CUSTODY"],
                "allowed_operations": ["read", "apply"],
            },
            target={
                "resources": {
                    "module_access": {
                        "document_id": access.document_id,
                        "reader_role": access.reader_role,
                        "writer_role": access.writer_role,
                    }
                }
            },
        )
        custody = managed._run_custody(inputs, sources, principals)
        assert custody["caller_savepoint_restored"] is True
        assert custody["public_refusal_type"] == "QueryRefused"
        assert custody["native_before_sha256"] == custody["native_after_sha256"]

        def open_destination(*, destination_id: str) -> _SQLiteFeedDestination:
            return _SQLiteFeedDestination(tmp_path / "feed.sqlite3", destination_id)

        feed: dict[str, Any] = feed_module._feed_delivery(
            controls={"open_feed_destination": open_destination},
            sources=sources,
            principals=principals,
            module_access={
                "document_id": access.document_id,
                "source_sha256": "0d9c4bd6c390803483937200812e838d45734e0e0ab7925374d88aceb767f16f",
                "reader_role": access.reader_role,
            },
            consumer_id="local-managed-feed-" + "b" * 12,
            backend=backend,
        )
        assert feed["feed_page_count"] == feed["transaction_page_count"] + 1
        assert feed["transaction_page_count"] >= 1
        assert feed["empty_interval_drained"] is True
        assert feed["destination_receipt_sha256"]
        assert feed["source_ack_reconciled"] == "matched"
        assert feed["destination_reopened_equal"] is True
        assert feed["destination_replay_equal"] is True
