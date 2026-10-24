# SPDX-License-Identifier: MIT OR Apache-2.0
"""In-memory backends for a host's own tests (CONTRACT-005).

A host embeds Arras over Truss and Ashlar, neither of which a unit test can reach. The default
`InMemory` pair exercises legacy backend behavior. An explicit `arras-umf-set/1` opt-in creates a
single authority for the candidate action subset; it does not expose a replica.

    world = InMemory()
    world.register(module_document)                 # as the administrator
    carol = world.person("carol", "catalog", "read")   # a person the backends know
    world.arras.session(carol).query("catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100")

Differences from the real backends that a test must allow for:

- The replica copies the authority only when `sync()` is called, so a `bulk` read is stale until
  then, as a real replica is. Call `sync()` where a test expects the copy to have caught up.
- Access is a table of grants made with `person()`, not Postgres roles or Unity Catalog.
- Positions look like `fake:3`. A test must not parse a receipt's token.
- Nothing here measures latency or exercises migrations or connection sources.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import resources
from typing import Literal

from arras.core import Arras
from arras.errors import Unsupported
from arras.fakes import FakeAccess, MemoryReplica, MemoryStore
from arras.model import Placement
from arras.results import ImportResult, RegistryResult
from arras.types import Principal

Mode = Literal["read", "write", "journal", "schema"]

__all__ = ["InMemory", "example_module"]


def example_module() -> str:
    """A small UMF module (`catalog`: use cases and solutions, with actions) for a first test.

    It is placed on the memory authority with the memory replica, as `InMemory` places it."""
    return resources.files("arras.conformance").joinpath("module.umf.json").read_text()


class InMemory:
    """An in-memory store (reader and provider) and replica, the people they know, and a `Arras` over them."""

    def __init__(
        self,
        *,
        store: str = "memory",
        replica: str = "memory_replica",
        action_profile: Literal["arras-umf-set/1"] | None = None,
    ) -> None:
        """Create a legacy authority/replica pair or explicitly opted-in single authority."""
        if action_profile is not None and (
            type(action_profile) is not str or action_profile != "arras-umf-set/1"
        ):
            raise ValueError("unsupported in-memory action profile")
        self._action_profile: Literal["arras-umf-set/1"] | None = action_profile
        self._access = FakeAccess()
        self._store = MemoryStore(self._access, store, action_profile=action_profile)
        self._replica = MemoryReplica(self._store, self._access, replica)
        self.admin: Principal = self._access.grant(
            "admin", "*", "read", "write", "schema", admin=True
        )
        """The administrative principal: registers modules and imports records."""
        self.arras: Arras = self.start()
        """A `Arras` over both backends, naming `admin` as its administrator."""

    @property
    def backends(self) -> Mapping[str, MemoryStore | MemoryReplica]:
        """The backends by name, for `Arras.start` when a test needs its own instance."""
        if self._action_profile == "arras-umf-set/1":
            return {self._store.name: self._store}
        return {self._store.name: self._store, self._replica.name: self._replica}

    def start(
        self,
        *,
        backends: Sequence[str] | None = None,
        expected: Sequence[str] | None = None,
    ) -> Arras:
        """A new `Arras` over some of the backends (default all), as a host starting with one
        missing does. `expected` defaults to every backend, so an absent one is `not_configured`."""
        held = self.backends
        chosen = {n: b for n, b in held.items() if backends is None or n in backends}
        default_expected = (
            (self._store.name,) if self._action_profile == "arras-umf-set/1" else tuple(held)
        )
        default_placement = (
            Placement(self._store.name)
            if self._action_profile == "arras-umf-set/1"
            else Placement(self._store.name, (self._replica.name,))
        )
        return Arras.start(
            chosen,
            expected=default_expected if expected is None else tuple(expected),
            admin=self.admin,
            default_placement=default_placement,
            metadata_profile=self._action_profile or "legacy-arras/1",
        )

    # -- people

    def person(self, user: str, module: str, *modes: Mode) -> Principal:
        """A person the backends know, with a token and the given access to `module`.

        Called again for the same person it adds to what they may do; a call with no `modes`
        makes a person who is known but may do nothing, whom the backends refuse."""
        return self._access.grant(user, module, *modes)

    def expire(self, principal: Principal) -> None:
        """The backends no longer accept this principal's token, as after it lapses."""
        self._access.expire(principal.token)

    # -- the administrator's work

    def register(self, document: bytes | str) -> RegistryResult:
        """Register a module as the administrator, and tell the replica of it."""
        return self.arras.session(self.admin).registry().register(document)

    def import_records(
        self,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str = "test-load",
    ) -> ImportResult:
        """Load seed records as the administrator."""
        return self.arras.session(self.admin).import_records(module, records, load_id=load_id)

    # -- the replica and outages

    def sync(self) -> None:
        """Bring the legacy replica up to its authority's current position."""
        if self._action_profile == "arras-umf-set/1":
            raise Unsupported("sync", ["the selected action profile is store-only"])
        self._replica.feed()

    def set_available(self, backend: str, up: bool) -> None:
        """Take a backend down (`unreachable`) or bring it back. Operations that need it raise
        `Unavailable`, and those that do not still work."""
        self.backends[backend].available = up
