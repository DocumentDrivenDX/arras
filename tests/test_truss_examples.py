# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic, reportOptionalSubscript=false, reportOptionalMemberAccess=false
"""The three sample ontologies (examples/catalog, northwind, pizza) on Truss: each registers, seeds
(with its graph file for the catalog), lists every type the way the console does, opens a record by
its key and takes a modification of every kind its actions define. Truss-marked: needs PostgreSQL
18.6 (`uv run --extra truss --group truss-test pytest -m truss`); the run is the dev host's own world
(`arras.devtruss`), so it also proves what `python -m arras.devhost --truss` serves.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from arras import graphfile
from arras.devtruss import TrussBox
from arras.entityread import relationships_of
from arras.sandbox import read_steps
from test_console import Client
from test_truss_harness import _require

pytestmark = pytest.mark.truss

EXAMPLES = Path(__file__).parent.parent / "examples"
MODULES = ("catalog", "northwind", "pizza")


def _lower(name: str) -> str:
    return name[:1].lower() + name[1:]


@pytest.fixture(scope="module")
def box() -> Iterator[TrussBox]:
    _require()
    b = TrussBox()
    try:
        for name in MODULES:
            here = EXAMPLES / name
            graph = None
            if name == "catalog":
                graph = graphfile.loads((here / "catalog.graph.json").read_text(encoding="utf-8"))
            b.load(
                (here / f"{name}.umf.json").read_text(encoding="utf-8"),
                read_steps(here / "seed.json"),
                graph,
            )
        yield b
    finally:
        b.close()


@pytest.fixture(scope="module")
def console(box: TrussBox) -> Client:
    return Client(box=box)


def _types(box: TrussBox) -> list[tuple[str, Any, Any]]:
    alice = box.arras.session(box.people["alice"])
    return [(m.name, m, t) for m in alice.modules() for t in m.entity_types]


def _cases(name: str) -> list[Any]:
    """(module, type name) of every entity type of an example, read from its document."""
    doc = json.loads((EXAMPLES / name / f"{name}.umf.json").read_text(encoding="utf-8"))
    return [
        pytest.param(name, e["id"], id=f"{name}.{e['id']}")
        for e in doc["modules"][0]["elements"]
        if e["kind"] == "record"
    ]


ALL_TYPES = [c for name in MODULES for c in _cases(name)]


def _selection(box: TrussBox, module: str, local: str) -> str:
    mod = next(m for m in box.arras.session(box.people["alice"]).modules() if m.name == module)
    t = mod.entity_type(local)
    assert t is not None
    return " ".join(f"{n} {{ module type key }}" for n, _ in relationships_of(mod, t))


@pytest.mark.parametrize(("module", "local"), ALL_TYPES)
def test_every_type_lists_the_way_the_console_asks_and_opens_by_its_key(
    box: TrussBox, console: Client, module: str, local: str
) -> None:
    rels = _selection(box, module, local)
    field = f"{_lower(local)}List"
    status, got, _ = console.gql(
        f"{{ {field}(limit: 100) {{ items {{ key {rels} }} truncated freshness {{ backend }} }} }}",
        f"/graphql/{module}",
    )
    assert status == 200 and "errors" not in got, got
    items = got["data"][field]["items"]
    assert items, f"{module}.{local} holds nothing: its seed or graph file did not load"
    assert got["data"][field]["freshness"]["backend"] == "primary"
    first = items[0]["key"]
    status, one, _ = console.gql(
        f'{{ {_lower(local)}(key: "{first}") {{ key version createdBy {rels} }} }}',
        f"/graphql/{module}",
    )
    assert status == 200 and "errors" not in one, one
    row = one["data"][_lower(local)]
    assert row["key"] == first and row["version"] and row["createdBy"]


def _keys(console: Client, module: str, local: str) -> list[str]:
    field = f"{_lower(local)}List"
    _, got, _ = console.gql(
        f"{{ {field}(limit: 100) {{ items {{ key }} }} }}", f"/graphql/{module}"
    )
    return [i["key"] for i in got["data"][field]["items"]]


def _read(console: Client, module: str, local: str, key: str, fields: str) -> dict[str, Any]:
    query = f'{{ {_lower(local)}(key: "{key}") {{ {fields} }} }}'
    _, got, _ = console.gql(query, f"/graphql/{module}")
    assert "errors" not in got, got
    return got["data"][_lower(local)]


def test_the_catalog_takes_an_add_a_rename_a_correct_and_a_link_and_an_unlink(
    box: TrussBox, console: Client
) -> None:
    alice = box.arras.session(box.people["alice"])
    new = "uc-" + uuid.uuid4().hex[:6]
    use_case = _keys(console, "catalog", "UseCase")[0]
    solution = _keys(console, "catalog", "Solution")[0]
    alice.invoke("catalog.AddUseCase", {"code": new, "name": "Added"})
    assert _read(console, "catalog", "UseCase", new, "name version") == {
        "name": "Added",
        "version": "1",
    }
    alice.invoke("catalog.RenameUseCase", {"useCase": new, "name": "Renamed"})
    alice.invoke("catalog.CorrectUseCase", {"useCase": new, "description": "Corrected"})
    got = _read(console, "catalog", "UseCase", new, "name description version")
    assert got == {"name": "Renamed", "description": "Corrected", "version": "3"}
    alice.invoke("catalog.AddressUseCase", {"useCase": use_case, "solution": solution})
    linked = _read(console, "catalog", "UseCase", use_case, "addressedBy { key }")
    assert {"key": solution} in linked["addressedBy"]
    alice.invoke("catalog.UnaddressUseCase", {"useCase": use_case, "solution": solution})
    unlinked = _read(console, "catalog", "UseCase", use_case, "addressedBy { key }")
    assert {"key": solution} not in unlinked["addressedBy"]


def test_northwind_takes_an_add_a_rename_a_correct_and_a_link_and_an_unlink(
    box: TrussBox, console: Client
) -> None:
    alice = box.arras.session(box.people["alice"])
    new = "cat-" + uuid.uuid4().hex[:6]
    alice.invoke("northwind.AddCategory", {"code": new, "name": "Added"})
    alice.invoke("northwind.RenameCategory", {"category": new, "name": "Renamed"})
    alice.invoke("northwind.CorrectCategory", {"category": new, "description": "Corrected"})
    assert _read(console, "northwind", "Category", new, "name description") == {
        "name": "Renamed",
        "description": "Corrected",
    }
    order = _keys(console, "northwind", "Order")[0]
    employees = _keys(console, "northwind", "Employee")
    held = _read(console, "northwind", "Order", order, "handledBy { key }")["handledBy"]
    free = next(e for e in employees if {"key": e} not in held)
    alice.invoke("northwind.LinkOrderHandledBy", {"order": order, "handledBy": free})
    assert {"key": free} in _read(console, "northwind", "Order", order, "handledBy { key }")[
        "handledBy"
    ]
    alice.invoke("northwind.UnlinkOrderHandledBy", {"order": order, "handledBy": free})
    assert {"key": free} not in _read(console, "northwind", "Order", order, "handledBy { key }")[
        "handledBy"
    ]


def test_pizza_takes_an_add_a_rename_a_correct_and_a_link_and_an_unlink_of_has_topping(
    box: TrussBox, console: Client
) -> None:
    alice = box.arras.session(box.people["alice"])
    new = "top-" + uuid.uuid4().hex[:6]
    alice.invoke("pizza.AddTopping", {"code": new, "name": "Added"})
    alice.invoke("pizza.RenameTopping", {"topping": new, "name": "Renamed"})
    assert _read(console, "pizza", "Topping", new, "name")["name"] == "Renamed"
    pizza = _keys(console, "pizza", "Pizza")[0]
    alice.invoke(
        "pizza.CorrectPizza",
        {"pizza": pizza, "description": "Corrected", "price": Decimal("12.50")},
    )
    assert _read(console, "pizza", "Pizza", pizza, "description price") == {
        "description": "Corrected",
        "price": "12.50",
    }
    alice.invoke("pizza.LinkPizzaHasTopping", {"pizza": pizza, "hasTopping": new})
    assert {"key": new} in _read(console, "pizza", "Pizza", pizza, "hasTopping { key }")[
        "hasTopping"
    ]
    alice.invoke("pizza.UnlinkPizzaHasTopping", {"pizza": pizza, "hasTopping": new})
    assert {"key": new} not in _read(console, "pizza", "Pizza", pizza, "hasTopping { key }")[
        "hasTopping"
    ]


def test_a_whole_entity_list_with_the_facts_reads_every_type_of_every_example(
    box: TrussBox, console: Client
) -> None:
    """A list that selects a fact (`version`, an attribution field) is the whole-entity read, whose
    statement names no relationship column twice (R17.2); one that does not is a projection."""
    for module, mod, t in _types(box):
        field = f"{_lower(t.local_name)}List"
        rels = " ".join(f"{n} {{ key }}" for n, _ in relationships_of(mod, t))
        status, got, _ = console.gql(
            f"{{ {field}(limit: 3) {{ items {{ key version createdBy updatedAt {rels} }} }} }}",
            f"/graphql/{module}",
        )
        assert status == 200 and "errors" not in got, (module, t.local_name, got)
        assert got["data"][field]["items"], (module, t.local_name)
