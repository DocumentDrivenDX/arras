# SPDX-License-Identifier: MIT OR Apache-2.0
"""Private, owned-database hooks used by the native conformance harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arras.adapters.truss.local import LocalTruss


def tamper_install_marker(
    local: LocalTruss, saved_marker: str | None, *, restore: bool
) -> str | None:
    """Simulate a release mismatch only in a harness-owned throwaway database."""
    if local.persistent:
        raise RuntimeError("marker simulation is allowed only on an owned throwaway database")
    if local.superuser_password is None:
        raise RuntimeError("the owned Truss superuser credential is unavailable")

    import psycopg

    params = local.endpoint.parameters()
    params.update(user="postgres", password=local.superuser_password, autocommit=True)
    with psycopg.connect(**params) as conn:
        table = "truss.catalog_runtime_installation"
        if not restore:
            row = conn.execute(f"SELECT release_id FROM {table}").fetchone()
            if row is None:
                raise RuntimeError("the owned Truss installation marker is missing")
            saved_marker = str(row[0])
            conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER catalog_immutable")
            conn.execute(
                f"UPDATE {table} SET release_id = %s", ["truss-catalog-runtime/0.39-candidate"]
            )
        else:
            if saved_marker is None:
                raise RuntimeError("no owned install marker is available to restore")
            conn.execute(f"UPDATE {table} SET release_id = %s", [saved_marker])
            conn.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER catalog_immutable")
            saved_marker = None
    return saved_marker
