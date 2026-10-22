# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""The Truss adapter's `import_records` (TR-09).

The always-on tests drive the adapter against a scripted fake of Truss's assembly (results named as
Truss names them, which the adapter recognizes by class name); the Truss-marked tests run the import
corpus cases and direct checks against a real Truss on PostgreSQL 18.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

import arras.adapters.truss.load as load
from arras.actions import Plan, Ref, Unlink
from arras.adapters.truss import CommitUnknown, TrussBackend
from arras.errors import Invalid, Refused, Unavailable
from arras.results import ImportResult
from arras.types import Principal, Statement
from test_truss_harness import _world, cluster  # noqa: F401
from test_truss_plan import ApplyAssembly, ApplyRig, RecordingWire, error, ident, ok
from test_truss_registry import ALICE

# -- Truss's import results, named as Truss names them


@dataclass(frozen=True)
class ImportCreated:
    input_index: str
    identity: Any = "id"
    version: str = "1"


@dataclass(frozen=True)
class ImportSkipped:
    input_index: str
    reason: str = "live_identity"
    identity: Any = "id"


@dataclass(frozen=True)
class Absent:
    pass


@dataclass(frozen=True)
class ImportRejected:
    input_index: str
    code: str = "invalid"


@dataclass(frozen=True)
class ImportAttemptUnknown:
    input_index: str


@dataclass(frozen=True)
class ImportReported:
    report: Any


@dataclass(frozen=True)
class BuiltImportRecords:
    context: Any
    records: tuple[Any, ...]


@dataclass(frozen=True)
class BatchedImportExecutionResult:
    result: Any
    empty_load_settlement: Any = None


@dataclass(frozen=True)
class EmptyLoadDisposition:
    disposition: str
    evidence: str = ""


@dataclass(frozen=True)
class ImportInvalid:
    diagnostic: Any = None


@dataclass(frozen=True)
class ImportResourceLimited:
    reason: str = "operation_deadline"


@dataclass(frozen=True)
class ImportExecutionFailed:
    error: Any
    report: Any = None


def reported(*outcomes: Any) -> Any:
    return ImportReported(SimpleNamespace(outcomes=tuple(outcomes)))


class ImportWire(RecordingWire):
    def import_origin(self, initiated_by: str) -> Any:
        return ("origin", "import_records", initiated_by)

    def import_source(self, author: str | None, at: str | None) -> Any:
        return None if author is None and at is None else ("source", author, at)

    def null_order(self) -> Any:
        return "null-order"

    def object_draft(
        self, document_id: str, module_id: str, record_id: str, values: Any, source: Any
    ) -> Any:
        return (
            "object",
            {
                "document_id": document_id,
                "module_id": module_id,
                "record_id": record_id,
                "values": values,
                "source": source,
            },
        )

    def edge_draft(
        self, document_id: str, module_id: str, relationship_id: str, source: Any, target: Any
    ) -> Any:
        return (
            "edge",
            {
                "document_id": document_id,
                "module_id": module_id,
                "relationship_id": relationship_id,
                "source_endpoint": source,
                "target_endpoint": target,
                "values": (),
                "order_key": "null-order",
            },
        )


class ImportAssembly(ApplyAssembly):
    def __init__(self) -> None:
        super().__init__()
        self.imports: list[Any] = []
        self.scripted: list[Any] = []  # results of import_batched_in_transaction, in order
        self.builder: Any = None  # an Outcome that replaces the records builder's answer

    def build_import_records_in_transaction(self, tx: Any, drafts: Any) -> Any:
        self.log.append(f"build:{len(drafts)}")
        context = SimpleNamespace(
            input=lambda records, load_id, asserted_origin, chunk_size: SimpleNamespace(
                records=records, load_id=load_id, origin=asserted_origin, chunk_size=chunk_size
            )
        )
        return self.builder or ok(BuiltImportRecords(context, tuple(drafts)))

    def import_batched_in_transaction(self, tx: Any, inp: Any, *, documents: Any) -> Any:
        self.log.append(f"import:{len(inp.records)}")
        self.imports.append((inp, documents))
        if self.scripted:
            result = self.scripted.pop(0)
        else:
            result = reported(
                *(ImportCreated(str(i), ident("T", f"k{i}")) for i in range(len(inp.records)))
            )
        if isinstance(result, BatchedImportExecutionResult):
            return result
        return BatchedImportExecutionResult(result)


class Rigged(ApplyRig):
    assembly: ImportAssembly  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.assembly = ImportAssembly()  # type: ignore[assignment]

    def backend(self, **_: Any) -> TrussBackend:  # type: ignore[override]
        backend = super().backend()
        return TrussBackend("truss", backend.connections, ImportWire())


def entity(kind: str, key: str, **props: Any) -> dict[str, Any]:
    return {"type": kind, "key": key, "properties": {"name": key, **props}}


def edge(source: str, target: str, name: str = "addresses") -> dict[str, Any]:
    return {"relationship": name, "source": source, "target": target}


def named(kind: str, key: str) -> str:
    return str(Ref(f"catalog.{kind}", key))


def run(rig: Rigged, records: list[Any], **kw: Any) -> ImportResult:
    kw.setdefault("load_id", "L1")
    kw.setdefault("initiated_by", "alice")
    return rig.backend().import_records(kw.pop("who", ALICE), "catalog", records, **kw)


def committed(rig: Rigged) -> int:
    return sum(1 for c in rig.writes if "commit" in c.log)


# -- the call


def test_a_load_checks_the_registrar_reads_the_module_builds_records_and_commits() -> None:
    rig = Rigged()
    when = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))
    got = run(
        rig,
        [{**entity("UseCase", "uc-7"), "original_author": "ann", "original_at": when}],
    )
    assert got == ImportResult(1, 0, ())
    log = rig.assembly.log
    assert log[:3] == ["registrar", "catalog", "document:sandbox"]
    assert log[3:] == ["build:1", "import:1"]  # one builder call and one batched import
    [(inp, documents)] = rig.assembly.imports
    assert documents == (("document", "sandbox", documents[0][2]),)
    assert inp.load_id == "L1" and inp.origin == ("origin", "import_records", "alice")
    assert inp.chunk_size == 128
    ((_, record),) = inp.records
    assert record["record_id"] == "UseCase" and record["module_id"] == "catalog"
    assert record["values"] == (
        ("val", "name", ("text", "string", "uc-7")),
        ("val", "code", ("text", "string", "uc-7")),
    )
    assert record["source"] == ("source", "ann", "2020-01-02T01:04:05.000000Z")
    [write] = rig.writes
    assert write.log[-2:] == ["SET CONSTRAINTS ALL IMMEDIATE", "commit"]


@pytest.mark.parametrize(
    "at",
    [datetime(2020, 1, 1, 12), "2020-01-01", "2020-01-01T12:00:00", "yesterday", 7, True],
)
def test_an_original_time_with_no_offset_or_no_time_rejects_its_record(at: object) -> None:
    rig = Rigged()
    got = run(
        rig,
        [
            {**entity("UseCase", "a"), "original_at": at, "original_author": "x"},
            entity("UseCase", "c"),
        ],
    )
    assert got.created == 1
    [rejected] = got.rejected
    assert (rejected.kind, rejected.identity) == ("entity", named("UseCase", "a"))
    assert "original_at: not an ISO timestamp with an offset" in rejected.reason
    assert [r[1]["source"] for r in rig.assembly.imports[0][0].records] == [None]


def test_a_time_written_as_rfc_3339_text_is_the_original_time_as_an_export_writes_it() -> None:
    rig = Rigged()
    run(
        rig,
        [
            {**entity("UseCase", "a"), "original_at": "2020-01-02T03:04:05+02:00"},
            {
                **entity("UseCase", "b"),
                "original_at": "2020-01-02T03:04:05Z",
                "original_author": "x",
            },
        ],
    )
    sources = [r[1]["source"] for r in rig.assembly.imports[0][0].records]
    assert sources == [
        ("source", None, "2020-01-02T01:04:05.000000Z"),
        ("source", "x", "2020-01-02T03:04:05.000000Z"),
    ]


def test_a_person_who_is_not_a_registrar_is_refused_before_anything_else() -> None:
    rig = Rigged()
    rig.assembly.status = error("execution_obligation", sql_state="42501")
    with pytest.raises(Refused) as raised:
        run(rig, [], initiated_by="someone-else")
    assert raised.value.reason == "no_access" and rig.assembly.log == ["registrar"]


def test_a_load_started_by_another_is_invalid_and_commits_nothing() -> None:
    rig = Rigged()
    with pytest.raises(Invalid) as raised:
        run(rig, [entity("UseCase", "a")], initiated_by="someone-else")
    assert raised.value.violations[0].code == "attribution"
    assert committed(rig) == 0 and "build:1" not in rig.assembly.log


@pytest.mark.parametrize("load_id", ["", "x" * 4097, "a\x00b"])
def test_a_load_id_outside_trusss_bound_is_invalid(load_id: str) -> None:
    rig = Rigged()
    with pytest.raises(Invalid) as raised:
        run(rig, [], load_id=load_id)
    assert raised.value.violations[0].path == "load_id"


def test_a_load_id_of_the_longest_length_is_taken() -> None:
    assert run(Rigged(), [], load_id="é" * 2048) == ImportResult(0, 0, ())


def test_a_load_with_no_token_never_connects() -> None:
    rig = Rigged()
    with pytest.raises(Refused) as raised:
        run(rig, [], who=Principal("alice", ""))
    assert raised.value.reason == "token_expired" and rig.conns == []


def test_an_empty_load_still_asks_truss_so_an_outage_and_a_stranger_are_told() -> None:
    rig = Rigged()
    assert run(rig, []) == ImportResult(0, 0, ())
    assert rig.assembly.log == ["registrar", "catalog", "document:sandbox", "build:0", "import:0"]
    assert committed(rig) == 1


def test_a_backend_with_no_connection_source_is_unavailable() -> None:
    with pytest.raises(Unavailable) as raised:
        TrussBackend("truss").import_records(
            ALICE, "catalog", [], load_id="L", initiated_by="alice"
        )
    assert raised.value.reason == "not_configured"


def test_a_person_who_can_read_no_such_module_is_refused() -> None:
    rig = Rigged()
    with pytest.raises(Refused):
        rig.backend().import_records(ALICE, "other", [], load_id="L", initiated_by="alice")
    assert committed(rig) == 0


# -- the records


def test_a_record_that_fails_the_module_is_rejected_and_never_sent() -> None:
    rig = Rigged()
    got = run(
        rig,
        [
            entity("Nope", "a"),
            entity("UseCase", "bad key/!"),
            {"type": "UseCase", "key": "x", "properties": {}},
            entity("UseCase", "y", stray=1),
            entity("UseCase", "good"),
            edge("good", "ghost"),
            edge("a", "b", "unrelated"),
        ],
    )
    assert (got.created, got.skipped) == (1, 0)
    assert [(r.kind, r.identity) for r in got.rejected] == [
        ("entity", named("Nope", "a")),
        ("entity", named("UseCase", "bad key/!")),
        ("entity", named("UseCase", "x")),
        ("entity", named("UseCase", "y")),
        ("relationship", "addresses/good/ghost"),
        ("record", "unrelated/a/b"),
    ]
    assert rig.assembly.log.count("import:1") == 1


def test_entities_are_imported_before_relationships_whatever_their_order() -> None:
    rig = Rigged()
    rig.assembly.objects[("UseCase", "uc-1")] = ident("UseCase", "uc-1")
    got = run(rig, [edge("s-1", "uc-1"), entity("Solution", "s-1")])
    assert got.created == 2
    kinds = [r[0] for chunk in rig.assembly.imports for r in chunk[0].records]
    assert kinds == ["object", "edge"] and committed(rig) == 2


def test_an_endpoint_this_load_made_is_not_looked_up_again() -> None:
    rig = Rigged()
    rig.assembly.scripted = [reported(ImportCreated("0", ident("UseCase", "uc-1")))]
    rig.assembly.objects[("Solution", "s-1")] = ident("Solution", "s-1")
    run(rig, [entity("UseCase", "uc-1"), edge("s-1", "uc-1")])
    assert [x for x in rig.assembly.log if x.startswith("lookup")] == ["lookup:Solution:s-1"]


def test_an_edge_to_a_missing_endpoint_is_rejected_and_the_inverse_name_swaps_the_ends() -> None:
    rig = Rigged()
    rig.assembly.objects[("UseCase", "uc-1")] = ident("UseCase", "uc-1")
    rig.assembly.objects[("Solution", "s-1")] = ident("Solution", "s-1")
    got = run(rig, [edge("uc-1", "s-1", "addressedBy"), edge("ghost", "uc-1")])
    assert got.created == 1 and [(r.kind, r.identity) for r in got.rejected] == [
        ("relationship", "addresses/ghost/uc-1")
    ]
    [(_, record)] = rig.assembly.imports[0][0].records
    assert record["source_endpoint"] == ident("Solution", "s-1")
    assert record["target_endpoint"] == ident("UseCase", "uc-1")
    assert record["relationship_id"] == "solution-addresses" and record["values"] == ()


def test_a_held_record_is_skipped_and_its_identity_serves_an_edge() -> None:
    rig = Rigged()
    rig.assembly.scripted = [reported(ImportSkipped("0", identity=ident("UseCase", "uc-1")))]
    rig.assembly.objects[("Solution", "s-1")] = ident("Solution", "s-1")
    got = run(rig, [entity("UseCase", "uc-1"), edge("s-1", "uc-1")])
    assert (got.created, got.skipped) == (1, 1)
    assert "lookup:UseCase:uc-1" not in rig.assembly.log


def test_a_deleted_identity_is_skipped_and_gives_an_edge_no_endpoint() -> None:
    rig = Rigged()
    rig.assembly.scripted = [reported(ImportSkipped("0", "reserved_identity", Absent()))]
    got = run(rig, [entity("UseCase", "uc-2"), edge("uc-2", "uc-2", "addressedBy")])
    assert got.skipped == 1 and [r.kind for r in got.rejected] == ["relationship"]


def test_truss_rejections_are_kept_per_record() -> None:
    rig = Rigged()
    rig.assembly.scripted = [reported(ImportRejected("0", "invalid"), ImportCreated("1"))]
    got = run(rig, [entity("UseCase", "a"), entity("UseCase", "b")])
    assert got.created == 1 and [(r.kind, r.identity) for r in got.rejected] == [
        ("entity", named("UseCase", "a"))
    ]
    assert "invalid" in got.rejected[0].reason


def test_outcomes_are_read_by_input_position() -> None:
    rig = Rigged()
    rig.assembly.scripted = [reported(ImportCreated("1"), ImportRejected("0", "conflict"))]
    got = run(rig, [entity("UseCase", "a"), entity("UseCase", "b")])
    assert got.rejected[0].identity == named("UseCase", "a")


# -- chunks


def test_a_load_is_sent_in_calls_with_a_commit_each_and_the_counts_are_summed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(load, "BATCH", 2)
    rig = Rigged()
    rig.assembly.objects[("UseCase", "uc-0")] = ident("UseCase", "uc-0")
    records = [entity("UseCase", f"uc-{i}") for i in range(5)] + [edge("s-9", "uc-0")] * 3
    rig.assembly.objects[("Solution", "s-9")] = ident("Solution", "s-9")
    records.append(entity("UseCase", "bad key/!"))
    got = run(rig, records)
    sizes = [len(i[0].records) for i in rig.assembly.imports]
    assert sizes == [2, 2, 1, 2, 1] and committed(rig) == 5
    assert (got.created, got.skipped, len(got.rejected)) == (8, 0, 1)


def test_a_load_is_sent_at_128_records_a_call_and_a_commit_one_chunk_each() -> None:
    rig = Rigged()
    run(rig, [entity("UseCase", f"uc-{i}") for i in range(129)])
    assert (load.BATCH, load.CHUNK) == (128, 128)
    assert [len(i[0].records) for i in rig.assembly.imports] == [128, 1] and committed(rig) == 2
    assert {i[0].chunk_size for i in rig.assembly.imports} == {128}


def test_one_native_call_builds_every_record_of_a_call() -> None:
    rig = Rigged()
    run(rig, [entity("UseCase", f"uc-{i}") for i in range(100)])
    assert [x for x in rig.assembly.log if x.startswith("build")] == ["build:100"]
    assert not any(x.startswith("object") for x in rig.assembly.log)


def test_a_call_that_fails_leaves_the_earlier_calls_committed_and_says_what_they_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(load, "BATCH", 1)
    rig = Rigged()
    rig.assembly.scripted = [
        reported(ImportCreated("0")),
        ImportExecutionFailed(SimpleNamespace(code="retry", sql_state="40001")),
    ]
    with pytest.raises(Unavailable) as raised:
        run(rig, [entity("UseCase", "a"), entity("UseCase", "b"), entity("UseCase", "c")])
    assert committed(rig) == 1 and len(rig.writes) == 2
    assert raised.value.__notes__ == ["1 created and 0 skipped by 1 confirmed call(s)"]


def test_a_commit_of_unknown_outcome_is_not_replayed() -> None:
    rig = Rigged()
    rig.commit_failures = [True]
    with pytest.raises(CommitUnknown):
        run(rig, [entity("UseCase", "a")])
    assert len(rig.assembly.imports) == 1


def test_an_empty_load_pending_for_the_caller_is_committed_with_the_call() -> None:
    rig = Rigged()
    rig.assembly.scripted = [
        BatchedImportExecutionResult(reported(), EmptyLoadDisposition("pending", "caller"))
    ]
    assert run(rig, []) == ImportResult(0, 0, ())
    assert committed(rig) == 1


@pytest.mark.parametrize("disposition", ["rolled_back", "commit_unknown", "transaction_unresolved"])
def test_an_empty_load_settled_otherwise_is_unavailable_and_nothing_is_inferred(
    disposition: str,
) -> None:
    rig = Rigged()
    rig.assembly.scripted = [
        BatchedImportExecutionResult(reported(), EmptyLoadDisposition(disposition))
    ]
    with pytest.raises(Unavailable) as raised:
        run(rig, [])
    assert disposition in raised.value.detail and committed(rig) == 0
    assert rig.conns[-1].closed == (disposition != "rolled_back")  # an uncertain one is discarded


def test_a_builder_answer_that_is_not_the_built_records_is_not_taken_for_success() -> None:
    rig = Rigged()
    rig.assembly.builder = ok(SimpleNamespace(refused="x"))  # an Ok that holds no records
    with pytest.raises(Unavailable):
        run(rig, [entity("UseCase", "a")])
    assert committed(rig) == 0 and "import:1" not in rig.assembly.log


def test_partial_progress_keeps_what_a_later_call_could_not_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(load, "BATCH", 2)
    rig = Rigged()
    rig.assembly.scripted = [
        reported(ImportCreated("0"), ImportSkipped("1")),
        ImportExecutionFailed(SimpleNamespace(code="commit_unknown", sql_state=None)),
    ]
    with pytest.raises(Unavailable) as raised:
        run(rig, [entity("UseCase", f"u{i}") for i in range(4)])
    assert raised.value.__notes__ == ["1 created and 1 skipped by 1 confirmed call(s)"]
    assert len(rig.assembly.imports) == 2  # an uncertain call is never repeated by the adapter


# -- Truss's failures


@pytest.mark.parametrize(
    ("result", "expected", "reason"),
    [
        (
            ImportExecutionFailed(SimpleNamespace(code="x", sql_state="54000")),
            Unavailable,
            "resource",
        ),
        (ImportExecutionFailed(SimpleNamespace(code="x", sql_state="42501")), Refused, "no_access"),
        (
            ImportExecutionFailed(SimpleNamespace(code="cancelled", sql_state=None)),
            Unavailable,
            "unreachable",
        ),
        (ImportResourceLimited(), Unavailable, "resource"),
        (ImportInvalid(), Invalid, None),
        (reported(ImportRejected("0", "unauthorized")), Refused, "no_access"),
        (reported(ImportAttemptUnknown("0")), Unavailable, "unreachable"),
        (reported(), Unavailable, "unreachable"),
        ("something else", Unavailable, "unreachable"),
    ],
)
def test_what_truss_cannot_do_is_raised_inside_the_call_so_nothing_commits(
    result: Any, expected: type[Any], reason: str | None
) -> None:
    rig = Rigged()
    rig.assembly.scripted = [result]
    with pytest.raises(expected) as raised:
        run(rig, [entity("UseCase", "a")])
    if reason is not None:
        assert raised.value.reason == reason
    assert committed(rig) == 0


def test_a_person_without_the_writer_role_is_refused_at_the_record_builder() -> None:
    rig = Rigged()
    rig.assembly.builder = error("execution_obligation", sql_state="42501")
    with pytest.raises(Refused):
        run(rig, [entity("UseCase", "a")])
    assert committed(rig) == 0


def test_a_credential_never_appears_in_an_error() -> None:
    rig = Rigged()
    rig.assembly.scripted = [ImportExecutionFailed(SimpleNamespace(code="x", sql_state=None))]
    with pytest.raises(Unavailable) as raised:
        run(rig, [entity("UseCase", "a")], who=Principal("alice", "s3cret-token"))
    assert "s3cret-token" not in repr(raised.value) and "s3cret-token" not in str(raised.value)


# -- against a real Truss


def world(cluster: Any) -> Any:
    return _world(cluster, "basic")


def load_as(h: Any, who: str, records: list[Any], **kw: Any) -> ImportResult:
    kw.setdefault("load_id", "L1")
    kw.setdefault("initiated_by", who)
    return h.backend().import_records(h.principal(who), "catalog", records, **kw)


def whole(h: Any, key: str, record: str = "UseCase") -> dict[str, Any]:
    sql = f"SELECT x.* FROM catalog.{record} x WHERE x.code = '{key}' ORDER BY x.code LIMIT 100"
    [row] = h.backend().query(h.principal("carol"), "catalog", Statement(sql, {}), limit=100).rows
    return dict(row)


def partners(h: Any, use_case: str) -> list[str]:
    sql = (
        "SELECT s.code FROM catalog.Solution s "
        f"WHERE HAS_RELATED(s.addresses, KEY('{use_case}')) ORDER BY s.code LIMIT 100"
    )
    return [
        r["code"]
        for r in h.backend()
        .query(h.principal("carol"), "catalog", Statement(sql, {}), limit=100)
        .rows
    ]


@pytest.mark.truss
def test_a_load_stores_its_provenance_apart_from_the_loading_person(cluster: Any) -> None:
    h = world(cluster)
    at = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))
    got = load_as(
        h, "alice", [{**entity("UseCase", "uc-7"), "original_author": "ann", "original_at": at}]
    )
    assert got == ImportResult(1, 0, ())
    row = whole(h, "uc-7")
    assert (row["_created_by"], row["_original_author"], row["_load_id"]) == ("alice", "ann", "L1")
    assert row["_original_at"] == datetime(2020, 1, 2, 1, 4, 5, tzinfo=UTC)


@pytest.mark.truss
def test_a_load_across_calls_commits_each_and_resolves_edges_to_earlier_calls(
    cluster: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load, "BATCH", 2)
    monkeypatch.setattr(load, "CHUNK", 1)
    h = world(cluster)
    got = load_as(
        h,
        "alice",
        [
            edge("s-2", "uc-3"),
            entity("Solution", "s-2"),
            entity("UseCase", "uc-3"),
            edge("sol-1", "uc-3"),
        ],
    )
    assert got == ImportResult(4, 0, ())
    assert partners(h, "uc-3") == ["s-2", "sol-1"]
    assert load_as(h, "alice", [entity("UseCase", "uc-3"), edge("s-2", "uc-3")]) == ImportResult(
        0, 2, ()
    )


@pytest.mark.truss
def test_a_rejected_record_does_not_stop_the_rest_and_an_unlinked_edge_stays_gone(
    cluster: Any,
) -> None:
    h = world(cluster)
    h.backend().apply(
        h.principal("alice"),
        Plan(
            "catalog.X",
            (),
            (
                Unlink(
                    "addresses", Ref("catalog.Solution", "sol-1"), Ref("catalog.UseCase", "uc-1")
                ),
            ),
        ),
        idempotency_key=None,
    )
    got = load_as(
        h,
        "alice",
        [
            {"type": "UseCase", "key": "uc-8", "properties": {}},
            entity("UseCase", "uc-9"),
            edge("sol-1", "uc-1"),
            edge("sol-1", "ghost"),
        ],
    )
    assert (got.created, got.skipped, [r.kind for r in got.rejected]) == (
        1,
        1,
        ["entity", "relationship"],
    )
    assert partners(h, "uc-1") == []


@pytest.mark.truss
@pytest.mark.parametrize("who", ["bob", "carol", "dave"])
def test_only_a_registrar_may_load(cluster: Any, who: str) -> None:
    h = world(cluster)
    with pytest.raises(Refused):
        load_as(h, who, [entity("UseCase", "uc-5")])
    assert [
        r
        for r in h.backend()
        .query(
            h.principal("carol"),
            "catalog",
            Statement("SELECT u.code FROM catalog.UseCase u WHERE u.code = 'uc-5' LIMIT 10", {}),
            limit=10,
        )
        .rows
    ] == []


@pytest.mark.truss
def test_a_load_over_one_calls_bound_is_two_batched_calls_and_a_repeat_skips_every_record(
    cluster: Any,
) -> None:
    h = world(cluster)
    records = [entity("UseCase", f"bulk-{i:04d}") for i in range(load.BATCH + 76)]
    records += [edge("sol-1", f"bulk-{i:04d}") for i in (0, 5, load.BATCH + 75)]
    got = load_as(h, "alice", records, load_id="big")
    assert got == ImportResult(len(records), 0, ())
    assert partners(h, "bulk-0005") == ["sol-1"] and partners(h, f"bulk-{load.BATCH + 75:04d}")
    again = load_as(h, "alice", records, load_id="big-again")
    assert again == ImportResult(0, len(records), ())


@pytest.mark.truss
def test_an_empty_load_is_settled_by_truss_and_creates_nothing(cluster: Any) -> None:
    h = world(cluster)
    assert load_as(h, "alice", [], load_id="nothing") == ImportResult(0, 0, ())
    assert load_as(h, "alice", [entity("UseCase", "a")], load_id="a") == ImportResult(1, 0, ())
