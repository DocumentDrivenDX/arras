# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Verify declared public origins, consumer imports, sensitive-source patterns and fixture provenance.

This is an offline declaration/integrity check. It does not test remote availability, infer identity,
or decide redistribution rights. Production imports are a static AST inventory, including literal
dynamic targets; arbitrary runtime-computed import names are outside this check's claim.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href" and v is not None)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_https(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def _requirements_names(values: Iterable[str]) -> set[str]:
    return {
        re.split(r"[<>=!~;\[]", req, maxsplit=1)[0].strip().lower().replace("_", "-")
        for req in values
    }


def _dependency_errors(root: Path, policy: Mapping[str, Any]) -> list[str]:
    return (
        _python_dependency_errors(root, policy["dependencies"]["python"])
        + _release_page_errors(root, policy["dependencies"]["python"])
        + _npm_dependency_errors(root, policy["dependencies"]["npm"])
    )


def _python_dependency_errors(root: Path, expected: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject.get("project", {})
    deps = project.get("dependencies", [])
    required = _requirements_names(deps)
    declared_required = set(expected["required"])
    if required != declared_required:
        errors.append(
            f"pyproject.toml: required Python dependencies differ from policy (actual={sorted(required)})"
        )
    optional = project.get("optional-dependencies", {})
    declared_extras = expected["optional_extras"]
    if set(optional) != set(declared_extras):
        errors.append("pyproject.toml: optional Python extras differ from policy")
    for extra, expected_names in declared_extras.items():
        if _requirements_names(optional.get(extra, [])) != set(expected_names):
            errors.append(f"pyproject.toml: optional extra {extra!r} differs from policy")

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    lock_packages = {package["name"]: package for package in lock.get("package", [])}
    errors.extend(_import_dependency_errors(expected, required, declared_extras, lock_packages))

    py_origin = expected["registry"]
    allowed_registry_sources = {py_origin, expected["release_page"]}
    artifact_hosts = set(expected["artifact_hosts"])
    for package in lock.get("package", []):
        source = package.get("source", {})
        if source.get("registry") and source["registry"] not in allowed_registry_sources:
            errors.append(f"uv.lock: {package.get('name')} uses undeclared registry origin")
        for artifact in [package.get("sdist", {}), *package.get("wheels", [])]:
            url = artifact.get("url")
            if url:
                parsed = urlsplit(url)
                if not _safe_https(url) or parsed.hostname not in artifact_hosts:
                    errors.append(
                        f"uv.lock: {package.get('name')} has an undeclared artifact origin"
                    )
                if not re.search(r"sha256:[0-9a-f]{64}\b", artifact.get("hash", "")):
                    errors.append(f"uv.lock: {package.get('name')} has an artifact without SHA-256")

    return errors


def _import_dependency_errors(
    expected: Mapping[str, Any],
    required: set[str],
    extras: Mapping[str, Any],
    lock_packages: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for import_root, record in expected.get("imports", {}).items():
        distribution = record["distribution"].lower().replace("_", "-")
        source = record["source"]
        if source == "required":
            valid = distribution in required
        elif source.startswith("optional:"):
            extra = source.partition(":")[2]
            valid = distribution in set(extras.get(extra, []))
        elif source.startswith("transitive:"):
            extra = source.partition(":")[2]
            parent = record["parent"].lower().replace("_", "-")
            parent_lock = lock_packages.get(parent, {})
            valid = (
                parent in set(extras.get(extra, []))
                and distribution in lock_packages
                and distribution
                in {
                    item["name"]
                    for item in parent_lock.get("optional-dependencies", {}).get(
                        record["parent_extra"], []
                    )
                }
            )
        else:
            valid = False
        if not valid or distribution not in lock_packages:
            errors.append(
                f"public-content-policy: import root {import_root!r} does not map to a declared dependency source"
            )
    return errors


def _release_page_errors(root: Path, expected: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    page = expected["release_page"]
    links = _Links()
    links.feed((root / page).read_text(encoding="utf-8"))
    release_hosts = set(expected["release_hosts"])
    for url in links.hrefs:
        parsed = urlsplit(url)
        digest = parsed.fragment.removeprefix("sha256=")
        if (
            not _safe_https(url)
            or parsed.hostname not in release_hosts
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            errors.append(f"{page}: release link lacks a declared HTTPS origin or SHA-256")

    return errors


def _npm_dependency_errors(root: Path, npm: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    package = _load(root / "ui/package.json")
    package_lock = _load(root / "ui/package-lock.json")
    if package.get("dependencies", {}) != npm["required_runtime"]:
        errors.append("ui/package.json: runtime dependencies differ from policy")
    peers = package.get("peerDependencies", {})
    peer_meta = package.get("peerDependenciesMeta", {})
    declared_optional_peers = set(npm["optional_peers"])
    if not set(peers) <= declared_optional_peers:
        errors.append("ui/package.json: peer dependency is missing from policy")
    for name, optional_peer in npm["optional_peers"].items():
        # Optional integrations may be absent entirely. If one is declared,
        # keep its version/category exact and never promote it to runtime.
        if name in peers and (
            peers[name] != optional_peer["version"]
            or peer_meta.get(name, {}).get("optional") is not True
        ):
            errors.append(f"ui/package.json: optional peer {name!r} changed category or version")
        if name in package.get("dependencies", {}):
            errors.append(f"ui/package.json: optional peer {name!r} became required")
        dev_version = optional_peer.get("dev_dependency_version")
        if dev_version is not None and package.get("devDependencies", {}).get(name) != dev_version:
            errors.append(
                f"ui/package.json: optional peer {name!r} dev test pin differs from policy"
            )
    lock_root = package_lock.get("packages", {}).get("", {})
    if lock_root.get("peerDependencies", {}) != peers:
        errors.append("ui/package-lock.json: peer dependency declarations differ from package.json")
    if lock_root.get("peerDependenciesMeta", {}) != peer_meta:
        errors.append("ui/package-lock.json: optional-peer markers differ from package.json")
    for item in package_lock.get("packages", {}).values():
        resolved = item.get("resolved") if isinstance(item, dict) else None
        if resolved:
            parsed = urlsplit(resolved)
            if not _safe_https(resolved) or parsed.hostname != npm["registry_host"]:
                errors.append("ui/package-lock.json: package resolution uses undeclared origin")
                break
    return errors


def _public_names(manifest: Mapping[str, Any]) -> dict[str, set[str]]:
    python = manifest["python"]
    names = set(python["root_all"])
    return {
        module: names if record.get("names") == "root_all" else set(record.get("names", []))
        for module, record in python["modules"].items()
    }


def consumer_import_errors(
    consumer_root: Path, public_modules: Mapping[str, set[str]]
) -> list[str]:
    """Check `arras` imports in explicitly designated consumer Python sources only."""
    errors: list[str] = []
    for path in sorted(consumer_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"{path}: cannot inspect consumer source ({type(exc).__name__})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [(alias.name, None) for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [(node.module, alias.name) for alias in node.names]
            else:
                continue
            for module, name in imports:
                if module != "arras" and not module.startswith("arras."):
                    continue
                allowed = public_modules.get(module)
                if allowed is None:
                    errors.append(f"{path}:{node.lineno}: undeclared Arras import {module}")
                elif name is not None and name not in allowed:
                    errors.append(f"{path}:{node.lineno}: undeclared Arras name {module}.{name}")
    return errors


def _literal_import_targets(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node.lineno
        elif isinstance(node, ast.Call):
            function = node.func
            is_dynamic_import = (
                isinstance(function, ast.Name) and function.id in {"__import__", "import_module"}
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr in {"import_module", "__import__"}
            )
            is_otel_helper = isinstance(function, ast.Name) and function.id == "_otel"
            if (is_dynamic_import or is_otel_helper) and node.args:
                target = node.args[0]
                if isinstance(target, ast.Constant) and isinstance(target.value, str):
                    yield target.value, node.lineno


def production_import_errors(source_root: Path, external_imports: Mapping[str, Any]) -> list[str]:
    """Check production source imports against stdlib, Arras, and declared distribution roots."""
    allowed = set(sys.stdlib_module_names) | {"arras"} | set(external_imports)
    errors: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"{path}: cannot inspect production source ({type(exc).__name__})")
            continue
        for target, line in _literal_import_targets(tree):
            module_root = target.split(".", maxsplit=1)[0]
            if module_root and module_root not in allowed:
                errors.append(
                    f"{path}:{line}: production import root {module_root!r} is undeclared"
                )
    return errors


_SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|https?)://[^\s/@:]+:[^\s/@]+@"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|private[_-]?token)\s*[:=]\s*['\"](?!<|your|example|placeholder|redacted)[A-Za-z0-9_./+=-]{20,}['\"]"
    ),
)


def _content_errors(root: Path, policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    fixture_policy = policy["fixtures"]
    known: set[str] = set()
    for entry in fixture_policy["entries"]:
        rel = entry["path"]
        known.add(rel)
        path = root / rel
        if not path.is_file():
            errors.append(f"{rel}: fixture declared in policy is missing")
            continue
        if not entry.get("provenance") or not entry.get("source"):
            errors.append(f"{rel}: fixture lacks provenance classification or source")
        source = entry.get("source", "")
        if source.startswith("https://"):
            if not _safe_https(source):
                errors.append(f"{rel}: provenance URL is not a credential-free HTTPS URL")
        elif not (root / source.split("#", 1)[0]).is_file():
            errors.append(f"{rel}: provenance source path is missing")
        if _digest(path) != entry.get("sha256"):
            errors.append(f"{rel}: fixture digest is stale")
    for directory in fixture_policy["roots"]:
        for path in (root / directory).rglob("*.json"):
            rel = path.relative_to(root).as_posix()
            if rel not in known:
                errors.append(f"{rel}: JSON fixture has no provenance declaration")

    for rel in policy["sensitive_scan_files"]:
        target = root / rel
        paths = (
            [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
        )
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {
                ".py",
                ".md",
                ".json",
                ".toml",
                ".yml",
                ".yaml",
                ".ts",
                ".tsx",
                ".html",
            }:
                continue
            source_name = path.relative_to(root).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            errors.extend(sensitive_content_errors(source_name, content))

    imports = _public_names(_load(root / policy["public_api_manifest"]))
    for rel in policy["consumer_roots"]:
        errors.extend(consumer_import_errors(root / rel, imports))
    return errors


def sensitive_content_errors(path: str, content: str) -> list[str]:
    """Return high-confidence credential pattern findings for unit controls."""
    if any(pattern.search(content) for pattern in _SENSITIVE_PATTERNS):
        return [f"{path}: credential-shaped content matched a high-confidence pattern"]
    return []


def validate_workspace_path(workspace: Path, value: str, *, directory: bool) -> Path:
    """Resolve an explicit POSIX path and reject controls, traversal, symlinks, or wrong kind."""
    relative = PurePosixPath(value)
    if (
        not value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in value
    ):
        raise ValueError("path must be a safe relative workspace path")
    root = workspace.resolve()
    target = (root / Path(*relative.parts)).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path resolves outside the workspace")
    if not (target.is_dir() if directory else target.is_file()):
        raise ValueError("path does not exist with the required kind")
    return target


def check(root: Path, policy_path: Path | None = None) -> list[str]:
    root = root.resolve()
    policy_path = policy_path or root / "tools/public-content-policy.json"
    policy = _load(policy_path)
    return (
        _dependency_errors(root, policy)
        + _content_errors(root, policy)
        + production_import_errors(root / "src/arras", policy["dependencies"]["python"]["imports"])
    )


def _pytest_junit_counts(path: Path) -> dict[str, int] | None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    return {
        name: sum(int(suite.get(name, "0")) for suite in suites)
        for name in ("tests", "errors", "failures", "skipped")
    }


def pytest_junit_errors(path: Path, stage: str) -> list[str]:
    """Reject empty, failed, errored, or skipped pytest reports for a selected cohort."""
    totals = _pytest_junit_counts(path)
    if totals is None:
        return [f"{stage} test report is unreadable or contains no test suites"]
    if totals["tests"] < 1:
        return [f"{stage} test target collected no tests"]
    findings = [name for name in ("errors", "failures", "skipped") if totals[name]]
    if findings:
        return [f"{stage} test target has {', '.join(findings)} in its report"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--verify-pytest-junit", type=Path)
    parser.add_argument("--stage", default="selected")
    args = parser.parse_args()
    if args.verify_pytest_junit:
        errors = pytest_junit_errors(args.verify_pytest_junit, args.stage)
        if errors:
            for error in errors:
                print(error)
            return 1
        counts = _pytest_junit_counts(args.verify_pytest_junit)
        assert counts is not None
        print(
            f"{args.stage} tests passed: tests={counts['tests']} errors={counts['errors']} "
            f"failures={counts['failures']} skipped={counts['skipped']}"
        )
        return 0
    errors = check(args.root)
    if errors:
        print("Public content check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Public content declarations and fixture integrity are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
