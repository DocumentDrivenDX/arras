# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The sample documents (examples/pizza, northwind and catalog, the largest of them 88 KB) prepare,
accept and register on a real Truss. Truss-marked: needs PostgreSQL 18.6."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from arras.devtruss import TrussBox
from test_truss_harness import _require

pytestmark = pytest.mark.truss

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def box() -> Iterator[TrussBox]:
    _require()
    b = TrussBox()
    try:
        yield b
    finally:
        b.close()


@pytest.mark.parametrize(
    "path",
    [
        "pizza/pizza.umf.json",
        "northwind/northwind.umf.json",
        "catalog/catalog.umf.json",
    ],
)
def test_a_sample_document_registers(box: TrussBox, path: str) -> None:
    root = box.arras.session(box.people["root"])
    got = root.registry().register((EXAMPLES / path).read_text(encoding="utf-8"))
    assert got.changed
