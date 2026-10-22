# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run only against built and installed Arras and extension-host distributions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    assert "env_prefix" not in distribution
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


def test_public_launcher_uses_packaged_example_config_and_env_prefix() -> None:
    config = resources.files("extension_host").joinpath("config", "default.toml")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "installed-example-test", "version": "0"},
        },
    }
    launcher = (
        "from arras.distribution import DistributionConfig; "
        "from arras.mcp import launch; "
        'launch([], distribution=DistributionConfig(env_prefix="EXTENSION_HOST"))'
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("ARRAS_", "EXTENSION_HOST_"))
        and key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env["PATH"] = os.environ.get("PATH", "")

    with tempfile.TemporaryDirectory() as cwd, resources.as_file(config) as config_path:
        env["EXTENSION_HOST_CONFIG_DIR"] = str(config_path.parent)
        result = subprocess.run(
            [sys.executable, "-I", "-c", launcher],
            input=json.dumps(request) + "\n",
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["result"]["serverInfo"]["name"] == "Extension Host Example MCP"
    assert "default.toml" in result.stderr


@pytest.mark.parametrize("resource", ["unknown.json", "module.umf.json"])
def test_example_refuses_resources_outside_its_explicit_allowlist(resource: str) -> None:
    with pytest.raises((OSError, ValueError)):
        compose(settings(resource))  # type: ignore[arg-type]
