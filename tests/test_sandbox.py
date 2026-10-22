# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The sandbox the dev host serves: a developer's own module, and what the people hold on it."""

import json
from pathlib import Path
from typing import Any

import pytest

from arras.devhost import build
from arras.errors import Invalid, Refused
from arras.sandbox import Sandbox, catalog_document, read_steps
from arras.serialize import jsonable

EXAMPLE = Path(__file__).parent.parent / "examples" / "catalog"


def test_jsonable_handles_the_interface_types() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    out = jsonable(
        {"d": Decimal("1.50"), "t": datetime(2026, 1, 1, tzinfo=UTC), "s": {1, 2}, "b": b"\x01"}
    )
    assert out["d"] == "1.50" and out["t"].startswith("2026-01-01") and out["b"] == "AQ=="
    json.dumps(out)


def test_a_developers_own_module_takes_the_sandboxs_place() -> None:
    box = build(EXAMPLE / "catalog.umf.json", EXAMPLE / "seed.json")
    carol = box.arras.session(box.people["carol"])
    [m] = carol.describe()
    assert {t.name for t in m.entity_types} == {
        "catalog.UseCase",
        "catalog.Solution",
        "catalog.Product",
        "catalog.CoverageAssertion",
        "catalog.ProductVersion",
        "catalog.Finding",
    }

    keys = {
        "UseCase": ("addressedBy", "coveredBy"),
        "CoverageAssertion": ("ofProduct",),
        "Solution": ("providedBy",),
        "Product": ("provides",),
    }

    def one(type_name: str, code: str) -> Any:
        cols = "".join(f", RELATED_KEYS(x.{r}, 100) AS {r}" for r in keys.get(type_name, ()))
        sql = (
            f"SELECT x.*{cols} FROM catalog.{type_name} x WHERE x.code = :k ORDER BY x.code LIMIT 1"
        )
        return carol.query("catalog", sql, {"k": code}).rows[0]

    rows = carol.query(
        "catalog", "SELECT s.* FROM catalog.Solution s ORDER BY s.code LIMIT 100"
    ).rows
    assert {r["deliveryMode"] for r in rows} == {"chat", "handoff", "app"} and len(rows) == 9
    alerts = one("UseCase", "triage-incident-alerts")
    assert alerts["addressedBy"] == ["alert-triage-playbook", "lumen-triage-prompt"]
    covered = {
        one("CoverageAssertion", c)["ofProduct"][0]: one("CoverageAssertion", c)["level"]
        for c in alerts["coveredBy"]
    }
    assert covered == {"pylon": "full", "beacon": "partial"}
    assert one("Solution", "lumen-triage-prompt")["providedBy"] == ["lumen"]
    assert one("Product", "lumen")["provides"] == [
        "lumen-runbook-prompt",
        "lumen-triage-prompt",
    ]


def test_people_hold_on_a_renamed_module_what_they_hold_on_catalog() -> None:
    document = catalog_document().replace('"catalog"', '"inventory"')
    box = Sandbox().load(document, [("inventory.AddUseCase", {"code": "uc-1", "name": "One"})])
    carol = box.arras.session(box.people["carol"])
    assert [
        r["code"]
        for r in carol.query(
            "inventory", "SELECT u.* FROM inventory.UseCase u ORDER BY u.code LIMIT 100"
        ).rows
    ] == ["uc-1"]
    with pytest.raises(Refused):
        carol.invoke("inventory.AddUseCase", {"code": "uc-2", "name": "Two"})
    assert box.arras.session(box.people["dave"]).describe() == []


def test_a_refused_module_and_a_misshapen_seed_say_why(tmp_path: Path) -> None:
    bad = tmp_path / "bad.umf.json"
    bad.write_text(catalog_document().replace('"0.10.0"', '"0.9.0"'), encoding="utf-8")
    with pytest.raises(Invalid) as refused:
        build(bad, None)
    assert [v.path for v in refused.value.violations] == ["umf"]
    seed = tmp_path / "seed.json"
    for text, why in (('{"action": "x"}', "JSON list"), ('[{"inputs": {}}]', "step 0")):
        seed.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=why):
            read_steps(seed)


def test_the_demo_catalog_is_richer_than_the_sandbox_and_a_module_replaces_it() -> None:
    plain, demo = build(None, None), build(None, None, demo=True)

    def count(box: Sandbox) -> int:
        return len(
            box.arras.session(box.people["alice"])
            .query("catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
            .rows
        )

    assert count(demo) > count(plain)
