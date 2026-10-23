# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private per-call catalog collection shared by the Arras interface (CONTRACT-002)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from arras.backend import Backend
from arras.errors import ArrasError, Refused, Unavailable
from arras.model import ModuleInfo, Placement
from arras.types import Principal


@dataclass(frozen=True)
class Catalogs:
    """What each backend said about the modules the principal may read, and who failed."""

    by_backend: dict[str, Mapping[str, ModuleInfo]]
    failures: dict[str, ArrasError]

    def failure(self) -> ArrasError | None:
        """The error to report: an expired token is `Refused`, whatever else is down."""
        refused = [e for e in self.failures.values() if isinstance(e, Refused)]
        return (refused or list(self.failures.values()) or [None])[0]

    def module(self, name: str) -> ModuleInfo | None:
        """The record store's copy where it answered, else another backend's."""
        holders = [(b, c[name]) for b, c in self.by_backend.items() if name in c]
        for b, module in holders:
            if module.placement.record == b:
                return module
        return holders[0][1] if holders else None

    def of(self, backend: str, name: str) -> ModuleInfo | None:
        return self.by_backend.get(backend, {}).get(name)

    def names(self) -> list[str]:
        return sorted({name for catalog in self.by_backend.values() for name in catalog})


def collect_catalogs(
    backends: Mapping[str, Backend],
    principal: Principal,
    placement_of: Callable[[str], Placement | None],
) -> Catalogs:
    """Collect fresh catalogs as this principal, filtering to host-placed readable modules."""
    by_backend: dict[str, Mapping[str, ModuleInfo]] = {}
    failures: dict[str, ArrasError] = {}
    for name, backend in backends.items():
        try:
            held = backend.catalog(principal)
        except (Unavailable, Refused) as error:
            failures[name] = error
            continue
        by_backend[name] = {
            module: replace(info, placement=placement)
            for module, info in held.items()
            if (placement := placement_of(module)) is not None and name in placement.readers
        }
    return Catalogs(by_backend, failures)
