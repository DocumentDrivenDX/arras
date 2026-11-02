# SPDX-License-Identifier: MIT OR Apache-2.0
"""A custom backend and its conformance harness, written against public names only.

`ToyBackend` stands in for a host's own backend. It forwards to the store that `InMemory` exposes
through `arras.testing`, so the test needs nothing from `arras.fakes` or `arras.conformance.fakes`.
A real backend implements the same methods against its own store; only the harness shape
(`HarnessBase`, `run_corpus`) and the registration through `Arras.start` are the point here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from arras import (
    Arras,
    BackendStatus,
    BatchReceipt,
    ChangesPage,
    ImportResult,
    LoadsPage,
    ModuleInfo,
    Principal,
    Receipt,
    RecordsPage,
    RegisteredDocument,
    RegistrationCheck,
    RegistryResult,
    Revision,
    Statement,
    Validation,
)
from arras.backend import Answer, Backend, BackendInfo, Plan, Provider, TextMatch
from arras.conformance import HarnessBase, run_corpus
from arras.testing import InMemory, example_module


class ToyBackend:
    """A provider that delegates each operation to an inner store."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def describe(self) -> BackendInfo:
        return self.inner.describe()

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        return self.inner.catalog(principal)

    def status(self) -> BackendStatus:
        return self.inner.status()

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        return self.inner.query(principal, module, statement, limit=limit, text=text)

    def reached(self, principal: Principal, token: str) -> bool:
        return self.inner.reached(principal, token)

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        return self.inner.attach(principal, module)

    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation:
        return self.inner.apply(principal, plan, idempotency_key=idempotency_key, dry_run=dry_run)

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        return self.inner.apply_batch(
            principal,
            plans,
            atomic=atomic,
            idempotency_key=idempotency_key,
            stop_on_error=stop_on_error,
        )

    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        return self.inner.import_records(
            principal, module, records, load_id=load_id, initiated_by=initiated_by
        )

    def export_records(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> RecordsPage:
        return self.inner.export_records(principal, module, limit=limit, after=after)

    def changes(
        self,
        principal: Principal,
        *,
        module: str | None,
        type: str | None,
        key: str | None,
        by: str | None,
        action: str | None,
        group: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        after: str | None,
    ) -> ChangesPage:
        return self.inner.changes(
            principal,
            module=module,
            type=type,
            key=key,
            by=by,
            action=action,
            group=group,
            since=since,
            until=until,
            limit=limit,
            after=after,
        )

    def loads(
        self, principal: Principal, module: str, *, limit: int, after: str | None
    ) -> LoadsPage:
        return self.inner.loads(principal, module, limit=limit, after=after)

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        return self.inner.register(
            principal,
            document,
            module,
            unknown_endpoint=unknown_endpoint,
            expected_revision=expected_revision,
        )

    def validate_register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
    ) -> RegistrationCheck:
        return self.inner.validate_register(
            principal, document, module, unknown_endpoint=unknown_endpoint
        )

    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        return self.inner.document(principal, module)


class ToyHarness(HarnessBase):
    """What a from-scratch backend implements to run the corpus: the people, the module, the
    records, a write, an outage and an expired token, over a fresh backend per case."""

    roles = ("reader", "provider")
    corpus_version = 13

    def __init__(self) -> None:
        super().__init__()
        self.world = InMemory()
        self.toy = ToyBackend(self.world.backends["memory"])

    def issue_token(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> str:
        principal = self.world.person(
            user, "catalog", admin=admin
        )  # known by token, may do nothing yet
        for module, modes in modules.items():
            principal = self.world.person(user, module, *modes, admin=admin)  # type: ignore[arg-type]
        return principal.token

    def install(self, module: ModuleInfo, document: bytes) -> None:
        self.world.register(document)

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        result = self.toy.import_records(
            self.users[user], "catalog", records, load_id="seed", initiated_by=user
        )
        assert not result.rejected

    def write(self, user: str, plan: Plan) -> str:
        receipt = self.toy.apply(self.users[user], plan, idempotency_key=None)
        assert isinstance(receipt, Receipt)
        return receipt.token

    def sync(self) -> None:
        self.world.sync()

    def outage(self, reason: str | None) -> None:
        if reason is None:
            self.world.set_available("memory", True)
        else:
            self.world.set_available("memory", False, reason=reason)  # type: ignore[arg-type]

    def expire(self, user: str) -> None:
        self.world.expire(self.users[user])

    def backend(self) -> Backend:
        return self.toy


def test_the_toy_backend_satisfies_the_public_protocols() -> None:
    toy = ToyHarness().backend()
    assert isinstance(toy, ToyBackend)
    backend: Backend = toy  # a reader
    provider: Provider = ToyBackend(None)  # and a provider, for pyright
    assert backend.describe().roles == ("reader", "provider")
    assert provider is not None


def test_a_toy_backend_is_registered_through_arras_start() -> None:
    world = InMemory()
    toy = ToyBackend(world.backends["memory"])
    host = Arras.start({"memory": toy}, admin=world.admin)
    assert host.status()["memory"].available
    assert example_module()


def test_the_corpus_runs_against_a_harness_built_on_the_public_base() -> None:
    report = run_corpus(ToyHarness)
    assert [r for r in report.results if not r.ok] == []
    assert report.passed
