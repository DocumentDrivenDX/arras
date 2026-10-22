# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The memory adapter's relational reads (W-011), held against Weft's own parser.

Two batteries, kept here as data, over the test module `shop` (customers, purchases, lines):

- `ACCEPTED`: statements the memory adapter serves (joins, SUM, multi-column GROUP BY, ORDER BY,
  tuple keysets, HAS_RELATED, RELATED_KEYS, AS). Weft must read each one: no parse-stage fault
  under the read profile the memory adapter classifies it to (`general` sends none).
- `REFUSED`: statements Weft refuses at the parse stage (OR, DISTINCT, OFFSET, outer joins,
  subqueries, a bare `*`, syntax errors, unknown names and types, repeated output names). The
  memory adapter must refuse each one too, `Invalid` or `Unsupported`.

The batteries run against the memory adapter always; against Weft when `import weft` succeeds, and
skip saying so when it does not. The rest of the file checks what the memory adapter answers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from arras import Invalid, Unsupported
from arras.fakes_eval import MAX_WORK
from arras.fakes_weft import (
    COUNT,
    ENTITY,
    GENERAL,
    RELATED,
    SUBSET,
    WEFT,
    profiles_needed,
    resolve,
)
from arras.results import WeftSupport
from arras.types import Statement
from arras.umf import parse_module
from shop_module import MODULE, document, shop_store
from test_weft_parser import PARSE_FAULTS, _codes, _profile, _request, classify, compile_or_skip

DOC = document()
SHOP = parse_module(DOC)
JOIN = "FROM shop.Customer c JOIN shop.Purchase p ON p.customer = c.code"

# (sql, params, the profile the memory adapter classifies it to)
ACCEPTED: list[tuple[str, dict[str, Any], str]] = [
    (f"SELECT c.code, p.code AS purchase {JOIN} ORDER BY p.code LIMIT 10", {}, GENERAL),
    (
        f"SELECT c.region, SUM(p.total) AS spent {JOIN} GROUP BY c.region ORDER BY c.region LIMIT 10",
        {},
        GENERAL,
    ),
    (
        f"SELECT c.region, c.name, COUNT(*) {JOIN} GROUP BY c.region, c.name"
        " ORDER BY c.region, c.name LIMIT 10",
        {},
        COUNT,
    ),
    ("SELECT SUM(p.qty) AS units FROM shop.Purchase p", {}, GENERAL),
    ("SELECT COUNT(*) FROM shop.Purchase p WHERE p.customer = 'c1'", {}, COUNT),
    (
        "SELECT p.customer, SUM(p.qty) AS units, COUNT(*) AS n FROM shop.Purchase p"
        " GROUP BY p.customer ORDER BY p.customer LIMIT 10",
        {},
        GENERAL,
    ),
    (
        "SELECT p.customer, p.code FROM shop.Purchase p WHERE (p.customer, p.code) > (:c, :k)"
        " ORDER BY p.customer, p.code LIMIT 2",
        {"c": "c1", "k": "o1"},
        GENERAL,
    ),
    (
        "SELECT p.code FROM shop.Purchase p WHERE HAS_RELATED(p.placedBy, KEY('c1'))"
        " ORDER BY p.code LIMIT 10",
        {},
        RELATED,
    ),
    (
        "SELECT c.code, RELATED_KEYS(c.places, 10) AS orders FROM shop.Customer c"
        " ORDER BY c.code LIMIT 10",
        {},
        RELATED,
    ),
    (
        f'SELECT c.name, l.sku, l.amount {JOIN} JOIN shop.Line l ON l."order" = p.code'
        " WHERE l.amount > 3 ORDER BY l.code LIMIT 10",
        {},
        GENERAL,
    ),
    ("SELECT c.name, c.region FROM shop.Customer c ORDER BY c.region, c.name LIMIT 5", {}, GENERAL),
    (
        'SELECT p.code FROM shop.Purchase p JOIN shop.Line l ON l."order" = p.code'
        " WHERE l.amount = p.total ORDER BY p.code LIMIT 5",
        {},
        GENERAL,
    ),
    (
        "SELECT p.*, c.name FROM shop.Purchase p JOIN shop.Customer c ON c.code = p.customer"
        " ORDER BY p.code LIMIT 5",
        {},
        GENERAL,
    ),
    ("SELECT Customer.code FROM Customer ORDER BY Customer.code LIMIT 5", {}, ENTITY),
    (
        "SELECT c.* FROM shop.Customer c WHERE c.code > :last ORDER BY c.code LIMIT 2",
        {"last": "c1"},
        ENTITY,
    ),  # fmt: skip
    (
        "SELECT a.code, b.code AS other FROM shop.Customer a JOIN shop.Customer b"
        " ON a.region = b.region WHERE a.code > b.code ORDER BY a.code LIMIT 10",
        {},
        GENERAL,
    ),
    (
        f"SELECT c.region, COUNT(*) AS n {JOIN} WHERE c.region = :r GROUP BY c.region"
        " ORDER BY c.region LIMIT 3",
        {"r": "east"},
        COUNT,
    ),
    # the forms Weft reads that a narrower reader might refuse: parameters case-folded and spaced,
    # a spaced sign, an absent-allowed column, words that begin excluded constructs as aliases,
    # column equality in a page or a count, exact decimals in their domain, the whitespace Weft reads
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :K ORDER BY c.code LIMIT 5", {"k": "c1"}, ENTITY),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :  k ORDER BY c.code LIMIT 5", {"k": "c1"}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = - 1 ORDER BY p.code LIMIT 5", {}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total > - 1.5 ORDER BY p.code LIMIT 5", {}, GENERAL),
    ("SELECT c.note, c.code FROM shop.Customer c ORDER BY c.code LIMIT 5", {}, ENTITY),
    ("SELECT not.code FROM shop.Customer not ORDER BY not.code LIMIT 5", {}, ENTITY),
    ("SELECT desc.code FROM shop.Customer AS desc ORDER BY desc.code LIMIT 5", {}, ENTITY),
    ("SELECT like.code FROM shop.Customer like ORDER BY like.code LIMIT 5", {}, ENTITY),
    ("SELECT with.code FROM shop.Customer AS with ORDER BY with.code LIMIT 5", {}, ENTITY),
    ("SELECT case.code FROM shop.Customer case ORDER BY case.code LIMIT 5", {}, ENTITY),
    ("SELECT has_related.code FROM shop.Customer has_related ORDER BY has_related.code LIMIT 5", {}, ENTITY),
    ("SELECT c.code FROM shop.Customer c WHERE c.region = c.name ORDER BY c.code LIMIT 5", {}, ENTITY),
    (
        "SELECT c.region, COUNT(*) FROM shop.Customer c WHERE c.region = c.name GROUP BY c.region"
        " ORDER BY c.region LIMIT 5",
        {},
        COUNT,
    ),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = 10 ORDER BY p.code LIMIT 5", {}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = 10.500 ORDER BY p.code LIMIT 5", {}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = -9999999999.99 ORDER BY p.code LIMIT 5", {}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = :t ORDER BY p.code LIMIT 5", {"t": Decimal("10.5")}, ENTITY),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = -9223372036854775808 ORDER BY p.code LIMIT 5", {}, ENTITY),
    ('SELECT c.code AS "A", c.name AS a FROM shop.Customer c ORDER BY c.code LIMIT 5', {}, ENTITY),
    ("SELECT c.code FROM shop.Customer c\t\r\nORDER BY c.code LIMIT 5\x0c", {}, ENTITY),
]  # fmt: skip

_C = "SELECT c.code FROM shop.Customer c"
REFUSED: list[tuple[str, dict[str, Any]]] = [
    (f"{_C} WHERE c.code = 'c1' OR c.code = 'c2' ORDER BY c.code LIMIT 5", {}),
    ("SELECT DISTINCT c.region FROM shop.Customer c ORDER BY c.region LIMIT 5", {}),
    (f"{_C} ORDER BY c.code LIMIT 5 OFFSET 5", {}),
    (f"{_C} LEFT JOIN shop.Purchase p ON p.customer = c.code ORDER BY c.code LIMIT 5", {}),
    (f"{_C} FULL OUTER JOIN shop.Purchase p ON p.customer = c.code ORDER BY c.code LIMIT 5", {}),
    (f"{_C} CROSS JOIN shop.Purchase p ORDER BY c.code LIMIT 5", {}),
    (f"{_C}, shop.Purchase p WHERE p.customer = c.code ORDER BY c.code LIMIT 5", {}),
    (f"{_C} WHERE c.code = (SELECT p.customer FROM shop.Purchase p) LIMIT 5", {}),
    (f"{_C} WHERE (SELECT p.customer FROM shop.Purchase p) > ('a') LIMIT 5", {}),
    (f"{_C} WHERE c.code IN ('c1', 'c2') ORDER BY c.code LIMIT 5", {}),
    ("SELECT * FROM shop.Customer c LIMIT 5", {}),
    ("SELECT c.code FROM", {}),
    (f"{_C} WHERE", {}),
    ("SELECT c.code shop.Customer c", {}),
    (f"{_C} ORDER BY c.code LIMIT", {}),
    ("SELECT c.nope FROM shop.Customer c ORDER BY c.code LIMIT 5", {}),
    ("SELECT x.code FROM shop.Nope x ORDER BY x.code LIMIT 5", {}),
    ("SELECT x.code FROM shop.Customer c ORDER BY c.code LIMIT 5", {}),
    (
        f"{_C} JOIN shop.Purchase p ON p.customer = l.code JOIN shop.Line l ON l.code = p.code LIMIT 5",
        {},
    ),
    (f"SELECT c.code, p.code {JOIN} ORDER BY c.code LIMIT 5", {}),
    (f"SELECT c.code, p.customer AS code {JOIN} ORDER BY c.code LIMIT 5", {}),
    (f"{_C} JOIN shop.Purchase c ON c.code = c.code LIMIT 5", {}),
    (
        "SELECT c.name, COUNT(*) FROM shop.Customer c GROUP BY c.region ORDER BY c.region LIMIT 5",
        {},
    ),
    (
        "SELECT c.region, COUNT(*) FROM shop.Customer c GROUP BY c.region ORDER BY c.name LIMIT 5",
        {},
    ),
    ("SELECT SUM(c.name) AS s FROM shop.Customer c", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = 'x' ORDER BY p.code LIMIT 5", {}),
    (f"{_C} ORDER BY c.code DESC LIMIT 5", {}),
    ("SELECT l.order FROM shop.Line l ORDER BY l.code LIMIT 5", {}),
    (f"{_C} WHERE c.code < 'c2' ORDER BY c.code LIMIT 5", {}),
    (f"{_C} ORDER BY c.code LIMIT 1001", {}),
    (f"{_C} WHERE c.code = :k ORDER BY c.code LIMIT 5", {}),
    ("SELECT c.region FROM shop.Customer c GROUP BY c.region HAVING COUNT(*) > 1 LIMIT 5", {}),
    (f"{_C} UNION SELECT p.code FROM shop.Purchase p LIMIT 5", {}),
    ("SELECT upper(c.name) FROM shop.Customer c ORDER BY c.code LIMIT 5", {}),
    # numbers: no comparison across integer and decimal; an integer parameter is no decimal; a
    # literal or a parameter outside its field's domain (scale, precision, integer width)
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = p.qty ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty > p.total ORDER BY p.code LIMIT 5", {}),
    ('SELECT p.code FROM shop.Purchase p JOIN shop.Line l ON l.amount = p.qty ORDER BY p.code LIMIT 5', {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = :t ORDER BY p.code LIMIT 5", {"t": 10}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = 10.505 ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = 12345678901.00 ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total > -1.505 ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.total = :t ORDER BY p.code LIMIT 5", {"t": Decimal("10.505")}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = 99999999999999999999 ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = 9223372036854775808 ORDER BY p.code LIMIT 5", {}),
    ("SELECT p.code FROM shop.Purchase p WHERE p.qty = :q ORDER BY p.code LIMIT 5", {"q": 99999999999999999999}),
    ("SELECT p.code FROM shop.Purchase p WHERE (p.total, p.code) > (10.505, 'a') ORDER BY p.total, p.code LIMIT 5", {}),
    # names and text: `count` and `related_keys` begin projections, a reserved word names no
    # parameter, NUL and whitespace Weft does not read, output names compared case-folded,
    # parameter names distinct after folding, a filter or a group on an absent-allowed field
    ("SELECT count.code FROM shop.Customer count ORDER BY count.code LIMIT 5", {}),
    ("SELECT related_keys.code FROM shop.Customer AS related_keys ORDER BY related_keys.code LIMIT 5", {}),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :select ORDER BY c.code LIMIT 5", {"select": "c1"}),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :Order ORDER BY c.code LIMIT 5", {"order": "c1"}),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = 'a\x00b' ORDER BY c.code LIMIT 5", {}),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :k ORDER BY c.code LIMIT 5", {"k": "a\x00b"}),
    ("SELECT c.code FROM shop.Customer c ORDER BY c.code LIMIT 5\u00a0", {}),
    ("SELECT c.code FROM shop.Customer c\x0bORDER BY c.code LIMIT 5", {}),
    ("SELECT c.code FROM shop.Customer c\u2003ORDER BY c.code LIMIT 5", {}),
    ("SELECT c.code AS a, c.name AS A FROM shop.Customer c ORDER BY c.code LIMIT 5", {}),
    ('SELECT c.code AS "a", c.name AS A FROM shop.Customer c ORDER BY c.code LIMIT 5', {}),
    ("SELECT c.code, c.name AS CODE FROM shop.Customer c ORDER BY c.code LIMIT 5", {}),
    ("SELECT c.code FROM shop.Customer c WHERE c.code = :K ORDER BY c.code LIMIT 5", {"k": "c1", "K": "c2"}),
    ("SELECT c.code FROM shop.Customer c WHERE c.note = 'x' ORDER BY c.code LIMIT 5", {}),
    ("SELECT c.note, COUNT(*) FROM shop.Customer c GROUP BY c.note ORDER BY c.note LIMIT 5", {}),
]  # fmt: skip

# Where Weft reads a statement and the memory adapter refuses it (the safe direction), held here so
# the list stays true: each is refused by the memory adapter and read by Weft.
KNOWN_NARROWER: list[tuple[str, dict[str, Any], str | None]] = [
    # appended facts are no output names in Weft; the memory adapter's row cannot hold both
    ('SELECT c.*, c.code AS "_version" FROM shop.Customer c ORDER BY c.code LIMIT 5', {}, None),
    # the memory adapter bounds the general dialect itself: a LIMIT, or a global aggregate
    ("SELECT c.region, COUNT(*) FROM shop.Customer c GROUP BY c.region", {}, None),
]

# Weft's statement-level refusals: its parse-stage faults (output names and numeric domains among
# them), and its check of the statement's LIMIT.
WEFT_REFUSES = PARSE_FAULTS | {"WFT-LIMIT"}


def _store():
    return shop_store()


def _ask(sql: str, params: dict[str, Any] | None = None, limit: int = 50, store=None):
    store, carol = store or _store()
    return store.query(carol, MODULE, Statement(sql, params or {}), limit=limit)


# -- the batteries against the memory adapter -----------------------------------------------------


@pytest.mark.parametrize(("sql", "params", "profile"), ACCEPTED, ids=range(len(ACCEPTED)))
def test_the_memory_adapter_serves_the_accepted_battery(sql, params, profile) -> None:
    assert profiles_needed(resolve(Statement(sql, params), SHOP)) == (profile,)
    _ask(sql, params)


@pytest.mark.parametrize(("sql", "params"), REFUSED, ids=range(len(REFUSED)))
def test_the_memory_adapter_refuses_the_refused_battery(sql, params) -> None:
    with pytest.raises((Invalid, Unsupported)):
        _ask(sql, params)


# -- the batteries against Weft ------------------------------------------------------------------


def _compile():
    return compile_or_skip("the batteries were checked against the memory adapter only")


def test_weft_reads_every_statement_the_memory_adapter_accepts() -> None:
    compile_json = _compile()
    unread = []
    for sql, params, profile in ACCEPTED:
        assert _profile(sql, params, DOC) == (None if profile == GENERAL else profile)
        codes = _codes(compile_json(_request(sql, params, DOC)))
        if classify(codes) != "read":
            unread.append(f"{sql} -> {sorted(codes)}")
    assert unread == []


def test_weft_refuses_every_statement_of_the_refused_battery() -> None:
    compile_json = _compile()
    read = []
    for sql, params in REFUSED:
        codes = _codes(compile_json(_request(sql, params, DOC)))
        if not codes & WEFT_REFUSES:
            read.append(f"{sql} -> {sorted(codes)}")
    assert read == []


def test_the_known_disagreements_are_only_narrower() -> None:
    """The statements Weft reads and the memory adapter refuses, each still both."""
    compile_json = _compile()
    for sql, params, profile in KNOWN_NARROWER:
        with pytest.raises((Invalid, Unsupported)):
            _ask(sql, params)
        codes = _codes(compile_json(_request(sql, params, DOC, profile)))
        assert classify(codes) == "read", (sql, codes)


# -- what the memory adapter answers -------------------------------------------------------------


def test_an_inner_join_is_a_bag() -> None:
    a = _ask(f"SELECT c.code, p.code AS purchase {JOIN} ORDER BY p.code LIMIT 10")
    assert [(r["code"], r["purchase"]) for r in a.rows] == [
        ("c1", "o1"),
        ("c1", "o2"),
        ("c2", "o3"),
        ("c2", "o4"),
    ]  # c3 places nothing: an inner join drops it
    assert [c.name for c in a.columns] == ["code", "purchase"]
    # a self join on a shared value keeps every matching pair, duplicates included
    pairs = _ask(
        "SELECT a.code, b.code AS other FROM shop.Customer a JOIN shop.Customer b"
        " ON a.region = b.region ORDER BY a.code, b.code LIMIT 20"
    )
    assert [(r["code"], r["other"]) for r in pairs.rows] == [
        ("c1", "c1"),
        ("c1", "c3"),
        ("c2", "c2"),
        ("c3", "c1"),
        ("c3", "c3"),
    ]
    n = _ask(
        "SELECT COUNT(*) AS n FROM shop.Customer a JOIN shop.Customer b ON a.region = b.region"
    )
    assert n.rows == ({"n": 5},)  # COUNT(*) counts the bag's rows


def test_sum_is_exact_and_grouped_by_several_columns() -> None:
    spent = _ask(
        f"SELECT c.region, SUM(p.total) AS spent {JOIN} GROUP BY c.region ORDER BY c.region LIMIT 10"
    )
    assert spent.rows == (
        {"region": "east", "spent": Decimal("14.75")},
        {"region": "west", "spent": Decimal("8.25")},
    )
    assert [(c.name, c.type) for c in spent.columns] == [("region", "string"), ("spent", "decimal")]
    units = _ask("SELECT SUM(p.qty) AS units, COUNT(*) FROM shop.Purchase p")
    assert units.rows == ({"units": 7, "count": 4},)
    none = _ask("SELECT SUM(p.qty) AS units FROM shop.Purchase p WHERE p.customer = 'c3'")
    assert none.rows == ({"units": None},)  # a global aggregate answers one row, also over nothing
    multi = _ask(
        f"SELECT c.region, c.name, COUNT(*) {JOIN} GROUP BY c.region, c.name"
        " ORDER BY c.region, c.name LIMIT 10"
    )
    assert multi.rows == (
        {"region": "east", "name": "Ann", "count": 2},
        {"region": "west", "name": "Bob", "count": 2},
    )
    by_customer = _ask(
        "SELECT p.customer, SUM(p.qty) AS units, SUM(p.total) AS total FROM shop.Purchase p"
        " GROUP BY p.customer ORDER BY p.customer LIMIT 1"
    )
    assert by_customer.rows == ({"customer": "c1", "units": 4, "total": Decimal("14.75")},)


def test_three_joins_filters_and_reserved_names() -> None:
    a = _ask(
        f'SELECT c.name, l.sku, l.amount {JOIN} JOIN shop.Line l ON l."order" = p.code'
        " WHERE l.amount > 3 ORDER BY l.code LIMIT 10"
    )
    assert a.rows == (
        {"name": "Ann", "sku": "ink", "amount": Decimal("8.00")},
        {"name": "Bob", "sku": "pen", "amount": Decimal("7.00")},
    )
    same = _ask(
        'SELECT p.code FROM shop.Purchase p JOIN shop.Line l ON l."order" = p.code'
        " WHERE l.amount = p.total ORDER BY p.code LIMIT 5"
    )
    assert same.rows == ({"code": "o3"},)  # a column compared with a column
    with pytest.raises(Invalid) as e:  # a reserved word names a member only when quoted
        _ask("SELECT l.order FROM shop.Line l ORDER BY l.code LIMIT 5")
    assert e.value.violations[0].code == "syntax"


def test_order_limit_and_the_tuple_keyset() -> None:
    sql = (
        "SELECT p.customer, p.code FROM shop.Purchase p WHERE (p.customer, p.code) > (:c, :k)"
        " ORDER BY p.customer, p.code LIMIT 2"
    )
    page = _ask(sql, {"c": "c1", "k": "o1"})
    assert [r["code"] for r in page.rows] == ["o2", "o3"]
    page = _ask(sql, {"c": "c2", "k": "o3"})
    assert [r["code"] for r in page.rows] == ["o4"]
    by_name = _ask("SELECT c.name, c.region FROM shop.Customer c ORDER BY c.region, c.name LIMIT 5")
    assert [r["name"] for r in by_name.rows] == ["Ann", "Cy", "Bob"]
    capped = _ask(f"SELECT c.code, p.code AS purchase {JOIN} ORDER BY p.code LIMIT 10", limit=3)
    assert len(capped.rows) == 3 and capped.truncated


def test_related_reads_and_whole_entities_across_a_join() -> None:
    a = _ask(
        "SELECT p.code FROM shop.Purchase p WHERE HAS_RELATED(p.placedBy, KEY('c1'))"
        " ORDER BY p.code LIMIT 10"
    )
    assert [r["code"] for r in a.rows] == ["o1", "o2"]
    keys = _ask(
        "SELECT c.code, RELATED_KEYS(c.places, 1) AS orders FROM shop.Customer c"
        " ORDER BY c.code LIMIT 10"
    )
    assert [r["orders"] for r in keys.rows] == [["o1"], ["o3"], []]
    whole = _ask(
        "SELECT p.*, c.name FROM shop.Purchase p JOIN shop.Customer c ON c.code = p.customer"
        " ORDER BY p.code LIMIT 1"
    )
    row = whole.rows[0]
    assert row["code"] == "o1" and row["name"] == "Ann" and row["total"] == Decimal("10.50")
    assert row["_version"] == 1 and row["_load_id"] == "shop"  # the facts of the starred scan


def test_the_general_profile_is_bounded_by_the_memory_adapter() -> None:
    for sql in (  # no LIMIT on a statement that may answer many rows
        f"SELECT c.code, p.code AS purchase {JOIN} ORDER BY p.code",
        "SELECT c.name FROM shop.Customer c ORDER BY c.name",
        "SELECT p.customer, SUM(p.qty) AS units FROM shop.Purchase p GROUP BY p.customer",
    ):
        with pytest.raises(Unsupported) as e:
            _ask(sql)
        assert e.value.supported[1:] == SUBSET, sql
    store, carol = _store()
    store.weft = WeftSupport(WEFT.version, (ENTITY, RELATED, COUNT))  # the named profiles only
    with pytest.raises(Unsupported) as e:
        store.query(carol, MODULE, Statement(ACCEPTED[0][0], {}), limit=50)
    assert e.value.construct == "profile general"
    assert GENERAL not in e.value.supported[0] and "memory" in e.value.supported[0]


def test_joins_are_capped_and_the_bag_is_bounded(monkeypatch) -> None:
    joins = " ".join(f"JOIN shop.Customer c{i} ON c{i}.code = c.code" for i in range(17))
    with pytest.raises(Invalid) as e:
        _ask(f"SELECT c.code FROM shop.Customer c {joins} ORDER BY c.code LIMIT 5")
    assert e.value.violations[0].code == "bound"
    sixteen = " ".join(f"JOIN shop.Customer c{i} ON c{i}.code = c.code" for i in range(16))
    assert (
        len(_ask(f"SELECT c.code FROM shop.Customer c {sixteen} ORDER BY c.code LIMIT 5").rows) == 3
    )
    import arras.fakes_eval as fe

    monkeypatch.setattr(fe, "MAX_WORK", 4)
    with pytest.raises(Unsupported) as u:  # a region self join holds 5 rows: the data's bound
        _ask(
            "SELECT a.code FROM shop.Customer a JOIN shop.Customer b ON a.region = b.region"
            " ORDER BY a.code LIMIT 1"
        )
    assert "4 rows of work" in u.value.construct and u.value.supported[1:] == SUBSET
    assert MAX_WORK == 10_000


def _bulk(n: int):
    """The shop with `n` more customers, each placing one purchase."""
    store, carol = shop_store()
    root = store.access.grant("bulk", MODULE, "read", "write", "schema", admin=True)
    records: list[dict[str, Any]] = []
    for i in range(n):
        records.append(
            {
                "type": "Customer",
                "key": f"b{i:05}",
                "properties": {"name": f"N{i}", "region": "north"},
            }
        )
        records.append({"type": "Purchase", "key": f"q{i:05}", "properties": {"customer": f"b{i:05}", "total": Decimal("1.00"), "qty": 1}})  # fmt: skip
        records.append({"relationship": "places", "source": f"b{i:05}", "target": f"q{i:05}"})
    assert not store.import_records(
        root, MODULE, records, load_id="bulk", initiated_by="bulk"
    ).rejected
    return store, carol


def test_a_join_is_hashed_on_its_equality_and_the_cap_is_charged_first() -> None:
    import time

    world = _bulk(2000)
    start = time.perf_counter()
    a = _ask(
        f"SELECT c.code, p.code AS purchase, RELATED_KEYS(c.places, 5) AS placed {JOIN}"
        " WHERE c.region = 'north' ORDER BY p.code LIMIT 1000",
        limit=1000,
        store=world,
    )
    joined = time.perf_counter() - start
    assert len(a.rows) == 1000 and a.rows[0]["placed"] == ["q00000"]
    assert joined < 1.0, joined  # 2,003 by 2,004 rows: a hash join, not four million comparisons
    start = time.perf_counter()
    with pytest.raises(Unsupported):  # no pair links b to a: every combination, refused up front
        _ask(
            "SELECT a.code FROM shop.Customer a JOIN shop.Customer b ON a.code = a.code"
            " ORDER BY a.code LIMIT 5",
            store=world,
        )
    assert time.perf_counter() - start < 0.5


def test_names_are_resolved_once_each() -> None:
    for sql, code in (
        (f"SELECT c.code, p.code {JOIN} ORDER BY c.code LIMIT 5", "duplicate_column"),
        (f"{_C} JOIN shop.Purchase c ON c.code = c.code LIMIT 5", "duplicate_alias"),
        (
            f"{_C} JOIN shop.Purchase p ON p.customer = l.code JOIN shop.Line l ON l.code = p.code LIMIT 5",
            "unknown_alias",
        ),
        ("SELECT SUM(c.name) AS s FROM shop.Customer c", "type"),
        (
            "SELECT c.name, COUNT(*) FROM shop.Customer c GROUP BY c.region ORDER BY c.region LIMIT 5",
            "group_by",
        ),
        (f"SELECT c.code {JOIN} WHERE p.qty = c.code ORDER BY c.code LIMIT 5", "type"),
        ("SELECT p.code FROM shop.Purchase p WHERE p.total = p.qty ORDER BY p.code LIMIT 5", "type"),
        ("SELECT p.code FROM shop.Purchase p WHERE p.total = 10.505 ORDER BY p.code LIMIT 5", "numeric_domain"),
        ("SELECT p.code FROM shop.Purchase p WHERE p.qty = 9223372036854775808 ORDER BY p.code LIMIT 5", "numeric_domain"),
        ("SELECT c.code AS a, c.name AS A FROM shop.Customer c ORDER BY c.code LIMIT 5", "duplicate_column"),
    ):  # fmt: skip
        with pytest.raises(Invalid) as e:
            _ask(sql)
        assert e.value.violations[0].code == code, sql
    with pytest.raises(Unsupported) as u:  # one module per statement
        _ask("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 5")
    assert "outside module shop" in u.value.construct


def test_numbers_are_held_at_their_domain_and_sum_carries_its_scale() -> None:
    store, carol = shop_store()
    root = store.access.grant("loader", MODULE, "read", "write", "schema", admin=True)
    loaded = store.import_records(
        root,
        MODULE,
        [
            {"type": "Purchase", "key": "o5", "properties": {"customer": "c3", "total": 7, "qty": 1}},
            {"type": "Purchase", "key": "o6", "properties": {"customer": "c3", "total": Decimal("3.1"), "qty": 1}},
            {"type": "Purchase", "key": "o7", "properties": {"customer": "c3", "total": Decimal("1.005"), "qty": 1}},
            {"type": "Purchase", "key": "o8", "properties": {"customer": "c3", "total": 10**10, "qty": 1}},
        ],
        load_id="scale",
        initiated_by="loader",
    )  # fmt: skip
    # a decimal(12,2) holds 7 as 7.00 and 3.1 as 3.10, and refuses what does not fit it
    assert loaded.created == 2
    assert [("o7" in r.identity, "o8" in r.identity) for r in loaded.rejected] == [
        (True, False),
        (False, True),
    ]
    assert all(r.reason.startswith("total:") for r in loaded.rejected)
    whole = store.query(
        carol,
        MODULE,
        Statement(
            "SELECT p.* FROM shop.Purchase p WHERE p.customer = 'c3' ORDER BY p.code LIMIT 5"
        ),
        limit=50,
    )
    assert [str(r["total"]) for r in whole.rows] == ["7.00", "3.10"]
    store.state.entities[next(r for r in store.state.entities if r.key == "o5")].props["total"] = (
        Decimal("7")  # a value held off its scale: the sum still carries the argument's
    )
    s = store.query(
        carol,
        MODULE,
        Statement("SELECT SUM(p.total) AS s FROM shop.Purchase p WHERE p.customer = 'c3'"),
        limit=50,
    )
    assert str(s.rows[0]["s"]) == "10.10"
    with pytest.raises(Invalid) as e:  # an integer parameter is no decimal
        store.query(
            carol,
            MODULE,
            Statement(
                "SELECT p.code FROM shop.Purchase p WHERE p.total = :t ORDER BY p.code LIMIT 5",
                {"t": 10},
            ),
            limit=50,
        )
    assert e.value.violations[0].code == "type"
