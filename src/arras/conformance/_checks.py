# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private expectation checks shared by the conformance runner."""

from __future__ import annotations

from typing import Any

from arras.errors import ArrasError


class Failure(AssertionError):
    def __init__(self, message: str, cause: ArrasError | None = None) -> None:
        super().__init__(message)
        self.cause = cause  # the backend's error a step ended in, when it did


def eq(label: str, got: Any, want: Any) -> None:
    if got != want:
        raise Failure(f"{label}: {got!r} != {want!r}")


def check_rows(want: list[dict[str, Any]], out: Any) -> None:
    got_rows: list[dict[str, Any]] = list(out.rows)
    eq("row count", len(got_rows), len(want))
    for i, (row, w) in enumerate(zip(got_rows, want, strict=True)):
        for k, v in w.items():
            if k not in row:
                raise Failure(f"row {i} has no {k!r}")
            eq(f"row {i}.{k}", row[k], v)


def check_row_len(want: dict[str, int], out: Any) -> None:
    for col, n in want.items():
        eq(f"len({col})", len(out.rows[0][col]), n)


def check_refs(want: list[dict[str, Any]], out: Any) -> None:
    for i, w in enumerate(want):
        for k, v in w.items():
            eq(f"refs[{i}].{k}", getattr(out.refs[i], k), v)


def check_weft(want: dict[str, Any], out: Any) -> None:
    """`version` present, and the profiles a backend declares (`profiles` as a set)."""
    weft = out.weft
    if weft is None:
        raise Failure("describe names no Weft version")
    for k, v in want.items():
        if k == "has_version":
            eq("weft.version present", bool(weft.version), v)
        elif k == "profiles_include":
            missing = sorted(set(v) - set(weft.profiles))
            eq("weft.profiles missing", missing, [])
        else:
            raise Failure(f"unknown weft expectation {k!r}")


def check_capabilities(want: dict[str, dict[str, Any]], out: Any) -> None:
    for type_name, capabilities in want.items():
        for key, value in capabilities.items():
            eq(f"{type_name}.{key}", getattr(out.capabilities[type_name], key), value)
