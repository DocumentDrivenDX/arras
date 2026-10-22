# SPDX-License-Identifier: MIT OR Apache-2.0
"""The pure parts of search (CONTRACT-010, section C): the fold, the words, ranking, excerpts and the
result types.

Nothing here reads a backend. `fold` and `check_text` turn what a person typed into the words a
backend matches; `rank` scores an entity the library has already received, re-checking the match
with the same fold so a backend's different case handling cannot show a non-match; `excerpt` cuts
the text a result shows around the first match as segments, never as markup. The text and the words
never leave this module in an error message: they are not telemetry (CONTRACT-008).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from arras.errors import Invalid, Violation
from arras.types import Freshness

MIN_CHARS = 2
MAX_CHARS = 200
MAX_WORDS = 6
MAX_LIMIT = 50
CANDIDATES = 50  # read per type
MAX_TYPES = 20  # searched in one request
MAX_ENTITIES = 1000  # a request's budget (CONTRACT-006)
EXCERPT_CHARS = 160
EXCERPT_BEFORE = 40  # context shown before the first match
BOUNDARY_SLACK = 16  # how far an excerpt moves to end at a word boundary
ELLIPSIS = "…"

NOT_SEARCHED_REASONS = ("no_searchable_property", "no_capability", "unavailable", "over_budget")


@dataclass(frozen=True)
class TextMatch:
    """A structured text match (CONTRACT-010): the entities for which every word occurs, after the
    fold, in at least one of the named string properties. It travels to the backend beside the
    statement as data, never as SQL text, and Arras does not read the statement it narrows."""

    words: tuple[str, ...]
    properties: tuple[str, ...]


# -- the text ----------------------------------------------------------------------------------


def lower(text: str) -> str:
    """`text` lowercased one character at a time (Unicode lowercase, no compatibility
    normalisation). Per character, so that the query, the ranking and the excerpt fold alike and
    each character's origin is known: `str.lower()` of a whole string is context-sensitive (a
    Greek capital sigma ending a word becomes a final sigma), which a character alone is not."""
    return "".join(c.lower() for c in text)


def fold(text: str) -> str:
    """Trimmed, whitespace runs collapsed to one space, then lowercased with `lower`."""
    return lower(" ".join(text.split()))


def check_text(text: str) -> tuple[str, tuple[str, ...]]:
    """The folded text and its words, or `Invalid` (`BAD_QUERY`). The message never repeats the
    text."""
    folded = fold(text)
    words = tuple(folded.split(" ")) if folded else ()
    if not MIN_CHARS <= len(folded) <= MAX_CHARS:
        raise Invalid(
            [Violation("text", "bound", f"text is {MIN_CHARS} to {MAX_CHARS} characters")]
        )
    if len(words) > MAX_WORDS:
        raise Invalid([Violation("text", "bound", f"text is at most {MAX_WORDS} words")])
    return folded, words


# -- ranking -----------------------------------------------------------------------------------


def tier(value: str, word: str) -> int:
    """How a folded value matches a folded word: 4 equal, 3 starts with it, 2 a word within it
    starts with it, 1 contains it, 0 not at all."""
    if value == word:
        return 4
    if value.startswith(word):
        return 3
    at = value.find(word)
    while at > 0:
        if not value[at - 1].isalnum():
            return 2
        at = value.find(word, at + 1)
    return 1 if word in value else 0


@dataclass(frozen=True)
class Ranked:
    """An entity that matched: its score, the properties that matched (in the type's order) and the
    first of them, which the excerpt is cut from."""

    score: int
    matched: tuple[str, ...]


def rank(words: Sequence[str], properties: Sequence[str], row: Mapping[str, Any]) -> Ranked | None:
    """`None` unless every word is in at least one property. Per word the best tier over the
    properties, each scaled by its position (`tier × (n − i)` for position `i` of `n`), summed."""
    values = {p: lower(v) for p in properties if isinstance(v := row.get(p), str)}
    n = len(properties)
    score = 0
    matched: set[str] = set()
    for word in words:
        best = 0
        for i, p in enumerate(properties):
            t = tier(values[p], word) if p in values else 0
            if t:
                matched.add(p)
                best = max(best, t * (n - i))
        if best == 0:
            return None
        score += best
    return Ranked(score, tuple(p for p in properties if p in matched))


# -- excerpts ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    text: str
    mark: bool


def _folded_with_origins(value: str) -> tuple[str, list[int]]:
    """`lower(value)` and, for each character of it, the index of the character it came from
    (a character can fold to more than one)."""
    parts: list[str] = []
    origins: list[int] = []
    for i, c in enumerate(value):
        lowered = c.lower()
        parts.append(lowered)
        origins.extend([i] * len(lowered))
    return "".join(parts), origins


def _spans(value: str, words: Sequence[str]) -> list[tuple[int, int]]:
    """The matched ranges of `value`, merged and in order."""
    folded, origins = _folded_with_origins(value)
    found: list[tuple[int, int]] = []
    for word in set(words):
        at = folded.find(word)
        while at >= 0 and word:
            found.append((origins[at], origins[at + len(word) - 1] + 1))
            at = folded.find(word, at + len(word))
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(found):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _window(value: str, first: tuple[int, int]) -> tuple[int, int]:
    """Up to 160 characters around the first match, moved to word boundaries where one is near."""
    if len(value) <= EXCERPT_CHARS:
        return 0, len(value)
    lo = max(0, first[0] - EXCERPT_BEFORE)
    hi = min(len(value), lo + EXCERPT_CHARS)
    if lo > 0:
        for i in range(lo, min(first[0], lo + BOUNDARY_SLACK)):
            if value[i - 1].isspace() and not value[i].isspace():
                lo = i
                break
    if hi < len(value):
        for i in range(hi, max(first[1], hi - BOUNDARY_SLACK), -1):
            if value[i].isspace():
                hi = i
                break
    return lo, hi


def excerpt(value: str, words: Sequence[str]) -> tuple[Segment, ...]:
    """The part of `value` around its first match, as consecutive segments: `mark` is true for the
    matched text. A cut start or end is an ellipsis, which is its own unmarked segment or part of
    the unmarked segment beside it. Empty when `value` contains no word."""
    spans = _spans(value, words)
    if not spans:
        return ()
    lo, hi = _window(value, spans[0])
    pieces: list[tuple[str, bool]] = []
    at = lo
    for s, e in spans:
        s, e = max(s, lo), min(e, hi)
        if s >= e:
            continue
        if s > at:
            pieces.append((value[at:s], False))
        pieces.append((value[s:e], True))
        at = e
    if at < hi:
        pieces.append((value[at:hi], False))
    if lo > 0:
        pieces = _join_ellipsis(pieces, front=True)
    if hi < len(value):
        pieces = _join_ellipsis(pieces, front=False)
    return tuple(Segment(t, m) for t, m in pieces)


def _join_ellipsis(pieces: list[tuple[str, bool]], *, front: bool) -> list[tuple[str, bool]]:
    edge = pieces[0] if front else pieces[-1]
    if edge[1]:  # a marked edge keeps its text exactly: the ellipsis is a segment of its own
        return [(ELLIPSIS, False), *pieces] if front else [*pieces, (ELLIPSIS, False)]
    joined = (ELLIPSIS + edge[0], False) if front else (edge[0] + ELLIPSIS, False)
    return [joined, *pieces[1:]] if front else [*pieces[:-1], joined]


# -- the results -------------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchHit:
    type: str  # the module's local type name
    key: str
    score: int
    label: str
    excerpt: tuple[Segment, ...] | None
    matched: tuple[str, ...]
    row: Mapping[str, Any]  # the entity as the read returned it: `alias.*`
    freshness: Freshness  # of the read it came from


@dataclass(frozen=True)
class TypeCount:
    type: str
    count: int
    at_least: bool


@dataclass(frozen=True)
class NotSearched:
    type: str
    reason: str  # one of NOT_SEARCHED_REASONS
    backend: str | None = None


@dataclass(frozen=True)
class SearchPage:
    text: str  # as searched, folded
    hits: tuple[SearchHit, ...]
    counts: tuple[TypeCount, ...]
    not_searched: tuple[NotSearched, ...]
    truncated: bool
    freshness: tuple[Freshness, ...]  # one per backend that answered


class Budget(Protocol):
    """A request's entity budget (CONTRACT-006): candidates are reserved before a query runs and
    settled to what it returned."""

    def try_reserve(self, n: int) -> bool: ...

    def settle(self, reserved: int, actual: int) -> None: ...


class EntityBudget:
    """The budget of a request that has no other fields: the whole 1,000."""

    def __init__(self, limit: int = MAX_ENTITIES) -> None:
        self.limit = limit
        self.used = 0

    def try_reserve(self, n: int) -> bool:
        if self.used + n > self.limit:
            return False
        self.used += n
        return True

    def settle(self, reserved: int, actual: int) -> None:
        self.used -= reserved - actual
