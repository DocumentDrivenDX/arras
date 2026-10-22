# SPDX-License-Identifier: MIT OR Apache-2.0
from dataclasses import replace
from pathlib import Path

import pytest

from arras import Invalid
from arras.compat import check
from arras.model import ModuleInfo, PropertyInfo
from arras.umf import parse_module

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"


class Stats:
    def __init__(
        self, counts: dict[str, int] | None = None, missing: dict[str, list[str]] | None = None
    ) -> None:
        self.counts = counts or {}
        self.miss = missing or {}

    def count(self, type_name: str) -> int:
        return self.counts.get(type_name, 0)

    def missing(self, type_name: str, prop: str) -> list[str]:
        return self.miss.get(f"{type_name}.{prop}", [])


def base() -> ModuleInfo:
    return parse_module(EXAMPLE.read_bytes())


def with_props(m: ModuleInfo, tname: str, props: tuple[PropertyInfo, ...]) -> ModuleInfo:
    types = tuple(replace(t, properties=props) if t.name == tname else t for t in m.entity_types)
    return replace(m, entity_types=types)


def codes(old: ModuleInfo | None, new: ModuleInfo, stats: Stats) -> set[str]:
    with pytest.raises(Invalid) as e:
        check(old, new, stats)
    return {v.code for v in e.value.violations}


def test_first_registration_and_identity_are_accepted() -> None:
    check(None, base(), Stats())
    check(base(), base(), Stats({"catalog.Solution": 5}))


def test_adding_optional_property_is_accepted() -> None:
    old = base()
    sol = old.entity_type("Solution")
    assert sol is not None
    new = with_props(
        old, "catalog.Solution", (*sol.properties, PropertyInfo("note", "string", True, "optional"))
    )
    check(old, new, Stats({"catalog.Solution": 5}))


def test_adding_required_property_refused_only_with_records() -> None:
    old = base()
    sol = old.entity_type("Solution")
    assert sol is not None
    new = with_props(
        old, "catalog.Solution", (*sol.properties, PropertyInfo("n", "string", True, "one"))
    )
    check(old, new, Stats())
    assert codes(old, new, Stats({"catalog.Solution": 2})) == {"incompatible_change"}


def test_optional_to_required_lists_offenders() -> None:
    old = base()
    sol = old.entity_type("Solution")
    assert sol is not None
    props = tuple(
        PropertyInfo(p.name, p.type, p.scalar, "one") if p.name == "coverageLevel" else p
        for p in sol.properties
    )
    new = with_props(old, "catalog.Solution", props)
    check(old, new, Stats({"catalog.Solution": 2}))
    with pytest.raises(Invalid) as e:
        check(old, new, Stats({"catalog.Solution": 2}, {"catalog.Solution.coverageLevel": ["a"]}))
    assert "['a']" in e.value.violations[0].message


def test_type_cardinality_and_key_changes_refused() -> None:
    old = base()
    sol = old.entity_type("Solution")
    assert sol is not None
    props = tuple(
        PropertyInfo(p.name, "integer", p.scalar, p.cardinality) if p.name == "name" else p
        for p in sol.properties
    )
    assert codes(old, with_props(old, "catalog.Solution", props), Stats()) == {
        "incompatible_change"
    }
    props = tuple(
        PropertyInfo(p.name, p.type, p.scalar, "many") if p.name == "name" else p
        for p in sol.properties
    )
    assert codes(old, with_props(old, "catalog.Solution", props), Stats()) == {
        "incompatible_change"
    }
    new = replace(
        old,
        entity_types=tuple(
            replace(t, key="name") if t.name == "catalog.Solution" else t for t in old.entity_types
        ),
    )
    assert codes(old, new, Stats()) == {"incompatible_change"}


def test_removals() -> None:
    old = base()
    sol = old.entity_type("Solution")
    assert sol is not None
    new = with_props(
        old, "catalog.Solution", tuple(p for p in sol.properties if p.name != "coverageLevel")
    )
    check(old, new, Stats())
    assert codes(old, new, Stats({"catalog.Solution": 1})) == {"incompatible_change"}
    gone = replace(old, entity_types=(old.entity_types[0],), relationships=())
    check(old, gone, Stats())
    assert codes(old, gone, Stats({"catalog.Solution": 1})) == {"incompatible_change"}
    named = replace(old, entity_types=(old.entity_types[0],))
    assert codes(old, named, Stats()) == {"incompatible_change"}


def test_relationship_endpoints_widen_but_do_not_narrow() -> None:
    old = base()
    rel = old.relationships[0]
    wide = replace(old, relationships=(replace(rel, source=(*rel.source, "catalog.UseCase")),))
    check(old, wide, Stats({"catalog.Solution": 1}))
    narrow = replace(wide, relationships=(replace(rel, source=("catalog.UseCase",)),))
    check(wide, narrow, Stats())
    assert codes(wide, narrow, Stats({"catalog.Solution": 1})) == {"incompatible_change"}


def test_one_to_optional_and_other_cardinality_changes_are_refused() -> None:
    old = base()
    uc = old.entity_type("UseCase")
    assert uc is not None
    props = tuple(
        PropertyInfo(p.name, p.type, p.scalar, "optional") if p.name == "name" else p
        for p in uc.properties
    )
    assert codes(old, with_props(old, "catalog.UseCase", props), Stats()) == {"incompatible_change"}


def test_module_name_cannot_change() -> None:
    old = base()
    assert codes(old, replace(old, name="other"), Stats()) == {"incompatible_change"}
