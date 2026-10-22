# SPDX-License-Identifier: MIT OR Apache-2.0
"""The catalog cache of the Truss adapter (plan decision D8).

Reading a person's catalog costs a reader-catalog call, one accepted-document read per module and a
parse (about 0.5 s on Truss), and core asks on every operation. The cache keeps the parsed module per
(document id, accepted digest, source catalog revision): the module entry of the reader catalog states
the revision at which the document's current bytes were accepted, and a document registered, rolled
back to earlier bytes and registered again has the same digest at a new revision.

It keeps one more thing per person: the last reader-catalog snapshot with the validator Truss gave it
(one for a read-only call and one for a read-write call: Truss's validator names the view of the
transaction it was given in), so the next call can ask Truss whether it changed (`reader_catalog_if_changed_in_transaction`) and,
when it did not, skip the catalog payload.

The cache never answers an access question. A caller asks Truss, as the person, on every call: the
conditional read re-answers that person's access each time (a revoked role is refused with the
validator in hand, and its entry is dropped), and the cache is used only to avoid re-reading a
catalog or re-parsing a document that answer names. It also remembers the latest module of each name
it has served, which is all `describe` (no person, no connection) can say about types.

It is shared between the host's threads, so every access holds the lock.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from arras.model import ModuleInfo

# (document id, accepted document digest, the revision at which those bytes were accepted)
Key = tuple[str, str, int]
CATALOG_HOLDERS = 1024  # people whose last snapshot is kept; the oldest is dropped past it


class CatalogCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._parsed: dict[Key, ModuleInfo] = {}
        self._seen: dict[str, ModuleInfo] = {}
        self._snapshots: dict[tuple[str, bool], tuple[Any, str]] = {}
        self._shown: dict[str, tuple[str, Mapping[str, ModuleInfo]]] = {}
        self._documents: dict[str, str] = {}  # module name -> the Truss document id it was read in

    def get(self, key: Key) -> ModuleInfo | None:
        with self._lock:
            return self._parsed.get(key)

    def put(self, key: Key, info: ModuleInfo) -> None:
        """Keep the module under its key, dropping the document's entries of other revisions."""
        with self._lock:
            self._parsed = {k: v for k, v in self._parsed.items() if k[0] != key[0]}
            self._parsed[key] = info
            self._documents[info.name] = key[0]
            self.note(info)

    def document_of(self, module: str) -> str | None:
        """The document id this module was last read in (not a statement about anyone's access)."""
        with self._lock:
            return self._documents.get(module)

    def snapshot(self, who: str, read_only: bool) -> tuple[Any, str] | None:
        """The (reader catalog, validator) last read as this person in a read-only or a read-write
        transaction, or None. Truss's validator names the person's view as the transaction sees it,
        and a read-only call and a read-write call do not share one, so each keeps its own."""
        with self._lock:
            return self._snapshots.get((who, read_only))

    def keep_snapshot(self, who: str, read_only: bool, catalog: Any, validator: str) -> None:
        with self._lock:
            self._snapshots.pop((who, read_only), None)
            self._snapshots[(who, read_only)] = (catalog, validator)
            while len(self._snapshots) > CATALOG_HOLDERS:
                del self._snapshots[next(iter(self._snapshots))]

    def keep_shown(self, who: str, validator: str, modules: Mapping[str, ModuleInfo]) -> None:
        """The modules a read-only `catalog` call showed this person, with the validator of the
        snapshot they were parsed from. It answers no access question: it is what a combined read
        presents, and Truss answers whether it is still the person's current view."""
        with self._lock:
            self._shown.pop(who, None)
            self._shown[who] = (validator, dict(modules))
            while len(self._shown) > CATALOG_HOLDERS:
                del self._shown[next(iter(self._shown))]

    def shown(self, who: str) -> tuple[str, Mapping[str, ModuleInfo]] | None:
        with self._lock:
            return self._shown.get(who)

    def drop_shown(self, who: str) -> None:
        with self._lock:
            self._shown.pop(who, None)

    def drop_snapshot(self, who: str) -> None:
        """Forget what was read as this person, in either kind of transaction."""
        with self._lock:
            self._shown.pop(who, None)
            for mode in (True, False):
                self._snapshots.pop((who, mode), None)

    def note(self, info: ModuleInfo) -> None:
        """The latest module served under its name (called with the lock held)."""
        held = self._seen.get(info.name)
        if held is None or _later(info, held):
            self._seen[info.name] = info

    def seen(self) -> list[ModuleInfo]:
        with self._lock:
            return list(self._seen.values())

    def remember(self, info: ModuleInfo) -> None:
        with self._lock:
            self.note(info)


def _later(new: ModuleInfo, old: ModuleInfo) -> bool:
    a, b = _number(new), _number(old)
    return a is None or b is None or a >= b


def _number(info: ModuleInfo) -> int | None:
    values = [v for v in info.revision.by_backend.values() if isinstance(v, int)]
    return values[0] if values else None
