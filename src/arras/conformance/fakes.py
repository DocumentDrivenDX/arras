# SPDX-License-Identifier: MIT OR Apache-2.0
"""Harnesses that let the in-memory fakes run the corpus."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from arras.actions import Plan
from arras.backend import Backend
from arras.conformance import HarnessBase
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.model import ModuleInfo
from arras.results import Receipt


class _Base(HarnessBase):
    roles: tuple[str, ...] = ()
    corpus_version = 13

    def __init__(self) -> None:
        super().__init__()
        self.access = FakeAccess()
        self.auth = MemoryStore(self.access)
        self.root = self.access.grant("root", "catalog", "read", "write", "schema", admin=True)

    def issue_token(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> str:
        token = f"token-{user}"
        self.access.tokens[token] = user  # known by token, with whatever grants follow
        for module, modes in modules.items():
            token = self.access.grant(user, module, *cast(Any, modes), admin=admin).token
        return token

    def install(self, module: ModuleInfo, document: bytes) -> None:
        self.auth.register(self.root, document, module, unknown_endpoint="reject")

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        p = self.users[user]
        r = self.auth.import_records(p, "catalog", records, load_id="seed", initiated_by=user)
        if r.rejected:
            raise ValueError(f"the corpus fixture did not load: {r.rejected}")

    def write(self, user: str, plan: Plan) -> str:
        r = self.auth.apply(self.users[user], plan, idempotency_key=None)
        assert isinstance(r, Receipt)
        return r.token

    def expire(self, user: str) -> None:
        self.access.expire(self.users[user].token)


class MemoryStoreHarness(_Base):
    roles = ("reader", "provider")

    def backend(self) -> Backend:
        return self.auth

    def sync(self) -> None:
        pass

    def outage(self, reason: str | None) -> None:
        self.auth.outage = cast(Any, reason)


class MemoryReplicaHarness(_Base):
    roles = ("reader",)

    def __init__(self) -> None:
        super().__init__()
        self.replica = MemoryReplica(self.auth, self.access)

    def install(self, module: ModuleInfo, document: bytes) -> None:
        super().install(module, document)
        self.replica.attach(self.root, self.auth.modules[module.name])

    def backend(self) -> Backend:
        return self.replica

    def sync(self) -> None:
        self.replica.feed()

    def outage(self, reason: str | None) -> None:
        self.replica.outage = cast(Any, reason)
