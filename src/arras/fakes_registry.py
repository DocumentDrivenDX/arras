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
from arras.errors import Conflict, Invalid, Violation
from arras.model import ModuleInfo
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

    def validate_register(
        self, principal: Principal, document: bytes, module: ModuleInfo, *, unknown_endpoint: str
    ) -> RegistrationCheck:
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
