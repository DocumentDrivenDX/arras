# SPDX-License-Identifier: MIT OR Apache-2.0
"""Local-only integration checks for the strict install probe's real psycopg transaction modes."""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from test_truss_harness import Cluster, available

pytestmark = pytest.mark.truss


@pytest.fixture(scope="module")
def local_cluster() -> Generator[Cluster, None, None]:
    reason = available()
    if reason is not None:
        if os.environ.get("ARRAS_REQUIRE_TRUSS") == "1":
            pytest.fail(f"ARRAS_REQUIRE_TRUSS=1 and the Truss harness cannot run: {reason}")
        pytest.skip(reason)
    instance = Cluster()
    try:
        yield instance
    finally:
        instance.close()


TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
try:
    _NATIVE_SPEC = importlib.util.spec_from_file_location(
        "_lakebase_native_local_integration", TOOLS / "_lakebase_native.py"
    )
    assert _NATIVE_SPEC is not None and _NATIVE_SPEC.loader is not None
    native: Any = importlib.util.module_from_spec(_NATIVE_SPEC)
    sys.modules[_NATIVE_SPEC.name] = native
    _NATIVE_SPEC.loader.exec_module(native)
finally:
    sys.path.pop(0)


@pytest.mark.parametrize("autocommit", [False, True], ids=["driver-begins", "explicit-begin"])
def test_strict_probe_preserves_a_real_owned_transaction(
    local_cluster: Cluster,
    autocommit: bool,
) -> None:
    with local_cluster.bare_database() as bare:

        @contextmanager
        def installer_connection_source() -> Generator[Any, None, None]:
            with bare.installing_connection() as connection:
                connection.autocommit = autocommit
                yield connection

        probe = native._strict_default_probe(
            {"installer_connection_source": installer_connection_source}, ()
        )
        generated_roles = (probe.owner_role, probe.registrar_role)
        for role in generated_roles:
            if type(role) is str:
                bare.roles.append(role)

        assert probe.outcome == "unexpected_success"
        assert probe.caller_state_unchanged is True
        assert probe.native_state_unchanged is False
        assert type(probe.owner_role) is str
        assert type(probe.registrar_role) is str

    assert not local_cluster.su.execute(
        "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", [bare.db]
    ).fetchone()
    roles = [role for role in generated_roles if type(role) is str]
    assert len(roles) == 2
    assert (
        local_cluster.su.execute(
            "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)", [roles]
        ).fetchall()
        == []
    )
