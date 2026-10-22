# SPDX-License-Identifier: MIT OR Apache-2.0
"""Which backend serves a statement: the named module's placement and the consistency level
(CONTRACT-001, Query language).

Arras never reads the statement. `latest` is the module's record store. `bulk` is the first
replica of the placement, in order, that declares `read` for one of the module's types and whose
`query` accepts the statement: a replica that answers `Unsupported` falls through to the next and
finally to the record store, and any other outcome, a replica's outage included, is raised. A reader
the placement names that the host did not configure is `Unavailable` (`not_configured`). The wait
for `at_least` runs on each backend before it is asked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from arras import telemetry
from arras.backend import Backend
from arras.errors import Unavailable, Unsupported
from arras.model import ModuleInfo
from arras.results import Answer
from arras.searchplan import TextMatch
from arras.types import Consistency, Principal, Statement

Wait = Callable[[Backend, str], None]  # waits for `at_least` on a backend, or raises


class Router:
    """One statement over one module, for one principal."""

    def __init__(
        self,
        backends: Mapping[str, Backend],
        module: ModuleInfo,
        principal: Principal,
        statement: Statement,
        *,
        limit: int,
        wait: Wait,
        text: TextMatch | None = None,
    ) -> None:
        self.backends = backends
        self.module = module
        self.principal = principal
        self.statement = statement
        self.limit = limit
        self.wait = wait
        self.text = text

    def serve(self, consistency: Consistency) -> tuple[str, Answer]:
        """The backend that served, and its answer."""
        if consistency == "bulk":
            for name in self.module.placement.replicas:
                backend = self._backend(name)
                if not self._reads_the_module(backend):
                    continue
                try:
                    return name, self._ask(name, backend)
                except Unsupported:
                    continue  # this replica does not serve the statement: the next is asked
        record = self.module.placement.record
        return record, self._ask(record, self._backend(record))

    def _ask(self, name: str, backend: Backend) -> Answer:
        telemetry.annotate(backend=name)  # so a refusal or a wait that fails names who raised it
        self.wait(backend, name)
        return backend.query(
            self.principal, self.module.name, self.statement, limit=self.limit, text=self.text
        )

    def _reads_the_module(self, backend: Backend) -> bool:
        """Whether the replica declares `read` for any of the module's types. Arras does not
        know which type the statement reads; the replica's `query` decides the rest."""
        caps = backend.describe().capabilities
        return any((c := caps.get(t.name)) is not None and c.read for t in self.module.entity_types)

    def _backend(self, name: str) -> Backend:
        b = self.backends.get(name)
        if b is None:
            raise Unavailable(name, "not_configured", f"{name} is not configured")
        return b
