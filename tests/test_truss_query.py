# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's `query` (TR-06): Weft statements passed to Truss, the `maximum_rows` rule, the
fact columns and the error map.

The unit tests are always on: a scripted fake of Truss's assembly behind the connection layer's
`Toolkit` seam, with results named as Truss names them (the adapter recognizes them by class name).
The Truss-marked tests run the read corpus cases and the plan's gate checks against a real Truss on
PostgreSQL 18.6 (`uv run --extra truss --group truss-test pytest -m truss`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from arras.adapters.truss import describe as describe_module
from arras.adapters.truss import query as query_module
from arras.errors import Invalid, Refused, Unavailable, Unsupported
from arras.results import WeftSupport
from arras.searchplan import TextMatch
from arras.types import Column, Position, Principal, Statement
from test_truss_harness import _world, cluster  # noqa: F401
from test_truss_registry import (
    ALICE,
    CatalogRefused,
    CatalogUnavailable,
    FakeAssembly,
    ReaderCatalog,
    Rig,
    entry,
    error,
    fake_truss,  # noqa: F401
    ok,
)

AT = datetime(2026, 10, 14, 0, 5, 8, 180949, tzinfo=UTC)

# -- results as Truss names them


@dataclass(frozen=True)
class QueryReadPosition:
    value: str
    at: datetime
    caller_xid_assigned: bool = False


@dataclass(frozen=True)
class QueryRows:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    catalog_revision: int = 3
    as_of: QueryReadPosition | None = QueryReadPosition("truss-read-position-v1:x", AT)


@dataclass(frozen=True)
class QueryDiagnostic:
    code: str
    message: str = ""


@dataclass(frozen=True)
class QueryRefused:
    code: str
    diagnostics: tuple[QueryDiagnostic, ...] = ()


@dataclass(frozen=True)
class QueryUnavailable:
    reason: str


@dataclass(frozen=True)
class QueryRelatedKeys:
    items: tuple[tuple[str, ...], ...]
    truncated: bool = False


@dataclass(frozen=True)
class QueryAbsent:
    pass


@dataclass(frozen=True)
class TextValue:
    kind: str
    text: str


def refused(code: str, *diagnostics: tuple[str, str]) -> Any:
    return ok(QueryRefused(code, tuple(QueryDiagnostic(c, m) for c, m in diagnostics)))


class QueryAssembly(FakeAssembly):
    """The registry fake with `query_in_transaction`: each call takes the next scripted answer."""

    def __init__(self) -> None:
        super().__init__()
        self.answers: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    def query_in_transaction(self, tx: Any, **kw: Any) -> Any:
        self.log.append("query")
        self.calls.append(kw)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


@dataclass
class QueryRig(Rig):
    assembly: QueryAssembly = field(default_factory=QueryAssembly)  # type: ignore[assignment]


def rig(*answers: Any) -> QueryRig:
    r = QueryRig()
    r.assembly.answers = list(answers) or [ok(QueryRows(("code",), (("uc-1",),)))]
    return r


def ask(
    r: Rig,
    sql: str = "SELECT u.code FROM catalog.UseCase u",
    params: dict[str, Any] | None = None,
    *,
    limit: int = 50,
    text: TextMatch | None = None,
    module: str = "catalog",
    principal: Principal = ALICE,
) -> Any:
    return r.backend().query(
        principal, module, Statement(sql, params or {}), limit=limit, text=text
    )


# -- the call


def test_the_statement_and_parameters_go_to_truss_unchanged_over_the_modules_document() -> None:
    r = rig()
    ask(r, "SELECT u.code FROM catalog.UseCase u WHERE u.name = :n", {"n": "x"})
    [call] = r.assembly.calls
    assert call["sql"] == "SELECT u.code FROM catalog.UseCase u WHERE u.name = :n"
    assert call["document_ids"] == ("sandbox",)  # the UMF root id, not the module name
    assert call["parameters"] == {"n": "x"}
    assert call["maximum_rows"] == 10_000
    assert "read_profile" not in call


def test_a_call_with_no_parameters_passes_none() -> None:
    r = rig()
    ask(r)
    assert r.assembly.calls[0]["parameters"] is None


def test_a_query_is_one_read_only_call_that_is_rolled_back() -> None:
    r = rig()
    ask(r)
    [conn] = r.conns
    assert conn.log[0].endswith("READ ONLY") and conn.log[-1] == "rollback"
    assert r.assembly.log.count("catalog") == 1  # access is the person's own reader catalog


def test_a_query_with_no_token_never_connects() -> None:
    r = rig()
    with pytest.raises(Refused) as raised:
        ask(r, principal=Principal("anon", ""))
    assert (raised.value.reason, r.conns) == ("token_expired", [])


# -- the module comes first


@pytest.mark.parametrize("catalog", [ok(CatalogRefused()), ok(ReaderCatalog(3, ()))])
def test_a_module_the_person_cannot_read_is_unknown_and_truss_is_never_queried(
    catalog: Any,
) -> None:
    r = rig()
    r.assembly.catalog = catalog
    with pytest.raises(Invalid) as raised:
        ask(r)
    assert [v.code for v in raised.value.violations] == ["unknown_type"]
    assert "query" not in r.assembly.log


def test_the_module_is_checked_before_text_and_parameters() -> None:
    r = rig()
    r.assembly.catalog = ok(ReaderCatalog(3, (entry(module="other"),)))
    with pytest.raises(Invalid) as raised:
        ask(r, params={"p": 1.5}, text=TextMatch(("x",), ("name",)))
    assert raised.value.violations[0].code == "unknown_type"


def test_text_is_unsupported_after_the_module_is_known() -> None:
    r = rig()
    with pytest.raises(Unsupported):
        ask(r, text=TextMatch(("x",), ("name",)))
    assert "query" not in r.assembly.log


def test_an_install_with_nothing_registered_holds_no_module() -> None:
    r = rig()
    r.assembly.status = ok(SimpleNamespace(installed=True, revision=0))
    r.assembly.catalog = ok(CatalogUnavailable("profile"))
    with pytest.raises(Invalid) as raised:
        ask(r)
    assert raised.value.violations[0].code == "unknown_type"


def test_a_genuine_release_mismatch_is_unavailable() -> None:
    r = rig()
    r.assembly.catalog = ok(CatalogUnavailable("profile"))  # the head is 3
    with pytest.raises(Unavailable) as raised:
        ask(r)
    assert raised.value.reason == "unsupported_version"


def test_a_person_who_loses_authority_between_the_steps_sees_an_unknown_module() -> None:
    r = rig(refused("unauthorized"))
    with pytest.raises(Invalid) as raised:
        ask(r)
    assert raised.value.violations[0].code == "unknown_type"


# -- parameters


@pytest.mark.parametrize("value", ["a", 3, True, Decimal("1.50")])
def test_a_string_integer_boolean_or_decimal_parameter_goes_through(value: Any) -> None:
    r = rig()
    ask(r, params={"p": value})
    assert r.assembly.calls[0]["parameters"] == {"p": value}


@pytest.mark.parametrize("value", [1.5, None, [1], datetime(2026, 1, 1, tzinfo=UTC), b"x"])
def test_any_other_parameter_is_invalid_before_truss_and_names_the_parameter(value: Any) -> None:
    r = rig()
    with pytest.raises(Invalid) as raised:
        ask(r, params={"p": value})
    [v] = raised.value.violations
    assert (v.path, v.code) == ("params.p", "param_type")
    assert "query" not in r.assembly.log


def test_a_string_subclass_is_not_a_parameter_truss_takes() -> None:
    class Name(str):
        pass

    with pytest.raises(Invalid):
        ask(rig(), params={"p": Name("x")})


# -- rows, the cap and the position


def test_rows_are_capped_at_the_limit_and_truncated_says_so() -> None:
    rows = tuple((f"uc-{i}",) for i in range(3))
    got = ask(rig(ok(QueryRows(("code",), rows))), limit=2)
    assert [r["code"] for r in got.rows] == ["uc-0", "uc-1"] and got.truncated is True
    got = ask(rig(ok(QueryRows(("code",), rows))), limit=3)
    assert len(got.rows) == 3 and got.truncated is False


def test_the_position_is_truss_read_position_and_a_lower_bound() -> None:
    got = ask(rig())
    assert got.as_of == Position("truss-read-position-v1:x", AT)
    assert got.as_of.at.tzinfo is not None


def test_a_result_with_no_position_is_unavailable() -> None:
    with pytest.raises(Unavailable):
        ask(rig(ok(QueryRows(("code",), (("a",),), as_of=None))))


def test_an_absent_property_is_omitted_from_a_whole_entity_and_null_in_a_projection() -> None:
    whole = ask(
        rig(ok(QueryRows(("code", "name"), (("a", QueryAbsent()),)))),
        "SELECT u.* FROM catalog.UseCase u",
    )
    assert whole.rows == ({"code": "a"},)
    plain = ask(rig(ok(QueryRows(("code", "name"), (("a", QueryAbsent()),)))))
    assert plain.rows == ({"code": "a", "name": None},)


def test_related_keys_become_lists_of_keys() -> None:
    rows = (("uc-1", QueryRelatedKeys((("sol-1",), ("sol-2",)), True), ("sol-1",)),)
    got = ask(rig(ok(QueryRows(("code", "keys", "addressedBy"), rows))))
    assert got.rows[0]["keys"] == ["sol-1", "sol-2"] and got.rows[0]["addressedBy"] == ["sol-1"]


def test_a_composite_related_key_is_a_list_of_its_parts() -> None:
    got = ask(rig(ok(QueryRows(("keys",), ((QueryRelatedKeys((("a", "b"),)),),)))))
    assert got.rows[0]["keys"] == [["a", "b"]]


def test_the_fact_timestamps_are_datetimes_with_their_offset() -> None:
    names = ("code", "_version", "_created_at", "_updated_at", "_original_at", "_load_id")
    row = ("a", 1, "2026-10-14T00:05:08.180949Z", "2026-10-14T00:05:09.000001Z", None, "seed")
    got = ask(rig(ok(QueryRows(names, (row,)))), "SELECT u.* FROM catalog.UseCase u")
    r = got.rows[0]
    assert r["_created_at"] == AT and r["_created_at"].tzinfo is not None
    assert r["_updated_at"] > r["_created_at"] and r["_original_at"] is None


def test_timestamp_text_values_are_datetimes_and_binary_stays_text() -> None:
    row = (TextValue("timestamp", "2026-10-14T00:05:08.180949+00:00"), TextValue("binary", "AP8="))
    got = ask(rig(ok(QueryRows(("t", "b"), (row,)))))
    assert got.rows[0] == {"t": AT, "b": "AP8="}


# -- columns


def test_columns_are_typed_from_facts_the_module_and_the_values() -> None:
    names = ("code", "_version", "_created_at", "n", "keys", "ratio", "flag", "nothing")
    row = (
        "a",
        1,
        "2026-10-14T00:05:08.180949Z",
        4,
        QueryRelatedKeys((("s",),)),
        Decimal("1.5"),
        True,
        None,
    )
    got = ask(rig(ok(QueryRows(names, (row,)))))
    assert got.columns == (
        Column("code", True, "string"),
        Column("_version", True, "integer"),
        Column("_created_at", True, "timestamp"),
        Column("n", True, "integer"),
        Column("keys", False, "keys"),
        Column("ratio", True, "decimal"),
        Column("flag", True, "boolean"),
        Column("nothing", True, "string"),
    )


def test_a_count_with_no_rows_still_names_its_column() -> None:
    got = ask(rig(ok(QueryRows(("name", "count"), ()))))
    assert [c.name for c in got.columns] == ["name", "count"] and got.rows == ()


def test_the_facts_a_whole_entity_row_carries_are_these_eight() -> None:
    assert set(query_module.FACTS) == {
        "_version", "_created_by", "_created_at", "_updated_by", "_updated_at",
        "_original_author", "_original_at", "_load_id",
    }  # fmt: skip


# -- the profile ladder


def test_a_whole_entity_statement_runs_only_under_complete_entity() -> None:
    r = rig(refused("unsupported_query", ("WFT-PROFILE", "x")))
    with pytest.raises(Unsupported):
        ask(r, "SELECT u.* FROM catalog.UseCase u")
    assert [c["read_profile"] for c in r.assembly.calls] == [
        "complete-entity"
    ]  # no fact-less retry


def test_a_whole_entity_statement_is_found_by_its_star_alone() -> None:
    for sql in ("SELECT u.*", "SELECT u. * FROM catalog.UseCase u"):
        r = rig()
        ask(r, sql)
        assert r.assembly.calls[0]["read_profile"] == "complete-entity"


def test_a_keyset_continuation_is_retried_under_each_page_profile_in_one_transaction() -> None:
    cap = refused("unsupported_query", ("WFT-CAPABILITY", "page"))
    prof = refused("unsupported_query", ("WFT-PROFILE", "no"))
    r = rig(cap, prof, ok(QueryRows(("code",), (("uc-2",),))))
    got = ask(
        r,
        "SELECT u.code FROM catalog.UseCase u WHERE u.code > :l ORDER BY u.code LIMIT 1",
        {"l": "a"},
    )
    assert got.rows == ({"code": "uc-2"},)
    assert [c.get("read_profile") for c in r.assembly.calls] == [
        None,
        "entity-page",
        "related-entity-page",
    ]
    assert len(r.conns) == 1


def test_no_page_profile_serving_it_reports_the_first_refusal_as_unsupported() -> None:
    cap = refused("unsupported_query", ("WFT-CAPABILITY", "page"))
    prof = refused("unsupported_query", ("WFT-PROFILE", "no"))
    r = rig(cap, prof)
    with pytest.raises(Unsupported) as raised:
        ask(r)
    assert "WFT-CAPABILITY" in raised.value.construct
    assert len(r.assembly.calls) == 4


@pytest.mark.parametrize("code", ["WFT-TYPE", "WFT-PROFILE"])
def test_another_unsupported_refusal_is_not_retried_under_a_page_profile(code: str) -> None:
    r = rig(refused("unsupported_query", (code, "x")))
    with pytest.raises(Unsupported):
        ask(r)
    assert len(r.assembly.calls) == 1


# -- refusals


@pytest.mark.parametrize(
    "answer, error_type, detail",
    [
        (refused("limits"), Unsupported, None),
        (refused("unsupported_query"), Unsupported, None),  # whatever Weft's diagnostics say
        (refused("invalid_query", ("WFT-PROFILE", "No profile serves this")), Unsupported, None),
        (refused("unsupported_query", ("WFT-TYPE", "")), Unsupported, None),
        (
            refused("invalid_query", ("WFT-UNSUPPORTED", "Excluded application construct: or")),
            Unsupported,
            None,
        ),
        (
            refused("invalid_query", ("WFT-UNSUPPORTED", "Expected dialect keyword")),
            Unsupported,
            None,
        ),
        (
            refused("invalid_query", ("WFT-NAME-MISSING", query_module._NO_SOURCE)),
            Unsupported,
            None,
        ),
        (
            refused(
                "invalid_query", ("WFT-NAME-MISSING", "Selected member name missing or ambiguous")
            ),
            Invalid,
            "wft-name-missing",
        ),
        (
            refused("invalid_query", ("WFT-PARAMETER", "Missing source parameter binding")),
            Invalid,
            "wft-parameter",
        ),
        (
            refused("invalid_query", ("WFT-OUTPUT-NAME", "Repeated output name")),
            Invalid,
            "wft-output-name",
        ),
        (
            refused("invalid_query", ("WFT-SYNTAX", "Expected dialect keyword")),
            Invalid,
            "wft-syntax",
        ),
        (refused("invalid_query"), Invalid, "invalid_query"),
        (refused("native_domain"), Invalid, "numeric_domain"),
        (refused("stale_context"), Unavailable, "busy"),
        (ok(QueryUnavailable("compiler")), Unavailable, "not_configured"),
        (ok(QueryUnavailable("installation")), Unavailable, "not_configured"),
        (ok(QueryUnavailable("resource")), Unavailable, "resource"),
        (ok(QueryUnavailable("observation")), Unavailable, "busy"),
    ],
)
def test_a_refusal_maps_by_truss_code_and_weft_diagnostic(
    answer: Any, error_type: type, detail: str | None
) -> None:
    with pytest.raises(error_type) as raised:
        ask(rig(answer))
    if error_type is Invalid:
        assert raised.value.violations[0].code == detail
    elif error_type is Unavailable:
        assert raised.value.reason == detail


def test_the_diagnostic_messages_the_name_mapping_relies_on_are_pinned() -> None:
    """Weft reports an unknown record type and an unknown column under one code; the adapter tells
    them apart by this message, so a Truss release that rewords it fails here, not in a client."""
    assert query_module._NO_SOURCE == "No queryable record matches source"


def test_a_refusal_never_carries_the_statement_or_a_parameter_value() -> None:
    answer = refused("invalid_query", ("WFT-PARAMETER", "Source parameter family is incompatible"))
    with pytest.raises(Invalid) as raised:
        ask(
            rig(answer),
            "SELECT u.code FROM catalog.UseCase u WHERE u.code = :secret",
            {"secret": "hunter2"},
        )
    text = repr(raised.value.violations) + str(raised.value)
    assert "hunter2" not in text and "secret" not in text and "UseCase" not in text


def test_an_error_outcome_maps_by_the_connection_layer() -> None:
    with pytest.raises(Refused) as raised:
        ask(rig(error("execution_obligation", sql_state="42501")))
    assert raised.value.reason == "no_access"
    with pytest.raises(Unavailable):
        ask(rig(error("execution_obligation", sql_state="XX000")))


# -- describe


def test_describe_declares_the_profiles_when_the_weft_release_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(describe_module.metadata, "version", lambda name: "0.4.49")
    weft = describe_module.weft_support()
    assert weft == WeftSupport(
        "weft-sql/0.2.0", ("entity-page", "related-entity-page", "count-summary", "general")
    )
    monkeypatch.setattr(describe_module.metadata, "version", lambda name: "0.4.33")
    assert describe_module.weft_support() is None


def test_describe_states_what_query_serves_per_type() -> None:
    r = rig()
    backend = r.backend()
    backend.catalog(ALICE)
    caps = backend.describe().capabilities
    use_case, solution = caps["catalog.UseCase"], caps["catalog.Solution"]
    assert (use_case.read, use_case.count, use_case.mutable) == (True, True, True)
    assert (use_case.search, use_case.searchable, use_case.latency_class) == ("none", (), "batch")
    assert use_case.columns == ("code", "name") and solution.columns == ("code", "name")
    assert use_case.relationships == ("addressedBy",) and solution.relationships == ("addresses",)


# -- against a real Truss


def _memory(fixture: str = "basic") -> Any:
    from arras.conformance import load_corpus
    from arras.conformance.fakes import MemoryStoreHarness
    from arras.umf import parse_module

    text = load_corpus()["_module_text"]
    h = MemoryStoreHarness()
    h.install(parse_module(text), text.encode())
    for step in load_corpus()["fixtures"][fixture][1:]:
        if step["op"] == "grant":
            h.grant(step["user"], step["modules"], step.get("admin", False))
        elif step["op"] == "seed":
            h.seed(step["as"], step["records"])
    return h


READS = [
    ("SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100", {}),
    (
        "SELECT u.code FROM catalog.UseCase u WHERE u.name = :a ORDER BY u.code LIMIT 100",
        {"a": "Alert review"},
    ),
    (
        "SELECT u.name, COUNT(*) AS n FROM catalog.UseCase u GROUP BY u.name "
        "ORDER BY u.name LIMIT 100",
        {},
    ),
    ("SELECT COUNT(*) FROM catalog.Solution s", {}),
    (
        "SELECT u.code, RELATED_KEYS(u.addressedBy, 10) AS keys FROM catalog.UseCase u "
        "ORDER BY u.code LIMIT 100",
        {},
    ),
    (
        "SELECT s.code FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('uc-1')) "
        "ORDER BY s.code LIMIT 100",
        {},
    ),
    (
        "SELECT u.code, s.code AS solution FROM catalog.UseCase u JOIN catalog.Solution s "
        "ON u.name = s.name ORDER BY u.code, s.code LIMIT 100",
        {},
    ),
    ("SELECT u.code FROM catalog.UseCase u WHERE u.code = 'nope' ORDER BY u.code LIMIT 100", {}),
]
# the refused statements both adapters classify, and the one Truss cannot tell from an unsupported
# construct (a syntax error: Invalid in memory, Unsupported on Truss; truss-requirements R17.3)
REFUSED = [
    ("SELECT u.code FROM catalog.UseCase u WHERE u.code = 'a' OR u.code = 'b'", {}, Unsupported),
    ("SELECT u.code FROM catalog.UseCase u ORDER BY u.code DESC LIMIT 5", {}, Unsupported),
    ("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 5 OFFSET 1", {}, Unsupported),
    ("SELECT t.code FROM other.Thing t", {}, Unsupported),
    ("SELECT t.code FROM catalog.Nope t", {}, Unsupported),
    ("SELECT u.nope FROM catalog.UseCase u ORDER BY u.code LIMIT 5", {}, Invalid),
    ("SELECT u.code FROM catalog.UseCase u WHERE u.code = :p LIMIT 5", {}, Invalid),
    ("SELECT u.code FROM catalog.UseCase u LIMIT 5", {"p": "x"}, Invalid),
    ("SELECT u.code FROM catalog.UseCase u WHERE u.code = :p LIMIT 5", {"p": 1.5}, Invalid),
    ("SELECT u.code, u.code FROM catalog.UseCase u LIMIT 5", {}, Invalid),
]


@pytest.mark.truss
def test_truss_and_the_memory_adapter_answer_the_same_statements_the_same_way(
    cluster: Any,  # noqa: F811
) -> None:
    truss, memory = _world(cluster, "basic"), _memory()
    for sql, params in READS:
        got = truss.backend().query(
            truss.principal("carol"), "catalog", Statement(sql, params), limit=100
        )
        want = memory.backend().query(
            memory.principal("carol"), "catalog", Statement(sql, params), limit=100
        )
        assert [c.name for c in got.columns] == [c.name for c in want.columns], sql
        assert [c.type for c in got.columns] == [c.type for c in want.columns], sql
        assert list(got.rows) == list(want.rows), sql
        assert got.truncated == want.truncated, sql
        assert got.as_of.value and got.as_of.at.tzinfo is not None
    for sql, params, kind in REFUSED:
        for h in (truss, memory):
            with pytest.raises(kind):
                h.backend().query(h.principal("carol"), "catalog", Statement(sql, params), limit=5)


@pytest.mark.truss
def test_a_whole_entity_carries_the_memory_adapters_columns_and_truss_appends_relationships(
    cluster: Any,  # noqa: F811
) -> None:
    truss, memory = _world(cluster, "basic"), _memory()
    sql = Statement("SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100", {})
    got = truss.backend().query(truss.principal("carol"), "catalog", sql, limit=100)
    want = memory.backend().query(memory.principal("carol"), "catalog", sql, limit=100)
    assert {c.name for c in want.columns} <= {c.name for c in got.columns}
    assert {c.name for c in got.columns} - {c.name for c in want.columns} == {"addressedBy"}
    for g, w in zip(got.rows, want.rows, strict=True):
        for name in w:
            if name.endswith("_at") and w[name] is not None:
                assert g[name].tzinfo is not None and w[name].tzinfo is not None, name
            else:
                assert g[name] == w[name], name
    assert got.rows[0]["addressedBy"] == ["sol-1"]
    by_name = {c.name: c for c in got.columns}
    assert (by_name["_version"].type, by_name["_created_at"].type) == ("integer", "timestamp")


@pytest.mark.truss
def test_a_statement_is_capped_at_the_limit_and_says_so(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster, "basic")
    sql = Statement("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 100", {})
    got = h.backend().query(h.principal("carol"), "catalog", sql, limit=1)
    assert [r["code"] for r in got.rows] == ["uc-1"] and got.truncated is True


@pytest.mark.truss
def test_a_non_member_is_told_the_module_is_unknown_for_any_statement(cluster: Any) -> None:  # noqa: F811
    h = _world(cluster, "basic")
    dave = h.principal("dave")
    for sql in ("SELECT COUNT(*) FROM catalog.UseCase u", "this is not sql"):
        with pytest.raises(Invalid) as raised:
            h.backend().query(dave, "catalog", Statement(sql, {}), limit=5)
        assert raised.value.violations[0].code == "unknown_type"


@pytest.mark.truss
def test_a_query_runs_as_the_person_read_only_and_leaves_nothing_behind(
    cluster: Any,  # noqa: F811
) -> None:
    from contextlib import contextmanager

    from arras.adapters.truss import Connections, TrussBackend

    h = _world(cluster, "basic")
    seen: list[tuple[str, int]] = []
    source = h.world.connection_source

    @contextmanager
    def watching(principal: Principal) -> Any:
        with source(principal) as conn:
            seen.append((conn.execute("SELECT session_user").fetchone()[0], 0))
            conn.rollback()
            yield conn
            seen.append(("status", conn.info.transaction_status))  # idle after the call

    backend = TrussBackend("truss", Connections("truss", watching))
    backend.query(
        h.principal("carol"),
        "catalog",
        Statement("SELECT COUNT(*) FROM catalog.UseCase u", {}),
        limit=5,
    )
    assert seen == [("carol", 0), ("status", 0)]
    again = h.backend().query(
        h.principal("carol"),
        "catalog",
        Statement("SELECT COUNT(*) FROM catalog.UseCase u", {}),
        limit=5,
    )
    assert again.rows == ({"count": 2},)
