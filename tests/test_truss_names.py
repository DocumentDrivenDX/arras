# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""Truss requires an authored, nonempty name on every Record and Field (UMF does not), and states
every element that lacks one (`TRUSS-NAME-MISSING`). The adapter lists them all as an `Invalid` and
fills nothing in; the historical contract example, which names none, is kept as written and its
revised copy (`catalog.named.umf.json`) is the one that registers (plan B9).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arras.adapters.truss.registry import _diagnosed  # pyright: ignore[reportPrivateUsage]
from arras.errors import Invalid
from arras.umf import parse_module
from test_truss_harness import cluster  # noqa: F401

EXAMPLES = Path(__file__).resolve().parent.parent / "docs/helix/02-design/contracts/examples"
ORIGINAL = EXAMPLES / "catalog.umf.json"
REVISED = EXAMPLES / "catalog.named.umf.json"


def elements(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e for m in document["modules"] for e in m["elements"] if e["kind"] in ("record", "field")
    ]


def test_the_historical_example_is_kept_without_names_and_its_revision_differs_only_by_them() -> (
    None
):
    original, revised = json.loads(ORIGINAL.read_text()), json.loads(REVISED.read_text())
    assert all("name" not in e for e in elements(original))
    assert all(e["name"] for e in elements(revised))
    for e in elements(revised):  # nothing else was touched
        e.pop("name")
    stripped = json.loads(json.dumps(revised))
    for m in json.loads(ORIGINAL.read_text())["modules"]:
        assert (
            m["elements"] == next(x for x in stripped["modules"] if x["id"] == m["id"])["elements"]
        )


def test_every_name_missing_diagnostic_is_one_violation_naming_its_element() -> None:
    def diagnostic(element: str, kind: str) -> bytes:
        return json.dumps(
            {
                "code": "TRUSS-NAME-MISSING",
                "severity": "error",
                "moduleId": "catalog",
                "elementId": element,
                "kind": kind,
                "path": "/modules/0/elements/0/name",
                "message": "x",
            }
        ).encode()

    found = _diagnosed(
        (diagnostic("UseCase", "record"), diagnostic("UseCase.code", "field"), b"not json")
    )
    assert [(v.path, v.code) for v in found] == [
        ("elements.catalog.UseCase.name", "name_missing"),
        ("elements.catalog.UseCase.code.name", "name_missing"),
    ]
    assert "record" in found[0].message and "field" in found[1].message


def test_another_diagnostic_is_a_violation_of_the_document_by_its_code() -> None:
    other = json.dumps({"code": "TRUSS-OTHER", "message": "m"}).encode()
    [v] = _diagnosed((other,))
    assert (v.path, v.code) == ("document", "truss-other")
    assert _diagnosed(()) == []


@pytest.mark.truss
def test_truss_lists_every_nameless_element_and_registers_the_revised_example(
    cluster: Any,  # noqa: F811
) -> None:
    original, revised = ORIGINAL.read_bytes(), REVISED.read_bytes()
    with cluster.bare_database() as bare:
        backend = bare.backend()
        migrated = backend.migrate()
        alice = bare.person("nm_alice", migrated.registrar_role)
        module = parse_module(original)
        for call in (backend.register, backend.validate_register):
            with pytest.raises(Invalid) as raised:
                call(alice, original, module, unknown_endpoint="reject")
            codes = {v.code for v in raised.value.violations}
            paths = {v.path for v in raised.value.violations}
            assert codes == {"name_missing"}
            want = {
                f"elements.{m['id']}.{e['id']}.name"
                for m in json.loads(original)["modules"]
                for e in m["elements"]
                if e["kind"] in ("record", "field")
            }
            assert paths == want and len(want) == len(raised.value.violations)
        got = backend.register(alice, revised, parse_module(revised), unknown_endpoint="reject")
        assert got.changed is True and got.module == "catalog"
