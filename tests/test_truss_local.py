# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The dev Truss world's authentication (TR-14): no role, the cluster superuser included, connects
to the throwaway cluster without a password. Truss-marked: needs PostgreSQL 18.6."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from arras.adapters.truss.local import LocalTruss
from test_truss_harness import _require

pytestmark = pytest.mark.truss


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[LocalTruss]:
    _require()
    local = LocalTruss(directory=Path(tmp_path_factory.mktemp("ar", numbered=True)))
    local.open()
    try:
        yield local
    finally:
        local.close()


def _connect(world: LocalTruss, user: str, password: str | None) -> None:
    import psycopg

    params: dict[str, Any] = {"host": world.endpoint.host, "dbname": "postgres", "user": user}
    if password is not None:
        params["password"] = password
    psycopg.connect(**params, connect_timeout=5).close()


def test_the_superuser_needs_its_password_like_everyone_else(world: LocalTruss) -> None:
    import psycopg

    with pytest.raises(psycopg.OperationalError, match="password"):
        _connect(world, "postgres", None)
    with pytest.raises(psycopg.OperationalError, match="authentication failed"):
        _connect(world, "postgres", "wrong")
    _connect(world, "postgres", world.superuser_password)


def test_no_rule_trusts_a_connection_and_the_world_still_works(world: LocalTruss) -> None:
    from pathlib import Path as P

    hba = P(world.su.execute("SHOW hba_file").fetchone()[0]).read_text()
    rules = [ln.split() for ln in hba.splitlines() if ln.strip() and not ln.startswith("#")]
    assert rules == [["local", "all", "all", "scram-sha-256"]]
    who = world.person("quinn")
    assert world.backend is not None and who.token == world.token("quinn")
