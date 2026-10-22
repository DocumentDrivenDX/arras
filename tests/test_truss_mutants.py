# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""Hand-written mutants of the Truss adapter's pure mapping tables (TR-12): each one a single textual
change to the plan to operation rules, the result to receipt and failure maps, the value domains, the
bounds and the token and query refusals, run against the suite that needs no Truss. Every mutant must
be killed (a test fails); a survivor names a rule no test pins. No mutation tool is added: the table
below is the whole mechanism.

A mutant runs in a temporary copy of `arras` that comes first on `PYTHONPATH`, in a subprocess, so
the working tree is never touched. The suite is the Truss adapter's always-on tests and the conformance
runner's (not this file, not the property machine, nothing marked `truss`). The copy of the suite is
confirmed green before any mutant is judged, and a mutant whose text is not found exactly once, or
that does not import, is a failure of this file, never a kill.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "arras"
ADAPTER = "adapters/truss/"
SUITE = [
    *(
        f"tests/test_truss_{name}.py"
        for name in (
            "plan", "batch", "connection", "reached", "query", "registry",
            "import", "audit", "apply", "toolkit", "harness",
        )
    ),
    "tests/test_conformance.py",
]  # fmt: skip

# (name, file under src/arras/adapters/truss, text that occurs exactly once, its mutation)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "outcome busy->resource dependencies delete",
        "outcome.py",
        'backend, "busy", "the object gained',
        'backend, "resource", "the object gained',
    ),
    (
        "outcome delete_object -> create_object",
        "outcome.py",
        'op.kind == "delete_object":',
        'op.kind == "create_object":',
    ),
    (
        "outcome multiplicity->invalid",
        "outcome.py",
        '"multiplicity", "the relationship',
        '"invalid", "the relationship',
    ),
    (
        "outcome exists/deleted swap",
        "outcome.py",
        '"exists" if exists_now(ref) else "deleted"',
        '"deleted" if exists_now(ref) else "exists"',
    ),
    (
        "outcome duplicate_relationship",
        "outcome.py",
        'Conflict("duplicate_relationship"',
        'Conflict("exists"',
    ),
    ("outcome not_found unlink cascade", "outcome.py", "if not op.cascade:", "if op.cascade:"),
    (
        "outcome profile unsupported->unavailable",
        "outcome.py",
        'if reason == "profile":',
        'if reason == "profilex":',
    ),
    (
        "outcome observation busy->unreachable",
        "outcome.py",
        '"busy", "another write holds',
        '"unreachable", "another write holds',
    ),
    (
        "outcome group_of event",
        "outcome.py",
        'return f"{event.source_epoch}:{event.xid}"',
        'return f"{event.xid}:{event.source_epoch}"',
    ),
    ("outcome receipt update unchanged", "outcome.py", '!= "Unchanged":', '== "Unchanged":'),
    ("outcome receipt deleted count", "outcome.py", "deleted += 1", "deleted += 0"),
    (
        "outcome receipt linked",
        "outcome.py",
        'elif kind == "Link":\n            linked += 1',
        'elif kind == "Link":\n            unlinked += 1',
    ),
    ("outcome version deletion", "outcome.py", "value = result.deletion_version", "value = 0"),
    (
        "outcome invalid_input busy",
        "outcome.py",
        'if code in ("original_documents", "catalog"):',
        'if code in ("original_documents",):',
    ),
    ("outcome expected_version", "outcome.py", 'Conflict("version"', 'Conflict("exists"'),
    ("outcome merge sort", "outcome.py", "rows.sort(key=lambda row: row[0])", "pass"),
    ("outcome merge first item", "outcome.py", "owner[rows[0][0]]", "owner[rows[-1][0]]"),
    ("conn 42501", "connection.py", '== "42501"', '== "42502"'),
    (
        "conn catalog unauthorized",
        "connection.py",
        '"unauthorized"\n    ):',
        '"unauthorizedx"\n    ):',
    ),
    ("conn cancelled", "connection.py", 'if code == "cancelled":', 'if code == "cancelledx":'),
    (
        "conn quarantine",
        "connection.py",
        '("transaction_unusable", "commit_unknown")',
        '("transaction_unusable",)',
    ),
    (
        "reach invalid_token",
        "reach.py",
        'if reason == "invalid_token":',
        'if reason == "invalid_tokenx":',
    ),
    (
        "reach authorization refused",
        "reach.py",
        'raise Refused(self.name, "reached", "no_access")',
        'raise Unavailable(self.name, "unreachable", "x")',
    ),
    ("reach bound", "reach.py", "len(token) > TOKEN_BOUND", "len(token) >= TOKEN_BOUND"),
    (
        "reach resource",
        "reach.py",
        'raise Unavailable(self.name, "resource", "truss resource")',
        'raise Unavailable(self.name, "unreachable", "truss resource")',
    ),
    ("plan range >", "plan.py", "return n + 1, None", "return n, None"),
    ("plan range <", "plan.py", "return 0, n - 1", "return 0, n"),
    ("plan range <=", "plan.py", "return 0, n\n", "return 0, n - 1\n"),
    ("plan MAX_OPERATIONS", "plan.py", "MAX_OPERATIONS = 1024", "MAX_OPERATIONS = 1025"),
    (
        "plan MAX_PRECONDITIONS",
        "plan.py",
        "MAX_PRECONDITIONS = 3072",
        "MAX_PRECONDITIONS = 3071",
    ),
    (
        "plan merge unset",
        "plan.py",
        "if name in op.unset:\n            op.unset.remove(name)",
        "if name in op.unset:\n            pass",
    ),
    ("query unauthorized", "query.py", 'if code == "unauthorized":', 'if code == "unauthorizedx":'),
    ("query stale", "query.py", 'if code == "stale_context":', 'if code == "stale_contextx":'),
    (
        "query limits",
        "query.py",
        'if code in ("unsupported_query", "limits"):',
        'if code in ("unsupported_query",):',
    ),
    ("values scale places", "values.py", "places > d.scale", "places >= d.scale"),
    (
        "values whole digits",
        "values.py",
        "whole > d.precision - d.scale",
        "whole >= d.precision - d.scale",
    ),
    ("values signed hi", "values.py", "2 ** (d.bits - 1) - 1)", "2 ** (d.bits - 1))"),
    ("values unsigned", "values.py", "0, 2**d.bits - 1", "0, 2**d.bits"),
    ("values timestamp Z", "values.py", '.replace("+00:00", "Z")', '.replace("+00:00", "")'),
    ("values micro", "values.py", 'timespec="microseconds"', 'timespec="milliseconds"'),
    (
        "values bool first",
        "values.py",
        "if isinstance(value, bool):\n        return wire.boolean(value)",
        "if False:\n        return wire.boolean(value)",
    ),
    (
        "load rejection relationship",
        "load.py",
        'Rejection("relationship", ident',
        'Rejection("record", ident',
    ),
    (
        "registry conflict revision",
        "registry.py",
        'if race and kind_of(out) == "CatalogUnchanged":\n                raise Conflict("revision", "another registration landed first")',
        'if race and kind_of(out) == "CatalogUnchanged":\n                raise Invalid([])',
    ),
    (
        "registry busy",
        "registry.py",
        'return Unavailable(backend, "busy", "the catalog is being changed")',
        'return Unavailable(backend, "unreachable", "x")',
    ),
    (
        "registry resource",
        "registry.py",
        'return Unavailable(backend, "resource", "a Truss resource limit")',
        'return Unavailable(backend, "busy", "x")',
    ),
    (
        "registry idempotency",
        "registry.py",
        'return Conflict("idempotency_key_reused", "Truss holds that request key for other input")',
        "return Invalid([])",
    ),
    (
        "registry observation busy",
        "registry.py",
        '"busy" if code == "observation" else "unreachable"',
        '"unreachable" if code == "observation" else "busy"',
    ),
    ("plan chunk", "load.py", "CHUNK = 128", "CHUNK = 129"),
    ("load batch", "load.py", "BATCH = 128", "BATCH = 129"),
    ("plan MAX_BATCH", "plan.py", "MAX_BATCH = 100", "MAX_BATCH = 101"),
    ("plan REQUEST_BYTES", "plan.py", "REQUEST_BYTES = 1024", "REQUEST_BYTES = 1025"),
    ("query unsupported_query", "query.py", '("unsupported_query", "limits")', '("limits",)'),
    (
        "query native_domain",
        "query.py",
        'if code == "native_domain":',
        'if code == "native_domainx":',
    ),
    (
        "plan derive_keys one key for all",
        "plan.py",
        'str(uuid.uuid5(_NAMESPACE, f"{request}#{i}"))',
        'str(uuid.uuid5(_NAMESPACE, f"{request}"))',
    ),
    ("plan GHOST_ID", "plan.py", 'GHOST_ID = "9223372036854775807"', 'GHOST_ID = "1"'),
    ("query WFT-PROFILE unsupported", "query.py", '"WFT-PROFILE", ', ""),
    ("query FACTS _load_id", "query.py", '    "_load_id": "string",\n', ""),
    ("reach TOKEN_BOUND", "reach.py", "TOKEN_BOUND = 16_384", "TOKEN_BOUND = 16_385"),
    ("values unsigned top", "values.py", "(0, 2**d.bits - 1)", "(0, 2**d.bits - 2)"),
]


def _run(root: Path, package: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(package.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *SUITE],
        cwd=root, capture_output=True, text=True, env=env, timeout=600,
    )  # fmt: skip


def _copy(into: Path) -> Path:
    package = into / "arras"
    shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns("__pycache__"))
    return package


def _judge(name: str, file: str, old: str, new: str) -> tuple[str, str]:
    """`killed`, `survived`, or `error: ...` for one mutant."""
    with tempfile.TemporaryDirectory(prefix="arras-mutant-") as tmp:
        package = _copy(Path(tmp))
        target = package / ADAPTER / file
        text = target.read_text()
        if text.count(old) != 1:
            return f"error: {old!r} occurs {text.count(old)} times in {file}", ""
        target.write_text(text.replace(old, new))
        done = _run(ROOT, package)
        tail = (done.stdout + done.stderr)[-400:]
        if done.returncode == 0:
            return "survived", tail
        if done.returncode == 1:  # tests ran and failed
            return "killed", tail
        return f"error: pytest exited {done.returncode}", tail  # no collection, usage or import


@pytest.fixture(scope="module")
def verdicts() -> Iterator[dict[str, tuple[str, str]]]:
    with tempfile.TemporaryDirectory(prefix="arras-control-") as tmp:
        control = _run(ROOT, _copy(Path(tmp)))
    assert control.returncode == 0, control.stdout[-1500:] + control.stderr[-500:]
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        futures = {name: pool.submit(_judge, name, *rest) for name, *rest in MUTANTS}
        yield {name: f.result() for name, f in futures.items()}


def test_every_mutant_is_named_once() -> None:
    names = [m[0] for m in MUTANTS]
    assert len(names) == len(set(names))
    assert all(m[2] != m[3] for m in MUTANTS)


@pytest.mark.parametrize("name", [m[0] for m in MUTANTS])
def test_the_mutant_is_killed(name: str, verdicts: dict[str, tuple[str, str]]) -> None:
    verdict, tail = verdicts[name]
    assert verdict == "killed", f"{name}: {verdict}\n{tail}"
