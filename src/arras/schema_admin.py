# SPDX-License-Identifier: MIT OR Apache-2.0
"""Validating and registering a module's document as a person (CONTRACT-002, ADR-026).

The record store's `schema` grant decides; Arras adds no role. The grant is asked first, so a
person without it learns nothing of the host's placement. `Ontology` is imported for types only."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from arras import gqlschema, telemetry
from arras.backend import Provider
from arras.errors import Invalid, Unsupported, Violation
from arras.model import EntityTypeInfo, ModuleInfo
from arras.registration import (
    _profile_qualification_violations,  # pyright: ignore[reportPrivateUsage]
    as_revision,
    host_violations,
    placed,
)
from arras.results import RegistrationCheck, RegistryResult, SchemaChange, SchemaPlan
from arras.types import Revision

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from arras.core import Ontology


def _kind(p: Any) -> str:
    return f"{'required' if p.required else 'optional'} {p.type}" + (
        "" if p.cardinality in ("one", "optional") else f" ({p.cardinality})"
    )


def changes(old: ModuleInfo | None, new: ModuleInfo) -> tuple[SchemaChange, ...]:
    """What registering `new` over `old` adds, changes and retires, from declared structure only:
    never a record or a value."""
    out: list[SchemaChange] = []
    held = {t.name: t for t in old.entity_types} if old is not None else {}
    for t in new.entity_types:
        ot = held.get(t.name)
        if ot is None:
            out.append(SchemaChange("added", "type", t.name, f"key {t.key}"))
            continue
        _properties(ot, t, out)
    out.extend(
        SchemaChange("retired", "type", n)
        for n in held
        if n not in {t.name for t in new.entity_types}
    )
    _by_name(
        {r.name: r for r in old.relationships} if old else {},
        {r.name: r for r in new.relationships},
        "relationship",
        new.name,
        out,
    )
    _by_name(
        {a.name: a for a in old.actions} if old else {},
        {a.name: a for a in new.actions},
        "action",
        new.name,
        out,
    )
    return tuple(out)


def _properties(old: EntityTypeInfo, new: EntityTypeInfo, out: list[SchemaChange]) -> None:
    before = {p.name: p for p in old.properties}
    for p in new.properties:
        name = f"{new.name}.{p.name}"
        if (o := before.get(p.name)) is None:
            out.append(SchemaChange("added", "property", name, _kind(p)))
        elif o != p:
            out.append(SchemaChange("changed", "property", name, f"{_kind(o)} to {_kind(p)}"))
    kept = {p.name for p in new.properties}
    out.extend(
        SchemaChange("retired", "property", f"{new.name}.{n}") for n in before if n not in kept
    )


def _by_name(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    element: Any,
    module: str,
    out: list[SchemaChange],
) -> None:
    def qualified(n: str) -> str:
        return n if "." in n else f"{module}.{n}"

    for n, v in new.items():
        if n not in old:
            out.append(SchemaChange("added", element, qualified(n)))
        elif old[n] != v:
            out.append(SchemaChange("changed", element, qualified(n)))
    out.extend(SchemaChange("retired", element, qualified(n)) for n in old if n not in new)


class Schema:
    """`session.schema()`: the person's own validate and register of a UMF document."""

    def __init__(self, ontology: Ontology) -> None:
        self.o = ontology

    def _store(self, document: bytes | str, op: str) -> tuple[bytes, ModuleInfo, Provider]:
        self.o.require_user(op)
        raw, mod = placed(self.o.h, document)  # unparsable or unplaced: no module to ask
        record = self.o.h.backends.get(mod.placement.record)
        if record is None or not record.describe().provides:
            raise Invalid(
                [Violation("placement", "invalid_placement", "the record store takes no revisions")]
            )
        if bad := _profile_qualification_violations(self.o.h, mod):
            raise Invalid(bad)
        return raw, mod, cast(Provider, record)

    @staticmethod
    def _check(
        store: Provider, who: Any, raw: bytes, mod: ModuleInfo, unknown_endpoint: str
    ) -> RegistrationCheck:
        dry = getattr(store, "validate_register", None)
        if dry is None:
            raise Unsupported("validate_register", [])
        return dry(who, raw, mod, unknown_endpoint=unknown_endpoint)

    def _host(self, mod: ModuleInfo) -> list[Violation]:
        """The host's and the module's own reasons, after the backend has said the person may ask."""
        readable = self.o._catalogs("schema").names()  # pyright: ignore[reportPrivateUsage]
        bad = host_violations(self.o.h, mod, readable)
        try:
            gqlschema.build_module_schema(mod)  # a module must be servable
        except Invalid as e:
            bad.extend(e.violations)
        return bad

    @telemetry.traced("arras.schema_validate", None, lambda r: {"module": r.module})
    def validate(self, document: bytes | str, *, unknown_endpoint: str = "reject") -> SchemaPlan:
        raw, mod, store = self._store(document, "validate")
        check = self._check(store, self.o.principal, raw, mod, unknown_endpoint)
        violations = (*self._host(mod), *check.violations)
        return SchemaPlan(
            module=mod.name,
            ok=not violations,
            violations=violations,
            changed=check.changed,
            revision=check.revision,
            changes=changes(check.current, mod),
            report=check.report,
        )

    @telemetry.traced("arras.schema_register", None, lambda r: {"module": r.module})
    def register(
        self,
        document: bytes | str,
        *,
        unknown_endpoint: str = "reject",
        expected_revision: Revision | Mapping[str, Any] | None = None,
    ) -> RegistryResult:
        raw, mod, store = self._store(document, "register")
        want = None if expected_revision is None else as_revision(expected_revision)
        check = self._check(store, self.o.principal, raw, mod, unknown_endpoint)
        if bad := (*self._host(mod), *check.violations):
            raise Invalid(list(bad))
        result = store.register(
            self.o.principal, raw, mod, unknown_endpoint=unknown_endpoint, expected_revision=want
        )
        # A replica learns of the module through its feed; a person may not attach to one.
        return replace(result, report=(*result.report, "replicas learn of it through their feed"))
