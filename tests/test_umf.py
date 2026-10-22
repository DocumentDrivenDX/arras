# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
import json
from pathlib import Path
from typing import Any

import pytest

from arras import Invalid
from arras.model import UNPLACED
from arras.names import check_name
from arras.umf import parse_module

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"


def load() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def codes(doc: dict[str, Any]) -> set[str]:
    with pytest.raises(Invalid) as e:
        parse_module(json.dumps(doc))
    return {v.code for v in e.value.violations}


def test_example_document() -> None:
    m = parse_module(EXAMPLE.read_bytes())
    assert m.name == "catalog"
    assert m.placement == UNPLACED  # where a module lives is the host's, never the document's
    uc = m.entity_type("UseCase")
    assert uc is not None and uc.key == "code"
    sol = m.entity_type("Solution")
    assert sol is not None
    cov = sol.property("coverageLevel")
    assert cov is not None and not cov.required and cov.type == "string"
    rel = m.relationships[0]
    assert (rel.name, rel.inverse) == ("addresses", "addressedBy")
    assert rel.source == ("catalog.Solution",) and rel.target == ("catalog.UseCase",)


def test_not_json_and_wrong_version() -> None:
    with pytest.raises(Invalid):
        parse_module("{")
    doc = load()
    doc["umf"] = "0.6.0"
    assert codes(doc) == {"invalid_document"}


def test_exactly_one_module() -> None:
    doc = load()
    doc["modules"] = doc["modules"] * 2
    assert codes(doc) == {"invalid_document"}


def test_module_name() -> None:
    doc = load()
    doc["modules"][0]["id"] = "Bad-Name"
    assert "invalid_name" in codes(doc)


def test_a_document_carries_no_placement() -> None:
    doc = load()
    doc["vocabularies"]["arras.placement"] = {"version": "0.1.0"}
    doc["modules"][0]["extensions"]["arras.placement"] = {"record": "primary", "replicas": []}
    assert codes(doc) == {"invalid_document"}


def test_key_rules() -> None:
    doc = load()
    doc["modules"][0]["elements"][0]["keys"] = []
    assert codes(doc) == {"missing_key"}
    doc = load()
    doc["modules"][0]["elements"][0]["keys"][0]["fields"].append(
        {"module": "catalog", "element": "UseCase.name"}
    )
    assert codes(doc) == {"missing_key"}
    doc = load()
    doc["modules"][0]["elements"][1]["nullability"] = "absent-allowed"  # UseCase.code
    assert "missing_key" in codes(doc)


def test_unknown_local_endpoint_and_foreign_endpoint() -> None:
    doc = load()
    doc["modules"][0]["relationships"][0]["target"][0]["element"] = "Nope"
    assert codes(doc) == {"unknown_type"}
    doc = load()
    doc["modules"][0]["relationships"][0]["target"][0] = {"module": "other", "element": "Thing"}
    assert parse_module(json.dumps(doc)).relationships[0].target == ("other.Thing",)


def test_float_is_not_a_family() -> None:
    doc = load()
    doc["modules"][0]["elements"][0]["extensions"]["umf.ddd"]["fields"]["name"]["type"]["name"] = (
        "float"
    )
    assert codes(doc) == {"invalid_document"}


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("UseCase", True),
        ("_x", False),
        ("Query", False),
        ("key", False),
        ("1a", False),
        ("A" * 65, False),
        ("Foo-Bar", False),
    ],
)
def test_check_name(name: str, ok: bool) -> None:
    assert (check_name(name, "p") is None) is ok


def test_type_suffixes_and_case_collisions() -> None:
    assert check_name("SolutionPage", "p", entity_type=True) is not None
    assert check_name("SolutionList", "p", entity_type=True) is not None
    assert check_name("SolutionList", "p") is None
    doc = load()
    doc["modules"][0]["elements"][0]["extensions"]["umf.ddd"]["fields"]["Name"] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "optional",
    }
    assert "invalid_name" in codes(doc)


def mutate(f: Any) -> set[str]:
    doc = load()
    f(doc["modules"][0])
    return codes(doc)


def test_missing_ids_and_names_are_not_the_string_none() -> None:
    assert "invalid_document" in mutate(lambda m: m["relationships"][0].pop("name"))
    assert "invalid_document" in mutate(lambda m: m["relationships"][0]["target"][0].pop("module"))
    assert "invalid_document" in mutate(lambda m: m["elements"][0].pop("id"))


def test_key_must_be_this_records_own_field() -> None:
    def other_record(m: Any) -> None:
        m["elements"][0]["keys"][0]["fields"][0]["element"] = "Solution.code"

    def other_module(m: Any) -> None:
        m["elements"][0]["keys"][0]["fields"][0]["module"] = "other"

    assert codes_of(other_record) == {"missing_key"}
    assert codes_of(other_module) == {"missing_key"}


def codes_of(f: Any) -> set[str]:
    return mutate(f)


def test_relationship_names_share_a_namespace_with_properties_and_types() -> None:
    assert mutate(lambda m: m["relationships"][0].__setitem__("name", "name")) == {"invalid_name"}
    assert mutate(lambda m: m["relationships"][0].__setitem__("inverse", "code")) == {
        "invalid_name"
    }
    assert mutate(lambda m: m["relationships"][0].__setitem__("name", "Solution")) == {
        "invalid_name"
    }


def test_value_objects_are_read_and_checked() -> None:
    def add(m: Any) -> None:
        m["elements"].extend(
            [
                {
                    "id": "Money",
                    "kind": "record",
                    "members": [{"module": "catalog", "element": "Money.amount"}],
                    "extensions": {
                        "umf.ddd": {
                            "kind": "value-object",
                            "fields": {
                                "amount": {
                                    "type": {"kind": "scalar", "name": "decimal"},
                                    "cardinality": "one",
                                }
                            },
                        }
                    },
                },
                {
                    "id": "Money.amount",
                    "kind": "field",
                    "nullability": "required",
                    "cardinality": "one",
                    "scalarType": "decimal",
                    "extensions": {},
                },
            ]
        )
        sol = m["elements"][3]["extensions"]["umf.ddd"]["fields"]
        sol["price"] = {"type": {"kind": "record", "name": "Money"}, "cardinality": "optional"}
        m["elements"][3]["members"].append({"module": "catalog", "element": "Solution.price"})
        m["elements"].append(
            {
                "id": "Solution.price",
                "kind": "field",
                "nullability": "absent-allowed",
                "cardinality": "one",
                "extensions": {},
            }
        )

    doc = load()
    add(doc["modules"][0])
    info = parse_module(json.dumps(doc))
    assert [v.name for v in info.value_types] == ["catalog.Money"]
    sol = info.entity_type("Solution")
    assert sol is not None and (p := sol.property("price")) is not None and not p.scalar
    # a structured property must name a value object, never an entity or an undefined record
    doc["modules"][0]["elements"][3]["extensions"]["umf.ddd"]["fields"]["price"]["type"]["name"] = (
        "UseCase"
    )
    with pytest.raises(Invalid):
        parse_module(json.dumps(doc))


def test_unknown_constructs_are_refused() -> None:
    assert mutate(lambda m: m.__setitem__("events", [])) == {"invalid_document"}
    assert mutate(lambda m: m["elements"].append({"id": "E", "kind": "enum"})) == {
        "invalid_document"
    }
    assert "invalid_document" in mutate(lambda m: m["elements"][0]["extensions"].pop("umf.ddd"))
    assert mutate(lambda m: m["extensions"].__setitem__("x.y", {})) == {"invalid_document"}
    doc = load()
    doc["vocabularies"]["x.y"] = {"version": "1"}
    assert codes(doc) == {"invalid_document"}


@pytest.mark.parametrize("declaration", [None, [], {}, {"version": "0.2.0"}, {"version": 1}])
def test_declared_ddd_vocabulary_requires_supported_version(declaration: Any) -> None:
    doc = load()
    doc["vocabularies"]["umf.ddd"] = declaration
    with pytest.raises(Invalid) as e:
        parse_module(json.dumps(doc))
    assert any(
        v.path == "vocabularies.umf.ddd.version" and v.code == "invalid_document"
        for v in e.value.violations
    )


def test_ddd_extensions_without_vocabulary_declaration_keep_existing_behavior() -> None:
    doc = load()
    doc["vocabularies"].pop("umf.ddd")
    assert parse_module(json.dumps(doc)).name == "catalog"


def test_actions_are_refused_until_they_are_read() -> None:
    assert mutate(lambda m: m.__setitem__("actions", [{"id": "A"}])) == {"invalid_document"}


def test_duplicates_are_refused() -> None:
    text = EXAMPLE.read_text().replace('"id": "catalog",', '"id": "catalog", "id": "x",', 1)
    with pytest.raises(Invalid):
        parse_module(text)
    assert mutate(lambda m: m["elements"].append(dict(m["elements"][1]))) == {"invalid_document"}


def test_forms_must_agree() -> None:
    cov = lambda m: m["elements"][-1].__setitem__("nullability", "required")  # noqa: E731
    assert mutate(cov) == {"invalid_document"}
    assert mutate(lambda m: m["elements"][1].__setitem__("scalarType", "integer")) == {
        "invalid_document"
    }
    ghost = {"type": {"kind": "scalar", "name": "string"}, "cardinality": "optional"}
    assert mutate(
        lambda m: m["elements"][0]["extensions"]["umf.ddd"]["fields"].__setitem__("ghost", ghost)
    ) == {"invalid_document"}


def test_relationship_shape() -> None:
    assert mutate(lambda m: m["relationships"][0].pop("sourceMultiplicity")) == {"invalid_document"}
    assert mutate(
        lambda m: m["relationships"][0].__setitem__("targetMultiplicity", {"min": 2, "max": 1})
    ) == {"invalid_document"}
    m = parse_module(EXAMPLE.read_bytes()).relationships[0]
    assert str(m.source_multiplicity) == "0..*"


def test_every_violation_is_reported_together() -> None:
    doc = load()
    doc["modules"][0]["elements"][0]["keys"] = []
    doc["modules"][0]["relationships"][0]["name"] = "Query"
    doc["modules"][0]["extensions"]["arras.placement"] = {"record": "primary"}
    assert codes(doc) == {"missing_key", "invalid_name", "invalid_document"}


def test_hashable_and_capabilities_do_not_take_part_in_equality() -> None:
    a = parse_module(EXAMPLE.read_bytes())
    assert hash(a) == hash(parse_module(EXAMPLE.read_bytes()))


ACTION = {
    "id": "CorrectSolution",
    "description": "Correct a solution's coverage",
    "inputs": [
        {"name": "solution", "type": {"kind": "ref", "type": "Solution"}},
        {"name": "level", "type": {"kind": "scalar", "name": "string"}},
    ],
    "preconditions": [
        {
            "id": "exists",
            "reason": "no such solution",
            "predicate": {"op": "exists", "ref": {"input": "solution"}},
        }
    ],
    "effects": [
        {
            "op": "update",
            "refType": "Solution",
            "key": {"input": "solution"},
            "properties": {"coverageLevel": {"input": "level"}},
        }
    ],
}


def with_action(f: Any = None) -> set[str]:
    def add(m: Any) -> None:
        a = json.loads(json.dumps(ACTION))
        if f is not None:
            f(a)
        m["actions"] = [a]

    return mutate(add) if f is not None else set()


def test_action_is_read_and_checked() -> None:
    doc = load()
    doc["modules"][0]["actions"] = [ACTION]
    info = parse_module(json.dumps(doc))
    [a] = info.actions
    assert a.name == "catalog.CorrectSolution" and a.inputs[0].kind == "ref"


def test_bad_declarations() -> None:
    def bad_prop(a: Any) -> None:
        a["effects"][0]["properties"]["nope"] = {"literal": 1}

    def bad_key(a: Any) -> None:
        a["effects"][0]["properties"]["code"] = {"literal": "x"}

    def bad_input(a: Any) -> None:
        a["effects"][0]["key"] = {"input": "ghost"}

    def bad_alias(a: Any) -> None:
        a["effects"][0]["key"] = {"alias": "later"}

    def bad_type(a: Any) -> None:
        a["effects"][0]["refType"] = "Nope"

    def bad_rel(a: Any) -> None:
        a["effects"] = [
            {
                "op": "link",
                "type": "nope",
                "source": {"input": "solution"},
                "target": {"input": "solution"},
            }
        ]

    def no_effects(a: Any) -> None:
        a["effects"] = []

    def bad_foreach(a: Any) -> None:
        a["effects"] = [{"op": "foreach", "over": "level", "body": []}]

    def bad_create(a: Any) -> None:
        a["effects"] = [
            {"op": "create", "type": "Solution", "key": {"generate": "uuid"}, "properties": {}}
        ]

    for f in (
        bad_prop,
        bad_key,
        bad_input,
        bad_alias,
        bad_type,
        bad_rel,
        no_effects,
        bad_foreach,
        bad_create,
    ):
        assert with_action(f), f.__name__
    assert with_action(bad_create) == {"missing_required"}
