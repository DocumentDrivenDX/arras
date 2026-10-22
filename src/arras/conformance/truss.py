# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned, throwaway native Truss resource for the packaged conformance corpus.

This is a testing helper, not a deployment or persistent-host attachment API. Native
dependencies and PostgreSQL are loaded only when a harness first provisions a case.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from arras.actions import Plan, resolve
from arras.conformance import Limit, load_corpus
from arras.model import ModuleInfo
from arras.results import Receipt
from arras.types import Principal


class TrussHarness:
    """A fresh local Truss provider per corpus case, owning every resource it creates."""

    roles = ("reader", "provider")
    corpus_version = 13
    LIMITS = {
        "read.relationship-columns-follow-ends": Limit(
            "step 0 (query)", "Invalid", "wft-output-name"
        ),
        "read.relationship-columns-are-capped": Limit(
            "step 2 (query)", "Unsupported", "refused the statement (limits)"
        ),
        "action.applies-atomically-and-reads-back": Limit(
            "step 3 (query)", "Invalid", "wft-output-name"
        ),
        "action.conflict-rolls-back-the-unit": Limit(
            "step 4 (query)", "Invalid", "wft-output-name"
        ),
        "action.keyed-retry-of-a-delete-replays": Limit(
            "step 1 (apply)", "Conflict", "idempotency_key_reused"
        ),
        "action.keyed-retry-of-an-unlink-replays": Limit(
            "step 1 (apply)", "Conflict", "idempotency_key_reused"
        ),
        "action.keyed-retry-after-its-target-was-deleted-replays": Limit(
            "step 2 (apply)", "Conflict", "idempotency_key_reused"
        ),
        "action.same-key-from-another-person-replays": Limit(
            "step 1 (apply)", "PreconditionFailed", "fresh"
        ),
    }
    limits = LIMITS

    def __init__(self) -> None:
        self._local: Any | None = None
        self._backend: Any | None = None
        self._module: ModuleInfo | None = None
        self._document: bytes | None = None
        self._people: dict[str, Principal] = {}
        self._owned: list[Any] = []
        self._foreign_receipt: str | None = None
        self._unsupported_marker: str | None = None
        self._outage: str | None = None
        self._closed = False

    def _open(self) -> Any:
        if self._closed:
            raise RuntimeError("the conformance harness is closed")
        if self._local is None:
            # Deliberately lazy: run_corpus creates a probe that only reads class metadata.
            from arras.adapters.truss.local import LocalTruss

            self._local = LocalTruss("conformance")
            self._owned.append(self._local)
            self._local.open()
        return self._local

    def install(self, module: ModuleInfo, document: bytes) -> None:
        local = self._open()
        self._module, self._document = module, bytes(document)
        assert local.backend is not None
        admin = local.person("arras_corpus_admin")
        local.membership(admin.user, local.registrar_role, grant=True)
        admin = Principal(admin.user, admin.token, admin=True)
        local.backend.register(admin, document, module, unknown_endpoint="reject")
        local.configure_module(module.name, json.loads(document)["id"])
        self._backend = self._configured_backend(local, module, document)

    @staticmethod
    def _configured_backend(local: Any, module: ModuleInfo, document: bytes) -> Any:
        from arras.adapters.truss import ModuleAccess, create_backend

        return create_backend(
            "truss_conformance",
            local._person_source,
            local._installing,
            module_access={
                module.name: ModuleAccess(
                    json.loads(document)["id"],
                    local.reader_role(module.name),
                    local.writer_role(module.name),
                    local.auditor_role(module.name),
                )
            },
        )

    def grant(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool = False) -> None:
        local = self._open()
        if self._module is None:
            raise RuntimeError("install must precede granting corpus people")
        person = local.person(user)
        for module, modes in modules.items():
            if module != self._module.name:
                raise ValueError("the conformance resource holds one module")
            for mode in modes:
                role = {
                    "read": local.reader_role(module),
                    "write": local.writer_role(module),
                    "journal": local.auditor_role(module),
                    "schema": local.registrar_role,
                }.get(mode)
                if role is None:
                    raise ValueError(f"unknown corpus grant {mode!r}")
                local.membership(user, role, grant=True)
        self._people[user] = Principal(person.user, person.token, admin=admin)
        if any("read" in modes for modes in modules.values()) and self._backend is not None:
            self._backend.catalog(self._people[user])

    def principal(self, name: str) -> Principal:
        if name == "anon":
            return Principal("anon", "")
        return self._people[name]

    def borrowed(self, user: str, token_owner: str) -> Principal:
        return Principal(user, self._people[token_owner].token)

    def foreign_token(self) -> str:
        if self._foreign_receipt is None:
            corpus = load_corpus()
            module = __import__("arras.umf", fromlist=["parse_module"]).parse_module(
                corpus["_module_text"]
            )
            self._foreign_receipt = self._make_foreign_receipt(module, corpus["_module_text"])
        return self._foreign_receipt

    def _make_foreign_receipt(self, module: ModuleInfo, document: str) -> str:
        from arras.adapters.truss.local import LocalTruss

        local = LocalTruss("conformance_foreign")
        self._owned.append(local)
        local.open()
        assert local.backend is not None
        admin = local.person("arras_foreign_admin")
        local.membership(admin.user, local.registrar_role, grant=True)
        admin = Principal(admin.user, admin.token, admin=True)
        raw = document.encode()
        local.backend.register(admin, raw, module, unknown_endpoint="reject")
        local.configure_module(module.name, json.loads(document)["id"])
        backend = self._configured_backend(local, module, raw)
        writer = local.person("arras_foreign_writer")
        local.membership(writer.user, local.reader_role(module.name), grant=True)
        local.membership(writer.user, local.writer_role(module.name), grant=True)
        action = next(a for a in module.actions if a.name.endswith("AddUseCase"))
        plan = resolve(
            action,
            {"code": f"foreign-{uuid.uuid4().hex}", "name": "Foreign receipt"},
            module,
            new_key=lambda: f"foreign-{uuid.uuid4().hex}",
        )
        receipt = backend.apply(writer, plan, idempotency_key=None)
        if not isinstance(receipt, Receipt):
            raise RuntimeError("the owned foreign Truss did not issue a receipt")
        return receipt.token

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        if self._backend is None or self._module is None:
            raise RuntimeError("install must precede corpus imports")
        outcome = self._backend.import_records(
            self.principal(user), self._module.name, records, load_id="seed", initiated_by=user
        )
        if outcome.rejected:
            raise ValueError(f"the conformance fixture import was rejected: {outcome.rejected}")

    def write(self, user: str, plan: Plan) -> str:
        if self._backend is None:
            raise RuntimeError("install must precede corpus writes")
        receipt = self._backend.apply(self.principal(user), plan, idempotency_key=None)
        if not isinstance(receipt, Receipt):
            raise RuntimeError("the conformance write did not return a receipt")
        return receipt.token

    def sync(self) -> None:
        pass

    def outage(self, reason: str | None) -> None:
        local = self._open()
        if reason == "unsupported_version":
            if self._outage != "unsupported_version":
                from arras.adapters.truss._conformance import tamper_install_marker

                self._unsupported_marker = tamper_install_marker(
                    local, self._unsupported_marker, restore=False
                )
            self._outage = reason
            return
        if self._outage == "unsupported_version":
            from arras.adapters.truss._conformance import tamper_install_marker

            self._unsupported_marker = tamper_install_marker(
                local, self._unsupported_marker, restore=True
            )
        local.outage(reason)
        self._outage = reason

    def expire(self, user: str) -> None:
        self._open().expire(user)

    def backend(self) -> Any:
        if self._backend is None:
            raise RuntimeError("install must precede backend operations")
        return self._backend

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors: list[Exception] = []
        for resource in reversed(self._owned):
            try:
                resource.close()
            except Exception as error:
                errors.append(error)
        self._owned.clear()
        if errors:
            raise RuntimeError(f"failed to close {len(errors)} owned Truss resource(s)") from None


__all__ = ["TrussHarness"]
