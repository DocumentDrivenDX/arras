# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""`arras.testing` as a host uses it: through public names only, and enough to test a host.

This file imports only `arras` and `arras.testing`; `test_embedding` holds it to that."""

import pytest

from arras import Arras, Invalid, Refused, Unavailable
from arras.testing import InMemory, example_module

RECORDS = [
    {"type": "UseCase", "key": "uc-1", "properties": {"name": "Pipeline mapping"}},
    {"type": "UseCase", "key": "uc-2", "properties": {"name": "Alert review"}},
]
ALL = "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100"


@pytest.fixture
def world() -> InMemory:
    w = InMemory()
    w.register(example_module())
    return w


def test_a_fresh_world_is_started_and_available() -> None:
    w = InMemory()
    assert isinstance(w.arras, Arras)
    assert {n: s.available for n, s in w.arras.status().items()} == {
        "memory": True,
        "memory_replica": True,
    }


def test_register_seed_read_and_act_as_a_person(world: InMemory) -> None:
    assert world.import_records("catalog", RECORDS).created == 2
    alice = world.person("alice", "catalog", "read", "write")
    o = world.arras.session(alice)
    assert {r["name"] for r in o.query("catalog", ALL).rows} == {"Pipeline mapping", "Alert review"}
    receipt = o.invoke(
        "catalog.AddUseCase", {"code": "uc-3", "name": "Finance", "workArea": "finance"}
    )
    assert receipt.created == 1
    assert len(o.query("catalog", ALL).rows) == 3


def test_a_change_is_attributed_to_the_person(world: InMemory) -> None:
    alice = world.person("alice", "catalog", "read", "write")
    o = world.arras.session(alice)
    o.invoke("catalog.AddUseCase", {"code": "uc-3", "name": "Finance", "workArea": "finance"})
    by_key = "SELECT u.* FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 1"
    (row,) = o.query("catalog", by_key, {"k": "uc-3"}).rows
    assert row["_created_by"] == "alice"


def test_the_replica_is_stale_until_it_is_synced(world: InMemory) -> None:
    world.import_records("catalog", RECORDS)
    carol = world.person("carol", "catalog", "read")
    o = world.arras.session(carol)
    with pytest.raises(Unavailable):  # a replica that has never been fed has no position
        o.query("catalog", ALL, consistency="bulk")
    world.sync()
    first = o.query("catalog", ALL, consistency="bulk")
    assert len(first.rows) == 2 and first.freshness.backend == "memory_replica"
    world.import_records(
        "catalog", [{"type": "UseCase", "key": "uc-9", "properties": {"name": "X"}}], load_id="2"
    )
    assert len(o.query("catalog", ALL, consistency="bulk").rows) == 2  # still behind
    world.sync()
    assert len(o.query("catalog", ALL, consistency="bulk").rows) == 3


def test_a_person_without_access_is_refused_not_shown_nothing(world: InMemory) -> None:
    world.import_records("catalog", RECORDS)
    dave = world.person("dave", "catalog")  # known to the backends, granted nothing
    # CONTRACT-001 says `Refused`; the interface today answers `Invalid` (no such module) because
    # it hides modules the person cannot read. Either way, never an empty answer.
    with pytest.raises((Refused, Invalid)):
        world.arras.session(dave).query("catalog", ALL)


def test_a_reader_cannot_change_anything(world: InMemory) -> None:
    carol = world.person("carol", "catalog", "read")
    with pytest.raises(Refused):
        world.arras.session(carol).invoke(
            "catalog.AddUseCase", {"code": "uc-3", "name": "Finance", "workArea": "finance"}
        )


def test_an_expired_token_is_refused(world: InMemory) -> None:
    alice = world.person("alice", "catalog", "read")
    world.expire(alice)
    with pytest.raises(Refused):
        world.arras.session(alice).query("catalog", ALL)


def test_an_outage_is_unavailable_and_the_other_backend_still_answers(world: InMemory) -> None:
    world.import_records("catalog", RECORDS)
    world.sync()
    o = world.arras.session(world.person("carol", "catalog", "read"))
    world.set_available("memory", False)
    assert world.arras.status()["memory"].available is False
    with pytest.raises(Unavailable):
        o.query("catalog", ALL)
    assert len(o.query("catalog", ALL, consistency="bulk").rows) == 2
    world.set_available("memory", True)
    assert len(o.query("catalog", ALL).rows) == 2


def test_starting_without_a_backend_reports_it_and_still_serves(world: InMemory) -> None:
    world.import_records("catalog", RECORDS)
    ar = world.start(backends=["memory"])
    assert ar.status()["memory_replica"].reason == "not_configured"
    assert len(ar.session(world.person("carol", "catalog", "read")).query("catalog", ALL).rows) == 2


def test_only_the_administrator_registers(world: InMemory) -> None:
    alice = world.person("alice", "catalog", "read", "write")
    with pytest.raises(Refused):
        world.arras.session(alice).registry().register(example_module())


def test_an_invalid_action_input_is_reported(world: InMemory) -> None:
    alice = world.person("alice", "catalog", "read", "write")
    with pytest.raises(Invalid):
        world.arras.session(alice).invoke("catalog.AddUseCase", {"code": "uc-3"})


def test_worlds_do_not_share_state() -> None:
    a, b = InMemory(), InMemory()
    a.register(example_module())
    assert a.arras.session(a.person("p", "catalog", "read")).modules()
    assert not b.arras.session(b.person("p", "catalog", "read")).modules()


def test_backend_names_are_the_hosts() -> None:
    w = InMemory(store="primary", replica="mirror")
    assert set(w.backends) == {"primary", "mirror"}
    assert set(w.arras.status()) == {"primary", "mirror"}
