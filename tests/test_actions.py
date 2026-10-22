# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from arras import Invalid
from arras.actioncheck import check_action
from arras.actions import (
    MAX_EFFECTS,
    ActionInfo,
    AliasKey,
    Create,
    EffectDecl,
    Generate,
    Input,
    InputSpec,
    Item,
    Link,
    Literal_,
    PreconditionDecl,
    Ref,
    Unlink,
    Update,
    resolve,
)
from arras.umf import parse_module

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
MODULE = parse_module(EXAMPLE.read_bytes())


def action(inputs=(), effects=(), pre=()) -> ActionInfo:
    return ActionInfo("catalog.A", "", tuple(inputs), tuple(pre), tuple(effects))


def problems(a: ActionInfo) -> list[str]:
    return [v.message for v in check_action(a, MODULE)]


def sound(a: ActionInfo) -> ActionInfo:
    assert problems(a) == []
    return a


CREATE = sound(
    ActionInfo(
        name="catalog.CreateCandidate",
        description="",
        inputs=(
            InputSpec("useCase", "UseCase", "ref", "one"),
            InputSpec("label", "string", "scalar", "one"),
        ),
        preconditions=(
            PreconditionDecl("uc_exists", "no such use case", "exists", {"ref": Input("useCase")}),
        ),
        effects=(
            EffectDecl(
                "create",
                alias="s",
                type="Solution",
                key=Generate(),
                properties={"name": Input("label"), "coverageLevel": Literal_("candidate")},
            ),
            EffectDecl("link", type="addresses", source=AliasKey("s"), target=Input("useCase")),
        ),
    )
)


def keys(n: int):
    it = iter(f"k{i}" for i in range(n))
    return lambda: next(it)


def test_resolves_effects_in_order_with_aliases_and_generated_keys() -> None:
    plan = resolve(CREATE, {"useCase": "uc-1", "label": "x"}, MODULE, new_key=keys(1))
    create, link = plan.effects
    assert create == Create(
        Ref("catalog.Solution", "k0"), {"name": "x", "coverageLevel": "candidate"}, True
    )
    assert isinstance(link, Link) and link.source == Ref("catalog.Solution", "k0")
    assert link.source.generated and not link.target.generated
    assert link.target == Ref("catalog.UseCase", "uc-1")
    assert plan.preconditions[0].args["ref"] == Ref("catalog.UseCase", "uc-1")


def test_all_input_violations_are_reported() -> None:
    with pytest.raises(Invalid) as e:
        resolve(CREATE, {"label": 3, "extra": 1, "useCase": "bad key!"}, MODULE)
    assert {(v.path, v.code) for v in e.value.violations} == {
        ("inputs.extra", "unknown_input"),
        ("inputs.label", "type"),
        ("inputs.useCase", "key"),
    }
    with pytest.raises(Invalid) as e:
        resolve(CREATE, {}, MODULE)
    assert {v.code for v in e.value.violations} == {"required"}


FOREACH = sound(
    action(
        inputs=(
            InputSpec("solutions", "Solution", "ref", "many"),
            InputSpec("useCase", "UseCase", "ref", "one"),
            InputSpec("level", "string", "scalar", "one"),
        ),
        effects=(
            EffectDecl(
                "foreach",
                over="solutions",
                body=(
                    EffectDecl(
                        "update",
                        ref_type="Solution",
                        key=Item(),
                        properties={"coverageLevel": Input("level")},
                    ),
                    EffectDecl("unlink", type="addresses", source=Item(), target=Input("useCase")),
                ),
            ),
        ),
    )
)


def test_foreach_repeats_effects_per_item() -> None:
    plan = resolve(FOREACH, {"solutions": ["a", "b"], "useCase": "u", "level": "full"}, MODULE)
    assert [type(e) for e in plan.effects] == [Update, Unlink] * 2
    assert plan.effects[2] == Update(Ref("catalog.Solution", "b"), {"coverageLevel": "full"})
    assert plan.effects[3] == Unlink(
        "addresses", Ref("catalog.Solution", "b"), Ref("catalog.UseCase", "u")
    )


def test_effect_bound_is_checked_before_expanding() -> None:
    a = sound(
        action(
            (InputSpec("xs", "string", "scalar", "many"),),
            (
                EffectDecl(
                    "foreach",
                    over="xs",
                    body=(
                        EffectDecl(
                            "create", type="UseCase", key=Item(), properties={"name": Literal_("n")}
                        ),
                    ),
                ),
            ),
        )
    )
    resolve(a, {"xs": [str(i) for i in range(MAX_EFFECTS)]}, MODULE)
    calls: list[int] = []

    def make_key() -> str:
        calls.append(1)
        return "k"

    for n in (MAX_EFFECTS + 1, 2_000_000):
        with pytest.raises(Invalid) as e:
            resolve(a, {"xs": [str(i) for i in range(n)]}, MODULE, new_key=make_key)
        assert e.value.violations[0].code == "bound" and not calls


def test_scalar_families_and_lists() -> None:
    def one(family: str, value: object, card: Any = "one"):
        a = action((InputSpec("x", family, "scalar", card),))
        return resolve(a, {"x": value}, MODULE)

    one("integer", 3)
    one("decimal", Decimal("1.5"))
    one("decimal", 2)
    one("boolean", True)
    one("string", ["a", "b"], "many")
    from datetime import UTC, datetime

    one("timestamp", datetime(2026, 1, 1, tzinfo=UTC))
    for family, bad in [
        ("integer", True),
        ("integer", "3"),
        ("boolean", 1),
        ("timestamp", "now"),
        ("timestamp", datetime(2026, 1, 1)),
        ("string", ["a"]),
        ("decimal", Decimal("NaN")),
        ("decimal", Decimal("Infinity")),
    ]:
        with pytest.raises(Invalid):
            one(family, bad)
    with pytest.raises(Invalid):
        one("string", "a", "many")
    with pytest.raises(Invalid):
        one("string", ["a"] * 1001, "many")


def test_absent_optional_values_stay_absent() -> None:
    a = sound(
        action(
            (
                InputSpec("code", "string", "scalar", "one"),
                InputSpec("cov", "string", "scalar", "optional"),
            ),
            (
                EffectDecl(
                    "create",
                    type="Solution",
                    key=Input("code"),
                    properties={"name": Literal_("n"), "coverageLevel": Input("cov")},
                ),
            ),
        )
    )
    [c] = resolve(a, {"code": "s1"}, MODULE).effects
    assert isinstance(c, Create) and c.properties == {"name": "n"}


def test_computed_keys_are_checked() -> None:
    a = sound(
        action(
            (InputSpec("xs", "string", "scalar", "many"),),
            (
                EffectDecl(
                    "foreach",
                    over="xs",
                    body=(
                        EffectDecl(
                            "create", type="UseCase", key=Item(), properties={"name": Literal_("n")}
                        ),
                    ),
                ),
            ),
        )
    )
    with pytest.raises(Invalid) as e:
        resolve(a, {"xs": ["ok", "bad key!", "x" * 240]}, MODULE)
    assert {v.path for v in e.value.violations} == {
        "effects[0].each[1].body[0].key",
        "effects[0].each[2].body[0].key",
    }
    assert {v.code for v in e.value.violations} == {"key"}


def test_alias_inside_foreach_cannot_shadow() -> None:
    body = EffectDecl(
        "create", alias="s", type="UseCase", key=Generate(), properties={"name": Literal_("n")}
    )
    a = action(
        (InputSpec("xs", "string", "scalar", "many"),),
        (body, EffectDecl("foreach", over="xs", body=(body,))),
    )
    assert any("declared twice" in m for m in problems(a))


def test_inverse_relationship_is_normalised() -> None:
    a = sound(
        action(
            (InputSpec("s", "Solution", "ref", "one"), InputSpec("u", "UseCase", "ref", "one")),
            (EffectDecl("link", type="addressedBy", source=Input("u"), target=Input("s")),),
        )
    )
    [e] = resolve(a, {"s": "s1", "u": "u1"}, MODULE).effects
    assert e == Link("addresses", Ref("catalog.Solution", "s1"), Ref("catalog.UseCase", "u1"))


def test_preconditions_are_resolved_and_checked() -> None:
    ins = (InputSpec("s", "Solution", "ref", "one"), InputSpec("n", "string", "scalar", "one"))
    eff = (EffectDecl("delete", ref_type="Solution", key=Input("s")),)
    pre = (
        PreconditionDecl("a", "r", "absent", {"type": "UseCase", "key": Input("n")}),
        PreconditionDecl(
            "b",
            "r",
            "property_equals",
            {"ref": Input("s"), "property": "name", "value": Literal_("x")},
        ),
        PreconditionDecl(
            "c", "r", "no_relationship", {"relationship": "addresses", "source": Input("s")}
        ),
        PreconditionDecl(
            "d",
            "r",
            "count",
            {"relationship": "addresses", "source": Input("s"), "cmp": ">=", "n": 1},
        ),
    )
    plan = resolve(sound(action(ins, eff, pre)), {"s": "s1", "n": "u9"}, MODULE)
    by = {p.id: p.args for p in plan.preconditions}
    assert by["a"] == {"type": "catalog.UseCase", "key": "u9"}
    assert by["b"]["ref"] == Ref("catalog.Solution", "s1") and by["b"]["value"] == "x"
    assert by["d"]["cmp"] == ">=" and by["d"]["n"] == 1
    bad = [
        PreconditionDecl("a", "r", "exists", {}),
        PreconditionDecl("a", "r", "exists", {"ref": Input("s")}),  # duplicate id
        PreconditionDecl(
            "e",
            "r",
            "count",
            {"relationship": "addresses", "source": Input("s"), "cmp": "~", "n": 1},
        ),
        PreconditionDecl("f", "r", "exists", {"ref": Input("ghost")}),
        PreconditionDecl(
            "g",
            "r",
            "property_equals",
            {"ref": Input("s"), "property": "nope", "value": Literal_(1)},
        ),
        PreconditionDecl(
            "h", "r", "no_relationship", {"relationship": "nope", "source": Input("s")}
        ),
        PreconditionDecl("i", "r", "exists", {"ref": Literal_("x")}),
    ]
    for p in bad:
        assert problems(action(ins, eff, (p,))) or p.id == "a", p


@pytest.mark.parametrize(
    "decl",
    [
        EffectDecl("create", type="UseCase", properties={"name": Literal_("n")}),  # no key
        EffectDecl("update", key=Input("s")),  # no refType
        EffectDecl("delete", ref_type="Solution"),  # no key
        EffectDecl("link", type="addresses", source=Literal_("x"), target=Input("u")),
        EffectDecl("link", type="addresses", source=Generate(), target=Input("u")),
        EffectDecl("link", type="addresses", source=Input("u"), target=Input("u")),  # wrong types
        EffectDecl(
            "link",
            type="addresses",
            source=Input("s"),
            target=Input("u"),
            properties={"x": Literal_(1)},
        ),
        EffectDecl("update", ref_type="Solution", key=Input("s"), unset=("name",)),  # required
        EffectDecl(
            "update", ref_type="Solution", key=Input("s"), properties={"code": Literal_("x")}
        ),
        EffectDecl(
            "update",
            ref_type="Solution",
            key=Input("s"),
            properties={"name": Input("n")},
            unset=("name",),
        ),
        EffectDecl(
            "update", ref_type="Solution", key=Input("s"), properties={"name": Input("i")}
        ),  # int to string
        EffectDecl("update", ref_type="Solution", key=Input("s"), properties={"name": Generate()}),
        EffectDecl(
            "update", ref_type="Solution", key=Input("opt"), properties={"name": Literal_("x")}
        ),
        EffectDecl("update", ref_type="Solution", key=Input("xs")),  # a list outside foreach
        EffectDecl("update", ref_type="Solution", key=Item()),  # item outside foreach
        EffectDecl(
            "create", type="Solution", key=Input("opt_str"), properties={"name": Literal_("n")}
        ),
        EffectDecl(
            "create", type="Solution", key=Generate(), properties={"name": Input("opt_str")}
        ),
        EffectDecl("foreach", over="s", body=()),  # not a list
        EffectDecl("foreach", over="xs", body=(EffectDecl("foreach", over="xs", body=()),)),
        EffectDecl(
            "foreach",
            over="xs",
            body=(EffectDecl("update", ref_type="Solution", key=Item("code")),),
        ),
        EffectDecl("delete", ref_type="Solution", key=Input("s"), unset=("name",)),
    ],
)
def test_declarations_that_would_misbehave_are_refused(decl: EffectDecl) -> None:
    ins = (
        InputSpec("s", "Solution", "ref", "one"),
        InputSpec("u", "UseCase", "ref", "one"),
        InputSpec("n", "string", "scalar", "one"),
        InputSpec("i", "integer", "scalar", "one"),
        InputSpec("opt", "Solution", "ref", "optional"),
        InputSpec("opt_str", "string", "scalar", "optional"),
        InputSpec("xs", "string", "scalar", "many"),
    )
    assert problems(action(ins, (decl,))), decl


def test_parse_is_robust_to_malformed_declarations() -> None:
    doc = json.loads(EXAMPLE.read_text())
    cases = [
        {"id": "A", "effects": [{"op": "create", "type": ["a"]}]},
        {"id": "A", "effects": [{"op": "foreach", "over": {"x": 1}}]},
        {"id": "A", "handler": 5},
        {"id": "A", "effects": [{"op": "delete", "refType": "Solution", "key": {"input": 5}}]},
        {"id": "A", "effects": [{"op": "delete", "refType": "Solution", "key": {"item": False}}]},
        {"id": "A", "effects": [{"op": "update", "unset": [1]}]},
        {"id": "A", "inputs": [{"name": 3, "type": {"kind": "scalar", "name": "string"}}]},
        {"id": "A", "preconditions": [{"id": "p", "predicate": {"op": "count", "n": [1]}}]},
    ]
    for c in cases:
        doc["modules"][0]["actions"] = [c]
        with pytest.raises(Invalid):
            parse_module(json.dumps(doc))


def test_every_checked_declaration_resolves() -> None:
    # a checked declaration never crashes the resolver for inputs that are themselves valid
    for a, inputs in (
        (CREATE, {"useCase": "u", "label": "x"}),
        (FOREACH, {"solutions": [], "useCase": "u", "level": "l"}),
        (FOREACH, {"solutions": ["a"], "useCase": "u", "level": "l"}),
    ):
        assert resolve(a, inputs, MODULE).action == a.name
