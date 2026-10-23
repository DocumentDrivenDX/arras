# SPDX-License-Identifier: MIT OR Apache-2.0
"""Session, restart, timeout, and settlement cases."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from _lakebase_managed_common import (
    DOCUMENT_ID as _DOCUMENT_ID,
)
from _lakebase_managed_common import (
    MODULE as _MODULE,
)
from _lakebase_managed_common import (
    QUERY as _QUERY,
)
from _lakebase_managed_common import (
    Blocked as _Blocked,
)
from _lakebase_managed_common import (
    Failed as _Failed,
)
from _lakebase_managed_common import (
    allowed as _allowed,
)
from _lakebase_managed_common import (
    digest as _digest,
)
from _lakebase_managed_feed import _feed_delivery, _reconcile
from _lakebase_managed_feed_destination import _reread_page
from _lakebase_managed_native import _native_inventory, _observer_snapshot
from _lakebase_managed_public import _insert_probe, _public_host, _query_probe


def _decode_json_bytea(value: Any) -> bytes | None:
    if value is None:
        return None
    if type(value) is not str or not value.startswith("\\x"):
        return None
    try:
        return bytes.fromhex(value[2:])
    except ValueError:
        return None


def _parse_json_row(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if type(parsed) is dict else {}


def _json_xid(row: dict[str, Any], expected: Any) -> bool:
    return row.get("xid") == expected


def _find_exact_request_receipt(
    inventory: Any, expected_request: bytes, *, expected_actor: str, expected_actor_oid: str
) -> tuple[str, dict[str, Any]]:
    relation = next(
        (item for item in inventory["relations"] if item["name"] == "request_receipt"),
        None,
    )
    if relation is None:
        raise _Failed("original_request_receipt_inventory_missing")
    installation_relation = next(
        (item for item in inventory["relations"] if item["name"] == "catalog_runtime_installation"),
        None,
    )
    installation_rows = (
        installation_relation.get("rows", ()) if installation_relation is not None else ()
    )
    if len(installation_rows) != 1 or type(installation_rows[0]) is not str:
        raise _Failed("original_request_installation_binding_missing")
    installation_id = _parse_json_row(installation_rows[0]).get("installation_id")
    try:
        if type(installation_id) is not str or str(uuid.UUID(installation_id)) != installation_id:
            raise ValueError
    except (TypeError, ValueError):
        raise _Failed("original_request_installation_binding_invalid") from None
    expected_namespace = f"truss-person:{installation_id}:{expected_actor_oid}".encode()
    attempt_relation = next(
        (item for item in inventory["relations"] if item["name"] == "runtime_object_attempt"),
        None,
    )
    if attempt_relation is None:
        raise _Failed("original_request_attempt_inventory_missing")
    attempt_rows = tuple(
        _parse_json_row(raw) for raw in attempt_relation.get("rows", ()) if type(raw) is str
    )
    matches: list[tuple[str, dict[str, Any]]] = []
    for raw in relation.get("rows", ()):
        value = _parse_json_row(raw) if isinstance(raw, str) else {}
        if _decode_json_bytea(value.get("request_id_utf8")) != expected_request:
            continue
        namespace_bytes = _decode_json_bytea(value.get("namespace_identity_utf8"))
        writer_context_bytes = _decode_json_bytea(value.get("original_writer_context_bytes"))
        receipt_bytes = _decode_json_bytea(value.get("original_receipt_bytes"))
        try:
            writer_context = json.loads(writer_context_bytes) if writer_context_bytes else None
            original_receipt = json.loads(receipt_bytes) if receipt_bytes else None
        except (TypeError, ValueError):
            writer_context = None
            original_receipt = None
        attempt_id = writer_context.get("attemptId") if type(writer_context) is dict else None
        try:
            attempt_uuid = str(uuid.UUID(attempt_id)) if type(attempt_id) is str else None
        except ValueError:
            attempt_uuid = None
        attempt = next((row for row in attempt_rows if row.get("id") == attempt_uuid), None)
        storage_row_id = value.get("storage_row_id")
        if (
            namespace_bytes != expected_namespace
            or _decode_json_bytea(value.get("request_sha256"))
            != hashlib.sha256(expected_request).digest()
            or _decode_json_bytea(value.get("namespace_sha256"))
            != hashlib.sha256(namespace_bytes).digest()
            or value.get("payload_state") != "complete"
            or receipt_bytes is None
            or value.get("expired_identity_bytes") is not None
            or type(writer_context) is not dict
            or writer_context.get("profile") != "truss-object-group-writer/0.1"
            or writer_context.get("actor") != expected_actor
            or writer_context.get("actorOid") != expected_actor_oid
            or writer_context.get("xid") != str(value.get("original_writer_xid"))
            or attempt_uuid is None
            or type(original_receipt) is not dict
            or original_receipt.get("profile") != "truss-object-group-receipt/0.1"
            or original_receipt.get("attemptId") != attempt_uuid
            or attempt is None
            or attempt.get("complete") is not True
            or str(attempt.get("actor_oid")) != expected_actor_oid
            or str(attempt.get("writer_xid")) != str(value.get("original_writer_xid"))
            or type(storage_row_id) is not int
            or attempt.get("receipt_id") != storage_row_id
        ):
            raise _Failed("original_request_receipt_binding_invalid")
        matches.append((raw, value))
    if len(matches) != 1:
        raise _Failed("original_request_receipt_cardinality_mismatch")
    return matches[0]


def _require_receipt_journal_binding(inventory: Any, receipt: Mapping[str, Any]) -> None:
    rows = next(
        (item.get("rows", ()) for item in inventory["relations"] if item["name"] == "journal"),
        (),
    )
    original_xid = receipt.get("original_writer_xid")
    if not any(
        _json_xid(_parse_json_row(raw), original_xid) for raw in rows if isinstance(raw, str)
    ):
        raise _Failed("original_request_journal_binding_missing")


def _adopt_readonly_handle(connection: Any) -> tuple[Any, Any, Any]:
    from truss import CatalogRuntimeConfiguration, Ok, adopt_psycopg_host, create_reference_assembly

    if int(connection.info.transaction_status) != 0:
        raise _Blocked("connection_not_idle")
    connection.execute("BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY")
    host = adopt_psycopg_host(connection, statement_timeout_ms=10_000, operation_timeout_ms=30_000)
    transaction = host.adopt_transaction(access_mode="read_only")
    assembly = create_reference_assembly(CatalogRuntimeConfiguration(), host)
    if not isinstance(transaction, Ok) or not isinstance(assembly, Ok):
        host.detach()
        raise _Blocked("transaction_or_assembly_adoption_failed")
    return host, transaction.value, assembly.value


def _foreign_handle_refused(result: Any) -> bool:
    """Accept only the host's typed foreign-transaction refusal."""
    from truss import Error

    return isinstance(result, Error) and result.error.code == "invalid_transaction"


def _ended_session_result_has_no_rows(result: Any) -> bool:
    """Reject any successful public result from a supposedly ended session."""
    from truss import Error, Ok

    if isinstance(result, Error):
        return result.error.code == "invalid_transaction"
    if not isinstance(result, Ok):
        return False
    if type(result.value).__name__ == "QueryRows":
        return False
    return type(result.value).__name__ in {"QueryRefused", "QueryUnavailable"}


def _connection_is_broken(connection: Any) -> bool:
    """Require psycopg to independently report a closed or unknown connection."""
    try:
        connection.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()
    except Exception:
        try:
            closed = int(connection.closed)
            status = int(connection.info.transaction_status)
        except (AttributeError, TypeError, ValueError):
            return False
        return closed != 0 or status == 4
    return False


def _backend_pid(connection: Any, code: str) -> int:
    """Read psycopg's existing backend PID without starting a transaction with SQL."""
    pid = getattr(connection.info, "backend_pid", None)
    if type(pid) is not int or pid <= 0:
        raise _Blocked(code)
    return pid


def _end_session(inputs: Any, connection: Any, terminate: Any, pid: int) -> str:
    if not callable(terminate):
        connection.close()
        return hashlib.sha256(b"client-closed-original-connection").hexdigest()
    event = terminate(actor_label="reader", backend_pid=pid)
    if type(event) is not dict or set(event) != {
        "resource_sha256",
        "backend_pid",
        "operation_sha256",
    }:
        raise _Blocked("session_termination_fact_invalid")
    if event["backend_pid"] != pid:
        raise _Failed("session_termination_target_mismatch")
    resource = _digest(event["resource_sha256"], "session_resource_identity_unavailable")
    expected = hashlib.sha256(inputs.target["provider_resource_id"].encode("utf-8")).hexdigest()
    if resource != expected:
        raise _Failed("session_termination_resource_mismatch")
    return _digest(event["operation_sha256"], "session_operation_hash_unavailable")


def _restart_facts(inputs: Any, callback: Any) -> tuple[str, str, str, str]:
    try:
        event = callback()
    except Exception:
        raise _Failed("compute_restart_control_failed") from None
    required = {"resource_sha256", "operation_sha256", "generation_before", "generation_after"}
    if type(event) is not dict or set(event) != required:
        raise _Blocked("compute_restart_fact_shape_invalid")
    resource = _digest(event["resource_sha256"], "restart_resource_identity_unavailable")
    operation = _digest(event["operation_sha256"], "restart_operation_identity_unavailable")
    before = _digest(event["generation_before"], "restart_generation_before_unavailable")
    after = _digest(event["generation_after"], "restart_generation_after_unavailable")
    expected = hashlib.sha256(inputs.target["provider_resource_id"].encode("utf-8")).hexdigest()
    if resource != expected or before == after:
        raise _Failed("compute_restart_resource_or_generation_mismatch")
    return operation, before, after, resource


def _run_session_lease(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, "MP-02")
    source = sources.get("person_connection_source")
    terminate = controls.get("terminate_session")
    if not callable(source):
        raise _Blocked("person_connection_source_unavailable")
    principal = principals.get("reader")
    if principal is None:
        raise _Blocked("reader_principal_unavailable")
    with source(principal) as connection:
        pid = _backend_pid(connection, "backend_pid_unavailable")
        host, transaction, assembly = _adopt_readonly_handle(connection)
        try:
            termination_hash = _end_session(inputs, connection, terminate, pid)
            stale = assembly.query_in_transaction(
                transaction,
                sql=_QUERY,
                document_ids=(_DOCUMENT_ID,),
                maximum_rows=100,
                maximum_scan_rows=1000,
                maximum_bytes=262_144,
            )
            if not _ended_session_result_has_no_rows(stale) or not _connection_is_broken(
                connection
            ):
                raise _Failed("ended_session_handle_still_usable")
        finally:
            try:
                host.detach()
            except Exception:
                pass
    with source(principal) as replacement_connection:
        replacement_host, replacement_transaction, replacement_assembly = _adopt_readonly_handle(
            replacement_connection
        )
        try:
            stale_on_replacement = replacement_assembly.query_in_transaction(
                transaction,
                sql=_QUERY,
                document_ids=(_DOCUMENT_ID,),
                maximum_rows=100,
                maximum_scan_rows=1000,
                maximum_bytes=262_144,
            )
            if not _foreign_handle_refused(stale_on_replacement):
                raise _Failed("ended_session_handle_rebound_to_replacement_host")
            fresh = replacement_assembly.query_in_transaction(
                replacement_transaction,
                sql=_QUERY,
                document_ids=(_DOCUMENT_ID,),
                maximum_rows=100,
                maximum_scan_rows=1000,
                maximum_bytes=262_144,
            )
            from truss import Ok

            if not isinstance(fresh, Ok) or type(fresh.value).__name__ != "QueryRows":
                raise _Failed("replacement_session_public_query_failed")
        finally:
            try:
                replacement_host.detach()
            except Exception:
                pass
    rows = _query_probe(backend, principal)
    return {
        "ended_backend_pid": pid,
        "termination_operation_sha256": termination_hash,
        "old_handle_refused": True,
        "new_session_row_count": len(rows),
        "old_handle_rebound": False,
    }


def _run_restart(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, "MP-01")
    restart = controls.get("restart_compute")
    if not callable(restart):
        raise _Blocked("compute_restart_control_unavailable")
    principal = principals.get("writer")
    if principal is None:
        raise _Blocked("writer_principal_unavailable")
    before = _observer_snapshot(sources)
    host = _public_host(backend, principals.get("registrar"))
    prefix = uuid.uuid4().hex[:10]
    _insert_probe(
        host, principal, "durable-one", code="mp01-" + prefix + "-a", key="mp01-" + prefix + "-a"
    )
    _insert_probe(
        host, principal, "durable-two", code="mp01-" + prefix + "-b", key="mp01-" + prefix + "-b"
    )
    feed_facts = _feed_delivery(
        controls=controls,
        sources=sources,
        principals=principals,
        module_access=inputs.target["resources"]["module_access"],
        consumer_id="mp01-" + prefix,
        backend=backend,
        return_private=True,
    )
    feed_private = feed_facts.pop("_private")
    populated = _observer_snapshot(sources)
    if populated["sha256"] == before["sha256"]:
        raise _Failed("public_population_not_visible_in_native_inventory")
    installer_source = sources.get("installer_connection_source")
    if not callable(installer_source):
        raise _Blocked("installer_observer_unavailable")
    old_connection_ended = False
    with installer_source() as connection:
        pid_before = _backend_pid(connection, "backend_pid_before_restart_unavailable")
        operation_hash, generation_before, generation_after, _resource_hash = _restart_facts(
            inputs, restart
        )
        try:
            connection.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()
        except Exception:
            old_connection_ended = True
    if not old_connection_ended:
        raise _Failed("pre_restart_session_remained_usable")
    rows = _query_probe(backend, principal)
    expected = {("mp01-" + prefix + "-a", "durable-one"), ("mp01-" + prefix + "-b", "durable-two")}
    if not expected.issubset({(row.get("code"), row.get("value")) for row in rows}):
        raise _Failed("public_objects_not_durable_after_restart")
    with installer_source() as connection:
        pid_after = _backend_pid(connection, "backend_pid_after_restart_unavailable")
        after = _native_inventory(connection)
    if pid_before == pid_after or after["sha256"] != populated["sha256"]:
        raise _Failed("managed_state_or_new_session_not_proven_after_restart")
    for delivery in feed_private["deliveries"]:
        _reread_page(sources["person_connection_source"], delivery["reader"], delivery["page"])
        _reconcile(
            sources["person_connection_source"],
            delivery["reader"],
            delivery["page"],
            destination_id=delivery["destination_id"],
            request_hash=delivery["request_hash"],
            publication_id=delivery["publication_id"],
            receipt=delivery["receipt"],
        )
    return {
        "operation_sha256": operation_hash,
        "generation_before_sha256": generation_before,
        "generation_after_sha256": generation_after,
        "backend_pid_changed": True,
        "public_object_count": len(expected),
        "native_inventory_sha256": after["sha256"],
        "feed": feed_facts,
    }


def _fault_event_cursor(controls: Mapping[str, Any]) -> int:
    callback = controls.get("fault_events")
    if not callable(callback):
        raise _Blocked("transport_fault_event_control_unavailable")
    try:
        events = callback()
    except Exception:
        raise _Failed("transport_fault_event_observation_failed") from None
    if type(events) not in {tuple, list}:
        raise _Blocked("transport_fault_event_shape_invalid")
    sequence = [
        event.get("sequence")
        for event in events
        if type(event) is dict and type(event.get("sequence")) is int
    ]
    return max(sequence, default=0)


def _fault_events(
    controls: Mapping[str, Any],
    actor: str,
    mode: str,
    *,
    after_sequence: int,
    request_sha256: str | None = None,
    publication_sha256: str | None = None,
    page_sha256: str | None = None,
) -> tuple[dict[str, Any], ...]:
    callback = controls.get("fault_events")
    if not callable(callback):
        raise _Blocked("transport_fault_event_control_unavailable")
    try:
        events = callback()
    except Exception:
        raise _Failed("transport_fault_event_observation_failed") from None
    if type(events) not in {tuple, list}:
        raise _Blocked("transport_fault_event_shape_invalid")
    selected: list[dict[str, Any]] = []
    all_sequences: list[int] = []
    phases = {
        "commit_entered",
        "ack_entered",
        "transport_interrupted",
        "provider_restart_completed",
        "driver_returned",
        "driver_error",
        "connection_closed",
    }
    for event in events:
        if type(event) is not dict or set(event) != {
            "sequence",
            "actor_label",
            "fault_mode",
            "phase",
            "connection_generation",
            "request_sha256",
            "publication_sha256",
            "page_sha256",
        }:
            raise _Blocked("transport_fault_event_shape_invalid")
        if (
            type(event["sequence"]) is not int
            or type(event["actor_label"]) is not str
            or type(event["fault_mode"]) is not str
            or event["phase"] not in phases
        ):
            raise _Blocked("transport_fault_event_shape_invalid")
        all_sequences.append(event["sequence"])
        _digest(event["connection_generation"], "transport_generation_unavailable")
        for key in ("request_sha256", "publication_sha256", "page_sha256"):
            if event[key] is not None:
                _digest(event[key], "transport_request_binding_invalid")
        if (
            event["sequence"] > after_sequence
            and event["actor_label"] == actor
            and event["fault_mode"] == mode
        ):
            if (
                event["request_sha256"] != request_sha256
                or event["publication_sha256"] != publication_sha256
                or event["page_sha256"] != page_sha256
            ):
                raise _Failed("transport_fault_request_binding_mismatch")
            selected.append(event)
    if all_sequences != sorted(set(all_sequences)):
        raise _Blocked("transport_fault_event_sequence_invalid")
    selected_phases = [event["phase"] for event in selected]
    generations = {event["connection_generation"] for event in selected}
    try:
        commit_position = selected_phases.index("commit_entered")
        interrupt_position = selected_phases.index("transport_interrupted")
        outcome_position = next(
            index
            for index, phase in enumerate(selected_phases)
            if phase in {"driver_returned", "driver_error"}
        )
        closed_position = selected_phases.index("connection_closed")
    except ValueError:
        raise _Failed("genuine_transport_interruption_not_observed") from None
    if (
        not selected
        or len(generations) != 1
        or len(selected_phases) != len(set(selected_phases))
        or not commit_position < interrupt_position < outcome_position < closed_position
    ):
        raise _Failed("genuine_transport_interruption_not_observed")
    return tuple(selected)


def _faulting_backend(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    mode: str,
    *,
    request_sha256: str | None = None,
    publication_sha256: str | None = None,
    page_sha256: str | None = None,
    observed_actor: dict[str, str] | None = None,
) -> Any:
    from arras.adapters.truss import ModuleAccess, create_backend

    callback = controls.get("fault_person_connection_source")
    if not callable(callback):
        raise _Blocked("genuine_transport_fault_control_unavailable")
    labels = {principal.user: label for label, principal in principals.items()}

    @contextmanager
    def fault_source(principal: Any) -> Any:
        label = labels.get(principal.user)
        if label is None:
            raise _Blocked("fault_actor_not_authorized")
        source_context = callback(
            actor_label=label,
            fault_mode=mode,
            request_sha256=request_sha256,
            publication_sha256=publication_sha256,
            page_sha256=page_sha256,
        )
        with source_context as connection:
            actor_oid = _verify_fault_connection(connection, inputs.target, principal)
            if observed_actor is not None and label == "writer":
                observed_actor["actor"] = principal.user
                observed_actor["actor_oid"] = actor_oid
            yield connection

    module = inputs.target["resources"]["module_access"]
    access = ModuleAccess(
        document_id=inputs.target["resources"]["module_access"]["document_id"],
        reader_role=module["reader_role"],
        writer_role=module["writer_role"],
        auditor_role=module.get("auditor_role"),
    )
    return create_backend(
        "truss",
        fault_source,
        sources.get("installer_connection_source"),
        module_access={_MODULE: access},
        tolerated_grantees=tuple(inputs.target["resources"]["tolerated_grantees"]),
    )


def _verify_fault_connection(connection: Any, target: Mapping[str, Any], principal: Any) -> str:
    endpoint = target.get("endpoint")
    if type(endpoint) is not dict:
        raise _Blocked("fault_endpoint_unavailable")
    info = getattr(connection, "info", None)
    parameters = getattr(info, "dsn_parameters", None)
    pgconn = getattr(connection, "pgconn", None)
    if (
        info is None
        or type(parameters) is not dict
        or getattr(info, "host", None) != endpoint.get("host")
        or getattr(info, "port", None) != endpoint.get("port")
        or getattr(info, "dbname", None) != endpoint.get("database")
        or parameters.get("sslmode") != "verify-full"
        or not parameters.get("sslrootcert")
        or getattr(pgconn, "ssl_in_use", False) is not True
    ):
        raise _Failed("fault_connection_endpoint_or_tls_mismatch")
    try:
        row = connection.execute(
            "SELECT session_user, current_user, current_setting('role'), current_database(), "
            "(SELECT oid::text FROM pg_catalog.pg_roles WHERE rolname=session_user), "
            "(SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid())"
        ).fetchone()
    except Exception:
        connection.rollback()
        raise _Failed("fault_connection_identity_unavailable") from None
    finally:
        try:
            connection.rollback()
        except Exception:
            pass
    if (
        type(row) not in {tuple, list}
        or len(row) != 6
        or row[0] != principal.user
        or row[1] != principal.user
        or row[2] not in {"none", ""}
        or row[3] != endpoint.get("database")
        or type(row[4]) is not str
        or not row[4].isdigit()
        or row[5] is not True
        or int(connection.info.transaction_status) != 0
    ):
        raise _Failed("fault_connection_identity_or_tls_mismatch")
    return row[4]


def _run_commit_fault(
    case: str,
    mode: str,
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, case)
    writer = principals.get("writer")
    registrar = principals.get("registrar")
    if writer is None or registrar is None:
        raise _Blocked("authorized_writer_or_registrar_unavailable")
    before = _observer_snapshot(sources)
    request = uuid.uuid4().hex
    code = f"{case.lower().replace('-', '')}-{request[:16]}"
    stable_key = f"arras-{case.lower()}-{request}"
    request_id = f"{_MODULE}.CreateProbe:{stable_key}".encode()
    request_sha256 = hashlib.sha256(request_id).hexdigest()
    fault_actor: dict[str, str] = {}
    broken = _faulting_backend(
        inputs,
        controls,
        sources,
        principals,
        mode,
        request_sha256=request_sha256,
        observed_actor=fault_actor,
    )
    host = _public_host(broken, registrar)
    event_cursor = _fault_event_cursor(controls)
    from arras.adapters.truss import CommitUnknown
    from arras.results import Receipt

    outcome: Any = None
    failure: Exception | None = None
    try:
        outcome = _insert_probe(host, writer, "managed-fault", code=code, key=stable_key)
    except Exception as exc:
        failure = exc
    events = _fault_events(
        controls,
        "writer",
        mode,
        after_sequence=event_cursor,
        request_sha256=request_sha256,
    )
    event_phases = tuple(event["phase"] for event in events)
    driver_reported_error = "driver_error" in event_phases
    if (
        not (isinstance(outcome, Receipt) or isinstance(failure, CommitUnknown))
        or not driver_reported_error
    ):
        raise _Failed("public_mutation_commit_fault_not_observed")
    retry_host = _public_host(backend, registrar)
    retry = _insert_probe(retry_host, writer, "managed-fault", code=code, key=stable_key)
    rows = _query_probe(backend, principals.get("reader"))
    matches = [
        row for row in rows if row.get("code") == code and row.get("value") == "managed-fault"
    ]
    after = _observer_snapshot(sources)
    if len(matches) != 1:
        raise _Failed("idempotent_retry_did_not_settle_exactly_once")
    # Verify exactly one original Truss request receipt is retained; never expose
    # receipt payloads, which may contain user inputs.
    receipt_raw, receipt_facts = _find_exact_request_receipt(
        after,
        f"{_MODULE}.CreateProbe:{stable_key}".encode(),
        expected_actor=writer.user,
        expected_actor_oid=fault_actor.get("actor_oid", ""),
    )
    _require_receipt_journal_binding(after, receipt_facts)
    if after["sha256"] == before["sha256"]:
        raise _Failed("committed_request_missing_from_native_state")
    return {
        "fault_mode": mode,
        "transport_event_count": len(events),
        "transport_phases": event_phases,
        "public_initial_outcome_type": (
            "CommitUnknown" if isinstance(failure, CommitUnknown) else type(outcome).__name__
        ),
        "idempotency_retry_receipt_type": type(retry).__name__,
        "exactly_one_public_object": True,
        "original_request_receipt_sha256": hashlib.sha256(receipt_raw.encode()).hexdigest(),
        "native_before_sha256": before["sha256"],
        "native_after_sha256": after["sha256"],
    }


def _run_mp05(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, "MP-05")
    source = sources.get("person_connection_source")
    observe = controls.get("observe_settings")
    if not callable(source) or not callable(observe):
        raise _Blocked("native_settings_observation_unavailable")
    principal = principals.get("writer")
    if principal is None:
        raise _Blocked("writer_principal_unavailable")
    with source(principal) as connection:
        try:
            raw = observe(connection)
        except Exception:
            raise _Failed("native_setting_observation_failed") from None
        required = {
            "server_version_num",
            "statement_timeout_ms",
            "lock_timeout_ms",
            "default_transaction_isolation",
            "transaction_isolation",
            "transaction_read_only",
        }
        if type(raw) is not dict or set(raw) != required:
            raise _Blocked("native_setting_observation_shape_invalid")
        if (
            type(raw["server_version_num"]) is not str
            or type(raw["statement_timeout_ms"]) is not int
            or type(raw["lock_timeout_ms"]) is not int
            or type(raw["default_transaction_isolation"]) is not str
            or type(raw["transaction_isolation"]) is not str
            or type(raw["transaction_read_only"]) is not bool
        ):
            raise _Blocked("native_setting_observation_type_invalid")
        server_version = connection.execute("SHOW server_version_num").fetchone()
        if server_version != (raw["server_version_num"],):
            raise _Failed("settings_callback_not_bound_to_connection")
        # The settings observer may have opened an implicit read transaction.
        connection.rollback()
        connection.execute("BEGIN")
        connection.execute("SET LOCAL statement_timeout = '50ms'")
        sqlstate: str | None = None
        try:
            connection.execute("SELECT pg_catalog.pg_sleep(0.250)")
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate != "57014":
            connection.rollback()
            raise _Failed("bounded_statement_timeout_not_observed")
        if int(connection.info.transaction_status) != 3:
            connection.rollback()
            raise _Failed("cancelled_transaction_not_aborted")
        connection.rollback()
    return {
        "server_version_num": raw["server_version_num"],
        "configured_statement_timeout_ms": raw["statement_timeout_ms"],
        "configured_lock_timeout_ms": raw["lock_timeout_ms"],
        "bounded_timeout_sqlstate": sqlstate,
        "transaction_aborted_then_rolled_back": True,
        "genuine_commit_fault": _run_commit_fault(
            "MP-05",
            "cut_transport_during_commit",
            inputs,
            controls,
            sources,
            principals,
            backend,
        ),
    }
