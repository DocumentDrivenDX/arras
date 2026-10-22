# SPDX-License-Identifier: MIT OR Apache-2.0
"""The resolved view of a module, kept by module and revision (CONTRACT-010, "Where the view lives").

A view is read from the module's registered document and resolved against its types. The document
changes only with a new revision, so a resolution is good for as long as the module's revision is
the one it was made at. The cache holds no access decision: the caller has already been shown the
module, and it holds no entity data.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from arras.errors import Invalid, Unsupported
from arras.model import ModuleInfo
from arras.results import RegisteredDocument
from arras.types import Revision
from arras.view import ResolvedModule, declared_from_text, resolve


class ViewCache:
    """The latest resolution of each module, with the revision it was made at."""

    def __init__(self) -> None:
        self._held: dict[str, tuple[Revision, ResolvedModule]] = {}
        self._lock = threading.Lock()

    def resolve(self, mod: ModuleInfo, fetch: Callable[[], RegisteredDocument]) -> ResolvedModule:
        """The module's view at its revision. `fetch` reads the registered document as the caller;
        a module that holds none (attached, never registered) has the defaults."""
        known = all(v is not None for v in mod.revision.by_backend.values())
        with self._lock:
            held = self._held.get(mod.name)
        if known and held is not None and held[0] == mod.revision:
            return held[1]
        try:
            doc: RegisteredDocument | None = fetch()
        except (Unsupported, Invalid):
            doc = None
        declared = declared_from_text(doc.text, mod) if doc is not None else None
        resolved = resolve(mod, declared)
        if known and (doc is None or doc.revision == mod.revision):
            with self._lock:
                self._held[mod.name] = (mod.revision, resolved)
        return resolved

    def clear(self) -> None:
        with self._lock:
            self._held.clear()
