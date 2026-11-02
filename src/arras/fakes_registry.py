# SPDX-License-Identifier: MIT OR Apache-2.0
"""Registering a module's document on a fake authority, and its dry run (CONTRACT-002, CONTRACT-004).

`register` and `validate_register` share one check, so what a plan reports is what registering
then raises. Both are the person's own act under the `schema` grant, checked before anything else
is answered."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from arras import compat
from arras.errors import Conflict, Invalid, Refused, Unsupported, Violation
from arras.model import ModuleInfo
from arras.registration import as_revision
from arras.results import RegistrationCheck, RegistryResult
from arras.types import Principal, Revision


class RegisterModules:
    """`MemoryStore`'s registry writes; it supplies `gate`, `modules`, `documents`, `catalog_revision`
    and the record counts `compat` asks for."""

    name: str
    modules: dict[str, ModuleInfo]
    documents: dict[str, bytes]
    catalog_revision: int
    origin_actor: dict[str, str]  # the person who registered each module's current revision
    action_source_owners: dict[str, str]
    _action_lock: Any

    def gate(self, principal: Principal, module: str | None, mode: Any, op: str) -> None:
        raise NotImplementedError  # `MemoryStore` supplies the real one

    def _violations(self, module: ModuleInfo, unknown_endpoint: str) -> list[Violation]:
        """Every reason this store would refuse the module, as `register` raises them."""
        if unknown_endpoint not in ("reject", "provisional"):
            raise Invalid([Violation("unknown_endpoint", "value", "reject or provisional")])
        bad: list[Violation] = []
        if unknown_endpoint == "reject":
            known = {t.name for m in self.modules.values() for t in m.entity_types} | {
                t.name for t in module.entity_types
            }
            bad = [
                Violation(f"relationships.{r.name}", "unknown_type", f"{e} is not defined")
                for r in module.relationships
                for e in (*r.source, *r.target)
                if e not in known
            ]
        try:
            compat.check(self.modules.get(module.name), module, self)  # type: ignore[arg-type]
        except Invalid as e:
            bad.extend(e.violations)
        return bad

    def _unchanged(self, module: ModuleInfo, document: bytes) -> bool:
        held = self.documents.get(module.name)
        return (
            module.name in self.modules
            and held is not None
            and json.loads(held) == json.loads(document)
        )

    def _prepare_declared_source(self, document: bytes, module: ModuleInfo) -> None:
        if type(document) is not bytes:
            raise Invalid([Violation("document", "type", "exact registered source bytes required")])
        if module.metadata_profile != "arras-umf-set/1":
            raise Unsupported("declared action registration", ["arras-umf-set/1"])
        try:
            from arras._umf_actions import prepare
        except ModuleNotFoundError as exc:
            if exc.name == "arras._umf_actions":
                raise Unsupported(
                    "declared action source", ["install the optional engine"]
                ) from None
            raise
        prepared = prepare(document)
        if (
            prepared.source != document
            or prepared.module.name != module.name
            or prepared.module.entity_types != module.entity_types
            or prepared.module.relationships != module.relationships
            or prepared.module.value_types != module.value_types
            or prepared.module.actions != module.actions
        ):
            raise Unsupported("declared action source", ["the prepared module does not match"])
        if prepared.module.metadata_profile != "arras-umf-set/1":
            raise Unsupported("declared action source", ["arras-umf-set/1"])

    def _validate_declared_source(
        self, principal: Principal, document: bytes, module: ModuleInfo
    ) -> RegistrationCheck:
        old = self.modules.get(module.name)
        owner = getattr(self, "action_source_owners", {}).get(module.name)
        if old is not None and owner != principal.user:
            raise Refused(self.name, "validate_register")
        if old is not None and self.documents.get(module.name) != document:
            raise Unsupported("declared action source", ["the first source is immutable"])
        if any(name != module.name for name in self.modules):
            raise Unsupported("declared action store", ["one canonical module is supported"])
        self._prepare_declared_source(document, module)
        return RegistrationCheck(
            revision=old.revision if old is not None else None,
            changed=old is None,
            current=old,
        )

    def _register_declared_source(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        expected_revision: Revision | None,
    ) -> RegistryResult:
        old = self.modules.get(module.name)
        owner = getattr(self, "action_source_owners", {}).get(module.name)
        if old is not None and owner != principal.user:
            raise Refused(self.name, "register")
        if expected_revision is not None:
            expected = as_revision(expected_revision)
            if old is None or old.revision != expected:
                raise Conflict(
                    "revision", f"{module.name} is at another revision than the caller's"
                )
        if old is not None:
            if self.documents.get(module.name) != document:
                raise Unsupported("declared action source", ["the first source is immutable"])
            self._prepare_declared_source(document, module)
            return RegistryResult(module.name, old.revision, False)
        if self.modules:
            raise Unsupported("declared action store", ["one canonical module is supported"])
        self._prepare_declared_source(document, module)
        self.catalog_revision += 1
        stored = replace(module, revision=Revision({self.name: self.catalog_revision}))
        self.modules[module.name] = stored
        self.documents[module.name] = bytes(document)
        self.origin_actor[module.name] = principal.user
        self.action_source_owners[module.name] = principal.user
        return RegistryResult(module.name, stored.revision, True, ("accepted",))

    def validate_register(
        self, principal: Principal, document: bytes, module: ModuleInfo, *, unknown_endpoint: str
    ) -> RegistrationCheck:
        if getattr(self, "action_profile", None) == "arras-umf-set/1":
            with self._action_lock:
                self.gate(principal, module.name, "schema", "validate_register")
                if unknown_endpoint not in ("reject", "provisional"):
                    raise Invalid([Violation("unknown_endpoint", "value", "reject or provisional")])
                return self._validate_declared_source(principal, document, module)
        self.gate(principal, module.name, "schema", "validate_register")
        old = self.modules.get(module.name)
        return RegistrationCheck(
            revision=old.revision if old is not None else None,
            changed=not self._unchanged(module, document),
            violations=tuple(self._violations(module, unknown_endpoint)),
            current=old,
        )

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        if getattr(self, "action_profile", None) == "arras-umf-set/1":
            with self._action_lock:
                self.gate(principal, module.name, "schema", "register")
                if unknown_endpoint not in ("reject", "provisional"):
                    raise Invalid([Violation("unknown_endpoint", "value", "reject or provisional")])
                return self._register_declared_source(
                    principal, document, module, expected_revision=expected_revision
                )
        self.gate(principal, module.name, "schema", "register")
        old = self.modules.get(module.name)
        if bad := self._violations(module, unknown_endpoint):
            raise Invalid(bad)
        if expected_revision is not None and (old is None or old.revision != expected_revision):
            raise Conflict("revision", f"{module.name} is at another revision than the caller's")
        if old is not None and self._unchanged(module, document):
            # the same meaning, in any bytes: no new revision, so the text registered at it stays
            return RegistryResult(module.name, old.revision, False)  # (CONTRACT-002)
        self.catalog_revision += 1
        stored = replace(module, revision=Revision({self.name: self.catalog_revision}))
        self.modules[module.name] = stored
        self.documents[module.name] = bytes(document)
        self.origin_actor[module.name] = principal.user
        return RegistryResult(module.name, stored.revision, True, ("accepted",))
