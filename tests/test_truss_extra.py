# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The optional extra `truss`: its pin, its marker, and the stub backend.

The tests that need the extra installed carry the `truss` marker and run with
`uv run --extra truss pytest -m truss`. The rest run in every environment.
"""

from __future__ import annotations

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


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_the_extra_names_the_toolkit_the_adapter_checks() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    extra: list[str] = project["optional-dependencies"]["truss"]  # pyright: ignore[reportUnknownVariableType]
    assert [item.split("[")[0].split("=")[0] for item in extra] == [TOOLKIT_DISTRIBUTION]
    assert "truss-toolkit" not in " ".join(project["dependencies"])  # pyright: ignore[reportUnknownArgumentType]


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
         "tests/test_conformance_truss.py"],
        capture_output=True, text=True, cwd=ROOT,
    )  # fmt: skip
    return done.stdout


def test_a_default_run_collects_no_truss_test_and_the_marker_selects_it() -> None:
    name = "test_owned_harness_registers_and_issues_a_real_foreign_receipt"
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


def test_a_missing_or_other_toolkit_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def absent(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", absent)
    with pytest.raises(ImportError, match=r"arras\[truss\]"):
        require_toolkit()
    for outside in ("0.0.2", "0.1.0"):
        monkeypatch.setattr(metadata, "version", lambda name, v=outside: v)
        with pytest.raises(ImportError, match=f"{outside} is installed but >=0.0.50,<0.1"):
            require_toolkit()
    for inside in (TOOLKIT_VERSION, "0.0.56"):
        monkeypatch.setattr(metadata, "version", lambda name, v=inside: v)
        assert require_toolkit() == inside
