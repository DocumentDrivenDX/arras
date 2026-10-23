# SPDX-License-Identifier: MIT OR Apache-2.0
"""Native schema binding and complete public Probe replica verification."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from typing import Any

from _lakebase_managed_common import DOCUMENT_ID as _DOCUMENT_ID
from _lakebase_managed_common import Blocked as _Blocked
from _lakebase_managed_common import Failed as _Failed
from _lakebase_managed_feed_codec import _json_bytes


def _verify_replica_query(
    backend: Any,
    reader: Any,
    deliveries: list[dict[str, Any]],
    schema_binding: Mapping[str, Any],
) -> None:
    expected_pairs = _probe_pairs_from_entities(
        (entity for delivery in deliveries for entity in delivery["decoded"]["entities"]),
        schema_binding,
    )
    actual_pairs = _observe_probe_pairs(backend, reader)
    if not expected_pairs or expected_pairs != actual_pairs:
        raise _Failed("feed_replica_public_query_mismatch")


def _probe_pairs_from_entities(
    entities: Any, schema_binding: Mapping[str, Any]
) -> Counter[tuple[str, str]]:
    pairs: Counter[tuple[str, str]] = Counter()
    for entity in entities:
        properties = entity.get("properties") if type(entity) is dict else None
        if (
            type(properties) is not list
            or len(properties) != 2
            or any(
                type(prop) is not dict or set(prop) != {"propertyId", "definitionPin", "value"}
                for prop in properties
            )
            or any(
                type(prop["propertyId"]) is not str or not prop["propertyId"].isdigit()
                for prop in properties
            )
            or any(
                type(prop["definitionPin"]) is not str or len(prop["definitionPin"]) != 64
                for prop in properties
            )
            or any(type(prop["value"]) is not str for prop in properties)
        ):
            raise _Blocked("feed_probe_property_shape_unsupported")
        property_names = schema_binding.get("property_names")
        property_order = schema_binding.get("property_order")
        property_pins = schema_binding.get("property_pins")
        if (
            type(property_names) is not dict
            or set(property_names.values()) != {"code", "value"}
            or type(property_order) is not list
            or type(property_pins) is not dict
            or [prop["propertyId"] for prop in properties] != property_order
            or set(property_pins) != set(property_order)
            or any(
                prop["definitionPin"] != property_pins.get(prop["propertyId"])
                for prop in properties
            )
        ):
            raise _Blocked("feed_probe_schema_binding_unavailable")
        values: dict[str, str] = {}
        for prop in properties:
            prop_id = prop["propertyId"]
            name = property_names.get(prop_id)
            if name not in {"code", "value"} or name in values:
                raise _Blocked("feed_probe_property_mapping_mismatch")
            values[name] = prop["value"]
        if set(values) != {"code", "value"}:
            raise _Blocked("feed_probe_property_mapping_mismatch")
        pairs[(values["code"], values["value"])] += 1
    return pairs


def _observe_probe_pairs(backend: Any, reader: Any) -> Counter[tuple[str, str]]:
    from _lakebase_managed_public import _query_probe

    _validate_probe_schema_binding(backend, reader)
    actual_rows = _query_probe(backend, reader)
    if len(actual_rows) >= 100:
        raise _Blocked("feed_probe_query_may_be_truncated")
    pairs: Counter[tuple[str, str]] = Counter()
    for row in actual_rows:
        if type(row) is not dict or set(row) != {"code", "value"}:
            raise _Failed("feed_replica_public_query_shape_mismatch")
        if type(row["code"]) is not str or type(row["value"]) is not str:
            raise _Failed("feed_replica_public_query_shape_mismatch")
        pairs[(row["code"], row["value"])] += 1
    return pairs


def _validate_probe_schema_binding(backend: Any, reader: Any) -> None:
    from _lakebase_operations import HARNESS_MODULE_DOCUMENT, HARNESS_MODULE_SHA256

    document = backend.document(reader, "lakebase_qualification")
    if (
        getattr(document, "module", None) != "lakebase_qualification"
        or getattr(document, "text", None) != HARNESS_MODULE_DOCUMENT.decode("utf-8")
        or hashlib.sha256(HARNESS_MODULE_DOCUMENT).hexdigest() != HARNESS_MODULE_SHA256
    ):
        raise _Blocked("feed_probe_document_binding_unavailable")
    catalog = backend.catalog(reader)
    module = catalog.get("lakebase_qualification") if isinstance(catalog, Mapping) else None
    if module is None:
        raise _Blocked("feed_probe_catalog_binding_unavailable")
    entity_type = module.entity_type("Probe")
    if entity_type is None or tuple(prop.name for prop in entity_type.properties) != (
        "code",
        "value",
    ):
        raise _Blocked("feed_probe_property_order_unavailable")


def _load_probe_schema_binding(sources: Mapping[str, Any]) -> dict[str, Any]:
    """Read the selected revision's pinned Probe field IDs from native schema metadata."""
    from _lakebase_operations import HARNESS_MODULE_DOCUMENT, HARNESS_MODULE_SHA256

    source = sources.get("installer_connection_source")
    if not callable(source):
        raise _Blocked("feed_probe_schema_binding_unavailable")
    if hashlib.sha256(HARNESS_MODULE_DOCUMENT).hexdigest() != HARNESS_MODULE_SHA256:
        raise _Blocked("feed_probe_document_binding_unavailable")
    try:
        with source() as connection:
            if int(connection.info.transaction_status) != 0:
                raise _Blocked("feed_probe_schema_connection_not_idle")
            connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '2000ms'")
            try:
                rows = connection.execute(
                    "WITH head AS (SELECT rev FROM truss.schema_head WHERE id=1), "
                    "documents AS (SELECT DISTINCT ON (doc_id) doc_id, doc_revision, "
                    "content_sha256, document FROM truss.schema_doc, head "
                    "WHERE schema_doc.rev <= head.rev ORDER BY doc_id, schema_doc.rev DESC) "
                    "SELECT head.rev, documents.doc_revision, documents.content_sha256, "
                    "documents.document, t.type_id, type_source.definition_pin, "
                    "property_source.definition_pin, ts.metadata::text, p.prop_id, p.name, "
                    "p.declaration_module, p.element, p.scalar_type, p.nullability, p.cardinality "
                    "FROM head JOIN documents ON documents.doc_id=%s "
                    "JOIN truss.type_def AS t ON t.document_id=documents.doc_id "
                    "AND t.module=%s AND t.element=%s AND t.kind='record' "
                    "AND NOT t.provisional AND t.since_rev<=head.rev "
                    "AND (t.retired_rev IS NULL OR t.retired_rev>head.rev) "
                    "JOIN truss.runtime_type_schema AS ts ON ts.rev=head.rev "
                    "AND ts.type_id=t.type_id AND ts.valid_properties "
                    "JOIN truss.runtime_definition_source AS type_source "
                    "ON type_source.rev=t.definition_rev AND type_source.ord=t.definition_doc_ord "
                    "AND type_source.doc_id=t.definition_document_id AND type_source.module_id=t.module "
                    "AND type_source.element_id=t.element AND type_source.kind='element' "
                    "AND type_source.key_id='' AND t.definition_document_id=documents.doc_id "
                    "JOIN truss.prop_def AS p ON p.type_id=t.type_id "
                    "AND p.since_rev<=head.rev "
                    "AND (p.retired_rev IS NULL OR p.retired_rev>head.rev) "
                    "JOIN truss.runtime_definition_source AS property_source "
                    "ON property_source.rev=p.definition_rev AND property_source.ord=p.definition_doc_ord "
                    "AND property_source.doc_id=p.definition_document_id "
                    "AND property_source.module_id=p.declaration_module "
                    "AND property_source.element_id=p.element AND property_source.kind='element' "
                    "AND property_source.key_id='' AND p.definition_document_id=documents.doc_id "
                    "ORDER BY p.prop_id",
                    (_DOCUMENT_ID, "lakebase_qualification", "Probe"),
                ).fetchall()
                return _normalize_probe_schema_rows(rows, HARNESS_MODULE_DOCUMENT)
            finally:
                connection.rollback()
    except _Blocked:
        raise
    except Exception:
        raise _Blocked("feed_probe_schema_binding_unavailable") from None


def _normalize_probe_schema_rows(rows: Any, expected_document: bytes) -> dict[str, Any]:
    if type(rows) not in {tuple, list} or len(rows) != 2:
        raise _Blocked("feed_probe_schema_binding_unavailable")
    first = rows[0]
    if type(first) not in {tuple, list} or len(first) != 15:
        raise _Blocked("feed_probe_schema_binding_unavailable")
    revision, document_revision, document_sha, document_text, type_id = first[:5]
    type_source_pin, first_property_source_pin = first[5:7]
    if (
        type(revision) is not int
        or type(document_revision) is not str
        or not document_revision
        or type(document_sha) is not str
        or type(document_text) is not str
        or hashlib.sha256(document_text.encode("utf-8")).hexdigest() != document_sha
        or document_text.encode("utf-8") != expected_document
        or type(type_id) is not int
        or type(type_source_pin) is not str
        or type(first[7]) is not str
        or type(first_property_source_pin) is not str
    ):
        raise _Blocked("feed_probe_document_binding_unavailable")

    metadata = _json_bytes(first[7].encode("utf-8"), "feed_probe_schema_metadata_invalid")
    expected_metadata_fields = {
        "typeId",
        "revision",
        "typePin",
        "propertyOrder",
        "propertyPins",
        "propertyAccess",
        "keyCodecs",
    }
    if (
        type(metadata) is not dict
        or set(metadata) != expected_metadata_fields
        or metadata["typeId"] != str(type_id)
        or metadata["revision"] != str(revision)
        or metadata["typePin"] != type_source_pin
        or type(metadata["typePin"]) is not str
        or len(metadata["typePin"]) != 64
        or any(char not in "0123456789abcdef" for char in metadata["typePin"])
        or type(metadata["propertyOrder"]) is not list
        or type(metadata["propertyPins"]) is not dict
    ):
        raise _Blocked("feed_probe_schema_metadata_invalid")
    prop_names: dict[str, str] = {}
    ordered_ids: list[str] = []
    for row in rows:
        if (
            type(row) not in {tuple, list}
            or len(row) != 15
            or row[:5] != first[:5]
            or row[5] != type_source_pin
            or type(row[6]) is not str
            or type(row[7]) is not str
            or type(row[8]) is not int
            or type(row[9]) is not str
            or row[9] not in {"code", "value"}
            or row[10] != "lakebase_qualification"
            or row[11] != f"Probe.{row[9]}"
            or row[12] != "string"
            or row[13] != "required"
            or row[14] != "one"
        ):
            raise _Blocked("feed_probe_schema_binding_unavailable")
        property_id = str(row[8])
        if property_id in prop_names or row[9] in prop_names.values():
            raise _Blocked("feed_probe_schema_binding_ambiguous")
        if metadata["propertyPins"].get(property_id) != row[6]:
            raise _Blocked("feed_probe_schema_property_pins_unavailable")
        prop_names[property_id] = row[9]
        ordered_ids.append(property_id)
    if (
        set(prop_names.values()) != {"code", "value"}
        or metadata["propertyOrder"] != ordered_ids
        or set(metadata["propertyPins"]) != set(ordered_ids)
        or any(
            type(metadata["propertyPins"][property_id]) is not str
            or len(metadata["propertyPins"][property_id]) != 64
            or any(char not in "0123456789abcdef" for char in metadata["propertyPins"][property_id])
            for property_id in ordered_ids
        )
    ):
        raise _Blocked("feed_probe_schema_property_pins_unavailable")
    return {
        "revision": revision,
        "document_revision": document_revision,
        "document_sha256": document_sha,
        "type_id": str(type_id),
        "type_pin": metadata["typePin"],
        "property_order": ordered_ids,
        "property_pins": metadata["propertyPins"],
        "property_names": prop_names,
    }
