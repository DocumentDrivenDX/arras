# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

_checker = importlib.import_module("tools.check_public_content")
_content_errors = _checker._content_errors
_python_dependency_errors = _checker._python_dependency_errors
_requirements_names = _checker._requirements_names
_npm_dependency_errors = _checker._npm_dependency_errors
check = _checker.check
consumer_import_errors = _checker.consumer_import_errors
sensitive_content_errors = _checker.sensitive_content_errors
pytest_junit_errors = _checker.pytest_junit_errors
production_import_errors = _checker.production_import_errors
validate_workspace_path = _checker.validate_workspace_path


def test_repository_public_origins_and_fixture_provenance_are_declared() -> None:
    assert check(ROOT) == []


def test_pep508_direct_reference_name_and_locked_origin_checks(tmp_path: Path) -> None:
    assert _requirements_names(
        [
            "plain-name",
            "versioned_name>=1.2",
            "extra-name[feature]==2.0",
            "umf-core @ https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/umf_core-0.10.0-py3-none-any.whl#sha256=abc",
        ]
    ) == {"plain-name", "versioned-name", "extra-name", "umf-core"}

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        (workspace / name).write_bytes((ROOT / name).read_bytes())
    policy = json.loads((ROOT / "tools/public-content-policy.json").read_text(encoding="utf-8"))
    expected = policy["dependencies"]["python"]
    lock_path = workspace / "uv.lock"
    lock = lock_path.read_text(encoding="utf-8")
    trusted = "https://github.com/DocumentDrivenDX/umf/releases/download/umf-v0.5.4/umf_core-0.10.0-py3-none-any.whl"

    lock_path.write_text(
        lock.replace(trusted, "https://untrusted.invalid/umf.whl"), encoding="utf-8"
    )
    assert any(
        "undeclared artifact origin" in error
        for error in _python_dependency_errors(workspace, expected)
    )

    lock_path.write_text(
        lock.replace(
            "sha256:49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9",
            "sha256:invalid",
        ),
        encoding="utf-8",
    )
    assert any(
        "without SHA-256" in error for error in _python_dependency_errors(workspace, expected)
    )


def test_undeclared_import_fails_only_in_consumer_scope(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "app.py").write_text("from arras.fakes import MemoryStore\n", encoding="utf-8")
    allowed = {"arras": {"Arras"}, "arras.testing": {"InMemory"}}
    errors = consumer_import_errors(consumer, allowed)
    assert errors and "undeclared Arras import arras.fakes" in errors[0]


def test_production_import_gate_rejects_undeclared_import_roots_and_literal_dynamic_imports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "arras"
    source.mkdir(parents=True)
    (source / "module.py").write_text(
        "import os\n"
        "from arras.types import Field\n"
        "import undeclared_consumer_package\n"
        "import importlib\n"
        "importlib.import_module('undeclared_dynamic_package.client')\n",
        encoding="utf-8",
    )
    errors = production_import_errors(
        source,
        {"declared_optional": {"distribution": "declared-extra", "source": "optional:extra"}},
    )
    assert any("undeclared_consumer_package" in error for error in errors)
    assert any("undeclared_dynamic_package" in error for error in errors)
    assert not any("'os'" in error or "'arras'" in error for error in errors)


def test_sensitive_check_catches_credential_shapes_without_customer_name_rules() -> None:
    assert sensitive_content_errors(
        "app.py", 'DATABASE_URL = "postgresql://user:secret@db.invalid/x"'
    )
    assert sensitive_content_errors("app.py", "-----BEGIN PRIVATE KEY-----\nmaterial")
    assert sensitive_content_errors("app.py", 'api_key = "a1b2c3d4e5f60718293a4b5c"')
    assert sensitive_content_errors("app.py", 'label = "a generic host application"') == []


def _mini_policy(root: Path, *, digest: str | None = None) -> dict[str, Any]:
    payload = b'{"example": true}\n'
    fixture = root / "fixtures" / "example.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(payload)
    (root / "sources").mkdir()
    (root / "sources" / "README.md").write_text("Authored fixture.\n", encoding="utf-8")
    manifest = root / "public-api.json"
    manifest.write_text(
        json.dumps(
            {"python": {"root_all": ["Arras"], "modules": {"arras": {"names": "root_all"}}}}
        ),
        encoding="utf-8",
    )
    return {
        "fixtures": {
            "roots": ["fixtures"],
            "entries": [
                {
                    "path": "fixtures/example.json",
                    "provenance": "authored-test-fixture",
                    "source": "sources/README.md",
                    "sha256": digest or hashlib.sha256(payload).hexdigest(),
                }
            ],
        },
        "sensitive_scan_files": [],
        "public_api_manifest": "public-api.json",
        "consumer_roots": [],
    }


def test_untracked_fixture_and_stale_digest_have_specific_safe_diagnostics(tmp_path: Path) -> None:
    policy = _mini_policy(tmp_path)
    (tmp_path / "fixtures" / "new.json").write_text("{}", encoding="utf-8")
    (tmp_path / "fixtures" / "example.json").write_text('{"changed": true}\n', encoding="utf-8")
    errors = _content_errors(tmp_path, policy)
    assert any("fixtures/new.json: JSON fixture has no provenance declaration" in e for e in errors)
    assert any("fixtures/example.json: fixture digest is stale" in e for e in errors)


def test_fixture_without_provenance_source_is_reported(tmp_path: Path) -> None:
    policy = _mini_policy(tmp_path)
    policy["fixtures"]["entries"][0]["source"] = "sources/missing.md"
    errors = _content_errors(tmp_path, policy)
    assert any("provenance source path is missing" in error for error in errors)


def test_optional_peer_may_be_absent_but_must_remain_optional_when_declared(
    tmp_path: Path,
) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    peer_name = "@example/renderer"
    policy = {
        "registry_host": "registry.npmjs.org",
        "required_runtime": {},
        "optional_peers": {peer_name: {"version": "*", "category": "optional-peer"}},
    }

    package = {"dependencies": {}}
    lock_root = {"dependencies": {}}
    (ui / "package.json").write_text(json.dumps(package), encoding="utf-8")
    (ui / "package-lock.json").write_text(
        json.dumps({"packages": {"": lock_root}}), encoding="utf-8"
    )
    assert _npm_dependency_errors(tmp_path, policy) == []

    package["peerDependencies"] = {peer_name: "*"}
    package["peerDependenciesMeta"] = {peer_name: {"optional": True}}
    lock_root["peerDependencies"] = package["peerDependencies"]
    lock_root["peerDependenciesMeta"] = package["peerDependenciesMeta"]
    (ui / "package.json").write_text(json.dumps(package), encoding="utf-8")
    (ui / "package-lock.json").write_text(
        json.dumps({"packages": {"": lock_root}}), encoding="utf-8"
    )
    assert _npm_dependency_errors(tmp_path, policy) == []

    package["peerDependenciesMeta"][peer_name]["optional"] = False
    (ui / "package.json").write_text(json.dumps(package), encoding="utf-8")
    assert any(
        "changed category or version" in error for error in _npm_dependency_errors(tmp_path, policy)
    )

    policy["optional_peers"][peer_name]["dev_dependency_version"] = "1.2.3"
    package["peerDependenciesMeta"][peer_name]["optional"] = True
    package["devDependencies"] = {peer_name: "1.2.2"}
    (ui / "package.json").write_text(json.dumps(package), encoding="utf-8")
    assert any(
        "dev test pin differs from policy" in error
        for error in _npm_dependency_errors(tmp_path, policy)
    )


def test_pytest_report_gate_rejects_empty_failed_skipped_and_unreadable_runs(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite tests="2" errors="0" failures="0" skipped="0" /></testsuites>',
        encoding="utf-8",
    )
    assert pytest_junit_errors(report, "native") == []

    for attributes, expected in (
        ('tests="0" errors="0" failures="0" skipped="0"', "collected no tests"),
        ('tests="1" errors="1" failures="0" skipped="0"', "has errors"),
        ('tests="1" errors="0" failures="1" skipped="0"', "has failures"),
        ('tests="1" errors="0" failures="0" skipped="1"', "has skipped"),
    ):
        report.write_text(f"<testsuite {attributes} />", encoding="utf-8")
        assert expected in pytest_junit_errors(report, "native")[0]

    report.write_text("not xml", encoding="utf-8")
    assert "unreadable" in pytest_junit_errors(report, "theme")[0]


def test_workflow_optional_stages_fail_closed_and_report_only_consumer_targets() -> None:
    workflow = (ROOT / ".github/workflows/downstream.yml").read_text(encoding="utf-8")
    assert 'ARRAS_REQUIRE_TRUSS: "1"' in workflow
    assert "native_setup_path:" in workflow
    consumer_section = workflow.split(
        "- name: Install and run explicit consumer test target", maxsplit=1
    )[1].split("      - name:", maxsplit=1)[0]
    consumer_script = consumer_section.split("        run: |", maxsplit=1)[1]
    assert consumer_script.lstrip().startswith("set -euo pipefail")
    assert '--junitxml="$RUNNER_TEMP/arras-downstream/consumer.xml"' in consumer_script
    assert consumer_script.index("-m pytest") < consumer_script.index('consumer.xml" consumer')
    for stage in (
        ("Optional native consumer target", "native", "status=consumer-target-passed"),
        ("Optional theme consumer target", "theme", "status=consumer-target-passed"),
    ):
        label, report_name, output = stage
        section = workflow.split(f"- name: {label}", maxsplit=1)[1].split(
            "      - name:", maxsplit=1
        )[0]
        script = section.split("        run: |", maxsplit=1)[1]
        assert script.lstrip().startswith("set -euo pipefail")
        pytest_position = script.index("-m pytest")
        receipt_position = script.index(
            f'python - "$RUNNER_TEMP/arras-downstream/{report_name}.xml"'
        )
        output_position = script.index(output)
        assert pytest_position < receipt_position < output_position
        assert "--junitxml=" in script
    assert "status=not_run" in workflow
    assert workflow.index("Optional consumer dependency setup") < workflow.index(
        "Install consumer project without implicit dependency resolution"
    )
    assert "--no-deps" in workflow
    theme_section = workflow.split("- name: Optional theme consumer target", maxsplit=1)[1]
    assert theme_section.index('"$GITHUB_WORKSPACE/$THEME_SETUP_PATH"') < theme_section.index(
        '"$GITHUB_WORKSPACE/$THEME_TEST_PATH"'
    )
    assert "renderer/theme pytest target" in workflow


def test_workflow_path_validation_rejects_traversal_control_and_symlink_escape(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "consumer"
    project.mkdir()
    target = project / "test.py"
    target.write_text("pass\n", encoding="utf-8")
    assert validate_workspace_path(workspace, "consumer/test.py", directory=False) == target
    for value in ("../outside.py", "/tmp/outside.py", "consumer/\ntest.py"):
        with pytest.raises(ValueError):
            validate_workspace_path(workspace, value, directory=False)

    outside = tmp_path / "outside.py"
    outside.write_text("pass\n", encoding="utf-8")
    (workspace / "escape.py").symlink_to(outside)
    with pytest.raises(ValueError, match="outside the workspace"):
        validate_workspace_path(workspace, "escape.py", directory=False)


def _embedded_workflow_python() -> list[str]:
    workflow = (ROOT / ".github/workflows/downstream.yml").read_text(encoding="utf-8")
    blocks = re.findall(
        r"(?m)^(?P<indent> +)[^\n]*<<'PY'\n(.*?)^(?P=indent)PY\s*$",
        workflow,
        flags=re.DOTALL,
    )
    return [textwrap.dedent(block) for _, block in blocks]


def _embedded_workflow_shell() -> list[str]:
    lines = (ROOT / ".github/workflows/downstream.yml").read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(?P<indent> +)run:\s*\|\s*$", lines[index])
        if match is None:
            index += 1
            continue

        base_indent = len(match.group("indent"))
        index += 1
        content: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip(" ")) <= base_indent:
                break
            content.append(line)
            index += 1
        blocks.append(textwrap.dedent("\n".join(content)) + "\n")
    return blocks


def test_workflow_shell_blocks_parse_and_optional_paths_skip_without_setup(
    tmp_path: Path,
) -> None:
    blocks = _embedded_workflow_shell()
    assert len(blocks) == 14
    for index, block in enumerate(blocks):
        parsed = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
        assert parsed.returncode == 0, f"workflow shell block {index}: {parsed.stderr}"

    consumer_setup = next(
        block for block in blocks if "Consumer dependency setup script: not supplied." in block
    )
    skipped_consumer = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", consumer_setup],
        text=True,
        env={**os.environ, "CONSUMER_SETUP_PATH": "", "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
    )
    assert skipped_consumer.returncode == 0, skipped_consumer.stderr
    assert "Consumer dependency setup script: not supplied." in skipped_consumer.stdout

    native_target = next(
        block for block in blocks if "No native consumer target was requested." in block
    )
    native_output = tmp_path / "native-output"
    skipped_native = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", native_target],
        text=True,
        env={
            **os.environ,
            "NATIVE_TEST_PATH": "",
            "GITHUB_OUTPUT": str(native_output),
        },
        capture_output=True,
    )
    assert skipped_native.returncode == 0, skipped_native.stderr
    assert native_output.read_text(encoding="utf-8").strip() == "status=not_run"

    theme_target = next(
        block for block in blocks if "No theme consumer target was requested." in block
    )
    theme_output = tmp_path / "theme-output"
    skipped_theme = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", theme_target],
        text=True,
        env={
            **os.environ,
            "THEME_TEST_PATH": "",
            "GITHUB_OUTPUT": str(theme_output),
        },
        capture_output=True,
    )
    assert skipped_theme.returncode == 0, skipped_theme.stderr
    assert theme_output.read_text(encoding="utf-8").strip() == "status=not_run"


def test_workflow_python_blocks_compile_and_run_without_upstream_tools(
    tmp_path: Path,
) -> None:
    blocks = _embedded_workflow_python()
    assert len(blocks) == 11
    for block in blocks:
        compile(block, "downstream workflow embedded Python", "exec")

    source_guard = next(
        block for block in blocks if "source_sha must be a full 40-hex commit" in block
    )
    valid_source = subprocess.run(
        [sys.executable, "-"],
        input=source_guard,
        text=True,
        env={**os.environ, "ARRAS_SOURCE_SHA": "a" * 40},
        capture_output=True,
    )
    assert valid_source.returncode == 0, valid_source.stderr
    for malformed_sha in ("a" * 39, "a" * 40 + "\nGITHUB_ENV=/tmp/injected"):
        rejected_source = subprocess.run(
            [sys.executable, "-"],
            input=source_guard,
            text=True,
            env={**os.environ, "ARRAS_SOURCE_SHA": malformed_sha},
            capture_output=True,
        )
        assert rejected_source.returncode != 0
        assert "full 40-hex commit" in rejected_source.stderr

    path_validation = next(
        block for block in blocks if "CONSUMER_PROJECT_PATH" in block and "checked_path" in block
    )

    workspace = tmp_path / "consumer-checkout"
    (workspace / "project").mkdir(parents=True)
    tests = workspace / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("def test_sample(): pass\n", encoding="utf-8")
    (tests / "native_setup.py").write_text("pass\n", encoding="utf-8")
    (tests / "consumer_setup.py").write_text("pass\n", encoding="utf-8")
    (tests / "theme_setup.py").write_text("pass\n", encoding="utf-8")
    env_file = tmp_path / "github-env"
    env = {
        **os.environ,
        "GITHUB_WORKSPACE": str(workspace),
        "GITHUB_ENV": str(env_file),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "WHEEL_URL": "https://example.invalid/arras-1.2.3-py3-none-any.whl",
        "WHEEL_SHA256": "a" * 64,
        "CONSUMER_PROJECT_PATH": "project",
        "CONSUMER_SETUP_PATH": "tests/consumer_setup.py",
        "CONSUMER_TEST_PATH": "tests/test_sample.py",
        "NATIVE_TEST_PATH": "tests/test_sample.py",
        "NATIVE_SETUP_PATH": "tests/native_setup.py",
        "THEME_TEST_PATH": "tests/test_sample.py",
        "THEME_SETUP_PATH": "tests/theme_setup.py",
    }
    result = subprocess.run(
        [sys.executable, "-"], input=path_validation, text=True, env=env, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    saved_env = env_file.read_text(encoding="utf-8")
    assert "ARRAS_CONSUMER_SETUP_SHA256=" in saved_env
    assert "ARRAS_NATIVE_SETUP_SHA256=" in saved_env
    assert "ARRAS_THEME_SETUP_SHA256=" in saved_env

    escaped_env = {**env, "CONSUMER_TEST_PATH": "../outside.py"}
    result = subprocess.run(
        [sys.executable, "-"],
        input=path_validation,
        text=True,
        env=escaped_env,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "workspace" in result.stderr

    missing_theme_env = {**env, "THEME_TEST_PATH": ""}
    result = subprocess.run(
        [sys.executable, "-"],
        input=path_validation,
        text=True,
        env=missing_theme_env,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "theme test target" in result.stderr

    junit_blocks = [block for block in blocks if "xml.etree.ElementTree" in block]
    assert len(junit_blocks) == 3
    report = tmp_path / "report.xml"
    for block in junit_blocks:
        report.write_text('<testsuite tests="2" errors="0" failures="0" skipped="0" />')
        passed = subprocess.run(
            [sys.executable, "-", str(report), "native"],
            input=block,
            text=True,
            capture_output=True,
        )
        assert passed.returncode == 0, passed.stderr
        for attrs in (
            'tests="1" errors="0" failures="0" skipped="1"',
            'tests="0" errors="0" failures="0" skipped="0"',
            'tests="1" errors="1" failures="0" skipped="0"',
            'tests="1" errors="0" failures="1" skipped="0"',
        ):
            report.write_text(f"<testsuite {attrs} />", encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, "-", str(report), "native"],
                input=block,
                text=True,
                capture_output=True,
            )
            assert rejected.returncode != 0


def test_workflow_supplied_wheel_payload_verifier_detects_replacement(tmp_path: Path) -> None:
    blocks = _embedded_workflow_python()
    verifier = next(block for block in blocks if "installed Arras payload differs" in block)
    fake_site = tmp_path / "site-packages"
    package = fake_site / "arras"
    dist_info = fake_site / "arras-1.2.3.dist-info"
    package.mkdir(parents=True)
    dist_info.mkdir()
    payloads = {
        "arras/__init__.py": b"VERSION = 'verified'\n",
        "arras-1.2.3.dist-info/METADATA": b"Metadata-Version: 2.1\nName: arras\nVersion: 1.2.3\n\n",
        "arras-1.2.3.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
    }
    (package / "__init__.py").write_bytes(payloads["arras/__init__.py"])
    (dist_info / "METADATA").write_bytes(payloads["arras-1.2.3.dist-info/METADATA"])
    (dist_info / "WHEEL").write_bytes(payloads["arras-1.2.3.dist-info/WHEEL"])
    wheel_path = tmp_path / "arras-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        for name, payload in payloads.items():
            wheel.writestr(name, payload)
        wheel.writestr("arras-1.2.3.dist-info/RECORD", "")
    verifier_path = tmp_path / "verify-installed-wheel.py"
    verifier_path.write_text(verifier, encoding="utf-8")
    verifier_env = {
        **os.environ,
        "PYTHONPATH": str(fake_site),
        "ARRAS_WHEEL_SHA256": hashlib.sha256(wheel_path.read_bytes()).hexdigest(),
    }
    passed = subprocess.run(
        [sys.executable, "-S", str(verifier_path), str(wheel_path)],
        text=True,
        env=verifier_env,
        capture_output=True,
    )
    assert passed.returncode == 0, passed.stderr
    (package / "__init__.py").write_bytes(b"VERSION = 'replaced'\n")
    replaced = subprocess.run(
        [sys.executable, "-S", str(verifier_path), str(wheel_path)],
        text=True,
        env=verifier_env,
        capture_output=True,
    )
    assert replaced.returncode != 0
    assert "payload differs" in replaced.stderr

    changed_wheel = tmp_path / "changed-wheel.whl"
    changed_wheel.write_bytes(wheel_path.read_bytes() + b"changed")
    changed = subprocess.run(
        [sys.executable, "-S", str(verifier_path), str(changed_wheel)],
        text=True,
        env=verifier_env,
        capture_output=True,
    )
    assert changed.returncode != 0
    assert "changed after its SHA-256 was verified" in changed.stderr
