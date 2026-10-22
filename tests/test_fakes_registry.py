# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The in-memory authority's registration under the `schema` grant, and its dry run (CONTRACT-004).

The shared corpus holds the cases every provider must pass (`registry.*`); these are what only the
fake can say: the grant on a module it does not hold, and how a registration reaches the replica."""

import json
from pathlib import Path

import pytest

from arras import Conflict, Invalid, Refused, Revision, Unsupported
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.model import ModuleInfo
from arras.umf import parse_module

EXAMPLE = Path(__file__).parents[1] / "docs/helix/02-design/contracts/examples/catalog.umf.json"
DOC = EXAMPLE.read_bytes()


def renamed(name: str) -> tuple[bytes, ModuleInfo]:
    text = DOC.decode().replace('"catalog"', f'"{name}"')
    return text.encode(), parse_module(text)


def world() -> tuple[FakeAccess, MemoryStore, MemoryReplica]:
    access = FakeAccess()
    store = MemoryStore(access)
    return access, store, MemoryReplica(store, access)


def test_a_module_the_store_does_not_hold_needs_the_right_to_create_one():
    access, store, _ = world()
    doc, mod = renamed("ledger")
    other = access.grant("ana", "elsewhere", "read", "write", "schema")  # not this module
    with pytest.raises(Refused):
        store.register(other, doc, mod, unknown_endpoint="provisional")
    with pytest.raises(Refused):
        store.validate_register(other, doc, mod, unknown_endpoint="provisional")
    maker = access.grant("mia", "*", "schema")  # in the fake, "*" is the right to create
    check = store.validate_register(maker, doc, mod, unknown_endpoint="provisional")
    assert check.revision is None and check.changed and not check.violations
    assert "ledger" not in store.modules  # a dry run holds nothing
    assert store.register(maker, doc, mod, unknown_endpoint="provisional").changed


def test_a_dry_run_leaves_no_revision_and_the_same_document_changes_nothing():
    access, store, _ = world()
    p = access.grant("ana", "catalog", "schema")
    doc, mod = renamed("catalog")
    first = store.register(p, doc, mod, unknown_endpoint="reject")
    revision = store.catalog_revision
    check = store.validate_register(p, doc, mod, unknown_endpoint="reject")
    assert not check.changed and check.revision == first.revision and check.current is not None
    assert store.catalog_revision == revision


def test_the_expected_revision_is_checked_where_the_registration_is_accepted():
    access, store, _ = world()
    p = access.grant("ana", "catalog", "schema")
    doc, mod = renamed("catalog")
    first = store.register(p, doc, mod, unknown_endpoint="reject")
    changed = json.loads(doc)
    changed["modules"][0]["extensions"]["umf.ddd"]["terms"] = []  # same module, other bytes
    text = json.dumps(changed, indent=3)
    with pytest.raises(Conflict):
        store.register(
            p,
            text.encode(),
            mod,
            unknown_endpoint="reject",
            expected_revision=Revision({"memory": 99}),
        )
    assert store.catalog_revision == first.revision.by_backend["memory"]


def test_a_registration_by_a_person_reaches_the_replica_through_its_feed():
    access, store, replica = world()
    p = access.grant("ana", "catalog", "schema")
    doc, mod = renamed("catalog")
    result = store.register(p, doc, mod, unknown_endpoint="reject")
    assert "catalog" not in replica.modules  # the person may not attach to a replica
    replica.feed()
    assert replica.modules["catalog"].revision == result.revision


def test_a_replica_has_no_dry_run():
    access, _, replica = world()
    p = access.grant("ana", "catalog", "schema")
    doc, mod = renamed("catalog")
    with pytest.raises(Unsupported):
        replica.validate_register(p, doc, mod, unknown_endpoint="reject")


def test_an_unknown_policy_is_a_bad_request_not_an_answer():
    access, store, _ = world()
    p = access.grant("ana", "*", "schema")
    doc, mod = renamed("ledger")
    with pytest.raises(Invalid):
        store.validate_register(p, doc, mod, unknown_endpoint="whatever")
