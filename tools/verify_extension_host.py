#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build and run the installed neutral extension-host example against an exact Arras wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, cast


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        output = "\n".join(
            part
            for part in (
                f"stdout:\n{result.stdout[-4000:]}" if result.stdout else "",
                f"stderr:\n{result.stderr[-4000:]}" if result.stderr else "",
            )
            if part
        )
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{output}")
    return result


def _json_output(result: subprocess.CompletedProcess[str], what: str) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{what} did not emit JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{what} did not emit a JSON object")
    return cast(dict[str, Any], value)


def _package_paths(python: Path, cwd: Path, env: dict[str, str]) -> dict[str, str]:
    result = _run(
        [
            str(python),
            "-I",
            "-c",
            "import arras, extension_host, json; print(json.dumps({'arras': arras.__file__, 'extension_host': extension_host.__file__}))",
        ],
        cwd=cwd,
        env=env,
    )
    return _json_output(result, "installed import probe")


def _require_installed_paths(paths: dict[str, str], site_packages: Path, checkout: Path) -> None:
    for package in ("arras", "extension_host"):
        path = Path(paths[package]).resolve()
        if not path.is_relative_to(site_packages.resolve()):
            raise RuntimeError(f"{package} imported outside the isolated environment: {path}")
        if path.is_relative_to(checkout.resolve()):
            raise RuntimeError(f"{package} imported from the checkout: {path}")


def _verify_seed_or_graph(result: dict[str, Any], resource: str, count: int) -> None:
    if (
        result.get("module") != "notes"
        or result.get("selected_resource") != resource
        or result.get("imported") != count
        or result.get("created_by_action") != 1
    ):
        raise RuntimeError(f"installed consumer result did not match {resource}: {result!r}")


def _verify_conformance(result: dict[str, Any]) -> None:
    counts = result.get("counts")
    if not isinstance(counts, dict):
        raise RuntimeError(f"installed conformance report has no counts: {result!r}")
    counts = cast(dict[str, Any], counts)
    if (
        result.get("backend") != "memory-store"
        or result.get("roles") != ["reader", "provider"]
        or result.get("newer_corpus") is not False
        or counts.get("passed", 0) <= 0
        or counts.get("failed", 0) != 0
        or counts.get("harness_error", 0) != 0
        or not result.get("results")
    ):
        raise RuntimeError(f"installed conformance report was not a complete pass: {result!r}")


def _build_consumer(example: Path, temp: Path, env: dict[str, str]) -> Path:
    project = temp / "extension_host_project"
    shutil.copytree(
        example,
        project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "dist", ".venv"),
    )
    built = temp / "built"
    built.mkdir()
    _run(_consumer_build_command(project, built), cwd=temp, env=env)
    wheels = list(built.glob("example_extension_host-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("declared backend did not produce exactly one extension-host wheel")
    return wheels[0]


def _consumer_build_command(project: Path, output: Path) -> list[str]:
    return [
        "uv",
        "build",
        "--no-config",
        "--default-index",
        "https://pypi.org/simple",
        "--wheel",
        "--out-dir",
        str(output),
        str(project),
    ]


def _environment(base: dict[str, str], cache: Path, *, fresh_dependencies: bool) -> dict[str, str]:
    if fresh_dependencies:
        env = {key: value for key, value in base.items() if not key.startswith(("PIP_", "UV_"))}
        env.update(
            {
                "PIP_CONFIG_FILE": os.devnull,
                "PIP_INDEX_URL": "https://pypi.org/simple",
                "UV_NO_CONFIG": "1",
                "UV_DEFAULT_INDEX": "https://pypi.org/simple",
            }
        )
    else:
        env = dict(base)
    env.update(PYTHONPATH="", UV_CACHE_DIR=str(cache))
    return env


def _install_command(python: Path, arras_wheel: Path, consumer_wheel: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--isolated",
        "--disable-pip-version-check",
        "--index-url",
        "https://pypi.org/simple",
        "pytest",
        str(arras_wheel),
        str(consumer_wheel),
    ]


def _configure_dependency_path(
    purelib: Path, shared_purelib: Path, *, fresh_dependencies: bool
) -> Path | None:
    if fresh_dependencies:
        return None
    # Explicit shared-dependency mode is an offline development convenience, not clean install
    # evidence. Its receipt names the reused location.
    pth = purelib / "arras-verifier-dependencies.pth"
    pth.write_text(str(shared_purelib.resolve()) + "\n")
    return shared_purelib.resolve()


def _installed_distributions(python: Path, cwd: Path, env: dict[str, str]) -> dict[str, str]:
    script = (
        "import importlib.metadata as m,json; "
        "print(json.dumps({d.metadata['Name']:d.version for d in m.distributions() "
        "if d.metadata.get('Name')}))"
    )
    return _json_output(
        _run([str(python), "-I", "-c", script], cwd=cwd, env=env), "package inventory"
    )


def _verify_installed_pytest_report(report: Path) -> dict[str, int]:
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as exc:
        raise RuntimeError(
            "installed consumer pytest did not produce a readable JUnit report"
        ) from exc
    if root.tag != "testsuites":
        raise RuntimeError("installed consumer pytest report has an unexpected root")
    names = ("tests", "failures", "errors", "skipped")
    if all(name in root.attrib for name in names):
        counts = {name: int(root.attrib[name]) for name in names}
    else:
        suites = root.findall("testsuite")
        counts = {name: sum(int(suite.attrib.get(name, "0")) for suite in suites) for name in names}
    if counts["tests"] <= 0 or any(counts[name] for name in ("failures", "errors", "skipped")):
        raise RuntimeError(f"installed consumer pytest did not pass completely: {counts!r}")
    return counts


def _run_installed_consumer_test(
    python: Path, target: Path, report: Path, *, cwd: Path, env: dict[str, str]
) -> dict[str, int]:
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pytest",
            "--import-mode=importlib",
            f"--junitxml={report}",
            str(target),
        ],
        cwd=cwd,
        env=env,
    )
    return _verify_installed_pytest_report(report)


def verify(arras_wheel: Path, output: Path, *, fresh_dependencies: bool = False) -> dict[str, Any]:
    arras_wheel = arras_wheel.resolve(strict=True)
    if arras_wheel.suffix != ".whl" or not arras_wheel.name.startswith("arras-"):
        raise ValueError("--wheel must name a built Arras wheel")
    with zipfile.ZipFile(arras_wheel) as wheel:
        if not any(name.endswith(".dist-info/METADATA") for name in wheel.namelist()):
            raise ValueError("--wheel is not a readable Python wheel")

    repository = Path(__file__).resolve().parents[1]
    example = repository / "examples/extension_host"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arras-extension-host-") as temp_name:
        temp = Path(temp_name)
        uv_cache = temp / "uv-cache"
        uv_cache.mkdir()
        env = _environment(dict(os.environ), uv_cache, fresh_dependencies=fresh_dependencies)
        consumer_wheel = _build_consumer(example, temp, env)

        venv = temp / "venv"
        _run([sys.executable, "-m", "venv", str(venv)], cwd=temp, env=env)
        python = venv / "bin/python"
        scripts = venv / "bin"
        purelib = Path(
            _run(
                [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                cwd=temp,
                env=env,
            ).stdout.strip()
        )
        dependency_purelib = _configure_dependency_path(
            purelib,
            Path(sysconfig.get_paths()["purelib"]),
            fresh_dependencies=fresh_dependencies,
        )
        if not fresh_dependencies:
            install = [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "pytest",
                str(arras_wheel),
                str(consumer_wheel),
            ]
        else:
            install = _install_command(python, arras_wheel, consumer_wheel)
        _run(install, cwd=temp, env=env)
        paths = _package_paths(python, temp, env)
        _require_installed_paths(paths, purelib, repository)

        graph = _json_output(
            _run(
                [str(python), "-I", "-m", "extension_host", "--resource", "graph.json"],
                cwd=temp,
                env=env,
            ),
            "installed graph example",
        )
        _verify_seed_or_graph(graph, "graph.json", 2)
        seed = _json_output(
            _run(
                [str(scripts / "extension-host-example"), "--resource", "seed.json"],
                cwd=temp,
                env=env,
            ),
            "installed console entry point",
        )
        _verify_seed_or_graph(seed, "seed.json", 1)
        if seed.get("imported_by") != "admin":
            raise RuntimeError("import attribution did not identify the host administrator")
        installed_test = repository / "examples/extension_host/tests/test_installed.py"
        junit_report = temp / "installed-consumer-junit.xml"
        installed_test_counts = _run_installed_consumer_test(
            python, installed_test, junit_report, cwd=temp, env=env
        )
        corpus = _json_output(
            _run(
                [str(python), "-I", "-m", "arras.conformance", "--backend", "memory-store"],
                cwd=temp,
                env=env,
            ),
            "installed memory corpus CLI",
        )
        _verify_conformance(corpus)
        installed = _installed_distributions(python, temp, env)
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "qualification": "installed-artifact consumer and fixed memory corpus",
            "arras_wheel": {"path": str(arras_wheel), "sha256": _sha256(arras_wheel)},
            "extension_host_wheel": {
                "filename": consumer_wheel.name,
                "sha256": _sha256(consumer_wheel),
                "build_backend": "hatchling via declared pyproject.toml and uv build",
            },
            "environment": {
                "python": sys.version.split()[0],
                "isolated_imports": True,
                "dependency_mode": (
                    "fresh-public-index-resolution"
                    if fresh_dependencies
                    else "shared-current-site-directory"
                ),
                "dependency_site_directory_reused": (
                    None if dependency_purelib is None else str(dependency_purelib)
                ),
                "installed_distributions": dict(
                    sorted(installed.items(), key=lambda pair: pair[0].lower())
                ),
                "arras_import": paths["arras"],
                "extension_host_import": paths["extension_host"],
            },
            "consumer_runs": {"graph": graph, "seed": seed},
            "installed_consumer_test": {
                "path": "examples/extension_host/tests/test_installed.py",
                "mode": "isolated pytest against installed distributions",
                "counts": installed_test_counts,
            },
            "memory_corpus": corpus,
            "commands": [
                "python -I -m extension_host --resource graph.json",
                "extension-host-example --resource seed.json",
                "python -I -m pytest --import-mode=importlib examples/extension_host/tests/test_installed.py",
                "python -I -m arras.conformance --backend memory-store",
            ],
        }
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", required=True, type=Path, help="exact built Arras wheel to install"
    )
    parser.add_argument(
        "--output-json", required=True, type=Path, help="qualification receipt path"
    )
    parser.add_argument(
        "--fresh-dependencies",
        action="store_true",
        help="resolve and install all declared dependencies from public PyPI in a clean venv",
    )
    args = parser.parse_args(argv)
    receipt = verify(args.wheel, args.output_json, fresh_dependencies=args.fresh_dependencies)
    print(
        json.dumps(
            {
                "arras_wheel_sha256": receipt["arras_wheel"]["sha256"],
                "extension_host_wheel_sha256": receipt["extension_host_wheel"]["sha256"],
                "receipt": str(args.output_json),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
