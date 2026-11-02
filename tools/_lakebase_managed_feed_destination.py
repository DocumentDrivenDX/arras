# SPDX-License-Identifier: MIT OR Apache-2.0
"""Durable semantic destination, receipts, and replay checks for MP-04."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_feed_codec import _canonical, _sha256


def _apply_destination(
    destination_source: Any,
    destination_id: str,
    publication_id: str,
    page: Any,
    decoded: Mapping[str, Any],
) -> tuple[bytes, Any, str]:
    request_hash = hashlib.sha256(page.content).hexdigest()
    with destination_source(destination_id=destination_id) as destination:
        before = destination.snapshot()
        if type(before) is not dict or set(before) != {"records", "receipts", "facts", "entities"}:
            raise _Blocked("feed_destination_snapshot_invalid")
        before_records = _snapshot_rows(before, "records")
        before_receipts = _snapshot_rows(before, "receipts")
        before_facts = _snapshot_rows(before, "facts")
        before_entities = _snapshot_rows(before, "entities")
        receipt = destination.apply_page(
            page_content=page.content,
            page_sha256=page.sha256,
            request_sha256=request_hash,
            publication_id=publication_id,
            semantic_page=decoded["semantic"],
        )
        if type(receipt) is not bytes or not receipt:
            raise _Failed("feed_destination_receipt_missing")
        after = destination.snapshot()
        if type(after) is not dict or set(after) != {"records", "receipts", "facts", "entities"}:
            raise _Blocked("feed_destination_snapshot_invalid")
        semantic_raw = _canonical(decoded["semantic"])
        expected_record = (
            page.sha256,
            request_hash,
            publication_id,
            page.content,
            _sha256(semantic_raw),
            semantic_raw,
        )
        expected_receipt_row = (receipt,)
        after_records = _snapshot_rows(after, "records")
        after_receipts = _snapshot_rows(after, "receipts")
        after_facts = _snapshot_rows(after, "facts")
        after_entities = _snapshot_rows(after, "entities")
        expected_facts = tuple(
            (
                publication_id,
                fact["kind"],
                fact["writer_xid"],
                fact["sequence"],
                fact["profile"],
                fact["sha256"],
                _canonical(fact["semantic"]),
            )
            for fact in decoded["facts"]
        )
        expected_entities = tuple(
            (
                publication_id,
                entity["source_epoch"],
                entity["writer_xid"],
                entity["sequence"],
                entity["entity_kind"],
                entity["entity_id"],
                entity["entity_type"],
                entity["document_id"],
                entity["module_id"],
                entity["definition_pin"],
                entity["record_version"],
                entity["catalog_revision"],
                _canonical(entity["properties"]),
                _canonical(entity["retained"]),
                entity["event_sha256"],
            )
            for entity in decoded["entities"]
        )
        if Counter(after_records) != Counter((*before_records, expected_record)):
            raise _Failed("feed_destination_record_transition_mismatch")
        if Counter(after_receipts) != Counter((*before_receipts, expected_receipt_row)):
            raise _Failed("feed_destination_receipt_transition_mismatch")
        if Counter(after_facts) != Counter((*before_facts, *expected_facts)):
            raise _Failed("feed_destination_semantic_fact_transition_mismatch")
        if Counter(after_entities) != Counter((*before_entities, *expected_entities)):
            raise _Failed("feed_destination_semantic_entity_transition_mismatch")
        after_frozen = {
            "records": after_records,
            "receipts": after_receipts,
            "facts": after_facts,
            "entities": after_entities,
        }
        replayed_receipt = destination.apply_page(
            page_content=page.content,
            page_sha256=page.sha256,
            request_sha256=request_hash,
            publication_id=publication_id,
            semantic_page=decoded["semantic"],
        )
        if type(replayed_receipt) is not bytes or replayed_receipt != receipt:
            raise _Failed("feed_destination_replay_receipt_mismatch")
        replay_snapshot = destination.snapshot()
        if (
            type(replay_snapshot) is not dict
            or set(replay_snapshot) != {"records", "receipts", "facts", "entities"}
            or any(
                _snapshot_rows(replay_snapshot, key) != after_frozen[key]
                for key in ("records", "receipts", "facts", "entities")
            )
        ):
            raise _Failed("feed_destination_replay_mutated_state")
    return receipt, after_frozen, request_hash


def _snapshot_rows(snapshot: Mapping[str, Any], key: str) -> tuple[tuple[Any, ...], ...]:
    rows = snapshot.get(key)
    if type(rows) not in {tuple, list}:
        raise _Blocked("feed_destination_snapshot_invalid")
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if type(row) not in {tuple, list}:
            raise _Blocked("feed_destination_snapshot_invalid")
        normalized.append(tuple(row))
    return tuple(normalized)


def _acknowledge(
    person_source: Any,
    reader: Any,
    page: Any,
    *,
    destination_id: str,
    request_hash: str,
    publication_id: str,
    receipt: bytes,
) -> None:
    from _lakebase_managed_feed import _feed_capability
    from truss import Ok

    with person_source(reader) as connection:
        host, transaction, _assembly, feed = _feed_capability(connection, access_mode="read_write")
        try:
            result = feed.acknowledge_feed_with_receipt_in_transaction(
                transaction,
                page,
                destination_id=destination_id,
                request_sha256=request_hash,
                publication_id=publication_id,
                receipt_bytes=receipt,
            )
            if (
                not isinstance(result, Ok)
                or type(result.value).__name__ != "FeedReceiptAcknowledged"
                or getattr(result.value, "outcome", None) not in {"advanced", "equal"}
            ):
                raise _Failed("feed_receipt_acknowledgement_failed")
        finally:
            if host.detach() is not True:
                raise _Failed("feed_ack_detach_failed")
            connection.commit()


def _reconcile(
    person_source: Any,
    reader: Any,
    page: Any,
    *,
    destination_id: str,
    request_hash: str,
    publication_id: str,
    receipt: bytes,
) -> None:
    from _lakebase_managed_feed import _feed_capability
    from truss import Ok

    with person_source(reader) as connection:
        host, transaction, _assembly, feed = _feed_capability(connection, access_mode="read_only")
        try:
            result = feed.reconcile_feed_ack_in_transaction(
                transaction,
                page,
                destination_id=destination_id,
                request_sha256=request_hash,
                publication_id=publication_id,
                receipt_bytes=receipt,
            )
            if (
                not isinstance(result, Ok)
                or type(result.value).__name__ != "FeedAckReconciled"
                or getattr(result.value, "outcome", None) != "matched"
                or getattr(result.value, "receipt", None) is None
                or result.value.receipt.receipt_bytes != receipt
            ):
                raise _Failed("feed_ack_reconciliation_mismatch")
        finally:
            if host.detach() is not True:
                raise _Failed("feed_reconciliation_detach_failed")
            connection.rollback()


def _reread_page(person_source: Any, reader: Any, page: Any) -> None:
    from _lakebase_managed_feed import _feed_capability
    from truss import Ok

    with person_source(reader) as connection:
        host, transaction, _assembly, feed = _feed_capability(connection, access_mode="read_only")
        try:
            replay = feed.reread_feed_in_transaction(transaction, page)
            if (
                not isinstance(replay, Ok)
                or type(replay.value).__name__ != "FeedPage"
                or replay.value.content != page.content
                or replay.value.sha256 != page.sha256
                or replay.value.prior != page.prior
                or replay.value.next != page.next
                or replay.value.consumer_id != page.consumer_id
                or replay.value.registration_id != page.registration_id
                or replay.value.writer_xid != page.writer_xid
                or replay.value.outcome != page.outcome
            ):
                raise _Failed("feed_reread_after_restart_mismatch")
        finally:
            if host.detach() is not True:
                raise _Failed("feed_reread_detach_failed")
            connection.rollback()


def _destination_reopened(destination_source: Any, destination_id: str, expected: Any) -> None:
    with destination_source(destination_id=destination_id) as destination:
        snapshot = destination.snapshot()
        if (
            type(snapshot) is not dict
            or set(snapshot) != {"records", "receipts", "facts", "entities"}
            or type(expected) is not dict
            or set(expected) != {"records", "receipts", "facts", "entities"}
            or any(_snapshot_rows(snapshot, key) != expected[key] for key in expected)
        ):
            raise _Failed("feed_destination_restart_durability_mismatch")
