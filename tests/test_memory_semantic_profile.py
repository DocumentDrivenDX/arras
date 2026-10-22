# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Whole-module refusal for declarations the memory writer does not enforce."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from arras import Principal, Refused, Unsupported
from arras.actions import Create, Plan, Ref
from arras.fakes import FakeAccess, MemoryStore
from arras.umf import parse_module

SOURCE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
ORIGINAL = SOURCE.read_bytes()
MODULE = parse_module(ORIGINAL)


def world() -> tuple[MemoryStore, Principal, Principal]:
    access = FakeAccess()
    store = MemoryStore(access, "profile")
    writer = access.grant("writer", "catalog", "read", "write", "schema", admin=True)
    reader = access.grant("reader", "catalog", "read")
    store.register(writer, ORIGINAL, MODULE, unknown_endpoint="reject")
    return store, writer, reader


def create(name: str = "in-bound") -> Plan:
    return Plan(
        "catalog.CreateUseCase",
        (),
        (Create(Ref("catalog.UseCase", name), {"name": "A name"}),),
    )


def plain_original() -> dict[str, Any]:
    """A consciously plain test derivative of the catalog source; retain all non-length slots."""
    raw = json.loads(ORIGINAL)
    for element in raw["modules"][0]["elements"]:
        facets = element.get("facets")
        if isinstance(facets, dict) and set(facets) == {"length"}:
            element.pop("facets")
    return raw


def snapshot(store: MemoryStore, principal: Principal) -> tuple[Any, ...]:
    return (
        copy.deepcopy(store.state),
        copy.deepcopy(store._journal),
        store.position(),
        store.document(principal, "catalog").text,
        store.catalog_revision,
    )


@pytest.mark.parametrize("candidate", ["Within the declared limit", "x" * 201])
def test_original_catalog_refuses_all_writes_without_effects(candidate: str) -> None:
    store, writer, _ = world()
    assert store.documents["catalog"] == ORIGINAL
    assert store.document(writer, "catalog").text.encode() == ORIGINAL
    # The operation's value is immaterial: the writer does not implement the declared length facet.
    plan = Plan(
        "catalog.CreateUseCase",
        (),
        (Create(Ref("catalog.UseCase", "case"), {"name": candidate}),),
    )
    before = snapshot(store, writer)
    with pytest.raises(Unsupported, match="writes to catalog") as err:
        store.apply(writer, plan, idempotency_key=None)
    assert any("UseCase.name.facets" in reason for reason in err.value.supported)
    assert snapshot(store, writer) == before


def test_profile_refusal_precedes_dry_run_replay_and_batches() -> None:
    store, writer, _ = world()
    plan = create()
    key = "cached"
    # Plant a matching key to prove the profile guard precedes the replay shortcut.
    digest = store._digest([plan])
    store._journal[(plan.action, key)] = (digest, {"sentinel": True})
    before = snapshot(store, writer)
    for call in (
        lambda: store.apply(writer, plan, idempotency_key=key),
        lambda: store.apply(writer, plan, idempotency_key=None, dry_run=True),
        lambda: store.apply_batch(writer, [plan, plan], atomic=True, idempotency_key="batch"),
        lambda: store.apply_batch(writer, [plan, plan], atomic=False, idempotency_key="batch"),
    ):
        with pytest.raises(Unsupported):
            call()
        assert snapshot(store, writer) == before


def test_import_auth_precedes_profile_refusal_and_profile_precedes_record_iteration() -> None:
    store, writer, reader = world()

    class Uniterable:
        def __iter__(self):
            raise AssertionError("unsupported import must not inspect records")

    before = snapshot(store, writer)
    # The cast preserves the deliberately uniterable runtime object while satisfying the API type.
    with pytest.raises(Unsupported):
        store.import_records(
            writer,
            "catalog",
            cast(Sequence[Mapping[str, object]], Uniterable()),
            load_id="load",
            initiated_by="writer",
        )
    assert snapshot(store, writer) == before
    with pytest.raises(Refused):
        store.import_records(
            reader,
            "catalog",
            cast(Sequence[Mapping[str, object]], Uniterable()),
            load_id="load",
            initiated_by="reader",
        )
    assert snapshot(store, writer) == before


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("default", "x"),
        ("allowedValues", ["x"]),
        ("semanticTypes", ["email"]),
        ("facets", {"length": {"max": 3}}),
    ],
)
def test_declared_field_semantics_are_reported_at_their_source_path(
    path: str, value: object
) -> None:
    raw = json.loads(ORIGINAL)
    field = next(e for e in raw["modules"][0]["elements"] if e.get("id") == "UseCase.name")
    field[path] = value
    from arras.fakes_profile import require_supported_write_profile

    with pytest.raises(Unsupported) as err:
        require_supported_write_profile(json.dumps(raw).encode(), "catalog")
    assert any(f"UseCase.name.{path}" in reason for reason in err.value.supported)


@pytest.mark.parametrize(
    ("transform", "expected"),
    [
        (lambda raw: raw["modules"][0].pop("elements"), "elements"),
        (lambda raw: raw["modules"].clear(), "module is missing"),
        (lambda raw: raw["modules"][0]["elements"][1].update(facets=None), "facets"),
        (
            lambda raw: raw["modules"][0]["elements"][1].update(itemType="string"),
            "non-direct scalar fields",
        ),
        (lambda raw: raw["modules"][0]["elements"][1].update(rules=[]), "rules"),
        (lambda raw: raw["modules"][0]["elements"][1].update(semanticTypes=None), "semanticTypes"),
        (
            lambda raw: raw["modules"][0]["elements"][1].update(scalarType=[]),
            "non-direct scalar fields",
        ),
    ],
    ids=[
        "missing-elements",
        "missing-module",
        "null-facets",
        "item-type",
        "empty-rules-slot",
        "malformed-semantic-types",
        "malformed-scalar-type",
    ],
)
def test_present_document_with_uninspectable_or_non_scalar_shape_fails_closed(
    transform, expected: str
) -> None:
    from arras.fakes_profile import require_supported_write_profile

    raw = plain_original()
    numeric_field = next(e for e in raw["modules"][0]["elements"] if e.get("id") == "UseCase.code")
    numeric_field["scalarType"] = "integer"
    numeric_field["facets"] = {"integerWidth": {"bits": 32, "signed": True}}
    require_supported_write_profile(json.dumps(raw).encode(), "catalog")
    transform(raw)
    with pytest.raises(Unsupported) as err:
        require_supported_write_profile(json.dumps(raw).encode(), "catalog")
    assert any(expected in reason for reason in err.value.supported)


def test_hand_built_module_without_raw_document_keeps_explicit_legacy_baseline() -> None:
    from arras.fakes_profile import require_supported_write_profile

    require_supported_write_profile(None, "handbuilt")


@pytest.mark.parametrize("document", [b"not json", b"[]"])
def test_malformed_present_document_fails_closed(document: bytes) -> None:
    from arras.fakes_profile import require_supported_write_profile

    with pytest.raises(Unsupported):
        require_supported_write_profile(document, "catalog")


@pytest.mark.parametrize(
    "width",
    [{}, {"bits": 8}, {"signed": False}, {"bits": 16, "signed": True}],
)
def test_supported_integer_width_subset_accepts_optional_legacy_members(
    width: dict[str, object],
) -> None:
    from arras.fakes_profile import require_supported_write_profile

    raw = plain_original()
    field = next(e for e in raw["modules"][0]["elements"] if e.get("id") == "UseCase.code")
    field["scalarType"] = "integer"
    field["facets"] = {"integerWidth": width}
    require_supported_write_profile(json.dumps(raw).encode(), "catalog")


@pytest.mark.parametrize(
    ("scalar", "facets"),
    [
        ("integer", {"integerWidth": {"bits": True}}),
        ("integer", {"integerWidth": {"unknown": 1}}),
        ("decimal", {"precision": 4}),
        ("decimal", {"precision": 4, "scale": 5}),
    ],
)
def test_malformed_numeric_facet_shapes_are_reported(
    scalar: str, facets: dict[str, object]
) -> None:
    from arras.fakes_profile import require_supported_write_profile

    raw = plain_original()
    field = next(e for e in raw["modules"][0]["elements"] if e.get("id") == "UseCase.code")
    field["scalarType"] = scalar
    field["facets"] = facets
    with pytest.raises(Unsupported):
        require_supported_write_profile(json.dumps(raw).encode(), "catalog")


def test_existing_supported_integer_and_decimal_profile_still_accepts_imports() -> None:
    from shop_module import MODULE as SHOP
    from shop_module import document as shop_document
    from shop_module import shop_store

    raw = shop_document().encode()
    from arras.fakes_profile import require_supported_write_profile

    require_supported_write_profile(raw, SHOP)
    store, _ = shop_store()
    assert store.count("shop.Purchase") == 4
