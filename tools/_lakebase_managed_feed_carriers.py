# SPDX-License-Identifier: MIT OR Apache-2.0
"""Selected SDK 0.49 feed revision, history, reservation, and source carriers."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping
from typing import Any

from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_feed_codec import (
    _CANONICALIZATION_PROFILE,
    _SHA256,
    _bytea,
    _canonical,
    _json_bytes,
    _sha256,
    _string_cell_text,
)

_SUPPORTED_HISTORY_PROFILES = {
    "truss-native-scalar-create/0.2",
    "truss-native-owned-create/0.1",
}


def _validate_history_ownership(value: Any) -> None:
    if value == {"state": "rootless"}:
        return
    if type(value) is not dict or set(value) != {"state", "root"} or value["state"] != "owned":
        raise _Blocked("feed_history_ownership_unknown")
    root = value["root"]
    if (
        type(root) is not dict
        or set(root) != {"id", "typeId", "definitionPin", "owner"}
        or type(root["id"]) is not str
        or not root["id"].isdigit()
        or type(root["typeId"]) is not str
        or not root["typeId"].isdigit()
        or type(root["definitionPin"]) is not str
        or _SHA256.fullmatch(root["definitionPin"]) is None
        or type(root["owner"]) is not dict
        or set(root["owner"]) != {"documentId", "moduleId"}
        or any(
            type(root["owner"][key]) is not str or not root["owner"][key]
            for key in ("documentId", "moduleId")
        )
    ):
        raise _Blocked("feed_history_ownership_unknown")


def _decode_journal(
    row: Any,
    *,
    writer_xid: str,
    expected_source_epoch: str,
    expected_owner: Mapping[str, Any],
    schema_binding: Mapping[str, Any] | None,
    ordered_event_digest: Callable[[bytes], str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    journal_fields = {
        "seq",
        "at",
        "xid",
        "entity_kind",
        "entity_id",
        "entity_type",
        "ver",
        "op",
        "prop_id",
        "old_value",
        "new_value",
        "rev",
        "origin",
    }
    if type(row) is not dict or set(row) != journal_fields:
        raise _Blocked("feed_journal_profile_unknown")
    if (
        type(row["seq"]) is not int
        or row["seq"] < 1
        or row["xid"] != writer_xid
        or row["entity_kind"] != "o"
        or type(row["entity_id"]) is not int
        or row["entity_id"] < 1
        or type(row["entity_type"]) is not int
        or row["entity_type"] < 1
        or row["ver"] != 1
        or row["op"] != "create"
        or row["prop_id"] is not None
        or row["old_value"] is not None
        or type(row["rev"]) is not int
        or type(row["at"]) is not str
    ):
        raise _Blocked("feed_journal_carrier_unsupported")
    wrapper_fields = {
        "interfaceVersion",
        "eventInterfaceVersion",
        "component",
        "canonicalizationProfile",
        "bytesBase64",
        "bytesSha256",
    }
    wrapper = row["new_value"]
    if (
        type(wrapper) is not dict
        or set(wrapper) != wrapper_fields
        or wrapper["interfaceVersion"] != "truss-journal-exact-bytes/0.2.0-proposal"
        or wrapper["eventInterfaceVersion"] != "truss-history-event/0.2.0-proposal"
        or wrapper["component"] != "event"
        or wrapper["canonicalizationProfile"] != _CANONICALIZATION_PROFILE
        or type(wrapper["bytesBase64"]) is not str
        or type(wrapper["bytesSha256"]) is not str
        or _SHA256.fullmatch(wrapper["bytesSha256"]) is None
    ):
        raise _Blocked("feed_journal_wrapper_unknown")
    try:
        event_bytes = base64.b64decode(wrapper["bytesBase64"], validate=True)
    except (ValueError, TypeError):
        raise _Blocked("feed_journal_wrapper_unknown") from None
    if _sha256(event_bytes) != wrapper["bytesSha256"]:
        raise _Blocked("feed_journal_event_digest_mismatch")
    event = _json_bytes(event_bytes, "feed_journal_event_invalid")
    event_fields = {
        "interfaceVersion",
        "sourceEpoch",
        "historyProfile",
        "xid",
        "seq",
        "identity",
        "eventVersion",
        "eventCatalogRevision",
        "operation",
        "after",
        "origin",
        "mutationGroup",
    }
    if type(event) is not dict or set(event) != event_fields:
        raise _Blocked("feed_history_profile_unknown")
    identity = _validate_history_identity(
        row, event, writer_xid, expected_source_epoch, expected_owner, schema_binding
    )
    after = event["after"]
    clean_properties = _validate_history_image(row, after, identity, event, schema_binding)
    group = event["mutationGroup"]
    if (
        type(group) is not dict
        or set(group) != {"profile", "eventCount", "orderedEventDigest"}
        or group["profile"] != "truss-history-group/0.1.0"
        or group["eventCount"] != "1"
        or type(group["orderedEventDigest"]) is not str
        or _SHA256.fullmatch(group["orderedEventDigest"]) is None
        or type(event["origin"]) is not dict
    ):
        raise _Blocked("feed_mutation_group_unsupported")
    if ordered_event_digest(event_bytes) != group["orderedEventDigest"]:
        raise _Blocked("feed_mutation_group_digest_mismatch")
    _validate_journal_origin(row["origin"], wrapper, event)
    entity = {
        "source_epoch": event["sourceEpoch"],
        "writer_xid": writer_xid,
        "sequence": row["seq"],
        "entity_kind": "object",
        "entity_id": row["entity_id"],
        "entity_type": row["entity_type"],
        "document_id": identity["owner"]["documentId"],
        "module_id": identity["owner"]["moduleId"],
        "definition_pin": identity["definitionPin"],
        "record_version": 1,
        "catalog_revision": row["rev"],
        "properties": clean_properties,
        "retained": after["retained"],
        "event_sha256": wrapper["bytesSha256"],
    }
    fact = {
        "kind": "journal",
        "writer_xid": writer_xid,
        "sequence": row["seq"],
        "profile": event["historyProfile"],
        "sha256": wrapper["bytesSha256"],
        "semantic": {"journal": row, "event": event},
    }
    return fact, entity


def _validate_history_identity(
    row: Mapping[str, Any],
    event: Mapping[str, Any],
    writer_xid: str,
    expected_source_epoch: str,
    expected_owner: Mapping[str, Any],
    schema_binding: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    identity = event["identity"]
    if schema_binding is None:
        raise _Blocked("feed_probe_schema_binding_unavailable")
    if (
        event["interfaceVersion"] != "truss-history-event/0.2.0-proposal"
        or type(event["historyProfile"]) is not str
        or event["historyProfile"] not in _SUPPORTED_HISTORY_PROFILES
        or event["xid"] != writer_xid
        or event["sourceEpoch"] != expected_source_epoch
        or event["seq"] != str(row["seq"])
        or event["eventVersion"] != "1"
        or event["eventCatalogRevision"] != str(row["rev"])
        or event["operation"] != "create"
        or type(event["sourceEpoch"]) is not str
        or not event["sourceEpoch"]
        or type(identity) is not dict
        or set(identity) != {"id", "typeId", "definitionPin", "owner"}
        or identity["id"] != str(row["entity_id"])
        or identity["typeId"] != str(row["entity_type"])
        or identity["typeId"] != schema_binding.get("type_id")
        or identity["definitionPin"] != schema_binding.get("type_pin")
        or type(identity["definitionPin"]) is not str
        or _SHA256.fullmatch(identity["definitionPin"]) is None
        or identity["owner"]
        != {
            "documentId": expected_owner["document_id"],
            "moduleId": "lakebase_qualification",
        }
    ):
        raise _Blocked("feed_history_profile_unknown")
    return identity


def _validate_history_image(
    row: Mapping[str, Any],
    after: Any,
    identity: Mapping[str, Any],
    event: Mapping[str, Any],
    schema_binding: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if type(after) is not dict or set(after) != {
        "interfaceVersion",
        "kind",
        "identity",
        "recordVersion",
        "catalogRevision",
        "createdAt",
        "updatedAt",
        "properties",
        "retained",
        "ownership",
    }:
        raise _Blocked("feed_history_image_unknown")
    properties = after["properties"]
    if (
        after["interfaceVersion"] != "truss-history-record/0.1.0"
        or after["kind"] != "object"
        or after["identity"] != identity
        or after["recordVersion"] != "1"
        or after["catalogRevision"] != str(row["rev"])
        or after["catalogRevision"] != str(schema_binding.get("revision"))
        or type(after["createdAt"]) is not str
        or type(after["updatedAt"]) is not str
        or type(properties) is not list
        or len(properties) != 2
        or type(after["retained"]) is not list
        or after["retained"]
    ):
        raise _Blocked("feed_history_image_unknown")
    _validate_history_ownership(after["ownership"])
    if event["historyProfile"] == "truss-native-scalar-create/0.2" and after["ownership"] != {
        "state": "rootless"
    }:
        raise _Blocked("feed_history_profile_ownership_mismatch")
    clean_properties = []
    for prop in properties:
        if (
            type(prop) is not dict
            or set(prop) != {"propertyId", "definitionPin", "value"}
            or type(prop["propertyId"]) is not str
            or not prop["propertyId"].isdigit()
            or type(prop["definitionPin"]) is not str
            or _SHA256.fullmatch(prop["definitionPin"]) is None
        ):
            raise _Blocked("feed_history_property_unsupported")
        _string_cell_text(prop["value"], "feed_history_property_unsupported")
        clean_properties.append(prop)
    expected_order = schema_binding.get("property_order")
    expected_pins = schema_binding.get("property_pins")
    if (
        type(expected_order) is not list
        or type(expected_pins) is not dict
        or [prop["propertyId"] for prop in clean_properties] != expected_order
        or set(expected_pins) != set(expected_order)
        or any(
            prop["definitionPin"] != expected_pins[prop["propertyId"]] for prop in clean_properties
        )
    ):
        raise _Blocked("feed_probe_property_pin_binding_mismatch")
    return clean_properties


def _validate_journal_origin(
    origin: Any, wrapper: Mapping[str, Any], event: Mapping[str, Any]
) -> None:
    wrapper_fields = {
        "interfaceVersion",
        "eventInterfaceVersion",
        "component",
        "canonicalizationProfile",
        "bytesBase64",
        "bytesSha256",
    }
    if (
        type(origin) is not dict
        or set(origin) != wrapper_fields
        or origin.get("interfaceVersion") != wrapper["interfaceVersion"]
        or origin.get("eventInterfaceVersion") != wrapper["eventInterfaceVersion"]
        or origin.get("component") != "origin"
        or origin.get("canonicalizationProfile") != _CANONICALIZATION_PROFILE
        or type(origin.get("bytesBase64")) is not str
        or type(origin.get("bytesSha256")) is not str
        or _SHA256.fullmatch(origin["bytesSha256"]) is None
    ):
        raise _Blocked("feed_journal_origin_unknown")
    try:
        origin_bytes = base64.b64decode(origin["bytesBase64"], validate=True)
    except (ValueError, TypeError):
        raise _Blocked("feed_journal_origin_unknown") from None
    if (
        _sha256(origin_bytes) != origin["bytesSha256"]
        or _json_bytes(origin_bytes, "feed_journal_origin_unknown") != event["origin"]
    ):
        raise _Blocked("feed_journal_origin_mismatch")


def _decode_reservation(
    item: Any, *, writer_xid: str, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    if type(item) is not dict or set(item) != {"kind", "row"} or item["kind"] != "object_key":
        raise _Blocked("feed_reservation_profile_unknown")
    row = item["row"]
    if type(row) is not dict or set(row) != {
        "storage_row_id",
        "namespace_bytes",
        "key_bytes",
        "original_reservation_bytes",
        "namespace_sha256",
        "key_sha256",
    }:
        raise _Blocked("feed_reservation_profile_unknown")
    namespace = _bytea(row["namespace_bytes"], "feed_reservation_profile_unknown")
    key_bytes = _bytea(row["key_bytes"], "feed_reservation_profile_unknown")
    original = _bytea(row["original_reservation_bytes"], "feed_reservation_profile_unknown")
    namespace_sha = _bytea(row["namespace_sha256"], "feed_reservation_profile_unknown")
    key_sha = _bytea(row["key_sha256"], "feed_reservation_profile_unknown")
    if (
        type(row["storage_row_id"]) is not int
        or row["storage_row_id"] < 1
        or len(namespace_sha) != 32
        or len(key_sha) != 32
        or hashlib.sha256(namespace).digest() != namespace_sha
        or hashlib.sha256(key_bytes).digest() != key_sha
    ):
        raise _Blocked("feed_reservation_integrity_mismatch")
    reservation = _json_bytes(original, "feed_reservation_profile_unknown")
    expected_fields = {
        "profile",
        "groupId",
        "sourceEpoch",
        "xid",
        "objectId",
        "typeId",
        "keyNumber",
        "contextBase64",
    }
    if (
        type(reservation) is not dict
        or set(reservation) != expected_fields
        or reservation["profile"] != "truss-created-key-reservation/0.1"
        or reservation["xid"] != writer_xid
        or type(reservation["sourceEpoch"]) is not str
        or not reservation["sourceEpoch"]
        or type(reservation["groupId"]) is not str
        or type(reservation["contextBase64"]) is not str
        or not any(
            entity["writer_xid"] == writer_xid
            and str(entity["entity_id"]) == reservation["objectId"]
            and str(entity["entity_type"]) == reservation["typeId"]
            for entity in entities
        )
    ):
        raise _Blocked("feed_reservation_profile_unknown")
    try:
        context_bytes = base64.b64decode(reservation["contextBase64"], validate=True)
    except (ValueError, TypeError):
        raise _Blocked("feed_reservation_context_unknown") from None
    context = _json_bytes(context_bytes, "feed_reservation_context_unknown")
    if (
        type(context) is not dict
        or set(context)
        != {
            "profile",
            "groupId",
            "sourceEpoch",
            "xid",
            "actorOid",
            "actor",
            "operationIndex",
            "derivation",
        }
        or context["profile"] != "truss-created-key-context/0.2"
        or context["groupId"] != reservation["groupId"]
        or context["sourceEpoch"] != reservation["sourceEpoch"]
        or context["xid"] != writer_xid
        or context["derivation"] != "postgresql-umf-key-tuple-v1"
        or type(context["actorOid"]) is not str
        or type(context["actor"]) is not str
        or type(context["operationIndex"]) is not str
        or not context["operationIndex"].isdigit()
    ):
        raise _Blocked("feed_reservation_context_unknown")
    return {
        "kind": "reservation",
        "writer_xid": writer_xid,
        "sequence": row["storage_row_id"],
        "profile": reservation["profile"],
        "sha256": _sha256(original),
        "semantic": {
            "kind": item["kind"],
            "row": row,
            "reservation": reservation,
            "context": context,
        },
    }


def _decode_source(item: Any, *, writer_xid: str) -> dict[str, Any]:
    if type(item) is not dict or set(item) != {
        "entity_kind",
        "entity_id",
        "load_id",
        "source",
    }:
        raise _Blocked("feed_source_profile_unknown")
    source = item["source"]
    if (
        item["entity_kind"] not in {"o", "e"}
        or type(item["entity_id"]) is not int
        or item["entity_id"] < 1
        or type(item["load_id"]) is not str
        or type(source) is not dict
    ):
        raise _Blocked("feed_source_profile_unknown")
    profile = source.get("profile")
    if profile is not None:
        raise _Blocked("feed_source_profile_unrecognized")
    encoded = _canonical(item)
    return {
        "kind": "source",
        "writer_xid": writer_xid,
        "sequence": None,
        "profile": "truss-record-source/0.1",
        "sha256": _sha256(encoded),
        "semantic": item,
    }
