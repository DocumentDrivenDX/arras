# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A failed `LocalTruss.open()` leaves no database process and no root behind. A scripted cluster:
no database is started."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from arras.adapters.truss.local import LocalTruss


class FakeCluster:
    entered = 0
    exited = 0

    def __init__(self, path: Path) -> None:
        self.info = SimpleNamespace(connection_uri="postgresql://postgres@/postgres?host=/tmp/x")

    def __enter__(self) -> FakeCluster:
        FakeCluster.entered += 1
        return self

    def __exit__(self, *exc: object) -> None:
        FakeCluster.exited += 1


def test_a_failed_open_stops_the_cluster_and_removes_its_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truss = pytest.importorskip("truss")
    monkeypatch.setattr(truss, "LocalPostgres", FakeCluster)
    FakeCluster.entered = FakeCluster.exited = 0

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("no role")

    monkeypatch.setattr("psycopg.connect", refuse)
    local = LocalTruss()
    root = local.root
    with pytest.raises(RuntimeError, match="no role"):
        local.open()
    assert (FakeCluster.entered, FakeCluster.exited, root.exists()) == (1, 1, False)
