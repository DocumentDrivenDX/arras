# SPDX-License-Identifier: MIT OR Apache-2.0
"""Per-call catalog collection preserves the core's principal and placement decisions."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, cast

import pytest

from arras import Arras, Ontology, Principal, Refused, Unavailable
from arras._catalogs import Catalogs, collect_catalogs
from arras.backend import Backend
from arras.core import Context, Registry
from arras.model import ModuleInfo, Placement
from arras.types import Revision


def info(name: str, record: str = "store") -> ModuleInfo:
    return ModuleInfo(name, Placement(record), Revision(), ())


class CatalogBackend:
    def __init__(self, catalog: dict[str, ModuleInfo] | Exception) -> None:
        self.value = catalog
        self.calls: list[Principal] = []

    def catalog(self, principal: Principal) -> dict[str, ModuleInfo]:
        self.calls.append(principal)
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_collection_is_fresh_and_uses_the_principal_and_host_placement() -> None:
    principal = Principal("reader", "stable-token")
    source = info("catalog")
    backend = CatalogBackend({"catalog": source, "hidden": info("hidden")})
    lookups: list[str] = []

    def placement_of(name: str) -> Placement | None:
        lookups.append(name)
        return Placement("store", ("replica",)) if name == "catalog" else None

    backends = cast(dict[str, Backend], {"replica": backend})
    first = collect_catalogs(backends, principal, placement_of)
    second = collect_catalogs(backends, principal, placement_of)

    assert backend.calls == [principal, principal]
    assert first is not second
    assert first.of("replica", "catalog") is not source
    assert first.of("replica", "catalog").placement == Placement("store", ("replica",))  # type: ignore[union-attr]
    assert first.names() == ["catalog"] and lookups == ["catalog", "hidden"] * 2


def test_record_store_copy_wins_and_refusal_has_priority() -> None:
    replica = CatalogBackend({"catalog": info("catalog", "store")})
    store_copy = CatalogBackend({"catalog": info("catalog", "store")})
    refused = Refused("private", "catalog")
    unavailable = Unavailable("offline", "unreachable")
    catalogs = collect_catalogs(
        cast(
            dict[str, Backend],
            {
                "replica": replica,
                "store": store_copy,
                "offline": CatalogBackend(unavailable),
                "private": CatalogBackend(refused),
            },
        ),
        Principal("reader", "token"),
        lambda name: Placement("store", ("replica",)),
    )

    assert catalogs.module("catalog") is catalogs.of("store", "catalog")
    assert catalogs.failure() is refused
    assert catalogs.failures == {"offline": unavailable, "private": refused}


def test_missing_token_is_refused_before_backends_are_read() -> None:
    class Untouched:
        def __getitem__(self, key: str) -> Any:
            raise AssertionError("backend mapping was consulted before token validation")

        def items(self) -> Any:
            raise AssertionError("backend mapping was consulted before token validation")

    ontology = object.__new__(Ontology)
    ontology.h = SimpleNamespace(backends=Untouched())  # type: ignore[assignment]
    ontology.principal = Principal("reader", "")

    with pytest.raises(Refused) as error:
        ontology._catalogs("describe")  # pyright: ignore[reportPrivateUsage]
    assert error.value.reason == "token_expired"


def test_public_types_stay_defined_by_core_and_catalog_wrapper_signature_is_stable() -> None:
    assert (
        Arras.__module__
        == Ontology.__module__
        == Registry.__module__
        == Context.__module__
        == "arras.core"
    )
    assert (
        str(inspect.signature(Ontology._catalogs)) == "(self, op: 'str') -> '_Catalogs'"  # pyright: ignore[reportPrivateUsage]
    )
    assert Catalogs.__module__ == "arras._catalogs"
