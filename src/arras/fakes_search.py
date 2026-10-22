# SPDX-License-Identifier: MIT OR Apache-2.0
"""Text search for the in-memory backends (CONTRACT-010, CONTRACT-004).

The memory adapter declares `substring` for every type and matches a `TextMatch` in memory: every
word must occur, after the fold, in at least one of the named properties. A word is plain text, so
`%`, `_` and `\\` match as themselves. A host can make a type declare `none` (or a narrower
`searchable`) to see the interface treat it as not searched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from arras.model import Capabilities, EntityTypeInfo, SearchMode
from arras.searchplan import TextMatch


def searchable_properties(t: EntityTypeInfo) -> tuple[str, ...]:
    """The single-valued string properties, optional ones included."""
    return tuple(
        p.name for p in t.properties if p.scalar and p.type == "string" and p.cardinality != "many"
    )


def text_matches(props: Mapping[str, Any], text: TextMatch) -> bool:
    """Whether every word is in at least one of the named properties, folded with `str.lower`."""
    values = [v.lower() for p in text.properties if isinstance(v := props.get(p), str)]
    return all(any(word in value for value in values) for word in text.words)


def with_search(caps: Capabilities, t: EntityTypeInfo, mode: SearchMode) -> Capabilities:
    """`caps` declaring `mode` for the type."""
    return replace(
        caps, search=mode, searchable=searchable_properties(t) if mode == "substring" else ()
    )
