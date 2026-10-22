# SPDX-License-Identifier: MIT OR Apache-2.0
"""Execute the release YAML's native verifier shell block with controlled Python outcomes."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def installed_native_run_block() -> str:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    marker = "      - name: Run the complete installed-native verifier\n        run: |\n"
    assert workflow.count(marker) == 1
    content = workflow.split(marker, 1)[1]
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("      - ") or line.startswith("  #"):
            break
        if not line.strip():
            lines.append("")
            continue
        assert line.startswith("          "), line
        lines.append(line[10:])
    script = textwrap.dedent("\n".join(lines))
    script = script.replace("${{ needs.build.outputs.wheel_name }}", "arras-0.5.0-py3-none-any.whl")
    script = script.replace("${{ needs.check.outputs.version }}", "0.5.0")
    script = script.replace("${{ needs.build.outputs.wheel_sha256 }}", "a" * 64)
    assert "${{" not in script
    return script


def run_workflow_block(
    tmp_path: Path, *, verifier_exit: int, helper_exit: int
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    artifacts = tmp_path / "artifacts"
    bin_dir.mkdir()
    artifacts.mkdir()
    stub = bin_dir / "python"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *tools/verify_native.py*)\n"
        '    printf "%s\\n" "verifier-stdout"\n'
        '    printf "%s\\n" "verifier-stderr" >&2\n'
        '    exit "$VERIFY_EXIT";;\n'
        "  *.github/scripts/ensure_native_receipt_failure.py*)\n"
        '    printf "%s\\n" "called" >> "$HELPER_CALLS"\n'
        '    exit "$FALLBACK_EXIT";;\n'
        '  *) printf "%s\\n" "unexpected python invocation" >&2; exit 98;;\n'
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    (artifacts / "native-verification.json").write_text(
        '{"schema_version":1,"status":"not_started"}\n', encoding="utf-8"
    )
    (artifacts / "native-verifier.stdout.log").write_text("", encoding="utf-8")
    (artifacts / "native-verifier.stderr.log").write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "VERIFY_EXIT": str(verifier_exit),
            "FALLBACK_EXIT": str(helper_exit),
            "HELPER_CALLS": str(tmp_path / "helper-calls.log"),
        }
    )
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", installed_native_run_block()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        result,
        tmp_path / "helper-calls.log",
        artifacts / "native-verifier.stdout.log",
        artifacts / "native-verifier.stderr.log",
    )


@pytest.mark.parametrize(("verifier_exit", "helper_exit"), [(23, 7), (23, 0)])
def test_actual_workflow_block_preserves_verifier_failure_status(
    tmp_path: Path, verifier_exit: int, helper_exit: int
) -> None:
    result, helper_calls, stdout_log, stderr_log = run_workflow_block(
        tmp_path, verifier_exit=verifier_exit, helper_exit=helper_exit
    )
    assert result.returncode == verifier_exit
    assert helper_calls.read_text(encoding="utf-8").splitlines() == ["called"]
    assert stdout_log.read_text(encoding="utf-8") == "verifier-stdout\n"
    assert stderr_log.read_text(encoding="utf-8") == "verifier-stderr\n"


def test_actual_workflow_block_skips_fallback_after_verifier_success(tmp_path: Path) -> None:
    result, helper_calls, stdout_log, stderr_log = run_workflow_block(
        tmp_path, verifier_exit=0, helper_exit=7
    )
    assert result.returncode == 0
    assert not helper_calls.exists()
    assert stdout_log.read_text(encoding="utf-8") == "verifier-stdout\n"
    assert stderr_log.read_text(encoding="utf-8") == "verifier-stderr\n"
