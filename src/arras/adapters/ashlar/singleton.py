# SPDX-License-Identifier: MIT OR Apache-2.0
"""One person's bounded lookup through Ashlar's public pinned-read operation.

This internal bridge does not compile Weft, interpret native carriers, issue a
Position or compare receipts. The eventual Backend must add those separately.
The host owns authenticated sessions and current policy; there is no default
credential source, pin authority or permissive policy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from arras.errors import Refused, Unavailable
from arras.types import Principal


@dataclass(frozen=True)
class Selection:
    """Explicit immutable publication and native identity, never a latest alias."""

    publication_id: str
    table: str
    kind: Literal["object", "edge"]
    source: str
    type_id: int
    entity_id: int


@dataclass(frozen=True, repr=False)
class Session:
    """Ports supplied afresh by the host for the exact requesting Principal.

    The source must authenticate executor, backend, pins and policy as that
    person, maintain their deadline and close them on exit. Ashlar independently
    checks the original full vector, publication, current authority and row
    policy, including absence. These are required ports, never inferred grants.
    """

    executor: Any
    backend: Any
    pins: Any
    vector: Any
    policy: Any
    context: Any
    supported_profiles: Sequence[str]
    supported_revisions: Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class Observation:
    publication_id: str
    row: Mapping[str, Any] | None = field(repr=False)


SessionSource = Callable[[Principal], AbstractContextManager[Session]]


def _read_singleton() -> Callable[..., Any]:
    # No unpinned owner package is discovered by the base distribution.
    raise ImportError("The host must supply the Ashlar read owner")


class SingletonReads:
    def __init__(
        self,
        name: str,
        sessions: SessionSource,
        *,
        read_singleton: Callable[..., Any] | None = None,
    ) -> None:
        self.name = name
        self.sessions = sessions
        self._read = read_singleton

    def lookup(self, principal: Principal, selection: Selection) -> Observation:
        if not principal.token:
            raise Refused(self.name, "query")
        try:
            read = self._read if self._read is not None else _read_singleton()
        except ImportError:
            raise Unavailable(
                self.name, "unsupported_version", "Ashlar read API unavailable"
            ) from None
        primary: Exception | None = None
        try:
            with self.sessions(principal) as session:
                try:
                    row = read(
                        session.executor,
                        session.backend,
                        session.pins,
                        session.vector,
                        session.policy,
                        publication_id=selection.publication_id,
                        table=selection.table,
                        kind=selection.kind,
                        source=selection.source,
                        type_id=selection.type_id,
                        entity_id=selection.entity_id,
                        context=session.context,
                        supported_profiles=tuple(session.supported_profiles),
                        supported_revisions={
                            key: tuple(values)
                            for key, values in session.supported_revisions.items()
                        },
                    )
                    # Copy before the host releases its session. Ashlar has
                    # already completed its own pin/policy release checks.
                    result = Observation(
                        selection.publication_id,
                        None if row is None else MappingProxyType(dict(row)),
                    )
                except Exception as error:
                    primary = error
                    raise
            return result
        except PermissionError as error:
            if primary is not None and primary is not error:
                # A cleanup denial cannot reclassify an earlier outage.
                raise Unavailable(self.name, "unreachable", "Ashlar pinned read failed") from None
            raise Refused(self.name, "query") from None
        except Exception:
            # Native errors can contain SQL, values and credentials. Unknown
            # failures never become empty rows, denied access or known-behind.
            raise Unavailable(self.name, "unreachable", "Ashlar pinned read failed") from None
