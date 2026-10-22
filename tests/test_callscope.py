# SPDX-License-Identifier: MIT OR Apache-2.0
"""The call scope keeps what one operation learned for that operation only."""

from __future__ import annotations

import threading

from arras import callscope


def test_nothing_is_kept_outside_an_operation() -> None:
    callscope.keep("k", 1)
    assert callscope.kept("k") is None and callscope.consistent() == frozenset()


def test_what_an_operation_keeps_is_gone_when_it_returns() -> None:
    @callscope.scoped
    def op() -> int | None:
        callscope.keep("k", 1)
        callscope.declare_consistent("truss")
        assert callscope.consistent() == {"truss"}
        return callscope.kept("k")

    assert op() == 1
    assert callscope.kept("k") is None and callscope.consistent() == frozenset()
    assert op() == 1  # the next operation starts empty and keeps its own


def test_a_nested_operation_has_a_scope_of_its_own() -> None:
    with callscope.open_scope():
        callscope.keep("k", "outer")
        with callscope.open_scope():
            assert callscope.kept("k") is None
            callscope.keep("k", "inner")
        assert callscope.kept("k") == "outer"


def test_another_thread_never_sees_the_scope() -> None:
    seen: list[object] = []
    with callscope.open_scope():
        callscope.keep("k", 1)
        t = threading.Thread(target=lambda: seen.append(callscope.kept("k")))
        t.start()
        t.join()
    assert seen == [None]


def test_a_failing_operation_leaves_no_scope_behind() -> None:
    @callscope.scoped
    def op() -> None:
        callscope.keep("k", 1)
        raise ValueError

    try:
        op()
    except ValueError:
        pass
    assert callscope.kept("k") is None
