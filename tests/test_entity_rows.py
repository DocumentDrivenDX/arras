# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The whole-entity statement the console and the search send, and the row they read from it.

A backend may append a column per relationship to `alias.*` (Truss does, whether asked or not) and
refuses a second output of that name (`WFT-OUTPUT-NAME`), so no statement Arras writes names a
relationship's keys by the relationship's own name; the rows come back under the relationship's name.
"""

from __future__ import annotations

import re
from typing import Any

from arras.entityread import FACT_FIELDS, entity_rows, entity_sql, keys_column, relationships_of
from arras.gqlschema import _ATTRIBUTION
from arras.sandbox import Sandbox
from arras.types import Column, Rows

CODE = Column("code", True, "string")


def _type() -> tuple[Any, Any]:
    box = Sandbox().seed()
    mod = next(m for m in box.arras.session(box.people["alice"]).modules() if m.name == "catalog")
    return mod, mod.entity_type("UseCase")


def _rows(columns: tuple[Column, ...], *rows: dict[str, Any]) -> Rows:
    return Rows(columns, rows, False, None, {})  # type: ignore[arg-type]


def test_no_output_name_of_a_whole_entity_statement_is_a_relationship_name() -> None:
    mod, t = _type()
    names = {n for n, _ in relationships_of(mod, t)}
    outputs = re.findall(r' AS "([^"]+)"', entity_sql(mod, t, "", 51))
    assert names and sorted(outputs) == sorted(keys_column(n) for n in names)
    assert not set(outputs) & names
    assert all(o.startswith("_") for o in outputs)  # no declared name begins with `_`


def test_rows_come_back_under_the_relationship_name_when_nothing_else_was_appended() -> None:
    mod, t = _type()
    alias = keys_column("addressedBy")
    got = entity_rows(
        mod, t, _rows((CODE, Column(alias, False, "keys")), {"code": "a", alias: ["s1"]})
    )
    assert got.rows == ({"code": "a", "addressedBy": ["s1"]},)
    assert [c.name for c in got.columns] == ["code", "addressedBy"]


def test_rows_hold_one_column_of_the_name_when_the_backend_appended_it_too() -> None:
    mod, t = _type()
    alias = keys_column("addressedBy")
    keys = Column("addressedBy", False, "keys")
    got = entity_rows(
        mod,
        t,
        _rows(
            (CODE, keys, Column(alias, False, "keys")),
            {"code": "a", "addressedBy": ["s1"], alias: ["s1"]},
        ),
    )
    assert got.rows == ({"code": "a", "addressedBy": ["s1"]},)
    assert [c.name for c in got.columns] == ["code", "addressedBy"]


def test_rows_of_another_statement_are_returned_as_they_are() -> None:
    mod, t = _type()
    rows = _rows((CODE,), {"code": "a"})
    assert entity_rows(mod, t, rows) is rows


def test_the_facts_a_projection_cannot_carry_are_the_fields_that_read_them() -> None:
    assert FACT_FIELDS == {"version", *_ATTRIBUTION}
