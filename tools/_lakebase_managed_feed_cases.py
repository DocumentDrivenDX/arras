# SPDX-License-Identifier: MIT OR Apache-2.0
"""Feed receipt replay and source restart case."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_common import allowed as _allowed
from _lakebase_managed_common import digest as _digest
from _lakebase_managed_feed import (
    _feed_delivery,
    _reconcile,
)
from _lakebase_managed_feed_destination import _reread_page
from _lakebase_managed_feed_probe import _observe_probe_pairs, _probe_pairs_from_entities
from _lakebase_managed_native import _observer_snapshot


def _run_mp04(
    inputs: Any,
    controls: Mapping[str, Any],
    sources: Mapping[str, Any],
    principals: Mapping[str, Any],
    backend: Any,
) -> dict[str, Any]:
    _allowed(inputs, "MP-04")
    module_access = inputs.target["resources"]["module_access"]
    consumer_id = "mp04-" + uuid.uuid4().hex
    aggregate = _feed_delivery(
        controls=controls,
        sources=sources,
        principals=principals,
        module_access=module_access,
        consumer_id=consumer_id,
        backend=backend,
        return_private=True,
    )
    private = aggregate.pop("_private")
    restart = controls.get("restart_compute")
    if not callable(restart):
        raise _Blocked("feed_source_restart_control_unavailable")
    before_restart = _observer_snapshot(sources)
    event = restart()
    if type(event) is not dict or set(event) != {
        "resource_sha256",
        "operation_sha256",
        "generation_before",
        "generation_after",
    }:
        raise _Blocked("feed_restart_fact_shape_invalid")
    resource_hash = _digest(event["resource_sha256"], "restart_resource_identity_unavailable")
    operation_hash = _digest(event["operation_sha256"], "restart_operation_identity_unavailable")
    gen_before = _digest(event["generation_before"], "restart_generation_before_unavailable")
    gen_after = _digest(event["generation_after"], "restart_generation_after_unavailable")
    expected_resource = hashlib.sha256(
        inputs.target["provider_resource_id"].encode("utf-8")
    ).hexdigest()
    if resource_hash != expected_resource or gen_before == gen_after:
        raise _Failed("feed_restart_resource_or_generation_mismatch")
    after = _observer_snapshot(sources)
    if before_restart["sha256"] != after["sha256"]:
        raise _Failed("feed_checkpoint_or_receipt_not_durable_across_restart")
    for delivery in private["deliveries"]:
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
    expected_pairs = _probe_pairs_from_entities(
        (
            entity
            for delivery in private["deliveries"]
            for entity in delivery["decoded"]["entities"]
        ),
        private["schema_binding"],
    )
    observed_pairs = _observe_probe_pairs(backend, principals["reader"])
    if not expected_pairs or expected_pairs != observed_pairs:
        raise _Failed("feed_replica_query_after_restart_mismatch")
    return {
        "consumer_id_sha256": aggregate["consumer_id_sha256"],
        "feed_page_sha256": aggregate["feed_page_sha256"],
        "feed_page_count": aggregate["feed_page_count"],
        "transaction_page_count": aggregate["transaction_page_count"],
        "empty_interval_drained": aggregate["empty_interval_drained"],
        "source_ack_reconciled": aggregate["source_ack_reconciled"],
        "destination_receipt_sha256": aggregate["destination_receipt_sha256"],
        "destination_reopened_equal": aggregate["destination_reopened_equal"],
        "destination_replay_equal": aggregate["destination_replay_equal"],
        "restart_operation_sha256": operation_hash,
        "generation_before_sha256": gen_before,
        "generation_after_sha256": gen_after,
        "native_after_restart_sha256": after["sha256"],
    }
