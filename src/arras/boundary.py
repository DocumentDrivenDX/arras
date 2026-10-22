# SPDX-License-Identifier: MIT OR Apache-2.0
"""The boundary check (US-033): Arras and its host depend on each other only through names.

Two directions fail the build. A host that uses anything of Arras's that is not public (a name
outside `arras.__all__`, a module other than the public ones, an attribute reached through an
imported module, a dynamic import), and an Arras module that imports the host.
`python -m arras.boundary --host DIR --host-package NAME` prints each violation and exits
non-zero when there is one, and when it was given nothing to check.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import arras

# What a host may use, by module (CONTRACT-005 and CONTRACT-006).
PUBLIC_MODULE_NAMES: dict[str, frozenset[str]] = {
    "arras": frozenset(arras.__all__),
    "arras.adapters": frozenset(),
    "arras.adapters.truss": frozenset(
        {
            "create_backend",
            "ModuleAccess",
            "TrussBackend",
            "InstallingSource",
            "ConnectionSource",
        }
    ),
    "arras.console": frozenset({"create_app", "Request"}),
    "arras.operate": frozenset({"create_app", "create_schema_app", "Request"}),
    "arras.testing": frozenset({"InMemory", "example_module"}),
}
_DYNAMIC = {"__import__", "import_module", "importlib.import_module", "importlib.__import__"}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _python_files(root: Path) -> list[Path]:
    skip = {".venv", "__pycache__", "node_modules", ".git"}
    return [p for p in sorted(root.rglob("*.py")) if not skip & set(p.relative_to(root).parts)]


def _dotted(node: ast.AST) -> str | None:
    """`a.b.c` for a chain of attributes on a name, else `None`."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *reversed(parts)])
    return None


def _public_use(chain: list[str], root_module: str) -> str | None:
    """A message if `chain` (attributes after a module bound to `root_module`) leaves the public
    surface; `None` while it stays inside."""
    module = root_module
    for attr in chain:
        if f"{module}.{attr}" in PUBLIC_MODULE_NAMES:
            module = f"{module}.{attr}"
            continue
        names = PUBLIC_MODULE_NAMES.get(module, frozenset())
        if attr not in names:
            return f"{module}.{attr} is not public"
        return None  # a public name: what is done with it is the host's own
    return None


def check_host(host: Path) -> list[Violation]:
    """Violations in `host`: any use of Arras beyond its public names."""
    out: list[Violation] = []
    for path in _python_files(host):
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as e:
            out.append(Violation(str(path), e.lineno or 0, f"cannot be parsed: {e.msg}"))
            continue
        out += _check_tree(tree, str(path))
    return out


def _check_tree(tree: ast.AST, path: str) -> list[Violation]:
    out: list[Violation] = []
    bound: dict[str, str] = {}  # local name -> the arras module it stands for

    def bad(line: int, message: str) -> None:
        out.append(Violation(path, line, message))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _check_import(node, bound, bad)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            _check_import_from(node, node.module, bound, bad)
        elif isinstance(node, ast.Call):
            _check_dynamic_import(node, bad)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            _check_attribute_use(node, tree, bound, bad)
    return _unique(out)


def _check_import(node: ast.Import, bound: dict[str, str], bad: Callable[[int, str], None]) -> None:
    for a in node.names:
        if a.name != "arras" and not a.name.startswith("arras."):
            continue
        parts = a.name.split(".")
        for i in range(1, len(parts) + 1):
            if ".".join(parts[:i]) not in PUBLIC_MODULE_NAMES:
                bad(node.lineno, f"{'.'.join(parts[:i])} is not a public module of arras")
                break
        else:
            bound[a.asname or parts[0]] = a.name if a.asname else parts[0]


def _check_import_from(
    node: ast.ImportFrom, module: str, bound: dict[str, str], bad: Callable[[int, str], None]
) -> None:
    if module != "arras" and not module.startswith("arras."):
        return
    if module not in PUBLIC_MODULE_NAMES:
        bad(node.lineno, f"{module} is not a public module of arras")
        return
    for a in node.names:
        full = f"{module}.{a.name}"
        if a.name == "*":
            bad(node.lineno, f"import * from {module} hides what is used")
        elif full in PUBLIC_MODULE_NAMES:
            bound[a.asname or a.name] = full  # a public submodule bound as a name
        elif a.name not in PUBLIC_MODULE_NAMES[module]:
            bad(node.lineno, f"{a.name} is not in {module}'s public names")


def _check_dynamic_import(node: ast.Call, bad: Callable[[int, str], None]) -> None:
    fn = _dotted(node.func)
    arg = node.args[0] if node.args else None
    if fn in _DYNAMIC and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        target = arg.value
        if (target == "arras" or target.startswith("arras.")) and target not in PUBLIC_MODULE_NAMES:
            bad(node.lineno, f"{target} is not a public module of arras")


def _check_attribute_use(
    node: ast.Attribute, tree: ast.AST, bound: dict[str, str], bad: Callable[[int, str], None]
) -> None:
    chain = _dotted(node)
    if chain is None:
        return
    head, *rest = chain.split(".")
    if head in bound and rest:
        msg = _public_use(rest, bound[head])
        if msg and not _inside_longer_chain(node, tree):
            bad(node.lineno, msg)


def _inside_longer_chain(node: ast.Attribute, tree: ast.AST) -> bool:
    """Only the outermost attribute of a chain is judged, so one use is reported once."""
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Attribute) and parent.value is node:
            return True
    return False


def _unique(found: list[Violation]) -> list[Violation]:
    seen: set[tuple[str, int, str]] = set()
    out: list[Violation] = []
    for v in found:
        k = (v.path, v.line, v.message)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _imports(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def check_library(library: Path, host_packages: Iterable[str]) -> list[Violation]:
    """Violations in Arras's own source: any import of a host package."""
    forbidden = set(host_packages)
    out: list[Violation] = []
    for path in _python_files(library):
        tree = ast.parse(path.read_text(), filename=str(path))
        for line, module in _imports(tree):
            if module.split(".")[0] in forbidden:
                out.append(Violation(str(path), line, f"Arras imports the host package {module}"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", type=Path, help="the host's source directory")
    ap.add_argument("--library", type=Path, default=Path(arras.__file__).parent)
    ap.add_argument(
        "--host-package", action="append", default=[], help="a host package Arras must not import"
    )
    args = ap.parse_args(argv)
    if not args.host and not args.host_package:
        ap.error("give --host and/or --host-package: a check of nothing is not a pass")
    found: list[Violation] = []
    if args.host:
        if not args.host.is_dir() or not _python_files(args.host):
            ap.error(f"{args.host} has no Python files to check")
        found += check_host(args.host)
    if args.host_package:
        found += check_library(args.library, args.host_package)
    for v in found:
        print(v, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
