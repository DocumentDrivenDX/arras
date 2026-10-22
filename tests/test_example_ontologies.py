# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The northwind and pizza examples: their files match their builders, they load with their seeds,
and all three examples can be served together (the interface then offers a module choice)."""

import importlib.util
from pathlib import Path

import pytest

from arras.devhost import build

EXAMPLES = Path(__file__).parent.parent / "examples"
NAMES = ["northwind", "pizza"]


def _builder(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_build", EXAMPLES / name / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", NAMES)
def test_files_match_their_builder(name: str) -> None:
    b = _builder(name)
    assert b.main(b.SPEC, EXAMPLES / name, ["--check"]) == 0


@pytest.mark.parametrize("name", NAMES)
def test_loads_with_its_seed(name: str) -> None:
    box = build(EXAMPLES / name / f"{name}.umf.json", EXAMPLES / name / "seed.json")
    alice = box.arras.session(box.people["alice"])
    assert name in {m.name for m in alice.modules()}


def test_three_modules_are_served_together() -> None:
    box = build(
        EXAMPLES / "catalog" / "catalog.umf.json",
        EXAMPLES / "catalog" / "seed.json",
        also=[(EXAMPLES / n / f"{n}.umf.json", EXAMPLES / n / "seed.json") for n in NAMES],
    )
    alice = box.arras.session(box.people["alice"])
    assert {"catalog", *NAMES} <= {m.name for m in alice.modules()}
