# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""A host embeds Arras through public names only (CONTRACT-005)."""

import subprocess
import sys
import textwrap

from arras import Arras, Principal, Unavailable
from arras.sandbox import Sandbox

WIRING = textwrap.dedent(
    """
    from arras import Arras, Placement, Principal
    from arras.console import create_app

    def build(store, replica, admin: Principal) -> Arras:
        return Arras.start(
            {"memory": store, "memory_replica": replica},
            expected=("memory", "memory_replica"),
            admin=admin,
            default_placement=Placement("memory", ("memory_replica",)),
        )

    def mount(ar: Arras):
        return create_app(ar, principal_for_request=lambda req: None, base_path="/arras")
    """
)


def test_a_host_using_public_names_passes_the_boundary_check(tmp_path):
    pkg = tmp_path / "fakehost"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "wiring.py").write_text(WIRING)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "arras.boundary",
            "--host",
            str(tmp_path),
            "--host-package",
            "fakehost",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


LIFECYCLE = textwrap.dedent(
    """
    from arras import Arras, MigrationResult
    from arras.adapters.truss import ModuleAccess, create_backend

    def build(source, installing, admin) -> tuple[Arras, object]:
        backend = create_backend(
            "truss", source, installing,
            module_access={"catalog": ModuleAccess("catalog", "catalog_reader", "catalog_writer")},
        )
        return Arras.start({"truss": backend}, expected=("truss",), admin=admin), backend

    def deploy(ar: Arras, backend) -> MigrationResult:
        result = ar.migrate(timeout=30)
        backend.configure_access(["catalog"])
        return result
    """
)


def _check_host(tmp_path, text: str):
    pkg = tmp_path / "fakehost"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "wiring.py").write_text(text)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "arras.boundary",
            "--host",
            str(tmp_path),
            "--host-package",
            "fakehost",
        ],
        capture_output=True,
        text=True,
    )


def test_a_host_building_the_truss_backend_through_its_factory_passes_the_boundary_check(tmp_path):
    run = _check_host(tmp_path, LIFECYCLE)
    assert run.returncode == 0, run.stdout + run.stderr


def test_a_host_reaching_the_truss_connection_layer_fails_the_boundary_check(tmp_path):
    run = _check_host(tmp_path, "from arras.adapters.truss.connection import Connections\n")
    assert run.returncode != 0 and "is not a public module of arras" in run.stdout + run.stderr
    run = _check_host(tmp_path / "b", "from arras.adapters.truss import Connections\n")
    assert run.returncode != 0


def test_the_lifecycle_wiring_runs_against_a_stand_in_source():
    from arras.adapters.truss import create_backend

    ns: dict = {}
    exec(LIFECYCLE, ns)
    ar, backend = ns["build"](None, None, None)  # no source: not configured, never raises
    assert ar.status()["truss"].reason == "not_configured"
    assert isinstance(backend, type(create_backend("truss", None)))


def test_the_fakes_are_not_public_to_a_host(tmp_path):
    """The raw fakes stay internal: a host reaches them through `arras.testing`."""
    pkg = tmp_path / "fakehost"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "testing.py").write_text("from arras.fakes import MemoryStore\n")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "arras.boundary",
            "--host",
            str(tmp_path),
            "--host-package",
            "fakehost",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0


def test_a_host_starts_serves_degrades_and_closes():
    box = Sandbox().seed()
    ns: dict = {}
    exec(WIRING, ns)
    ar = ns["build"](box.store, box.replica, box.people["root"])
    assert all(s.available for s in ar.status().values())
    o = ar.session(box.people["carol"])
    assert o.query(
        "catalog",
        "SELECT u.* FROM catalog.UseCase u WHERE u.code = :k ORDER BY u.code LIMIT 100",
        {"k": "uc-pipeline"},
    ).rows
    box.store.available = False
    assert ar.status()["memory"].reason == "unreachable"
    try:
        o.query("catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100")
    except Unavailable as e:
        assert e.reason == "unreachable"
    else:
        raise AssertionError("a latest read with the record store down must be Unavailable")
    bulk = o.query(
        "catalog", "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 100", consistency="bulk"
    )
    assert bulk.freshness.backend == "memory_replica" and len(bulk.rows) == 2
    ar.close()


def test_a_missing_backend_is_reported_not_raised():
    box = Sandbox().seed()
    ar = Arras.start({"memory": box.store}, expected=("memory", "memory_replica"))
    assert ar.status()["memory_replica"].reason == "not_configured"
    assert isinstance(box.people["carol"], Principal)


def test_the_testing_module_is_public_and_a_hosts_tests_may_use_it(tmp_path):
    """`tests/test_testing.py` is written as a host's tests would be; it passes the check."""
    from pathlib import Path

    (tmp_path / "host_test.py").write_text((Path(__file__).parent / "test_testing.py").read_text())
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "arras.boundary",
            "--host",
            str(tmp_path),
            "--host-package",
            "host_test",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
