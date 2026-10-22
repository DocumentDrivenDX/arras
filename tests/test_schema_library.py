# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A person's validate and register of a UMF document (CONTRACT-002, ADR-026).

The backend's `schema` grant decides, asked before the host's placement is mentioned; a plan says
what registering then does; nothing is applied by a plan."""

import json
from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from arras import Conflict, Invalid, Refused, Unsupported
from arras.fakes import MemoryStore
from arras.testing import InMemory, example_module

DOC = example_module()


def with_property(text: str, name: str, *, required: bool, type_: str = "UseCase") -> str:
    """The document with one more property on a type; a required one is set by the actions that
    create the type, or the document would not be valid."""
    d = json.loads(text)
    els = d["modules"][0]["elements"]
    rec = next(e for e in els if e["id"] == type_)
    rec["members"].append({"module": "catalog", "element": f"{type_}.{name}"})
    rec["extensions"]["umf.ddd"]["fields"][name] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "one" if required else "optional",
    }
    els.append(
        {
            "id": f"{type_}.{name}",
            "kind": "field",
            "nullability": "required" if required else "absent-allowed",
            "cardinality": "one",
            "scalarType": "string",
            "extensions": {},
        }
    )
    if required:
        for a in d["modules"][0]["actions"]:
            for e in a["effects"]:
                if e.get("op") == "create" and e.get("type") == type_:
                    e["properties"][name] = {"literal": "n/a"}
    return json.dumps(d)


@pytest.fixture
def world() -> InMemory:
    w = InMemory()
    w.register(DOC)
    return w


def author(w: InMemory, name: str = "ana"):
    return w.arras.session(w.person(name, "catalog", "read", "schema"))


def test_a_plan_names_what_registering_adds_and_applies_nothing(world: InMemory) -> None:
    o = author(world)
    before = o.document("catalog")
    plan = o.schema().validate(with_property(DOC, "notes", required=False))
    assert plan.ok and plan.changed and plan.module == "catalog" and not plan.violations
    reader = world.arras.session(world.person("jo", "catalog", "read", "journal"))
    rows = len(reader.changes(module="catalog").items)
    o.schema().validate(with_property(DOC, "more", required=False))
    assert len(reader.changes(module="catalog").items) == rows  # a dry run writes no journal row
    assert [(c.kind, c.element, c.name) for c in plan.changes] == [
        ("added", "property", "catalog.UseCase.notes")
    ]
    assert plan.revision == before.revision
    after = o.document("catalog")
    assert (after.text, after.revision) == (before.text, before.revision)


def test_a_plan_for_the_document_in_force_says_nothing_would_change(world: InMemory) -> None:
    plan = author(world).schema().validate(DOC)
    assert plan.ok and not plan.changed and plan.changes == ()


def test_an_incompatible_change_is_an_answer_naming_the_rule(world: InMemory) -> None:
    o = author(world)
    admin = world.arras.session(world.admin)
    admin.import_records(
        "catalog",
        [
            {"type": "UseCase", "key": f"uc-{i}", "properties": {"name": "Pipelines"}}
            for i in range(40)
        ],
        load_id="l1",
    )
    plan = o.schema().validate(with_property(DOC, "notes", required=True))
    assert not plan.ok
    assert any("40 records" in v.message for v in plan.violations)  # the count is named
    assert {v.code for v in plan.violations} == {"incompatible_change"}
    with pytest.raises(Invalid) as e:
        o.schema().register(with_property(DOC, "notes", required=True))
    assert tuple(e.value.violations) == plan.violations


def test_register_makes_a_revision_the_person_originated(world: InMemory) -> None:
    o = author(world)
    plan = o.schema().validate(with_property(DOC, "notes", required=False))
    result = o.schema().register(
        with_property(DOC, "notes", required=False), expected_revision=plan.revision
    )
    assert result.changed and result.revision != plan.revision
    assert "notes" in o.document("catalog").text
    assert (
        cast(MemoryStore, world.backends["memory"]).origin_actor["catalog"] == "ana"
    )  # the revision's origin actor
    again = o.schema().validate(with_property(DOC, "notes", required=False))
    assert not again.changed and again.revision == result.revision


def test_a_stale_expected_revision_applies_nothing(world: InMemory) -> None:
    o = author(world)
    stale = o.schema().validate(DOC).revision
    o.schema().register(with_property(DOC, "notes", required=False))
    with pytest.raises(Conflict) as e:
        o.schema().register(with_property(DOC, "more", required=False), expected_revision=stale)
    assert e.value.reason == "revision"
    assert "more" not in o.document("catalog").text


def test_a_wire_revision_is_read_as_a_revision(world: InMemory) -> None:
    o = author(world)
    current = o.document("catalog").revision
    wire = {k: v for k, v in current.by_backend.items()}
    assert o.schema().register(DOC, expected_revision=wire).changed is False
    with pytest.raises(Invalid):
        o.schema().register(DOC, expected_revision={"memory": object()})


def test_write_without_schema_is_refused_before_the_host_is_described(world: InMemory) -> None:
    writer = world.arras.session(world.person("bob", "catalog", "read", "write"))
    for call in (writer.schema().validate, writer.schema().register):
        with pytest.raises(Refused):
            call(DOC)
        with pytest.raises(Refused):  # a module the host placed nowhere is asked of the grant too
            call(DOC.replace('"catalog"', '"unplaced"'))


def test_the_administrative_principal_is_refused(world: InMemory) -> None:
    admin = world.arras.session(world.admin)
    with pytest.raises(Refused):
        admin.schema().validate(DOC)
    with pytest.raises(Refused):
        admin.schema().register(DOC)


def test_no_token_is_refused_before_anything(world: InMemory) -> None:
    from arras import Principal

    gone = world.arras.session(Principal("ana", ""))
    with pytest.raises(Refused) as e:
        gone.schema().validate(DOC)
    assert e.value.reason == "token_expired"


def test_a_document_that_does_not_parse_or_is_not_placed_is_invalid(world: InMemory) -> None:
    o = author(world)
    with pytest.raises(Invalid):
        o.schema().validate("{")
    host = InMemory()
    host.register(DOC)
    o2 = host.arras.session(host.person("ana", "*", "read", "schema"))
    other = o2.schema().validate(
        DOC.replace('"catalog"', '"ledger"'), unknown_endpoint="provisional"
    )
    assert other.ok and other.module == "ledger" and other.revision is None  # a new module


def test_an_unplaced_module_is_refused_when_the_host_places_nothing_for_it() -> None:
    w = InMemory()
    w.register(DOC)
    from arras import Arras

    strict = Arras.start(w.backends, admin=w.admin)  # no default placement
    ana = w.person("ana", "*", "schema")
    with pytest.raises(Invalid) as e:
        strict.session(ana).schema().validate(DOC)
    assert e.value.violations[0].code == "invalid_placement"


def test_a_provider_without_a_dry_run_is_unsupported(world: InMemory, monkeypatch) -> None:
    o = author(world)
    monkeypatch.setattr(world.backends["memory"], "validate_register", None)  # a provider without
    with pytest.raises(Unsupported):
        o.schema().validate(DOC)


@settings(max_examples=40, deadline=None)
@given(required=st.booleans(), records=st.booleans(), name=st.sampled_from(["notes", "tag", "x1"]))
def test_a_plan_equals_what_registering_then_does(required: bool, records: bool, name: str) -> None:
    w = InMemory()
    w.register(DOC)
    if records:
        w.import_records(
            "catalog", [{"type": "UseCase", "key": "uc-1", "properties": {"name": "L"}}]
        )
    o = author(w)
    text = with_property(DOC, name, required=required)
    plan = o.schema().validate(text)
    if plan.ok:
        result = o.schema().register(text, expected_revision=plan.revision)
        assert result.changed == plan.changed
    else:
        with pytest.raises(Invalid) as e:
            o.schema().register(text)
        assert {v.code for v in e.value.violations} == {v.code for v in plan.violations}
    assert plan.ok == (not (required and records))


def test_the_replica_learns_of_it_through_its_feed(world: InMemory) -> None:
    o = author(world)
    o.schema().register(with_property(DOC, "notes", required=False))
    world.sync()
    carol = world.arras.session(world.person("carol", "catalog", "read"))
    assert any(
        p.name == "notes"
        for m in carol.describe("catalog")
        for t in m.entity_types
        if t.name.endswith("UseCase")
        for p in t.properties
    )
