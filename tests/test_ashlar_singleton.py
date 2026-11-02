# SPDX-License-Identifier: MIT OR Apache-2.0
"""AS-2 bridge controls only; doubles establish no native/provider qualification."""

from contextlib import contextmanager
from typing import Any

import pytest

from arras.adapters.ashlar import singleton
from arras.errors import Refused, Unavailable
from arras.types import Principal

PERSON = Principal("ana", "private-token")
SELECTION = singleton.Selection("publication-1", "catalog.gold.objects", "object", "source", 7, 9)


def session() -> singleton.Session:
    return singleton.Session(
        object(),
        object(),
        object(),
        object(),
        object(),
        object(),
        ["ashlar-delta/0.4-xxhash64"],
        {"source": ["1"]},
    )


def test_no_token_refuses_before_sdk_or_session(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any) -> Any:
        pytest.fail("must refuse before opening SDK or session")

    monkeypatch.setattr(singleton, "_read_singleton", forbidden)
    reads = singleton.SingletonReads("replica", forbidden)
    with pytest.raises(Refused):
        reads.lookup(Principal("ana", ""), SELECTION)


@pytest.mark.parametrize("row", [None, {"id": "9", "entity_version": "9007199254740993"}])
def test_exact_person_ports_selection_and_carriers(
    monkeypatch: pytest.MonkeyPatch, row: dict[str, str] | None
) -> None:
    events: list[object] = []
    ports = session()

    @contextmanager
    def source(principal: Principal):
        events.append(principal)
        yield ports
        events.append("closed")

    def read(*args: Any, **kwargs: Any):
        assert args == (ports.executor, ports.backend, ports.pins, ports.vector, ports.policy)
        assert kwargs == {
            "publication_id": "publication-1",
            "table": "catalog.gold.objects",
            "kind": "object",
            "source": "source",
            "type_id": 7,
            "entity_id": 9,
            "context": ports.context,
            "supported_profiles": ("ashlar-delta/0.4-xxhash64",),
            "supported_revisions": {"source": ("1",)},
        }
        events.append("read")
        return row

    def forbidden():
        pytest.fail("explicit owner must not fall back to dependency discovery")

    monkeypatch.setattr(singleton, "_read_singleton", forbidden)
    out = singleton.SingletonReads("replica", source, read_singleton=read).lookup(PERSON, SELECTION)
    assert events == [PERSON, "read", "closed"]
    assert out.publication_id == SELECTION.publication_id
    assert out.row == row
    if row is not None:
        row["id"] = "changed after release"
        assert out.row is not None and out.row["id"] == "9"
        with pytest.raises(TypeError):
            out.row["id"] = "mutation"  # type: ignore[index]


def test_calls_open_fresh_for_each_person(monkeypatch: pytest.MonkeyPatch) -> None:
    people: list[Principal] = []

    @contextmanager
    def source(principal: Principal):
        people.append(principal)
        yield session()

    def empty(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(singleton, "_read_singleton", lambda: empty)
    reads = singleton.SingletonReads("replica", source)
    reads.lookup(PERSON, SELECTION)
    other = Principal("bea", "other-token")
    reads.lookup(other, SELECTION)
    assert people == [PERSON, other]


@pytest.mark.parametrize("phase", ["open", "read", "close"])
@pytest.mark.parametrize("failure", [PermissionError, RuntimeError, TimeoutError, ImportError])
def test_failure_returns_no_row_and_exposes_no_native_details(
    monkeypatch: pytest.MonkeyPatch, phase: str, failure: type[Exception]
) -> None:
    events: list[str] = []

    def fail() -> None:
        raise failure("private-token SECRET SQL input")

    @contextmanager
    def source(principal: Principal):
        if phase == "open":
            fail()
        try:
            yield session()
        finally:
            events.append("close")
            if phase == "close":
                fail()

    def read(*args: Any, **kwargs: Any):
        if phase == "read":
            fail()
        return {"id": "9"}

    monkeypatch.setattr(singleton, "_read_singleton", lambda: read)
    expected = Refused if failure is PermissionError else Unavailable
    with pytest.raises(expected) as found:
        singleton.SingletonReads("replica", source).lookup(PERSON, SELECTION)
    assert "SECRET" not in str(found.value) and PERSON.token not in str(found.value)
    if isinstance(found.value, Unavailable):
        assert found.value.reason == "unreachable"
    assert events == ([] if phase == "open" else ["close"])


def test_missing_owner_does_not_open_session() -> None:
    def forbidden(principal: Principal) -> Any:
        pytest.fail("missing owner cannot open a session")

    with pytest.raises(Unavailable) as found:
        singleton.SingletonReads("replica", forbidden).lookup(PERSON, SELECTION)
    assert found.value.reason == "unsupported_version"


def test_cleanup_denial_does_not_turn_read_outage_into_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def source(principal: Principal):
        try:
            yield session()
        finally:
            raise PermissionError("secret cleanup denial")

    def read(*args: Any, **kwargs: Any):
        raise RuntimeError("secret read outage")

    monkeypatch.setattr(singleton, "_read_singleton", lambda: read)
    with pytest.raises(Unavailable) as found:
        singleton.SingletonReads("replica", source).lookup(PERSON, SELECTION)
    assert found.value.reason == "unreachable"
