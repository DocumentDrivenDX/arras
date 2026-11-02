# SPDX-License-Identifier: MIT OR Apache-2.0
"""Optional people bookkeeping for backend conformance harnesses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from arras.actions import Plan
from arras.backend import Backend
from arras.model import ModuleInfo
from arras.types import Principal


class HarnessBase:
    """An optional base for a `Harness`: the people bookkeeping every harness repeats.

    A subclass states `roles` and `corpus_version` and implements `issue_token`, `install`,
    `seed`, `write`, `sync`, `outage`, `expire` and `backend`; the base supplies `grant`,
    `principal`, `borrowed` and `foreign_token`. `limits` and `close` stay optional, as on
    `Harness`. `run_corpus` takes a factory that builds a fresh instance per case."""

    roles: tuple[str, ...] = ()
    corpus_version: int = 0

    def __init__(self) -> None:
        self.users: dict[str, Principal] = {}

    def issue_token(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> str:
        """Make `user` known to the backend with the stated access, and return the token the
        backend knows them by. A call for a person already known adds to what they may do."""
        raise NotImplementedError

    def grant(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> None:
        self.users[user] = Principal(user, self.issue_token(user, modules, admin), admin=admin)

    def principal(self, name: str) -> Principal:
        return Principal("anon", "") if name == "anon" else self.users[name]

    def borrowed(self, user: str, token_owner: str) -> Principal:
        return Principal(user, self.users[token_owner].token)

    def foreign_token(self) -> str:
        """A string no backend issued and none can read as a position; override it for a backend
        whose positions this could parse as."""
        return "not-a-position"

    def install(self, module: ModuleInfo, document: bytes) -> None:
        raise NotImplementedError

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        raise NotImplementedError

    def write(self, user: str, plan: Plan) -> str:
        raise NotImplementedError

    def sync(self) -> None:
        raise NotImplementedError

    def outage(self, reason: str | None) -> None:
        raise NotImplementedError

    def expire(self, user: str) -> None:
        raise NotImplementedError

    def backend(self) -> Backend:
        raise NotImplementedError
