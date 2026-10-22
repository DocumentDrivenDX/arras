# SPDX-License-Identifier: MIT OR Apache-2.0
"""A world of fakes with people, a module and some data, for the dev host and for tests."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, cast

from arras.core import Arras
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.graphfile import GraphFile
from arras.model import Placement
from arras.telemetry import _logger  # pyright: ignore[reportPrivateUsage]
from arras.testing import example_module
from arras.types import Principal
from arras.umf import parse_module

# What a role grants, on every module, in the backends' own terms (the modes `FakeAccess` knows).
ROLES: dict[str, tuple[str, ...]] = {
    "none": (),
    "viewer": ("read",),
    "editor": ("read", "write"),
    "schema author": ("read", "schema"),
    "auditor": ("read", "journal"),
    "maintainer": ("read", "write", "journal", "schema"),
}
log = _logger("arras.sandbox")
NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")

Step = tuple[str, Mapping[str, Any]]
SANDBOX_STEPS: tuple[Step, ...] = (
    (
        "catalog.AddUseCase",
        {"code": "uc-pipeline", "name": "Pipeline mapping", "workArea": "data"},
    ),
    ("catalog.AddUseCase", {"code": "uc-alerts", "name": "Alert review", "workArea": "operations"}),
    (
        "catalog.AddSolution",
        {"code": "sol-1", "name": "Pipeline extractor", "useCase": "uc-pipeline"},
    ),
)


def read_steps(path: Path) -> list[Step]:
    """The seed file's steps; a `ValueError` says what is wrong with its shape."""
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("a seed file is a JSON list")
    steps: list[Step] = []
    for i, item in enumerate(cast(list[Any], raw)):
        step = cast(dict[str, Any], item) if isinstance(item, dict) else {}
        action, inputs = step.get("action"), step.get("inputs", {})
        if not isinstance(action, str) or not isinstance(inputs, dict):
            raise ValueError(f"step {i}: give an action name and an inputs object")
        steps.append((action, cast(dict[str, Any], inputs)))
    return steps


def catalog_document() -> str:
    """The sandbox's module: use cases and solutions, three actions, placed on the memory store.

    It is the corpus's module, so what the dev host shows is what the backends are tested with."""
    return example_module()


class Box(Protocol):
    """What the dev host serves and controls: a `Arras` and its people. `Sandbox` is the fakes;
    `arras.devtruss.TrussBox` is a local Truss. A control that has no meaning for a box raises
    `ValueError`, which the dev host answers as a 400."""

    arras: Arras
    people: dict[str, Principal]
    lock: Any

    @property
    def backends(self) -> Mapping[str, Any]: ...

    def principal(self, user: str | None) -> Principal: ...
    def person(self, name: str, role: str) -> Principal: ...
    def find(self, name: str) -> Principal | None: ...
    def load(self, document: str, steps: Iterable[Step] = ()) -> Box: ...
    def set_token(self, user: str, *, live: bool) -> None: ...
    def set_outage(self, backend: str, reason: str | None) -> None: ...
    def set_access(self, user: str, module: str, modes: list[str], *, grant: bool) -> None: ...
    def declare_search(self, backend: str, type: str, mode: str | None) -> None: ...
    def feed(self) -> None: ...
    def settle(self) -> None: ...


@dataclass
class Sandbox:
    """Fakes, a `Arras` over them, and a few people with tokens."""

    access: FakeAccess = field(default_factory=FakeAccess)
    people: dict[str, Principal] = field(default_factory=dict[str, Principal])
    minted: dict[str, tuple[str, Principal]] = field(
        default_factory=dict[str, tuple[str, Principal]]
    )  # name to (role, principal): people a developer made up
    lock: Any = field(default_factory=threading.RLock, repr=False)  # guards grants and the fakes
    warnings: list[str] = field(default_factory=list[str])  # what a load noticed and went on past

    def __post_init__(self) -> None:
        self.store = MemoryStore(self.access)
        self.replica = MemoryReplica(self.store, self.access)
        root = self.access.grant("root", "catalog", "read", "write", "schema", admin=True)
        # the host names its administrator, so no one else can claim to be one
        self.arras = Arras.start(
            self.backends,
            admin=root,
            default_placement=Placement(self.store.name, (self.replica.name,)),
        )
        self.people = {
            "root": replace(root, groups=("admins",)),
            "alice": replace(
                self.access.grant("alice", "catalog", "read", "write", "journal", "schema"),
                groups=("builders",),
            ),
            "carol": self.access.grant("carol", "catalog", "read"),
            "bob": replace(
                self.access.grant("bob", "catalog", "read", "write", "journal"),
                groups=("builders",),
            ),
            "dave": self.access.grant("dave", "elsewhere", "read"),
        }

    @property
    def backends(self) -> dict[str, MemoryStore | MemoryReplica]:
        """The sandbox's backends by the names the host gave them."""
        return {self.store.name: self.store, self.replica.name: self.replica}

    def seed(self) -> Sandbox:
        return self.load(catalog_document(), SANDBOX_STEPS)

    def load(
        self,
        document: str,
        steps: Iterable[Step] = (),
        records: GraphFile | None = None,
    ) -> Sandbox:
        """Register a module, run `steps` (an action and its inputs) as alice, then load `records`
        (a graph file, as the administrator: an import is administrative).

        A developer's own module takes the sandbox's place this way: whatever it is named, the
        people hold on it what they hold on `catalog`.

        A graph file that is not the whole graph (`complete` false, or not stated) loads, and the
        sandbox says so: in `warnings` and on the log."""
        name = parse_module(document).name
        if records is not None and records.module != name:
            raise ValueError(f"the graph file is for {records.module!r}, not {name!r}")
        self.know(name)
        root = self.arras.session(self.people["root"])  # the administrator registers
        root.registry().register(document)
        o = self.arras.session(self.people["alice"])
        for action, inputs in steps:
            o.invoke(action, dict(inputs))
        if records is not None:
            self.warn_if_partial(records)
            result = root.import_records(
                records.module, records.records, load_id=f"file:{records.module}"
            )
            if result.rejected:
                first = result.rejected[0]
                raise ValueError(
                    f"{len(result.rejected)} records were rejected; "
                    f"the first is {first.kind} {first.identity}: {first.reason}"
                )
        self.replica.feed()
        return self

    def warn_if_partial(self, records: GraphFile) -> None:
        if records.complete:
            return
        named = f" (omitted: {', '.join(records.omitted)})" if records.omitted else ""
        why = "is not the whole graph" if records.omitted else "is not marked complete"
        message = f"the graph file for {records.module!r} {why}{named}; the graph is what it holds"
        self.warnings.append(message)
        log.warning(message)

    def know(self, module: str) -> None:
        """Let the people use `module` as they use `catalog`: whatever a module is named, they
        hold on it what they hold on the sandbox's own."""
        with self.lock:
            for held in self.access.grants.values():
                held.update((module, mode) for m, mode in tuple(held) if m == "catalog")

    def person(self, name: str, role: str) -> Principal:
        """A made-up person who holds `role` on every module, with a token of their own.

        There is no sign-in to ask: the sandbox is for developing, so a name and a role are
        enough. The administrator and the sandbox's own people cannot be made up, and a name used
        again with another role has that role's grants and no others."""
        if role not in ROLES:
            raise ValueError(f"role is one of {sorted(ROLES)}")
        if not NAME.fullmatch(name) or name in self.people:
            raise ValueError("a name is 1 to 32 lower-case letters, digits, - or _, and not taken")
        with self.lock:
            held = self.minted.get(name)
            if held is not None and held[0] == role:
                return held[1]
            self.access.grants.pop(name, None)
            # A made-up person is an operator (the group `builders`), so the backends' grants for
            # the role, not the host's operator hook, decide what they may do.
            who = replace(
                self.access.grant(name, "*", *cast(Any, ROLES[role])), groups=("builders",)
            )
            self.minted[name] = (role, who)
            return who

    def find(self, name: str) -> Principal | None:
        """A sandbox person or one a developer made up, by name."""
        if name in self.people:
            return self.people[name]
        held = self.minted.get(name)
        return held[1] if held else None

    def set_token(self, user: str, *, live: bool) -> None:
        """`expire` (`live` false) or restore the token of a sandbox person or a made-up one."""
        person = self.find(user)
        if person is None:
            raise KeyError(user)
        if live:
            self.access.tokens[person.token] = person.user
        else:
            self.access.expire(person.token)

    def set_outage(self, backend: str, reason: str | None) -> None:
        self.backends[backend].outage = cast(Any, reason)

    def set_access(self, user: str, module: str, modes: list[str], *, grant: bool) -> None:
        held = self.access.grants.setdefault(user, set())
        for mode in modes:
            (held.add if grant else held.discard)((module, cast(Any, mode)))

    def declare_search(self, backend: str, type: str, mode: str | None) -> None:
        """What search `backend` declares for `type` (`catalog.UseCase`); `None` restores it."""
        if mode not in (None, "none", "substring"):
            raise ValueError(mode)
        self.backends[backend].declare_search(type, mode)

    def feed(self) -> None:
        self.replica.feed()

    def settle(self) -> None:
        """Let the replica catch up, after a seed."""
        self.replica.feed()

    def principal(self, user: str | None) -> Principal:
        if user is None:
            return self.people["alice"]
        if user == "(no token)":
            return Principal("alice", "")
        if user in self.people:
            return self.people[user]
        raise KeyError(user)
