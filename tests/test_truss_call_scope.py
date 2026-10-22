# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""One catalog read per call, and access that stays per call (the call scope, plan B7).

A person's read or action reads the person's reader catalog once and hands it to the backend call that
follows within the same operation (`arras.callscope`); it is gone when the operation returns. These
tests run against a real Truss and revoke a role's access to the module between two calls, and between
the two steps of one call: the next call asks Truss again and is refused, and the call that was
granted when it began is refused by Truss at its own statement.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from arras import Arras, Invalid, Placement, Refused
from arras.adapters.truss.registry import Registry
from arras.conformance import load_corpus
from arras.umf import parse_module
from test_truss_harness import cluster  # noqa: F401
from truss_harness import TrussHarness

MODULE_TEXT = load_corpus()["_module_text"]
HOST = "truss"
LIST = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
ADD = "catalog.AddUseCase"


class Rig:
    """One Truss with the corpus module, a writer (`bob`) and a reader (`carol`), and a count of the
    reader-catalog reads the adapter makes."""

    def __init__(self, cluster: Any) -> None:  # noqa: F811
        h = TrussHarness(cluster)
        h.install(parse_module(MODULE_TEXT), MODULE_TEXT.encode())
        h.grant("bob", {"catalog": ["read", "write"]}, False)
        h.grant("carol", {"catalog": ["read"]}, False)
        self.harness = h
        self.backend: Any = h.backend()
        self.host = Arras.start({HOST: self.backend}, default_placement=Placement(HOST, ()))
        self.catalog_reads = 0

    def person(self, user: str) -> Any:
        return self.host.session(self.harness.principal(user))

    def revoke(self, user: str, mode: str) -> None:
        role = getattr(self.harness.world, f"{mode}_role")("catalog")
        self.harness.world.cluster.su.execute(f'REVOKE "{role}" FROM "{user}"')

    def count_reads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real = Registry.reader_catalog

        def counted(registry: Registry, call: Any) -> Any:
            self.catalog_reads += 1
            return real(registry, call)

        monkeypatch.setattr(Registry, "reader_catalog", counted)


@pytest.fixture
def rig(cluster: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:  # noqa: F811
    r = Rig(cluster)
    r.person("bob").invoke(ADD, {"code": "a", "name": "A"})
    r.count_reads(monkeypatch)
    try:
        yield r
    finally:
        r.harness.world.cluster.end_world()


@pytest.mark.truss
def test_a_read_a_write_and_a_describe_each_read_the_catalog_once(rig: Rig) -> None:
    carol, bob = rig.person("carol"), rig.person("bob")
    rig.backend.cache.drop_shown("carol")  # a read of a module not yet shown reads the catalog once
    for work in (
        lambda: carol.query("catalog", LIST),
        lambda: bob.invoke(ADD, {"code": "b", "name": "B"}),
        lambda: bob.validate(ADD, {"code": "c", "name": "C"}),
        lambda: carol.describe(),
        lambda: carol.describe("catalog"),
    ):
        rig.catalog_reads = 0
        work()
        assert rig.catalog_reads == 1
    rig.catalog_reads = 0  # shown now: the read is the one combined operation, with no catalog read
    carol.query("catalog", LIST)
    assert rig.catalog_reads == 0


@pytest.mark.truss
def test_a_revoked_reader_is_refused_on_the_very_next_call(rig: Rig) -> None:
    carol = rig.person("carol")
    assert [r["code"] for r in carol.query("catalog", LIST).rows] == ["a"]
    rig.revoke("carol", "reader")
    with pytest.raises(Invalid) as raised:
        carol.query("catalog", LIST)
    assert raised.value.violations[0].code == "unknown_type"
    assert (
        carol.describe() == [] and carol.modules() == []
    )  # nothing carried over from the call before


@pytest.mark.truss
def test_a_revoked_writer_is_refused_on_the_very_next_call(rig: Rig) -> None:
    bob = rig.person("bob")
    bob.invoke(ADD, {"code": "b", "name": "B"})
    rig.revoke("bob", "reader")
    rig.revoke("bob", "writer")
    with pytest.raises(Invalid):  # the action's module is no longer one bob may read
        bob.invoke(ADD, {"code": "c", "name": "C"})
    assert [r["code"] for r in rig.person("carol").query("catalog", LIST).rows] == ["a", "b"]


@pytest.mark.truss
def test_access_revoked_between_the_steps_of_one_read_is_refused_by_truss(rig: Rig) -> None:
    carol = rig.person("carol")
    rig.backend.cache.drop_shown("carol")  # the ordinary route: the catalog, then the query
    real = rig.backend.query

    def revoking(*args: Any, **kwargs: Any) -> Any:
        rig.revoke("carol", "reader")  # after the call's catalog read, before its query
        return real(*args, **kwargs)

    rig.backend.query = revoking  # type: ignore[method-assign]
    with pytest.raises(Invalid) as raised:
        carol.query("catalog", LIST)
    assert raised.value.violations[0].code == "unknown_type"


@pytest.mark.truss
def test_access_revoked_between_the_steps_of_one_write_is_refused_by_truss(rig: Rig) -> None:
    bob = rig.person("bob")
    real = rig.backend.apply

    def revoking(*args: Any, **kwargs: Any) -> Any:
        rig.revoke("bob", "writer")
        rig.revoke("bob", "reader")
        return real(*args, **kwargs)

    rig.backend.apply = revoking  # type: ignore[method-assign]
    with pytest.raises(Refused):
        bob.invoke(ADD, {"code": "z", "name": "Z"})
    assert "z" not in [r["code"] for r in rig.person("carol").query("catalog", LIST).rows]


@pytest.mark.truss
def test_one_persons_catalog_is_never_another_persons(rig: Rig) -> None:
    rig.harness.grant("dave", {}, False)
    dave = rig.person("dave")
    assert rig.person("carol").query("catalog", LIST).rows  # carol's call just ran
    with pytest.raises(Invalid):
        dave.query("catalog", LIST)
