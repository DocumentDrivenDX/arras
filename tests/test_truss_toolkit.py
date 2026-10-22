# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The optional extra `truss`: its pin, its marker, and the stub backend.

The tests that need the extra installed carry the `truss` marker and run with
`uv run --extra truss pytest -m truss`. The rest run in every environment.
"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

from arras.adapters.truss import (
    TOOLKIT_DISTRIBUTION,
    TOOLKIT_VERSION,
    TrussBackend,
    require_toolkit,
)
from arras.backend import Provider
from arras.errors import ArrasError, Unavailable, Unsupported

ROOT = Path(__file__).resolve().parent.parent
WEFT_VERSION = "0.4.49"


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_the_extra_pins_the_toolkit_the_adapter_names() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    extra: list[str] = project["optional-dependencies"]["truss"]  # pyright: ignore[reportUnknownVariableType]
    assert extra == [f"{TOOLKIT_DISTRIBUTION}[native,query]=={TOOLKIT_VERSION}"]
    assert "truss-toolkit" not in " ".join(project["dependencies"])  # pyright: ignore[reportUnknownArgumentType]


def test_the_toolkit_and_weft_resolve_from_the_committed_find_links_page() -> None:
    uv = _pyproject()["tool"]["uv"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert uv["find-links"] == ["tools/find-links/index.html"]  # pyright: ignore[reportUnknownVariableType]
    page = (ROOT / "tools/find-links/index.html").read_text()
    assert f"/truss/releases/download/v{TOOLKIT_VERSION}/" in page
    assert f"/weft/releases/download/v{WEFT_VERSION}/" in page
    assert len(re.findall(r"#sha256=[0-9a-f]{64}\"", page)) == 6 + 12  # plus pgserver-pg18


def test_the_weft_pin_is_one_version_everywhere() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert f'WEFT_VERSION: "{WEFT_VERSION}"' in ci
    assert f"weft-sql {WEFT_VERSION}" in ci
    assert f"`weft-sql` {WEFT_VERSION}" in (ROOT / "README.md").read_text()
    assert f"`weft-sql` {WEFT_VERSION}" in (ROOT / "tests/test_weft_parser.py").read_text()
    lock = (ROOT / "uv.lock").read_text()
    assert re.search(rf'name = "weft-sql"\nversion = "{WEFT_VERSION}"', lock)
    assert re.search(rf'name = "truss-toolkit"\nversion = "{TOOLKIT_VERSION}"', lock)


def test_the_truss_marker_is_registered_and_a_default_run_leaves_it_out(
    request: pytest.FixtureRequest,
) -> None:
    markers: list[str] = request.config.getini("markers")  # pyright: ignore[reportAssignmentType]
    assert any(m.startswith("truss:") for m in markers)
    assert request.config.getini("addopts") == ["-m", "not truss"]


def _collected(*args: str) -> str:
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args,
         "tests/test_truss_toolkit.py"],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    return done.stdout


def test_a_default_run_collects_no_truss_test_and_the_marker_selects_it() -> None:
    name = "test_the_installed_extra_is_the_pinned_tuple"
    assert name not in _collected()
    assert name in _collected("-m", "truss")


PLACEHOLDERS: dict[str, tuple[tuple[object, ...], dict[str, object]]] = {  # placeholders only
    "describe": ((), {}),
    "catalog": ((None,), {}),
    "status": ((), {}),
    "query": ((None, "m", None), {"limit": 1}),
    "reached": ((None, "t"), {}),
    "attach": ((None, None), {}),
    "apply": ((None, None), {"idempotency_key": None}),
    "apply_batch": ((None, []), {"atomic": True, "idempotency_key": None}),
    "import_records": ((None, "m", []), {"load_id": "l", "initiated_by": "p"}),
    "changes": (
        (None,),
        {
            k: object()
            for k in ("module", "type", "key", "by", "action", "group", "since", "until", "after")
        }
        | {"limit": 1},
    ),
    "loads": ((None, "m"), {"limit": 1, "after": None}),
    "export_records": ((None, "m"), {"limit": 1, "after": None}),
    "register": ((None, b"", None), {"unknown_endpoint": "reject"}),
    "validate_register": ((None, b"", None), {"unknown_endpoint": "reject"}),
    "document": ((None, "m"), {}),
}


def _provider_operations() -> set[str]:
    return {
        n for n in dir(Provider) if not n.startswith("_") and callable(getattr(Provider, n, None))
    }


BUILT = {
    "describe",
    "catalog",
    "status",
    "query",
    "apply",
    "apply_batch",
    "import_records",
    "reached",
    "attach",
    "register",
    "validate_register",
    "document",
    "changes",
    "loads",
    "export_records",
}


def test_the_skeleton_is_a_provider_and_every_unbuilt_operation_names_its_slice() -> None:
    backend: Provider = TrussBackend("truss")
    # a method added to Provider with no placeholder here fails, so none is silently missed
    assert _provider_operations() == set(PLACEHOLDERS)
    for name in sorted(set(PLACEHOLDERS) - BUILT):
        args, kwargs = PLACEHOLDERS[name]
        with pytest.raises(NotImplementedError) as raised:
            getattr(backend, name)(*args, **kwargs)
        assert not isinstance(raised.value, ArrasError), name


def test_a_backend_with_no_connections_says_it_is_not_configured() -> None:
    backend = TrussBackend("truss")
    assert backend.describe().roles == ("reader", "provider")
    assert backend.describe().capabilities == {}
    status = backend.status()
    assert (status.available, status.reason) == (False, "not_configured")
    for name in (
        "catalog",
        "query",
        "apply",
        "import_records",
        "reached",
        "register",
        "validate_register",
        "document",
    ):
        args, kwargs = PLACEHOLDERS[name]
        with pytest.raises(Unavailable) as raised:
            getattr(backend, name)(*args, **kwargs)
        assert raised.value.reason == "not_configured", name
    with pytest.raises(Unsupported):
        backend.attach(None, None)  # pyright: ignore[reportArgumentType]


def test_every_toolkit_and_weft_file_in_the_lock_carries_a_hash() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    checked = 0
    for pkg in lock["package"]:
        if pkg["name"] not in ("truss-toolkit", "weft-sql"):
            continue
        assert not Path(pkg["source"]["registry"]).is_absolute()
        files = [*pkg.get("wheels", []), *([pkg["sdist"]] if "sdist" in pkg else [])]
        assert files, pkg["name"]
        for f in files:
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", f.get("hash", "")), f["url"]
            checked += 1
    assert checked == 6  # the toolkit's wheel (the sdist is not listed), Weft's five wheels


def test_the_truss_test_group_holds_the_local_server_and_every_wheel_is_hashed() -> None:
    groups = _pyproject()["dependency-groups"]
    assert groups["truss-test"] == [f"{TOOLKIT_DISTRIBUTION}[local]=={TOOLKIT_VERSION}"]  # pyright: ignore[reportIndexIssue]
    dev = " ".join(groups["dev"])  # pyright: ignore[reportIndexIssue, reportUnknownArgumentType]
    assert "truss" not in dev and "pgserver" not in dev
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    wheels = [w for p in lock["package"] if p["name"] == "pgserver-pg18" for w in p["wheels"]]
    assert len(wheels) == 9  # cp311 to cp313 on macOS 14 arm64 and manylinux x86_64 and aarch64
    for w in wheels:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", w.get("hash", "")), w["url"]
    page = (ROOT / "tools/find-links/index.html").read_text()
    assert "/pgserver/releases/download/pg18.6-pgv0.8.6-r2/" in page


def test_a_missing_or_other_toolkit_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", absent)
    with pytest.raises(ImportError, match=r"arras\[truss\]"):
        require_toolkit()
    monkeypatch.setattr(metadata, "version", lambda name: "0.0.2")
    with pytest.raises(ImportError, match="0.0.2 is installed but 0.0.45 is pinned"):
        require_toolkit()
    monkeypatch.setattr(metadata, "version", lambda name: TOOLKIT_VERSION)
    assert require_toolkit() == TOOLKIT_VERSION


@pytest.mark.truss
def test_the_installed_extra_is_the_pinned_tuple() -> None:
    import psycopg

    assert require_toolkit() == "0.0.45"
    assert metadata.version("weft-sql") == WEFT_VERSION
    assert metadata.version("psycopg") == "3.3.6"
    assert psycopg.pq.version() == 180006  # libpq 18.6
    import truss

    assert truss.__name__ == "truss"
