# SPDX-License-Identifier: MIT OR Apache-2.0
"""The request vocabulary of a Truss group (plan TR-07): the one place that builds Truss's own
request types.

`Wire` imports Truss inside its methods, so the base install needs none of it. The planner
(`plan.py`) takes a `Wire` and never names a Truss class, so the always-on tests pass a recording
`Wire` whose products are plain values and need no Truss at all; the Truss-marked tests use this one.
Truss's results are recognized by class name elsewhere.
"""

from __future__ import annotations

from typing import Any


class Wire:
    """Builds group operations, preconditions and values as Truss 0.0.45 names them."""

    # -- values

    def text(self, kind: str, text: str) -> Any:
        from truss.contracts import TextValue

        return TextValue(kind=kind, text=text)  # type: ignore[arg-type]

    def boolean(self, value: bool) -> Any:
        from truss.contracts import BooleanValue

        return BooleanValue(value=value)

    def authored(self, name: str, value: Any) -> Any:
        from truss.groups import AuthoredValue

        return AuthoredValue(name=name, value=value)

    def origin(self, action: str) -> Any:
        from truss.contracts import MapEntry, MapValue, TextValue

        return MapValue(
            entries=(MapEntry(key="x-action", value=TextValue(kind="string", text=action)),)
        )

    def import_origin(self, initiated_by: str) -> Any:
        """The origin an import asserts: Truss adds the load id itself and refuses one given here."""
        from truss.contracts import MapEntry, MapValue, TextValue

        return MapValue(
            entries=(
                MapEntry(key="x-action", value=TextValue(kind="string", text="import_records")),
                MapEntry(key="x-initiated-by", value=TextValue(kind="string", text=initiated_by)),
            )
        )

    def import_source(self, author: str | None, at: str | None) -> Any:
        """A record's own provenance (`author`, `at`); a fact left out stays absent. None when the
        record states neither."""
        from truss.contracts import MapEntry, MapValue, TextValue

        entries = tuple(
            MapEntry(key=key, value=TextValue(kind="string", text=text))
            for key, text in (("author", author), ("at", at))
            if text is not None
        )
        return MapValue(entries=entries) if entries else None

    def null_order(self) -> Any:
        from truss.groups import NullOrderKey

        return NullOrderKey()

    def object_draft(
        self, document_id: str, module_id: str, record_id: str, values: tuple[Any, ...], source: Any
    ) -> Any:
        """One entity of a batched import, for `build_import_records_in_transaction`."""
        from truss.batched_import import ObjectImportDraft

        return ObjectImportDraft(
            document_id=document_id,
            module_id=module_id,
            record_id=record_id,
            values=values,
            source=source,
        )

    def edge_draft(
        self, document_id: str, module_id: str, relationship_id: str, source: Any, target: Any
    ) -> Any:
        """One relationship of a batched import, between two identities that exist."""
        from truss.batched_import import EdgeImportDraft

        return EdgeImportDraft(
            document_id=document_id,
            module_id=module_id,
            relationship_id=relationship_id,
            source_endpoint=source,
            target_endpoint=target,
            values=(),
            order_key=self.null_order(),
        )

    # -- identities and references

    def ghost(self, template: Any, object_id: str) -> Any:
        """An identity that names no object, of the type `template` names: Truss answers a missing
        target as a failed condition or `not_found`, never as invalid input."""
        from truss.contracts import TypedIdentity

        return TypedIdentity(
            id=object_id,
            type_id=template.type_id,
            definition_pin=template.definition_pin,
            owner=template.owner,
        )

    def ghost_edge(self, relationship: Any, object_id: str) -> Any:
        from truss.contracts import TypedIdentity

        return TypedIdentity(
            id=object_id,
            type_id=str(relationship.relationship_id),
            definition_pin=relationship.definition_pin,
            owner=relationship.owner,
        )

    def stored(self, identity: Any) -> Any:
        from truss.groups import StoredObjectReference

        return StoredObjectReference(identity=identity)

    def alias_ref(self, alias: str) -> Any:
        from truss.groups import AliasObjectReference

        return AliasObjectReference(alias=alias)

    # -- operations

    def create_object(self, pin: str, values: tuple[Any, ...], alias: str) -> Any:
        from truss.groups import CreateObject, RootlessOwnership

        return CreateObject(
            type_definition_pin=pin, values=values, ownership=RootlessOwnership(), alias=alias
        )

    def create_edge(self, pin: str, source: Any, target: Any, alias: str) -> Any:
        from truss.groups import CreateEdge, NullOrderKey

        return CreateEdge(
            relationship_definition_pin=pin,
            source=source,
            target=target,
            values=(),
            order_key=NullOrderKey(),
            alias=alias,
        )

    def update_object(self, target: Any, set: tuple[Any, ...], unset: tuple[str, ...]) -> Any:
        from truss.groups import UpdateObject

        return UpdateObject(target=target, set=set, unset=unset)

    def delete(self, operation: str, target: Any) -> Any:
        from truss.groups import Delete

        return Delete(operation=operation, target=target)  # type: ignore[arg-type]

    # -- preconditions

    def object_exists(self, id: str, reason: str, target: Any) -> Any:
        from truss.groups import ObjectExists

        return ObjectExists(id=id, reason=reason, target=target)

    def key_absent(self, id: str, reason: str, pin: str, key_id: str, key: Any) -> Any:
        from truss.groups import KeyAbsent

        return KeyAbsent(
            id=id, reason=reason, type_definition_pin=pin, key_id=key_id, values=(key,)
        )

    def property_equals(self, id: str, reason: str, target: Any, name: str, value: Any) -> Any:
        from truss.groups import PropertyEquals

        return PropertyEquals(id=id, reason=reason, target=target, name=name, value=value)

    def relationship_absent(self, id: str, reason: str, pin: str, source: Any, target: Any) -> Any:
        from truss.groups import RelationshipAbsent

        return RelationshipAbsent(
            id=id, reason=reason, relationship_definition_pin=pin, source=source, target=target
        )

    def relationship_count(
        self,
        id: str,
        reason: str,
        pin: str,
        anchor: Any,
        direction: str,
        minimum: int,
        maximum: int | None,
    ) -> Any:
        from truss.contracts import ABSENT
        from truss.groups import RelationshipCount

        return RelationshipCount(
            id=id,
            reason=reason,
            relationship_definition_pin=pin,
            anchor=anchor,
            direction=direction,  # type: ignore[arg-type]
            minimum=str(minimum),
            maximum=ABSENT if maximum is None else str(maximum),
        )

    # -- audit

    def audit_cursor(self, kind: str, fields: dict[str, Any]) -> Any:
        """Truss's typed cursor of `kind` (`changes` or `loads`) from the fields an earlier one had."""
        from truss.load_audit import LoadAuditListingCursor, MutationGroupAuditListingCursor

        cls = MutationGroupAuditListingCursor if kind == "changes" else LoadAuditListingCursor
        return cls(**fields)

    # -- the request

    def document(self, document_id: str, content: bytes) -> Any:
        from truss import CatalogDocument

        return CatalogDocument(document_id, "accepted", content)
