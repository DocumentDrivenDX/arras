# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Legal UMF names that are Weft reserved words (`order`, `group`, `in`, ...) read through every
statement Arras writes: GraphQL, search and the console's templates write each name as a Weft
quoted identifier (`arras.names.quoted`), which the memory adapter and Weft's own parser read."""

from __future__ import annotations

import json
from typing import Any

import pytest

from arras.names import quoted, quoted_type
from test_console import Client
from test_weft_parser import _codes, _request, classify, compile_or_skip

MODULE = "desk"


def _field(owner: str, name: str) -> dict[str, Any]:
    return {
        "id": f"{owner}.{name}",
        "kind": "field",
        "nullability": "required",
        "cardinality": "one",
        "scalarType": "string",
        "extensions": {},
    }


def _record(name: str, fields: list[str]) -> list[dict[str, Any]]:
    rec = {
        "id": name,
        "kind": "record",
        "members": [{"module": MODULE, "element": f"{name}.{f}"} for f in fields],
        "extensions": {
            "umf.ddd": {
                "kind": "entity",
                "fields": {
                    f: {"type": {"kind": "scalar", "name": "string"}, "cardinality": "one"}
                    for f in fields
                },
                "identity": {"fields": ["code"], "scope": "context"},
            }
        },
        "keys": [
            {
                "id": "identity",
                "name": "Identity",
                "fields": [{"module": MODULE, "element": f"{name}.code"}],
                "primary": True,
            }
        ],
    }
    return [rec, *(_field(name, f) for f in fields)]


def document() -> str:
    """`Ticket` has properties named `order` and `group`; the relationship `limit` runs from a
    ticket to its `Queue`, whose inverse is named `in`."""
    rel = {
        "id": "ticket-limit",
        "name": "limit",
        "source": [{"module": MODULE, "element": "Ticket"}],
        "target": [{"module": MODULE, "element": "Queue", "key": "identity"}],
        "sourceMultiplicity": {"min": 0, "max": "*"},
        "targetMultiplicity": {"min": 0, "max": 1},
        "targetLifecycle": "independent",
        "directed": True,
        "inverse": "in",
    }
    return json.dumps(
        {
            "umf": "0.10.0",
            "id": MODULE,
            "vocabularies": {"umf.ddd": {"version": "0.1.0"}},
            "extensions": {},
            "modules": [
                {
                    "id": MODULE,
                    "namespace": MODULE,
                    "extensions": {"umf.ddd": {"kind": "bounded-context", "terms": []}},
                    "elements": [
                        *_record("Ticket", ["code", "order", "group"]),
                        *_record("Queue", ["code", "name"]),
                    ],
                    "relationships": [rel],
                }
            ],
        }
    )


@pytest.fixture
def c() -> Client:
    client = Client()
    client.box.load(document())
    root = client.box.arras.session(client.box.people["root"])
    records: list[dict[str, Any]] = [
        {"type": "Queue", "key": "q1", "properties": {"name": "Front desk"}},
        {"type": "Ticket", "key": "t1", "properties": {"order": "first", "group": "pipeline"}},
        {"type": "Ticket", "key": "t2", "properties": {"order": "second", "group": "pipeline"}},
        {"relationship": "limit", "source": "t1", "target": "q1"},
        {"relationship": "limit", "source": "t2", "target": "q1"},
    ]
    root.import_records(MODULE, records, load_id="desk")
    client.box.replica.feed()
    return client


def test_the_helper_writes_quoted_identifiers_of_admitted_names_only() -> None:
    assert quoted("order") == '"order"' and quoted_type("desk.Ticket") == '"desk"."Ticket"'
    for bad in ('a"b', "a b", "", "1a", "x; DROP"):
        with pytest.raises(ValueError):
            quoted(bad)


def test_graphql_reads_reserved_names(c: Client) -> None:
    status, r, _ = c.gql(
        '{ ticket(key: "t1") { key order group limit { key } } '
        'ticketList(filter: {order: "second", limit: "q1"}) { items { key order } truncated } '
        'queue(key: "q1") { in { key } } }',
        f"/graphql/{MODULE}",
    )
    assert status == 200 and "errors" not in r, r
    d = r["data"]
    assert d["ticket"] == {
        "key": "t1",
        "order": "first",
        "group": "pipeline",
        "limit": [{"key": "q1"}],
    }
    assert d["ticketList"]["items"] == [{"key": "t2", "order": "second"}]
    assert [x["key"] for x in d["queue"]["in"]] == ["t1", "t2"]
    _, page, _ = c.gql(
        '{ ticketList(limit: 1, afterKey: "t1") { items { key } truncated } }', f"/graphql/{MODULE}"
    )
    assert page["data"]["ticketList"] == {"items": [{"key": "t2"}], "truncated": False}


def test_search_reads_reserved_names(c: Client) -> None:
    carol = c.box.arras.session(c.box.people["carol"])
    page = carol.search(MODULE, "second")
    assert [(h.type, h.key) for h in page.hits] == [("Ticket", "t2")]


# the statements the console's insert template and Arras's generators write for this module
TEMPLATES = [
    'SELECT x.* FROM "desk"."Ticket" x ORDER BY x."code" LIMIT 51',
    'SELECT x."order", x."group" FROM "desk"."Ticket" x WHERE x."order" = :v ORDER BY x."code" LIMIT 51',
    'SELECT x.*, RELATED_KEYS(x."limit", 100) AS "limit" FROM "desk"."Ticket" x'
    ' WHERE HAS_RELATED(x."limit", KEY(:v)) ORDER BY x."code" LIMIT 51',
    'SELECT x.*, RELATED_KEYS(x."in", 100) AS "in" FROM "desk"."Queue" x ORDER BY x."code" LIMIT 51',
    'SELECT x."group", COUNT(*) FROM "desk"."Ticket" x GROUP BY x."group" ORDER BY x."group" LIMIT 51',
]


@pytest.mark.parametrize("sql", TEMPLATES)
def test_quoted_statements_read_on_the_memory_adapter_and_weft(c: Client, sql: str) -> None:
    params = {"v": "q1" if "KEY" in sql else "second"} if ":v" in sql else {}
    carol = c.box.arras.session(c.box.people["carol"])
    assert carol.query(MODULE, sql, params, limit=50).rows
    compile_json = compile_or_skip("checked on the memory adapter only")
    codes = _codes(compile_json(_request(sql, params, document())))
    assert classify(codes) == "read", codes
