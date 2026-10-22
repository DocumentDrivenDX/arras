# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
# ruff: noqa: F811
"""A read is one operation in one read-only transaction (Truss 0.0.45's
`query_with_catalog_in_transaction`, plan B9).

Once a person was shown a module, the next `latest` read presents what they were shown with the
statement: Truss answers the rows and the person's current catalog together, withholds both if the
authority or the sources moved, and the adapter gives the answer only when the catalog is
`unchanged`. These tests run against a real Truss: the transactions a read opens, the fallback when
the catalog moved, a role revoked between two calls and between the catalog step and the query step,
the original source's bytes and digest, and a statement Truss refuses leaving nothing behind.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from arras import Arras, Invalid, Placement
from arras.adapters.truss.connection import Connections
from arras.adapters.truss.query import _same_sources  # pyright: ignore[reportPrivateUsage]
from arras.conformance import _edited, load_corpus
from arras.errors import Unsupported
from arras.umf import parse_module
from test_truss_harness import cluster  # noqa: F401
from truss_harness import TrussHarness

MODULE_TEXT = load_corpus()["_module_text"]
LIST = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100"
ADD = "catalog.AddUseCase"


class Rig:
    def __init__(self, cluster: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
        h = TrussHarness(cluster)
        h.install(parse_module(MODULE_TEXT), MODULE_TEXT.encode())
        h.grant("bob", {"catalog": ["read", "write"]}, False)
        h.grant("carol", {"catalog": ["read"]}, False)
        h.grant("alice", {"catalog": ["read", "write", "schema"]}, True)
        self.harness = h
        self.backend: Any = h.backend()
        self.host = Arras.start({"truss": self.backend}, default_placement=Placement("truss", ()))
        self.reads = 0  # read-only transactions opened
        self.ops: list[str] = []
        real = Connections.read

        def counted(conns: Connections, principal: Any, operation: str) -> Any:
            self.reads += 1
            self.ops.append(operation)
            return real(conns, principal, operation)

        monkeypatch.setattr(Connections, "read", counted)
        self.calls: list[str] = []
        assembly = __import__("truss.catalog_runtime", fromlist=["x"]).CatalogReferenceAssembly
        for name in (
            "reader_catalog_if_changed_in_transaction",
            "query_in_transaction",
            "query_with_catalog_in_transaction",
        ):
            monkeypatch.setattr(assembly, name, self._spy(name, getattr(assembly, name)))
        self.sources: list[Any] = []

    def _spy(self, name: str, real: Any) -> Any:
        def spy(assembly: Any, tx: Any, **kw: Any) -> Any:
            self.calls.append(name)
            out = real(assembly, tx, **kw)
            value = getattr(out, "value", None)
            if name == "query_with_catalog_in_transaction" and value is not None:
                self.sources.extend(getattr(value, "documents", ()))
            return out

        return spy

    def person(self, user: str) -> Any:
        return self.host.session(self.harness.principal(user))

    def revoke(self, user: str) -> None:
        role = self.harness.world.reader_role("catalog")
        self.harness.world.cluster.su.execute(f'REVOKE "{role}" FROM "{user}"')

    def count(self, work: Any) -> tuple[Any, int, list[str]]:
        self.reads, self.calls[:] = 0, []
        out = work()
        return out, self.reads, list(self.calls)


@pytest.fixture
def rig(cluster: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:  # noqa: F811
    r = Rig(cluster, monkeypatch)
    r.person("bob").invoke(ADD, {"code": "a", "name": "A"})
    try:
        yield r
    finally:
        r.harness.world.cluster.end_world()


@pytest.mark.truss
def test_a_read_is_one_transaction_once_the_person_was_shown_the_module(rig: Rig) -> None:
    rig.harness.grant("tom", {"catalog": ["read"]}, False)
    tom = rig.person("tom")
    rig.backend.cache.drop_shown("tom")  # a process that has not shown tom the module yet
    first, reads, calls = rig.count(lambda: tom.query("catalog", LIST))
    assert [r["code"] for r in first.rows] == ["a"]
    # nothing was shown to tom yet: the catalog, then the query (two read-only transactions)
    assert reads == 2 and "query_with_catalog_in_transaction" not in calls, (rig.ops, calls)
    again, reads, calls = rig.count(lambda: tom.query("catalog", LIST))
    assert [r["code"] for r in again.rows] == ["a"]
    assert reads == 1 and calls == ["query_with_catalog_in_transaction"], (rig.ops, calls)
    assert again.revision == first.revision and again.freshness.consistency == "latest"


@pytest.mark.truss
def test_the_combined_answer_equals_the_ordinary_one(rig: Rig) -> None:
    carol = rig.person("carol")
    sql = "SELECT x.* FROM catalog.UseCase x WHERE x.code = :code ORDER BY x.code LIMIT 100"
    ordinary = carol.query("catalog", sql, {"code": "a"})
    combined = carol.query("catalog", sql, {"code": "a"})
    assert (combined.columns, combined.rows, combined.truncated) == (
        ordinary.columns,
        ordinary.rows,
        ordinary.truncated,
    )


@pytest.mark.truss
def test_a_registration_between_reads_is_not_missed_the_read_goes_the_ordinary_way(
    rig: Rig,
) -> None:
    carol = rig.person("carol")
    before = carol.query("catalog", LIST)
    carol.query("catalog", LIST)  # combined, unchanged
    new = _edited(MODULE_TEXT, "add-record-type").encode()
    rig.backend.register(
        rig.harness.principal("alice"), new, parse_module(new), unknown_endpoint="reject"
    )
    after, reads, calls = rig.count(lambda: carol.query("catalog", LIST))
    assert after.revision != before.revision  # the new module revision, not the one shown before
    assert "query_with_catalog_in_transaction" in calls and "query_in_transaction" in calls
    assert (
        reads == 3
    )  # the combined read (catalog moved: no answer), then the catalog and the query
    third, reads, calls = rig.count(lambda: carol.query("catalog", LIST))
    assert reads == 1 and third.revision == after.revision


@pytest.mark.truss
def test_a_role_revoked_between_two_reads_is_refused_on_the_very_next_one(rig: Rig) -> None:
    carol = rig.person("carol")
    carol.query("catalog", LIST)
    carol.query("catalog", LIST)  # warm: the next read is the combined one
    rig.revoke("carol")
    with pytest.raises(Invalid) as raised:
        carol.query("catalog", LIST)
    assert raised.value.violations[0].code == "unknown_type"


@pytest.mark.truss
def test_a_role_revoked_between_the_catalog_step_and_the_query_step_is_refused_by_truss(
    rig: Rig,
) -> None:
    carol = rig.person("carol")
    carol.query("catalog", LIST)
    real = rig.backend.query_current

    def revoking(*args: Any, **kwargs: Any) -> Any:
        rig.revoke("carol")  # after the person was shown the module, before Truss is asked
        return real(*args, **kwargs)

    rig.backend.query_current = revoking
    with pytest.raises(Invalid) as raised:
        carol.query("catalog", LIST)
    assert raised.value.violations[0].code == "unknown_type"
    assert carol.describe() == []  # and nothing of what was shown is kept for the next call


@pytest.mark.truss
def test_the_original_source_is_returned_with_its_digest_and_is_the_registered_document(
    rig: Rig,
) -> None:
    carol = rig.person("carol")
    carol.query("catalog", LIST)
    rig.sources.clear()
    carol.query("catalog", LIST)
    [source] = rig.sources
    registered = carol.document("catalog")
    assert source.content.decode() == registered.text  # the exact bytes, as registered
    import hashlib

    assert source.sha256 == hashlib.sha256(source.content).hexdigest()
    held = rig.backend.cache.snapshot("carol", True)[0]
    entry = next(e for e in held.modules if e["moduleId"] == "catalog")
    assert (source.document_id, source.sha256) == (entry["documentId"], entry["documentSha256"])


def test_sources_that_do_not_match_the_catalog_entry_are_not_accepted() -> None:
    class Doc:
        def __init__(self, document_id: str, sha256: str) -> None:
            self.document_id, self.sha256 = document_id, sha256

    catalog = type(
        "Catalog",
        (),
        {"modules": ({"moduleId": "m", "documentId": "d", "documentSha256": "abc"},)},
    )()
    assert _same_sources(catalog, "m", "d", (Doc("d", "abc"),))
    assert not _same_sources(catalog, "m", "d", (Doc("d", "other"),))  # another digest
    assert not _same_sources(catalog, "m", "d", (Doc("e", "abc"),))  # another document
    assert not _same_sources(catalog, "x", "d", (Doc("d", "abc"),))  # a module not in the catalog
    assert not _same_sources(catalog, "m", "d", ())  # no source returned


@pytest.mark.truss
def test_a_statement_truss_refuses_leaves_nothing_behind_and_the_next_read_is_combined(
    rig: Rig,
) -> None:
    carol = rig.person("carol")
    carol.query("catalog", LIST)
    with pytest.raises((Unsupported, Invalid)):
        carol.query("catalog", "SELEC nothing")
    rows, reads, calls = rig.count(lambda: carol.query("catalog", LIST))
    assert [r["code"] for r in rows.rows] == ["a"] and reads == 1, (rig.ops, calls)
    assert calls == ["query_with_catalog_in_transaction"]


@pytest.mark.truss
def test_one_persons_shown_catalog_is_never_presented_for_another(rig: Rig) -> None:
    rig.harness.grant("dave", {}, False)
    rig.person("carol").query("catalog", LIST)
    rig.person("carol").query("catalog", LIST)
    with pytest.raises(Invalid):
        rig.person("dave").query("catalog", LIST)  # never shown anything: the ordinary way refuses
