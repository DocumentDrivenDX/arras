# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev host's Truss world: the sandbox's people over a real Truss on a local PostgreSQL (TR-14).

    uv run --extra devhost --extra truss --group truss-test python -m arras.devhost --truss
    uv run --extra devhost --extra truss python -m arras.devhost --truss --truss-url postgresql://...

`TrussBox` has the surface of `arras.sandbox.Box`, so `DevHost` serves it as it serves the
sandbox: root (the administrator) registers modules, alice and bob write, carol reads, and the
controls that make sense on a database are real (`expire` is `VALID UNTIL`, `grant` and `revoke` are
role membership, `outage` is a socket that is not there or a revoked CONNECT). The ones Truss
has no meaning for (a replica's `feed`, a declared `search`, the `migration_failed` outage) answer a
400. The sandbox itself stays on the memory adapter; this is a development aid, never a deployed
app. With no server to attach to the database is a throwaway, removed at exit. With one
(`url`, a PostgreSQL server that is already running: `arras.adapters.truss.local`) the state is
kept: starting again verifies the installation, registers the modules again (an unchanged document
is unchanged), makes the people's roles when they are absent and gives their tokens new passwords,
re-gives the grants, and seeds only when no module holds an entity yet (`holds_objects`);
`close` drops nothing and stops nothing, and `reset` starts clean. The people are the roles
`arrasdev_root`, `arrasdev_alice` and so on there: role names are cluster-wide.
"""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from arras.adapters.truss.local import LocalTruss
from arras.core import Arras
from arras.errors import ArrasError
from arras.graphfile import GraphFile
from arras.model import Placement
from arras.names import quoted, quoted_type
from arras.sandbox import NAME, ROLES, Step
from arras.types import Principal
from arras.umf import parse_module

BATCH = 32  # steps of one action a seed sends as one atomic group

# name to (groups, what they hold on every module); `dave` is a reader of a module no one has
# registered in the sandbox, so here he holds nothing
PEOPLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "root": (("admins",), ("read", "write", "schema")),
    "alice": (("builders",), ("read", "write", "journal", "schema")),
    "carol": ((), ("read",)),
    "bob": (("builders",), ("read", "write", "journal")),
    "dave": ((), ()),
}


class TrussBox:
    """A `Arras` over one local Truss and the people the dev host names."""

    def __init__(
        self,
        name: str = "primary",
        *,
        directory: Path | None = None,
        url: str | None = None,
        reset: bool = False,
    ) -> None:
        self.truss = LocalTruss(name, directory=directory, url=url, reset=reset).open()
        self.persistent = url is not None
        self.name = name
        self.lock = threading.RLock()
        self.modules: dict[str, str] = {}  # module name to its document's id ("" for a kept one)
        self.minted: dict[str, tuple[str, Principal]] = {}
        self.people: dict[str, Principal] = {}
        self._pending: list[
            tuple[str, list[Step], GraphFile | None]
        ] = []  # a persistent server's seeds, held back
        self._seed: bool | None = (
            None if self.persistent and not reset else True
        )  # a reset is empty
        try:
            for user, (groups, modes) in PEOPLE.items():
                who = self.truss.person(user)
                self.people[user] = replace(who, groups=groups, admin=user == "root")
                if "schema" in modes:  # the registrar role, installation-wide (D3)
                    self.truss.membership(user, self.truss.registrar_role, grant=True)
            if self.persistent:  # the modules of an earlier run keep their people
                for module in self.truss.known_modules():
                    self.modules[module] = ""
                    for user, (_, modes) in PEOPLE.items():
                        self._hold(user, module, modes, grant=True)
            backend = self.truss.backend
            assert backend is not None
            self.arras = Arras.start(
                {name: backend},  # type: ignore[dict-item]
                admin=self.people["root"],
                default_placement=Placement(name),
            )
        except BaseException:
            self.truss.close()
            raise

    def close(self) -> None:
        self.truss.close()

    @property
    def backends(self) -> Mapping[str, Any]:
        return {}  # no fake to serialise: each call is its own connection

    def use_token(self, user: str, token: str) -> None:
        """Give a sandbox person a token of the shape a client sends (the database password too)."""
        self.truss.set_password(user, token)
        self.people[user] = replace(self.people[user], token=token)

    # -- modules
    def load(
        self, document: str, steps: Iterable[Step] = (), records: GraphFile | None = None
    ) -> TrussBox:
        """Register a module as root, hand its roles to Truss, give the people what they hold on
        every module, and run `steps` as alice. On a persistent server the steps wait for `finish`,
        which runs them only if the database holds no entities."""
        module = parse_module(document).name
        self.arras.session(self.people["root"]).registry().register(document)
        document_id = json.loads(document)["id"]
        self.truss.configure_module(module, document_id)
        with self.lock:
            self.modules[module] = document_id
            for user, (_, modes) in PEOPLE.items():
                self._hold(user, module, modes, grant=True)
            for user, (role, _) in self.minted.items():
                self._hold(user, module, ROLES[role], grant=True)
        if self.persistent:
            self._pending.append((module, list(steps), records))
        else:
            self._run(steps)
            self._import(records)
        return self

    def _run(self, steps: Iterable[Step]) -> None:
        """Run `steps` as alice. Consecutive steps of one action go as atomic batches (one Truss group
        and one commit for up to `BATCH` of them, where one step alone is three transactions and
        dozens of statements); a batch the backend refuses (a step that depends on an earlier step of
        its own batch, a precondition that fails) is run again one step at a time, so the outcome and
        the error are those of the steps in order."""
        alice = self.arras.session(self.people["alice"])
        for action, run in itertools.groupby(steps, key=lambda step: step[0]):
            items = [dict(inputs) for _, inputs in run]
            for at in range(0, len(items), BATCH):
                chunk = items[at : at + BATCH]
                if len(chunk) > 1:
                    try:
                        alice.invoke_batch(action, chunk, atomic=True)
                        continue
                    except ArrasError:
                        pass
                for inputs in chunk:
                    alice.invoke(action, inputs)

    def _import(self, records: GraphFile | None) -> None:
        """Load a graph file as the administrator, as the sandbox does (an import is administrative):
        a record that already exists is skipped, a rejected one is an error."""
        if records is None:
            return
        root = self.arras.session(self.people["root"])
        result = root.import_records(
            records.module, records.records, load_id=f"file:{records.module}"
        )
        if result.rejected:
            first = result.rejected[0]
            raise ValueError(
                f"{len(result.rejected)} records were rejected; "
                f"the first is {first.kind} {first.identity}: {first.reason}"
            )

    def seed(self) -> TrussBox:
        from arras.sandbox import SANDBOX_STEPS, catalog_document

        return self.load(catalog_document(), SANDBOX_STEPS)

    @property
    def seeded(self) -> bool | None:
        """Whether this run seeded: None until `finish` decides on a persistent server."""
        return self._seed

    def holds_objects(self) -> bool:
        """Whether any registered module holds an entity: one row asked of every entity type, as
        alice, who reads every module. Truss keeps no count the installing role may read, so this is
        the test for "an empty database"."""
        alice = self.arras.session(self.people["alice"])
        for mod in alice.modules():
            for t in mod.entity_types:
                sql = f"SELECT x.{quoted(t.key)} FROM {quoted_type(f'{mod.name}.{t.local_name}')} x LIMIT 1"
                if alice.query(mod.name, sql, limit=1).rows:
                    return True
        return False

    def finish(self, extra: Callable[[TrussBox], object] | None = None) -> TrussBox:
        """Run the seed steps held back, then `extra`, when the database holds no entities (decided
        once, after every module is registered). A throwaway always seeds; steps given to `load`
        there have run already."""
        if self._seed is None:
            self._seed = not self.holds_objects()
        if self._seed:
            for _, steps, records in self._pending:
                self._run(steps)
                self._import(records)
            if extra is not None:
                extra(self)
        self._pending.clear()
        return self

    def _hold(self, user: str, module: str, modes: Iterable[str], *, grant: bool) -> None:
        """A person's membership in the module's roles; `schema` is the installation's registrar
        and `journal` is the module's audit role (Truss's own grant, separate from reading)."""
        for mode in modes:
            if mode == "read":
                role = self.truss.reader_role(module)
            elif mode == "write":
                role = self.truss.writer_role(module)
            elif mode == "journal":
                role = self.truss.auditor_role(module)
            else:
                continue
            self.truss.membership(user, role, grant=grant)

    # -- people
    def find(self, name: str) -> Principal | None:
        if name in self.people:
            return self.people[name]
        held = self.minted.get(name)
        return held[1] if held else None

    def principal(self, user: str | None) -> Principal:
        if user is None:
            return self.people["alice"]
        if user == "(no token)":
            return Principal("alice", "")
        if user in self.people:
            return self.people[user]
        raise KeyError(user)

    def person(self, name: str, role: str) -> Principal:
        """A made-up person: a login role holding `role` on every registered module."""
        if role not in ROLES:
            raise ValueError(f"role is one of {sorted(ROLES)}")
        if not NAME.fullmatch(name) or name in self.people:
            raise ValueError("a name is 1 to 32 lower-case letters, digits, - or _, and not taken")
        with self.lock:
            held = self.minted.get(name)
            if held is not None and held[0] == role:
                return held[1]
            who = self.truss.person(name)
            if held is not None:
                for module in self.modules:
                    self._hold(name, module, ROLES[held[0]], grant=False)
                if "schema" in ROLES[held[0]]:
                    self.truss.membership(name, self.truss.registrar_role, grant=False)
            for module in self.modules:
                self._hold(name, module, ROLES[role], grant=True)
            if "schema" in ROLES[role]:
                self.truss.membership(name, self.truss.registrar_role, grant=True)
            who = replace(who, groups=("builders",))  # an operator, as in the sandbox
            self.minted[name] = (role, who)
            return who

    # -- controls
    def set_token(self, user: str, *, live: bool) -> None:
        if self.find(user) is None:
            raise KeyError(user)
        self.truss.expire(user, restore=live)

    def set_outage(self, backend: str, reason: str | None) -> None:
        if backend != self.name:
            raise KeyError(backend)
        if reason is not None and reason not in self.truss.outages:
            raise ValueError(f"Truss can be made {' or '.join(self.truss.outages)}, not {reason}")
        self.truss.outage(reason)

    def set_access(self, user: str, module: str, modes: list[str], *, grant: bool) -> None:
        if module not in self.modules:
            raise ValueError(module)
        self._hold(user, module, modes, grant=grant)
        if "schema" in modes:
            self.truss.membership(user, self.truss.registrar_role, grant=grant)

    def declare_search(self, backend: str, type: str, mode: str | None) -> None:
        raise ValueError("Truss declares no text search to change")

    def feed(self) -> None:
        raise ValueError("Truss has no replica to feed")

    def settle(self) -> None:
        pass  # Truss is the record store and the provider: nothing lags


__all__ = ["PEOPLE", "TrussBox"]
