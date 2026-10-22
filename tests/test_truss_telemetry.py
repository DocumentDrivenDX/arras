# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The Truss adapter's calls in telemetry (CONTRACT-008), always on: the scripted rigs of the plan
and lifecycle tests stand in for Truss. A per-person call names its backend on the operation core
is observing (the event is core's, with the adapter's own name on it); the lifecycle calls, which
core does not trace, are events of the backend. Nothing here may carry a credential or an input."""

from __future__ import annotations

import importlib.util
import logging

import pytest

from arras import Arras, Unavailable, telemetry
from arras.errors import Conflict
from test_telemetry import SECRET, Event, events
from test_truss_lifecycle import ACCESS, Rig, Script, StateError
from test_truss_plan import (
    ABSENT,
    ApplyRig,
    Created,
    GroupOperationFailure,
    applied,
    artifact_of,
    create_plan,
    failed,
    replayed,
)
from test_truss_registry import ALICE

needs_toolkit = pytest.mark.skipif(
    importlib.util.find_spec("truss") is None,
    reason="the truss extra is not installed",
)


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="arras.telemetry")
    return caplog


def only(records: pytest.LogCaptureFixture, name: str) -> Event:
    (one,) = [e for e in events(records) if e.arras_event == name]
    return one


# -- a per-person call names its backend on core's operation


def test_an_apply_names_the_backend_on_the_invocation_it_runs_in(records) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created()), replayed(Created(), token="t")]
    with telemetry.operation("arras.invoke", action="catalog.AddUseCase"):
        rig.backend().apply(ALICE, create_plan(), idempotency_key=SECRET)
    attrs = only(records, "arras.invoke").arras_attrs
    assert attrs["backend"] == "truss" and attrs["outcome"] == "ok"
    assert attrs["recovered"] is False
    assert SECRET not in str(attrs)


def test_a_commit_of_unknown_outcome_is_recovered_and_the_invocation_says_so(records) -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [applied(Created()), replayed(Created(), token="landed")]
    with telemetry.operation("arras.invoke"):
        rig.backend().apply(ALICE, create_plan(), idempotency_key="k")
    attrs = only(records, "arras.invoke").arras_attrs
    assert (attrs["backend"], attrs["recovered"]) == ("truss", True)


def test_an_atomic_batch_recovered_from_a_lost_commit_says_so(records) -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [applied(Created()), replayed(Created(), token="landed")]
    with telemetry.operation("arras.invoke_batch"):
        rig.backend().apply_batch(ALICE, [create_plan("a")], atomic=True, idempotency_key="k")
    attrs = only(records, "arras.invoke_batch").arras_attrs
    assert (attrs["backend"], attrs["recovered"]) == ("truss", True)


def test_an_independent_batch_recovered_from_a_lost_commit_says_so(records) -> None:
    rig = ApplyRig()
    rig.commit_failures = [True]
    rig.assembly.outcomes = [
        applied(Created()),
        replayed(Created(), token="landed"),
        applied(Created()),
        replayed(Created(), token="second"),
    ]
    with telemetry.operation("arras.invoke_batch"):
        got = rig.backend().apply_batch(
            ALICE, [create_plan("a"), create_plan("b")], atomic=False, idempotency_key="k"
        )
    assert got.succeeded == 2
    attrs = only(records, "arras.invoke_batch").arras_attrs
    assert (attrs["backend"], attrs["recovered"]) == ("truss", True)


def test_a_committed_write_whose_receipt_could_not_be_read_says_it_committed(records) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [
        applied(Created(), token=ABSENT),
        replayed(Created(), token=""),
        replayed(Created(), token=""),
    ]
    with pytest.raises(Unavailable):
        with telemetry.operation("arras.invoke"):
            rig.backend().apply(ALICE, create_plan(), idempotency_key=SECRET)
    attrs = only(records, "arras.invoke").arras_attrs
    assert attrs["committed"] is True
    assert (attrs["outcome"], attrs["reason"]) == ("error", "unreachable")
    assert SECRET not in str(attrs)


def test_a_write_whose_receipt_was_read_does_not_carry_committed(records) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [applied(Created(), token="t")]
    with telemetry.operation("arras.invoke"):
        rig.backend().apply(ALICE, create_plan(), idempotency_key="k")
    assert "committed" not in only(records, "arras.invoke").arras_attrs


def test_a_refusal_from_the_adapter_still_names_the_backend(records) -> None:
    rig = ApplyRig()
    rig.assembly.outcomes = [failed(GroupOperationFailure("0", artifact_of(code="key_conflict")))]
    backend = rig.backend()
    with pytest.raises(Conflict):
        with telemetry.operation("arras.invoke"):
            backend.apply(ALICE, create_plan(), idempotency_key="k")
    event = only(records, "arras.invoke")
    assert event.arras_attrs["backend"] == "truss"
    assert event.arras_attrs["error.type"] == "Conflict"


def test_a_backend_with_no_connection_source_names_itself_in_its_outage(records) -> None:
    from arras.adapters.truss import TrussBackend

    with pytest.raises(Unavailable):
        with telemetry.operation("arras.query"):
            TrussBackend("truss").query(ALICE, "catalog", None, limit=1)  # type: ignore[arg-type]
    attrs = only(records, "arras.query").arras_attrs
    assert (attrs["backend"], attrs["reason"]) == ("truss", "not_configured")


# -- the lifecycle calls are events of the backend


def test_migrate_is_an_event_with_the_backend_and_the_outcome_only(records) -> None:
    Rig().backend().migrate()
    event = only(records, "arras.backend.migrate")
    assert event.arras_attrs == {
        "backend": "truss",
        "outcome": "ok",
        "duration_ms": event.arras_attrs["duration_ms"],
    }
    assert "owner" not in event.message and "registrar" not in event.message


def test_a_failed_migrate_is_a_warning_with_its_reason(records) -> None:
    rig = Rig()
    rig.raises = {"pg_advisory_xact_lock": StateError("55P03")}
    with pytest.raises(Unavailable):
        rig.backend().migrate(timeout=1)
    event = only(records, "arras.backend.migrate")
    assert event.levelno == logging.WARNING
    assert event.arras_attrs["outcome"] == "error"
    assert event.arras_attrs["reason"] == "migration_failed"
    assert event.arras_attrs["backend"] == "truss"


@needs_toolkit
def test_configure_access_is_an_event_of_the_backend(records) -> None:
    rig = Rig(Script(installed=True, revision=1), module_access=ACCESS)
    backend = rig.backend()
    backend.configure_access()
    for name in ("arras.backend.configure_access",):
        attrs = only(records, name).arras_attrs
        assert (attrs["backend"], attrs["outcome"]) == ("truss", "ok")
    text = " ".join(e.message for e in events(records))
    assert "catalog_reader" not in text and "sandbox" not in text  # no role or document name


# -- core traces migrate


def test_arras_migrate_is_an_event_of_its_own(records) -> None:
    rig = Rig()
    Arras.start({"truss": rig.backend()}).migrate()  # type: ignore[dict-item]
    assert only(records, "arras.migrate").arras_attrs["outcome"] == "ok"
    assert only(records, "arras.backend.migrate").arras_attrs["backend"] == "truss"


def test_a_failed_arras_migrate_is_an_error_event_with_the_reason(records) -> None:
    dropped = telemetry.dropped()
    rig = Rig()
    rig.raises = {"pg_advisory_xact_lock": StateError("55P03")}
    ar = Arras.start({"truss": rig.backend()})  # type: ignore[dict-item]
    with pytest.raises(Unavailable):
        ar.migrate(timeout=1)
    attrs = only(records, "arras.migrate").arras_attrs
    assert (attrs["outcome"], attrs["error.type"], attrs["reason"]) == (
        "error",
        "Unavailable",
        "migration_failed",
    )
    assert telemetry.dropped() == dropped


def test_export_records_is_in_the_event_catalog() -> None:
    # core traces it, and an event outside the catalog is dropped
    assert {"arras.export_records", "arras.migrate"} <= telemetry.EVENTS
