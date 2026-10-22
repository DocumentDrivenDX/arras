# SPDX-License-Identifier: MIT OR Apache-2.0
"""The scope of one Arras call: what the call itself learned, handed from one backend call of the
same operation to the next, and gone when the operation ends.

A person's read or action asks the backend for the catalog first (what may this person read) and then
makes its own backend call (`query`, `apply`). Both need the answer to the same question, and the
second one need not ask again within the operation. The scope carries the first answer to the second
and nothing further: it is opened by one operation (`scoped`), lives in that operation's thread or
task (a context variable, so a concurrent call of another person never sees it), is never read after
the operation returns, and is never a cache. The next call opens an empty scope and asks the backend.

It decides nothing about access. A backend that uses what the scope holds still runs its own call as
the person, and the datastore refuses a person who lost access between the two statements; the
scope only spares the second catalog read the first has just answered.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Generator, Hashable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

_scope: ContextVar[dict[Hashable, Any] | None] = ContextVar("arras_call_scope", default=None)
_CONSISTENT: Hashable = ("arras", "describe_from_the_call")


@contextmanager
def open_scope() -> Generator[None]:
    """An empty scope for the operation inside the block; an enclosing one is left untouched."""
    token = _scope.set({})
    try:
        yield
    finally:
        _scope.reset(token)


def scoped(fn: Callable[P, R]) -> Callable[P, R]:
    """Run the method in a scope of its own."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with open_scope():
            return fn(*args, **kwargs)

    return wrapper


def keep(key: Hashable, value: Any) -> None:
    """Keep `value` for the rest of this operation; nothing happens outside an operation's scope."""
    held = _scope.get()
    if held is not None:
        held[key] = value


def kept(key: Hashable) -> Any | None:
    """What this operation kept under `key`, or None."""
    held = _scope.get()
    return None if held is None else held.get(key)


def declare_consistent(backend: str) -> None:
    """A backend states that its `describe` was derived from the catalog this call read, so a
    registration landing in between cannot make the two disagree."""
    held = _scope.get()
    if held is not None:
        held[_CONSISTENT] = frozenset(held.get(_CONSISTENT, frozenset())) | {backend}


def consistent() -> frozenset[str]:
    """The backends whose `describe` came from this call's own catalog."""
    return frozenset(kept(_CONSISTENT) or ())
