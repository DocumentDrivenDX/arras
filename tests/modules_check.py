# SPDX-License-Identifier: MIT OR Apache-2.0
"""The internal dependency rules of the library (architecture.md, Module Boundaries).

Each module belongs to one group, and a group may import only the groups it lists. Imports under
`if TYPE_CHECKING:` are not dependencies at run time and are not edges. The checker takes module
sources by name so a test can feed it a forbidden edge and see it fail.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

# A module's group is the longest prefix below that names one.
GROUPS: dict[str, str] = {
    "arras.errors": "foundation",
    "arras.types": "foundation",
    "arras.names": "foundation",
    "arras.serialize": "foundation",
    "arras.telemetry": "foundation",
    "arras.callscope": "foundation",
    "arras.versions": "foundation",
    "arras.http": "foundation",
    "arras.model": "domain",
    "arras.actions": "domain",
    "arras.actioncheck": "domain",
    "arras.results": "domain",
    "arras.compat": "domain",
    "arras.umf": "domain",
    "arras.inputs": "domain",
    "arras.view": "domain",
    "arras.viewcache": "domain",
    "arras.backend": "contract",
    "arras.adapters": "adapters",
    "arras.entityread": "schema",
    "arras.gqlschema": "schema",
    "arras.core": "core",
    "arras.routing": "core",
    "arras.registration": "core",
    "arras.schema_admin": "core",
    "arras.search": "core",
    "arras.graphfile": "core",
    "arras.exportcursor": "domain",
    "arras.searchplan": "domain",
    "arras.fakes": "doubles",
    "arras.fakes_journal": "doubles",
    "arras.fakes_state": "doubles",
    "arras.fakes_registry": "doubles",
    "arras.fakes_import": "doubles",
    "arras.fakes_export": "doubles",
    "arras.fakes_weft": "doubles",
    "arras.fakes_sql": "doubles",
    "arras.fakes_plan": "doubles",
    "arras.fakes_eval": "doubles",
    "arras.fakes_domain": "doubles",
    "arras.fakes_search": "doubles",
    "arras.testing": "doubles",
    "arras.conformance": "doubles",
    "arras.sandbox": "doubles",
    "arras.console": "console",
    "arras.operate": "operate",
    "arras.ui": "ui",
    "arras.devhost": "devhost",
    "arras.devtruss": "devhost",
    "arras.mcp": "mcp",
    "arras.boundary": "tooling",
    "arras": "root",
}

ALLOWED: dict[str, frozenset[str]] = {
    "foundation": frozenset({"foundation"}),
    "domain": frozenset({"foundation", "domain"}),
    "contract": frozenset({"foundation", "domain", "contract"}),
    "adapters": frozenset({"foundation", "domain", "contract", "adapters"}),
    "schema": frozenset({"foundation", "domain", "schema"}),
    "core": frozenset({"foundation", "domain", "contract", "schema", "core"}),
    "doubles": frozenset({"foundation", "domain", "contract", "core", "doubles"}),
    "console": frozenset({"foundation", "domain", "schema", "core", "console"}),
    "mcp": frozenset({"foundation", "domain", "contract", "core", "doubles", "adapters", "mcp"}),
    "operate": frozenset({"foundation", "domain", "core", "operate"}),
    "ui": frozenset({"foundation", "domain", "core", "console", "operate", "ui"}),
    "devhost": frozenset(
        {
            "foundation",
            "domain",
            "core",
            "doubles",
            "adapters",
            "console",
            "operate",
            "ui",
            "devhost",
        }
    ),
    "tooling": frozenset({"root", "tooling"}),
    "root": frozenset({"foundation", "domain", "core"}),
}


def group_of(module: str) -> str | None:
    parts = module.split(".")
    while parts:
        if (g := GROUPS.get(".".join(parts))) is not None:
            return g
        parts.pop()
    return None


def module_name(path: Path, src: Path) -> str:
    parts = list(path.relative_to(src).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def sources(src: Path) -> dict[str, str]:
    return {module_name(p, src): p.read_text() for p in (src / "arras").rglob("*.py")}


def _type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_imports(tree: ast.AST, package: str) -> list[tuple[str, int, list[str]]]:
    """`(module, line, imported names)` for every import that runs: lazy ones count, those under
    `if TYPE_CHECKING:` do not, and a relative import is resolved against `package`."""
    out: list[tuple[str, int, list[str]]] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and _type_checking(child.test):
                for other in child.orelse:  # the `else:` branch runs
                    walk_one(other)
                continue
            walk_one(child)

    def walk_one(child: ast.AST) -> None:
        if isinstance(child, ast.ImportFrom):
            base = child.module or ""
            if child.level:
                parts = package.split(".")
                parts = parts[: len(parts) - (child.level - 1)]
                base = ".".join([*parts, *([child.module] if child.module else [])])
            out.append((base, child.lineno, [a.name for a in child.names]))
        elif isinstance(child, ast.Import):
            out.extend((a.name, child.lineno, []) for a in child.names)
        walk(child)

    walk(tree)
    return out


def _package_of(name: str, mods: Mapping[str, str], is_package: set[str]) -> str:
    return name if name in is_package else name.rpartition(".")[0]


def edges(mods: Mapping[str, str]) -> dict[str, set[tuple[str, int]]]:
    """`importer -> {(imported module, line)}`, a submodule named by `from pkg import name` resolved."""
    packages = {n for n in mods if any(o.startswith(n + ".") for o in mods)}
    result: dict[str, set[tuple[str, int]]] = {}
    for name, text in mods.items():
        found: set[tuple[str, int]] = set()
        package = _package_of(name, mods, packages)
        for module, line, names in _runtime_imports(ast.parse(text), package):
            if not module.startswith("arras"):
                continue
            targets = [f"{module}.{n}" for n in names if f"{module}.{n}" in mods] or [module]
            found.update((t, line) for t in targets)
        result[name] = found
    return result


def violations(mods: Mapping[str, str]) -> list[str]:
    """Every edge a group does not allow, every module in no group, and every import cycle."""
    out: list[str] = []
    graph = edges(mods)
    for name in sorted(graph):
        mine = group_of(name)
        if mine is None:
            out.append(f"{name}: belongs to no group")
            continue
        for target, line in sorted(graph[name]):
            theirs = group_of(target)
            if theirs is None:
                out.append(f"{name}:{line}: imports {target}, which belongs to no group")
            elif theirs not in ALLOWED[mine]:
                out.append(f"{name}:{line}: {mine} must not import {target} ({theirs})")
    out += [
        f"cycle: {' -> '.join(c)}" for c in cycles({n: {t for t, _ in e} for n, e in graph.items()})
    ]
    return out


def cycles(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """One representative cycle per strongly connected component of more than one module."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    found: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in graph:
                continue
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                found.append(sorted(comp) + [sorted(comp)[0]])

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return found


def too_long(mods: Mapping[str, str], ceiling: int) -> dict[str, int]:
    """The modules with more lines than `ceiling`."""
    lengths = {name: len(text.splitlines()) for name, text in mods.items()}
    return {name: n for name, n in lengths.items() if n > ceiling}
