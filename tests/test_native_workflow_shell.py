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


APT_MAIN_QUERY_COMMAND = "apt-config shell ARRAS_MAIN Dir::Etc::main/f"
APT_MAIN_QUERY = "ARRAS_MAIN='/etc/apt/apt.conf'"
APT_CONFIG_COMMAND = (
    "apt-config shell ARRAS_RETRIES Acquire::Retries ARRAS_HTTP_TIMEOUT "
    "Acquire::http::Timeout ARRAS_HTTPS_TIMEOUT Acquire::https::Timeout "
    "ARRAS_APTGET_RETRIES Binary::apt-get::Acquire::Retries "
    "ARRAS_APTGET_HTTP_TIMEOUT Binary::apt-get::Acquire::http::Timeout "
    "ARRAS_APTGET_HTTPS_TIMEOUT Binary::apt-get::Acquire::https::Timeout"
)
EXPECTED_APT_CONFIG = (
    "ARRAS_RETRIES='2'\n"
    "ARRAS_HTTP_TIMEOUT='20'\n"
    "ARRAS_HTTPS_TIMEOUT='20'\n"
    "ARRAS_APTGET_RETRIES='2'\n"
    "ARRAS_APTGET_HTTP_TIMEOUT='20'\n"
    "ARRAS_APTGET_HTTPS_TIMEOUT='20'"
)
APT_POLICY = (
    "\nAcquire {\n"
    '  Retries "2";\n'
    '  http::Timeout "20";\n'
    '  https::Timeout "20";\n'
    "};\n"
    "Binary::apt-get::Acquire {\n"
    '  Retries "2";\n'
    '  http::Timeout "20";\n'
    '  https::Timeout "20";\n'
    "};\n"
)


def ci_apt_run_block() -> str:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    marker = (
        "      - name: Configure official Ubuntu HTTPS sources and bounded APT\n"
        "        working-directory: .\n"
        "        run: |\n"
    )
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
    assert "${{" not in script
    return script


def run_ci_apt_block(
    tmp_path: Path,
    *,
    apt_config: str = EXPECTED_APT_CONFIG,
    apt_config_exit: int = 0,
    apt_main_query: str = APT_MAIN_QUERY,
    apt_main_exit: int = 0,
    existing_main: str | None = "// runner configuration\n",
    main_is_regular: bool = True,
    main_is_symlink: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    config = tmp_path / "apt.conf"
    if existing_main is not None:
        config.write_text(existing_main, encoding="utf-8")
    (bin_dir / "python3").write_text(
        '#!/bin/sh\nprintf "python3 %s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
        encoding="utf-8",
    )
    (bin_dir / "sudo").write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  tee) shift; [ "$1" = "-a" ] && shift; target="$1"; printf \'sudo tee -a %s\\n\' "$target" >> "$CALL_LOG"; cat >> "$APT_CONFIG_FILE";;\n'
        '  python3) printf \'sudo python3 %s\\n\' "$*" >> "$CALL_LOG";;\n'
        '  apt-config) shift; printf \'sudo apt-config %s\\n\' "$*" >> "$CALL_LOG"; case "$*" in *Dir::Etc::main/f*) printf \'%s\' "$APT_MAIN_QUERY"; exit "$APT_MAIN_EXIT";; *) printf \'%s\' "$APT_CONFIG"; exit "$APT_CONFIG_EXIT";; esac;;\n'
        '  test) shift; printf \'sudo test %s\\n\' "$*" >> "$CALL_LOG"; case "$1" in -e) [ "$APT_MAIN_EXISTS" = "1" ];; -f) [ "$APT_MAIN_REGULAR" = "1" ];; -L) [ "$APT_MAIN_SYMLINK" = "1" ];; *) exit 98;; esac;;\n'
        "  *) printf '%s\\n' 'unexpected sudo invocation' >&2; exit 98;;\n"
        "esac\n",
        encoding="utf-8",
    )
    (bin_dir / "timeout").write_text(
        '#!/bin/sh\nprintf "timeout %s\\n" "$*" >> "$CALL_LOG"\nexit 0\n',
        encoding="utf-8",
    )
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALL_LOG": str(log),
            "APT_CONFIG_FILE": str(config),
            "APT_CONFIG": apt_config,
            "APT_CONFIG_EXIT": str(apt_config_exit),
            "APT_MAIN_QUERY": apt_main_query,
            "APT_MAIN_EXIT": str(apt_main_exit),
            "APT_MAIN_EXISTS": "1" if existing_main is not None else "0",
            "APT_MAIN_REGULAR": "1" if main_is_regular else "0",
            "APT_MAIN_SYMLINK": "1" if main_is_symlink else "0",
        }
    )
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", ci_apt_run_block()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text(encoding="utf-8"), config


def test_ci_apt_policy_appends_to_main_and_checks_global_and_apt_get_values(tmp_path: Path) -> None:
    previous = '// runner configuration\nAcquire::Retries "1";\n'
    result, calls, config = run_ci_apt_block(tmp_path, existing_main=previous)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert config.read_text(encoding="utf-8") == previous + APT_POLICY
    expected_calls = (
        "configure_ubuntu_apt_sources.py --self-test",
        "configure_ubuntu_apt_sources.py --apply",
        APT_MAIN_QUERY_COMMAND,
        "sudo test -e /etc/apt/apt.conf",
        "sudo test -f /etc/apt/apt.conf",
        "sudo test -L /etc/apt/apt.conf",
        "sudo tee -a /etc/apt/apt.conf",
        APT_CONFIG_COMMAND,
        "timeout --signal=TERM --kill-after=30s 180s sudo apt-get update",
    )
    assert all(call in calls for call in expected_calls)
    assert [calls.index(call) for call in expected_calls] == sorted(
        calls.index(call) for call in expected_calls
    )

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (
        "timeout --signal=TERM --kill-after=30s 240s npx --no-install playwright install-deps chromium"
        in workflow
    )
    assert (
        "timeout --signal=TERM --kill-after=30s 240s npx --no-install playwright install chromium"
        in workflow
    )


@pytest.mark.parametrize(
    "apt_config",
    [
        "ARRAS_RETRIES='1'\nARRAS_HTTP_TIMEOUT='20'\nARRAS_HTTPS_TIMEOUT='20'\nARRAS_APTGET_RETRIES='2'\nARRAS_APTGET_HTTP_TIMEOUT='20'\nARRAS_APTGET_HTTPS_TIMEOUT='20'",
        "ARRAS_RETRIES='2'\nARRAS_HTTPS_TIMEOUT='20'\nARRAS_APTGET_RETRIES='2'\nARRAS_APTGET_HTTP_TIMEOUT='20'\nARRAS_APTGET_HTTPS_TIMEOUT='20'",
        "ARRAS_RETRIES='2'\nARRAS_HTTP_TIMEOUT='20'\nARRAS_HTTPS_TIMEOUT='20'\nARRAS_APTGET_RETRIES='1'\nARRAS_APTGET_HTTP_TIMEOUT='15'\nARRAS_APTGET_HTTPS_TIMEOUT='15'",
    ],
    ids=("wrong-global-value", "missing-global-value", "binary-override"),
)
def test_ci_apt_policy_rejects_wrong_missing_or_binary_override(
    tmp_path: Path, apt_config: str
) -> None:
    result, calls, _ = run_ci_apt_block(tmp_path, apt_config=apt_config)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == apt_config + "\n"
    assert APT_CONFIG_COMMAND in calls
    assert "timeout --signal=TERM --kill-after=30s 180s sudo apt-get update" not in calls


def test_ci_apt_policy_fails_when_effective_query_fails(tmp_path: Path) -> None:
    result, calls, _ = run_ci_apt_block(tmp_path, apt_config_exit=17)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == EXPECTED_APT_CONFIG + "\n"
    assert APT_CONFIG_COMMAND in calls
    assert "timeout --signal=TERM --kill-after=30s 180s sudo apt-get update" not in calls


def test_ci_apt_policy_refuses_nonstandard_main_path(tmp_path: Path) -> None:
    main_query = "ARRAS_MAIN='/tmp/apt.conf'"
    result, calls, _ = run_ci_apt_block(tmp_path, apt_main_query=main_query)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == main_query + "\n"
    assert "sudo tee -a /etc/apt/apt.conf" not in calls
    assert APT_CONFIG_COMMAND not in calls


def test_ci_apt_policy_fails_when_main_file_is_not_regular(tmp_path: Path) -> None:
    result, calls, _ = run_ci_apt_block(tmp_path, main_is_regular=False)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == APT_MAIN_QUERY + "\n"
    assert "sudo tee -a /etc/apt/apt.conf" not in calls


def test_ci_apt_policy_creates_missing_standard_main_file(tmp_path: Path) -> None:
    result, calls, config = run_ci_apt_block(tmp_path, existing_main=None)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert config.read_text(encoding="utf-8") == APT_POLICY
    assert "sudo test -e /etc/apt/apt.conf" in calls
    assert "sudo test -f /etc/apt/apt.conf" not in calls
    assert APT_CONFIG_COMMAND in calls


def test_ci_apt_policy_refuses_broken_main_symlink(tmp_path: Path) -> None:
    result, calls, _ = run_ci_apt_block(tmp_path, existing_main=None, main_is_symlink=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == APT_MAIN_QUERY + "\n"
    assert "sudo test -L /etc/apt/apt.conf" in calls
    assert "sudo tee -a /etc/apt/apt.conf" not in calls
