# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded decoder for the selected native feed page and scalar-create profile."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_feed_carriers import (
    _decode_journal,
    _decode_reservation,
    _decode_source,
)
from _lakebase_managed_feed_codec import (
    _FEED_FIELDS,
    _MAX_PAGE_BYTES,
    _XID,
    _canonical,
    _checked_cursor,
    _json_bytes,
    _sha256,
    _validate_configuration,
)
from _lakebase_managed_feed_revisions import _validate_revision


def _decode_feed_page(
    page: Any,
    *,
    consumer_id: str,
    expected_owner: Mapping[str, Any],
    expected_prior: bytes | None,
    expected_cursor_identity: tuple[str, str, str] | None,
    schema_binding: Mapping[str, Any] | None = None,
    ordered_event_digest: Callable[[bytes], str] | None = None,
) -> dict[str, Any]:
    content = getattr(page, "content", None)
    if type(content) is not bytes or len(content) > _MAX_PAGE_BYTES:
        raise _Blocked("feed_page_bound_exceeded")
    page_sha = _sha256(content)
    if getattr(page, "sha256", None) != page_sha:
        raise _Failed("feed_page_digest_mismatch")
    prior_cursor = _checked_cursor(page.prior.content)
    next_cursor = _checked_cursor(page.next.content)
    cursor_identity = (
        prior_cursor["installationId"],
        prior_cursor["sourceEpoch"],
        prior_cursor["registrationId"],
    )
    safe_watermark = getattr(page, "safe_watermark_xid", None)
    if (
        prior_cursor["consumerId"] != consumer_id
        or next_cursor["consumerId"] != consumer_id
        or getattr(page, "consumer_id", None) != consumer_id
        or prior_cursor["registrationId"] != getattr(page, "registration_id", None)
        or next_cursor["registrationId"] != getattr(page, "registration_id", None)
        or prior_cursor["installationId"] != next_cursor["installationId"]
        or prior_cursor["sourceEpoch"] != next_cursor["sourceEpoch"]
        or prior_cursor["registrationId"] != next_cursor["registrationId"]
        or expected_prior is not None
        and page.prior.content != expected_prior
        or expected_cursor_identity is not None
        and cursor_identity != expected_cursor_identity
        or int(next_cursor["nextXid"]) < int(prior_cursor["nextXid"])
        or type(safe_watermark) is not str
        or _XID.fullmatch(safe_watermark) is None
        or int(next_cursor["nextXid"]) > int(safe_watermark)
    ):
        raise _Failed("feed_cursor_continuity_mismatch")
    payload = _json_bytes(content, "feed_page_payload_invalid")
    if type(payload) is not dict or set(payload) != _FEED_FIELDS:
        raise _Blocked("feed_payload_profile_unknown")
    if (
        payload["interfaceVersion"] != "truss-native-feed/0.1"
        or payload["prior"] != prior_cursor
        or payload["next"] != next_cursor
        or payload["writerXid"] != getattr(page, "writer_xid", None)
        or payload["writerXid"] is not None
        and (type(payload["writerXid"]) is not str or _XID.fullmatch(payload["writerXid"]) is None)
    ):
        # The envelope does not duplicate outcome; it is carried by FeedPage.
        raise _Blocked("feed_payload_profile_unknown")
    _validate_configuration(payload["configuration"])
    for key in ("catalogPrerequisites", "revisions", "changes", "sources", "reservations"):
        if type(payload[key]) is not list:
            raise _Blocked("feed_payload_profile_unknown")
    if getattr(page, "outcome", None) not in {"transaction", "empty_interval"}:
        raise _Blocked("feed_outcome_profile_unknown")
    writer_xid = payload["writerXid"]
    if getattr(page, "outcome", None) == "transaction":
        if (
            type(writer_xid) is not str
            or int(prior_cursor["nextXid"]) > int(writer_xid)
            or int(next_cursor["nextXid"]) != int(writer_xid) + 1
        ):
            raise _Failed("feed_transaction_cursor_writer_mismatch")
    if getattr(page, "outcome", None) == "empty_interval":
        if writer_xid is not None or any(
            payload[key]
            for key in ("catalogPrerequisites", "revisions", "changes", "sources", "reservations")
        ):
            raise _Failed("feed_empty_interval_contains_facts")
    elif writer_xid is None:
        raise _Failed("feed_transaction_writer_missing")
    facts, entities = _decode_page_facts(
        payload,
        writer_xid=writer_xid,
        expected_owner=expected_owner,
        schema_binding=schema_binding,
        page_sha=page_sha,
        prior_cursor=prior_cursor,
        next_cursor=next_cursor,
        ordered_event_digest=ordered_event_digest,
    )
    semantic = {
        "interfaceVersion": "arras-mp04-semantic-replica/1",
        "consumerId": consumer_id,
        "registrationId": page.registration_id,
        "prior": prior_cursor,
        "next": next_cursor,
        "priorSha256": _sha256(page.prior.content),
        "nextSha256": _sha256(page.next.content),
        "outcome": page.outcome,
        "safeWatermarkXid": safe_watermark,
        "writerXid": writer_xid,
        "configuration": payload["configuration"],
        "facts": facts,
        "entities": entities,
        "sourcePageSha256": page_sha,
    }
    semantic["semanticSha256"] = _sha256(_canonical(semantic))
    return {
        "semantic": semantic,
        "cursor_identity": cursor_identity,
        "prior": page.prior.content,
        "next": page.next.content,
        "page_sha256": page_sha,
        "payload_bytes": len(content),
        "outcome": page.outcome,
        "writer_xid": writer_xid,
        "facts": facts,
        "entities": entities,
    }


def _decode_page_facts(
    payload: Mapping[str, Any],
    *,
    writer_xid: str | None,
    expected_owner: Mapping[str, Any],
    schema_binding: Mapping[str, Any] | None,
    page_sha: str,
    prior_cursor: Mapping[str, Any],
    next_cursor: Mapping[str, Any],
    ordered_event_digest: Callable[[bytes], str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    if writer_xid is None:
        facts.append(
            {
                "kind": "empty_interval",
                "writer_xid": None,
                "sequence": None,
                "profile": "truss-native-feed/0.1",
                "sha256": page_sha,
                "semantic": {"prior": prior_cursor, "next": next_cursor},
            }
        )
        return facts, entities
    for row in payload["changes"]:
        if ordered_event_digest is None:
            raise _Blocked("feed_event_canonicalization_unavailable")
        fact, entity = _decode_journal(
            row,
            writer_xid=writer_xid,
            expected_source_epoch=prior_cursor["sourceEpoch"],
            expected_owner=expected_owner,
            schema_binding=schema_binding,
            ordered_event_digest=ordered_event_digest,
        )
        facts.append(fact)
        entities.append(entity)
    for item in payload["reservations"]:
        facts.append(_decode_reservation(item, writer_xid=writer_xid, entities=entities))
    for item in payload["sources"]:
        facts.append(_decode_source(item, writer_xid=writer_xid))
    for index, revision in enumerate(payload["revisions"]):
        facts.append(_revision_fact(revision, writer_xid=writer_xid, index=index, kind="revision"))
    for index, revision in enumerate(payload["catalogPrerequisites"]):
        facts.append(
            _revision_fact(revision, writer_xid=writer_xid, index=index, kind="prerequisite")
        )
    if not facts:
        raise _Blocked("feed_transaction_has_no_selected_facts")
    return facts, entities


def _revision_fact(value: Any, *, writer_xid: str, index: int, kind: str) -> dict[str, Any]:
    checked = _validate_revision(value)
    return {
        "kind": kind,
        "writer_xid": writer_xid,
        "sequence": index,
        "profile": "truss-feed-revision/0.1.0",
        "sha256": _sha256(_canonical(checked)),
        "semantic": checked,
    }
