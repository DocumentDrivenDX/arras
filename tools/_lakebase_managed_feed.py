# SPDX-License-Identifier: MIT OR Apache-2.0
"""Public Truss feed delivery and durable destination verification."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import DOCUMENT_ID as _DOCUMENT_ID
from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_feed_codec import (
    _MAX_FEED_PAGES,
    _MAX_PAGE_BYTES,
    _MAX_TOTAL_FEED_BYTES,
    _canonical,
    _sha256,
)
from _lakebase_managed_feed_destination import (
    _acknowledge,
    _apply_destination,
    _destination_reopened,
    _reconcile,
)
from _lakebase_managed_feed_pages import _decode_feed_page
from _lakebase_managed_feed_probe import (
    _load_probe_schema_binding,
    _validate_probe_schema_binding,
    _verify_replica_query,
)


def _feed_capability(connection: Any, *, access_mode: str) -> tuple[Any, Any, Any, Any]:
    from truss import CatalogRuntimeConfiguration, Ok, adopt_psycopg_host, create_reference_assembly

    if int(connection.info.transaction_status) != 0:
        raise _Blocked("feed_connection_not_idle")
    connection.execute(
        "BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY"
        if access_mode == "read_only"
        else "BEGIN ISOLATION LEVEL READ COMMITTED READ WRITE"
    )
    connection.execute("SET LOCAL statement_timeout = '2000ms'")
    host = adopt_psycopg_host(connection, statement_timeout_ms=10_000, operation_timeout_ms=30_000)
    transaction = host.adopt_transaction(access_mode=access_mode)
    assembly = create_reference_assembly(CatalogRuntimeConfiguration(), host)
    if not isinstance(transaction, Ok) or not isinstance(assembly, Ok):
        try:
            host.detach()
        except Exception:
            pass
        raise _Blocked("feed_truss_api_unavailable")
    provider = assembly.value.feed(assembly.value.feed_selection)
    if getattr(provider, "status", None) != "ok":
        host.detach()
        raise _Blocked("feed_capability_unavailable")
    return host, transaction.value, assembly.value, provider.capability


def _register_consumer(installer_source: Any, consumer_id: str, reader_role: str) -> None:
    from truss import Ok

    with installer_source() as connection:
        host, transaction, assembly, _feed = _feed_capability(connection, access_mode="read_write")
        try:
            result = assembly.register_feed_consumer_in_transaction(
                transaction, consumer_id=consumer_id, reader_role=reader_role
            )
            if not isinstance(result, Ok) or type(result.value).__name__ != "FeedConsumer":
                raise _Failed("feed_consumer_registration_failed")
        finally:
            if host.detach() is not True:
                raise _Failed("feed_registration_detach_failed")
            connection.commit()


def _read_page(person_source: Any, reader: Any, consumer_id: str) -> Any:
    from truss import Ok

    with person_source(reader) as connection:
        host, transaction, _assembly, feed = _feed_capability(connection, access_mode="read_only")
        try:
            first = feed.read_feed_in_transaction(
                transaction,
                consumer_id=consumer_id,
                maximum_facts=4096,
                maximum_bytes=_MAX_PAGE_BYTES,
            )
            replay = feed.read_feed_in_transaction(
                transaction,
                consumer_id=consumer_id,
                maximum_facts=4096,
                maximum_bytes=_MAX_PAGE_BYTES,
            )
            if not isinstance(first, Ok) or type(first.value).__name__ != "FeedPage":
                raise _Failed("feed_page_unavailable")
            page = first.value
            if (
                not isinstance(replay, Ok)
                or type(replay.value).__name__ != "FeedPage"
                or replay.value.content != page.content
                or replay.value.sha256 != page.sha256
                or replay.value.prior != page.prior
                or replay.value.next != page.next
            ):
                raise _Failed("unacknowledged_feed_replay_mismatch")
            return page
        finally:
            if host.detach() is not True:
                raise _Failed("feed_read_detach_failed")
            connection.rollback()


def _decode_page_with_pg_canonicalizer(
    person_source: Any,
    reader: Any,
    page: Any,
    *,
    consumer_id: str,
    expected_owner: Mapping[str, Any],
    expected_prior: bytes | None,
    expected_cursor_identity: tuple[str, str, str] | None,
    schema_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    with person_source(reader) as connection:
        if int(connection.info.transaction_status) != 0:
            raise _Blocked("feed_canonicalizer_connection_not_idle")
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '2000ms'")

        def ordered_event_digest(event_bytes: bytes) -> str:
            row = connection.execute(
                "SELECT encode(sha256(convert_to(pg_catalog.jsonb_build_array("
                "convert_from(%s, 'UTF8')::jsonb - 'mutationGroup')::text, 'UTF8')), 'hex')",
                (event_bytes,),
            ).fetchone()
            if type(row) not in {tuple, list} or len(row) != 1:
                raise _Blocked("feed_event_canonicalization_unavailable")
            return _sha256_hex(row[0])

        try:
            return _decode_feed_page(
                page,
                consumer_id=consumer_id,
                expected_owner=expected_owner,
                expected_prior=expected_prior,
                expected_cursor_identity=expected_cursor_identity,
                schema_binding=schema_binding,
                ordered_event_digest=ordered_event_digest,
            )
        finally:
            connection.rollback()


def _sha256_hex(value: Any) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise _Blocked("feed_event_canonicalization_unavailable")
    return value


def _drain_feed_pages(
    *,
    person_source: Any,
    reader: Any,
    consumer_id: str,
    destination_source: Any,
    destination_id: str,
    expected_owner: Mapping[str, Any],
    schema_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    deliveries: list[dict[str, Any]] = []
    page_hashes: list[str] = []
    expected_prior: bytes | None = None
    cursor_identity: tuple[str, str, str] | None = None
    total_bytes = 0
    transaction_pages = 0
    total_receipts = bytearray()
    empty_page_seen = False
    for _page_index in range(_MAX_FEED_PAGES):
        page = _read_page(person_source, reader, consumer_id)
        decoded = _decode_page_with_pg_canonicalizer(
            person_source,
            reader,
            page,
            consumer_id=consumer_id,
            expected_owner=expected_owner,
            expected_prior=expected_prior,
            expected_cursor_identity=cursor_identity,
            schema_binding=schema_binding,
        )
        if empty_page_seen:
            raise _Failed("feed_page_after_empty_interval")
        total_bytes += decoded["payload_bytes"]
        if total_bytes > _MAX_TOTAL_FEED_BYTES:
            raise _Blocked("feed_aggregate_bound_exceeded")
        if decoded["outcome"] == "transaction":
            transaction_pages += 1
        elif decoded["outcome"] == "empty_interval":
            empty_page_seen = True
        publication_id = "publication-" + uuid.uuid4().hex
        receipt, destination_state, request_hash = _apply_destination(
            destination_source, destination_id, publication_id, page, decoded
        )
        _acknowledge(
            person_source,
            reader,
            page,
            destination_id=destination_id,
            request_hash=request_hash,
            publication_id=publication_id,
            receipt=receipt,
        )
        _reconcile(
            person_source,
            reader,
            page,
            destination_id=destination_id,
            request_hash=request_hash,
            publication_id=publication_id,
            receipt=receipt,
        )
        _destination_reopened(destination_source, destination_id, destination_state)
        expected_prior = decoded["next"]
        cursor_identity = decoded["cursor_identity"]
        page_hashes.append(page.sha256)
        total_receipts.extend(len(receipt).to_bytes(8, "big"))
        total_receipts.extend(receipt)
        deliveries.append(
            {
                "reader": reader,
                "page": page,
                "decoded": decoded,
                "destination_id": destination_id,
                "publication_id": publication_id,
                "request_hash": request_hash,
                "receipt": receipt,
            }
        )
        if empty_page_seen:
            break
    if not empty_page_seen:
        raise _Blocked("feed_drain_bound_exceeded")
    if transaction_pages < 1:
        raise _Blocked("feed_drain_contains_no_transaction")
    return {
        "deliveries": deliveries,
        "page_sha256": _sha256(_canonical(page_hashes)),
        "receipt_sha256": _sha256(bytes(total_receipts)),
        "payload_bytes": total_bytes,
        "transaction_page_count": transaction_pages,
        "empty_interval_drained": empty_page_seen,
    }


def _feed_delivery(
    *,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    module_access: Mapping[str, Any],
    consumer_id: str,
    backend: Any | None = None,
    return_private: bool = False,
) -> dict[str, Any]:
    destination_source = controls.get("open_feed_destination")
    installer_source = sources.get("installer_connection_source")
    person_source = sources.get("person_connection_source")
    if not all(callable(item) for item in (destination_source, installer_source, person_source)):
        raise _Blocked("feed_destination_or_connection_source_unavailable")
    reader_role = module_access.get("reader_role")
    if type(reader_role) is not str:
        raise _Blocked("feed_reader_role_unavailable")
    from _lakebase_operations import HARNESS_MODULE_SHA256

    if (
        module_access.get("document_id") != _DOCUMENT_ID
        or module_access.get("source_sha256") != HARNESS_MODULE_SHA256
    ):
        raise _Blocked("feed_probe_schema_binding_unavailable")
    reader = principals.get("reader")
    if reader is None:
        raise _Blocked("reader_principal_unavailable")
    _register_consumer(installer_source, consumer_id, reader_role)
    destination_id = "arras-lakebase-" + uuid.uuid4().hex
    expected_owner = {
        "document_id": module_access.get("document_id"),
        "module_id": "lakebase_qualification",
    }
    if type(expected_owner["document_id"]) is not str or not expected_owner["document_id"]:
        raise _Blocked("feed_module_owner_unavailable")
    schema_binding = _load_probe_schema_binding(sources)
    if schema_binding["document_sha256"] != module_access.get("source_sha256"):
        raise _Blocked("feed_probe_document_binding_unavailable")
    if backend is not None:
        _validate_probe_schema_binding(backend, reader)
    drained = _drain_feed_pages(
        person_source=person_source,
        reader=reader,
        consumer_id=consumer_id,
        destination_source=destination_source,
        destination_id=destination_id,
        expected_owner=expected_owner,
        schema_binding=schema_binding,
    )
    if backend is not None:
        _verify_replica_query(backend, reader, drained["deliveries"], schema_binding)
    facts = {
        "consumer_id_sha256": hashlib.sha256(consumer_id.encode("utf-8")).hexdigest(),
        "feed_page_sha256": drained["page_sha256"],
        "feed_page_count": len(drained["deliveries"]),
        "transaction_page_count": drained["transaction_page_count"],
        "empty_interval_drained": drained["empty_interval_drained"],
        "feed_payload_bytes": drained["payload_bytes"],
        "unacknowledged_replay_equal": True,
        "destination_receipt_sha256": drained["receipt_sha256"],
        "source_ack_reconciled": "matched",
        "destination_reopened_equal": True,
        "destination_replay_equal": True,
    }
    if return_private:
        facts["_private"] = {
            "reader": reader,
            "deliveries": drained["deliveries"],
            "schema_binding": schema_binding,
        }
    return facts
