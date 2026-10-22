# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
EXAMPLE = ROOT / "examples/extension_host"
VERIFIER = ROOT / "tools/verify_extension_host.py"


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


def test_artifact_verifier_rejects_incomplete_or_nonpassing_reports() -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    verify_consumer = verifier["_verify_seed_or_graph"]
    verify_corpus = verifier["_verify_conformance"]
    verify_consumer(
        {
            "module": "notes",
            "selected_resource": "seed.json",
            "imported": 1,
            "created_by_action": 1,
        },
        "seed.json",
        1,
    )
    try:
        verify_consumer({"module": "catalog", "selected_resource": "seed.json"}, "seed.json", 1)
    except RuntimeError:
        pass
    else:
        raise AssertionError("wrong consumer module/resource must fail the artifact probe")

    verify_corpus(
        {
            "backend": "memory-store",
            "roles": ["reader", "provider"],
            "newer_corpus": False,
            "counts": {"passed": 1, "failed": 0, "harness_error": 0},
            "results": [{"case": "known", "status": "passed"}],
        }
    )
    for bad in (
        {
            "backend": "memory-store",
            "roles": ["reader", "provider"],
            "newer_corpus": False,
            "counts": {"passed": 0, "failed": 1},
            "results": [{}],
        },
        {
            "backend": "memory-store",
            "roles": ["reader", "provider"],
            "newer_corpus": True,
            "counts": {"passed": 1, "failed": 0},
            "results": [{}],
        },
        {
            "backend": "memory-store",
            "roles": ["reader", "provider"],
            "newer_corpus": False,
            "counts": {"passed": 0, "failed": 0},
            "results": [],
        },
    ):
        try:
            verify_corpus(bad)
        except RuntimeError:
            continue
        raise AssertionError(
            "an incomplete, failing or newer corpus must fail artifact verification"
        )


def test_fresh_artifact_mode_uses_public_indexes_and_installs_dependencies(tmp_path: Path) -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    environment = verifier["_environment"](
        {
            "PATH": "/usr/bin",
            "HOME": str(tmp_path),
            "PIP_INDEX_URL": "https://private.invalid/simple",
            "PIP_EXTRA_INDEX_URL": "https://extra.invalid/simple",
            "PIP_FIND_LINKS": "/private/wheels",
            "PIP_TRUSTED_HOST": "private.invalid",
            "UV_INDEX_URL": "https://private.invalid/simple",
            "UV_EXTRA_INDEX_URL": "https://extra.invalid/simple",
            "UV_DEFAULT_INDEX": "https://private.invalid/simple",
            "UV_FIND_LINKS": "/private/wheels",
        },
        tmp_path / "cache",
        fresh_dependencies=True,
    )
    assert environment["PIP_INDEX_URL"] == "https://pypi.org/simple"
    assert environment["UV_DEFAULT_INDEX"] == "https://pypi.org/simple"
    assert environment["PIP_CONFIG_FILE"] == os.devnull
    assert environment["UV_NO_CONFIG"] == "1"
    assert not any(
        key in environment
        for key in (
            "PIP_EXTRA_INDEX_URL",
            "PIP_FIND_LINKS",
            "PIP_TRUSTED_HOST",
            "UV_INDEX_URL",
            "UV_EXTRA_INDEX_URL",
            "UV_FIND_LINKS",
        )
    )
    command = verifier["_install_command"](
        Path("/venv/bin/python"), Path("arras.whl"), Path("consumer.whl")
    )
    assert "--no-deps" not in command
    assert "--isolated" in command
    assert command[command.index("--index-url") + 1] == "https://pypi.org/simple"
    assert command[command.index("pytest") - 1] == "https://pypi.org/simple"
    assert "pytest" in command
    assert command[-2:] == ["arras.whl", "consumer.whl"]
    build = verifier["_consumer_build_command"](Path("consumer"), Path("built"))
    assert "--no-config" in build
    assert build[build.index("--default-index") + 1] == "https://pypi.org/simple"


def test_fresh_artifact_mode_never_adds_shared_site_pth(tmp_path: Path) -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    isolated = tmp_path / "isolated-site"
    isolated.mkdir()
    assert (
        verifier["_configure_dependency_path"](
            isolated, tmp_path / "shared-site", fresh_dependencies=True
        )
        is None
    )
    assert list(isolated.iterdir()) == []

    reused = verifier["_configure_dependency_path"](
        isolated, tmp_path / "shared-site", fresh_dependencies=False
    )
    assert reused == (tmp_path / "shared-site").resolve()
    assert (isolated / "arras-verifier-dependencies.pth").read_text() == str(reused) + "\n"


def test_installed_pytest_report_requires_nonempty_clean_run(tmp_path: Path) -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    verify_report = verifier["_verify_installed_pytest_report"]
    report = tmp_path / "report.xml"
    report.write_text('<testsuites tests="2" failures="0" errors="0" skipped="0"/>')
    assert verify_report(report) == {"tests": 2, "failures": 0, "errors": 0, "skipped": 0}
    report.write_text(
        '<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
    )
    assert verify_report(report) == {"tests": 3, "failures": 0, "errors": 0, "skipped": 0}
    for xml in (
        '<testsuites tests="0" failures="0" errors="0" skipped="0"/>',
        '<testsuites tests="1" failures="1" errors="0" skipped="0"/>',
        '<testsuites tests="1" failures="0" errors="0" skipped="1"/>',
        '<testsuites><testsuite tests="1" failures="1" errors="0" skipped="0"/></testsuites>',
    ):
        report.write_text(xml)
        try:
            verify_report(report)
        except RuntimeError:
            pass
        else:
            raise AssertionError("empty, failing, or skipped installed tests must reject receipt")


def test_failed_command_diagnostic_includes_stdout_and_stderr(tmp_path: Path) -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    run = verifier["_run"]
    try:
        run(
            [
                sys.executable,
                "-c",
                "import sys; print('pytest failure summary'); print('detail', file=sys.stderr); sys.exit(1)",
            ],
            cwd=tmp_path,
            env=dict(os.environ),
        )
    except RuntimeError as exc:
        assert "pytest failure summary" in str(exc)
        assert "detail" in str(exc)
    else:
        raise AssertionError("nonzero subprocess must include captured output in its diagnostic")


def test_fresh_dependency_mode_is_exposed_by_the_cli(tmp_path: Path) -> None:
    verifier: dict[str, Any] = runpy.run_path(str(VERIFIER))
    seen: dict[str, Any] = {}

    def fake_verify(wheel: Path, output: Path, *, fresh_dependencies: bool) -> dict[str, Any]:
        seen.update(wheel=wheel, output=output, fresh=fresh_dependencies)
        return {
            "arras_wheel": {"sha256": "a"},
            "extension_host_wheel": {"sha256": "b"},
        }

    verifier["main"].__globals__["verify"] = fake_verify
    stdout = StringIO()
    with redirect_stdout(stdout):
        status = verifier["main"](
            [
                "--wheel",
                str(tmp_path / "arras.whl"),
                "--output-json",
                str(tmp_path / "r.json"),
                "--fresh-dependencies",
            ]
        )
    assert status == 0
    assert seen["fresh"] is True
    assert seen["wheel"] == tmp_path / "arras.whl"
    assert seen["output"] == tmp_path / "r.json"


def test_artifact_verifier_requires_an_existing_arras_wheel(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--wheel",
            str(tmp_path / "missing.whl"),
            "--output-json",
            str(tmp_path / "receipt.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "missing.whl" in result.stderr
    assert not (tmp_path / "receipt.json").exists()
