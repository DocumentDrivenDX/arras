# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run only against built and installed Arras and extension-host distributions."""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

import extension_host
import pytest
from extension_host import Arras, InMemory, Principal
from extension_host.app import compose, run
from extension_host.configuration import settings

import arras


def test_example_uses_installed_packages_and_explicit_seed_and_graph_resources() -> None:
    checkout = Path(__file__).resolve().parents[3]
    for package in (arras, extension_host):
        assert package.__file__ is not None
        path = Path(package.__file__).resolve()
        assert not path.is_relative_to(checkout), f"{package.__name__} imported from {path}"

    seed_settings = settings("seed.json")
    assert seed_settings.distribution.brand.name == "Extension Host Example"
    seed_world, selected, source = compose(seed_settings)
    assert isinstance(seed_world, InMemory)
    assert isinstance(seed_world.arras, Arras)
    assert selected == "seed.json"
    expected_source = (
        resources.files("extension_host").joinpath("resources", "module.umf.json").read_bytes()
    )
    assert source == expected_source
    reader = seed_world.person("installed_reader", "notes", "read")
    assert isinstance(reader, Principal)
    assert [module.name for module in seed_world.arras.session(reader).describe()] == ["notes"]
    rows = (
        seed_world.arras.session(reader)
        .query("notes", "SELECT e.* FROM notes.Entry e ORDER BY e.code LIMIT 10")
        .rows
    )
    assert [row["code"] for row in rows] == ["seeded"]
    assert rows[0]["_created_by"] == seed_world.admin.user
    assert rows[0]["_load_id"] == "seed.json"

    config = resources.files("extension_host").joinpath("config", "default.toml")
    config_data = tomllib.loads(config.read_text(encoding="utf-8"))
    distribution = config_data["distribution"]
    assert distribution["mcp_server_name"] == "Extension Host Example MCP"
    assert distribution["env_prefix"] == "EXTENSION_HOST"
    assert distribution["telemetry"] == {
        "attribute_namespace": "extension_host",
        "log_prefix": "extension_host",
        "event_prefix": "extension_host",
    }
    assert not {"endpoint", "token", "token_file", "dev_sandbox"}.intersection(config_data)

    graph_result = run(settings("graph.json"))
    assert graph_result["module"] == "notes"
    assert graph_result["selected_resource"] == "graph.json"
    assert graph_result["imported"] == 2
    assert graph_result["created_by_action"] == 1
    assert graph_result["actor"] == "example_owner"
    assert graph_result["imported_by"] == "admin"


@pytest.mark.parametrize("resource", ["unknown.json", "module.umf.json"])
def test_example_refuses_resources_outside_its_explicit_allowlist(resource: str) -> None:
    with pytest.raises((OSError, ValueError)):
        compose(settings(resource))  # type: ignore[arg-type]
