# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/extension_host"


def test_overlay_registers_only_own_module_and_explicitly_selected_resources() -> None:
    sys.path.insert(0, str(EXAMPLE / "src"))
    try:
        from extension_host.app import compose, run
        from extension_host.configuration import settings

        world, selected, source = compose(settings("seed.json"))
        reader = world.person("overlay_reader", "notes", "read")
        session = world.arras.session(reader)
        assert [module.name for module in session.describe()] == ["notes"]
        assert selected == "seed.json"
        assert source == (EXAMPLE / "src/extension_host/resources/module.umf.json").read_bytes()
        assert session.document("notes").text.encode() == source
        (seeded,) = session.query(
            "notes", "SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 1"
        ).rows
        assert seeded["_created_by"] == world.admin.user
        assert seeded["_load_id"] == "seed.json"

        result = run(settings("graph.json"))
        assert result["selected_resource"] == "graph.json"
        assert result["imported"] == 2
        assert result["created_by_action"] == 1
        assert result["actor"] == "example_owner"
    finally:
        sys.path.remove(str(EXAMPLE / "src"))


def test_two_explicit_hosts_keep_their_graphs_isolated() -> None:
    sys.path.insert(0, str(EXAMPLE / "src"))
    try:
        from extension_host.app import compose
        from extension_host.configuration import settings

        first, _, _ = compose(settings("seed.json"))
        second, _, _ = compose(settings("graph.json"))
        first_reader = first.person("first_reader", "notes", "read")
        second_reader = second.person("second_reader", "notes", "read")
        statement = "SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 100"
        first_rows = first.arras.session(first_reader).query("notes", statement).rows
        second_rows = second.arras.session(second_reader).query("notes", statement).rows
        assert {row["code"] for row in first_rows} == {"seeded"}
        assert {row["code"] for row in second_rows} == {"graph-one", "graph-two"}
    finally:
        sys.path.remove(str(EXAMPLE / "src"))
