# SPDX-License-Identifier: MIT OR Apache-2.0
# pyright: basic
"""The latency benchmark harness of US-044: the four targets of the PRD's success metrics, measured
at the host (the Arras interface praxis embeds) against a real Truss on PostgreSQL.

    uv run --extra truss python tests/bench_latency.py                # the dev host's database
    uv run --extra truss python tests/bench_latency.py --throwaway    # a local PostgreSQL of its own
    uv run --extra truss python tests/bench_latency.py --enforce      # exit 1 if a target is missed

It is a script, not a test, so the default `pytest` never collects it; `tests/test_truss_bench.py`
(Truss-marked) runs it small. ARRAS_REQUIRE_TRUSS=1 is that test's switch for failing instead of
skipping; the script itself exits 2 with the reason when Truss or PostgreSQL is missing.

Series, each a person who can read and write (a role of its own, `arrasdev_bench`, holding the reader
and writer role of every registered module; it never touches the dev host's people):

    in-process, warm    Ontology calls over one kept connection per person, as a pooling host
                        supplies them. These four are the acceptance criteria and what `--enforce`
                        judges: AC1 a singleton read by key, AC2 a three-effect action
                        (`catalog.AssertCoverage`: a create and two links) including its change
                        record, AC3 a type enumeration (`describe`), AC4 the 51-record use case list.
    in-process, cold    The same operations with a new connection for every call, which is what the
                        dev host's own sources do.
    http                The same operations over the dev host's HTTP API (the console's GraphQL and
                        the operator surface) when one answers; the host opens a connection per
                        call. Informational: it adds the HTTP server and JSON, and is never enforced.

The percentile is the nearest rank (p95 of 100 runs is the 95th smallest). Every action is a distinct
write (a key of this run's own), so none is a replay; the coverage assertions and solutions it makes
are retired afterwards, the use case it renames is renamed back, and the countries of the
single-effect create stay, since no declared action deletes one. The machine's load is sampled around
each series and a series run above `QUIET_LOAD` is labelled not quiet.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import http.client
import importlib.util
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from arras.errors import Unavailable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

QUIET_LOAD = 4.0  # a one-minute load average above this is not a quiet machine
TARGETS = {"AC1": 20.0, "AC2": 100.0, "AC3": 20.0, "AC4": 1000.0}  # p95, in milliseconds
EXAMPLES = ROOT / "examples"
MODULES = ("catalog", "northwind", "pizza")
PERSON = "bench"
LEFT = re.compile(r" ~bench\d+$")  # what a renamed use case carries until the run ends
PERF = time.perf_counter_ns


# -- what each call costs the database: round trips and the time spent waiting on it
@dataclass
class Meter:
    round_trips: int = 0
    connects: int = 0
    transactions: int = 0  # settled by a rollback or a commit
    db_ns: int = 0

    def reset(self) -> None:
        self.round_trips = self.connects = self.transactions = self.db_ns = 0


METER = Meter()


def _waiting(wait: Callable[..., Any]) -> Callable[..., Any]:
    """`Connection.wait`, which every round trip of psycopg passes through, counted and timed."""

    def call(*args: Any, **kw: Any) -> Any:
        t = PERF()
        try:
            return wait(*args, **kw)
        finally:
            METER.db_ns += PERF() - t
            METER.round_trips += 1

    return call


def _settling(settle: Callable[..., Any]) -> Callable[..., Any]:
    """`Connection.rollback` and `commit`, each of which ends one transaction, counted."""

    def call(*args: Any, **kw: Any) -> Any:
        METER.transactions += 1
        return settle(*args, **kw)

    return call


@contextlib.contextmanager
def _open(endpoint: Any, user: str, password: str) -> Iterator[Any]:
    """One new connection, as `arras.adapters.truss.endpoint.connect` makes it, and counted."""
    import psycopg

    t = PERF()
    # a plain Connection (Truss refuses a subclass); the counting wraps its `wait`
    conn = psycopg.Connection.connect(**endpoint.parameters(), user=user, password=password)
    METER.db_ns += PERF() - t
    METER.connects += 1
    conn.wait = _waiting(conn.wait)  # pyright: ignore[reportAttributeAccessIssue]
    conn.rollback = _settling(conn.rollback)  # pyright: ignore[reportAttributeAccessIssue]
    conn.commit = _settling(conn.commit)  # pyright: ignore[reportAttributeAccessIssue]
    try:
        yield conn
    finally:
        conn.close()


class Sources:
    """The connection sources of one Arras: warm (one connection kept per person, as a pool gives
    them back) or cold (a new connection for every call)."""

    def __init__(self, endpoint: Any, installer: str, password: str, *, warm: bool) -> None:
        self.endpoint, self.installer, self.password, self.warm = (
            endpoint,
            installer,
            password,
            warm,
        )
        self.kept: dict[str, Any] = {}
        self.stack = contextlib.ExitStack()

    def person(self, principal: Any) -> contextlib.AbstractContextManager[Any]:
        if not self.warm:
            return _open(self.endpoint, principal.user, principal.token)
        return self._kept(principal)

    @contextlib.contextmanager
    def _kept(self, principal: Any) -> Iterator[Any]:
        conn = self.kept.get(principal.user)
        if conn is None or conn.closed or getattr(conn, "broken", False):
            conn = self.stack.enter_context(_open(self.endpoint, principal.user, principal.token))
            self.kept[principal.user] = conn
        yield conn

    def installing(self) -> contextlib.AbstractContextManager[Any]:
        return _open(self.endpoint, self.installer, self.password)

    def close(self) -> None:
        self.stack.close()


# -- the world: a Truss, the person, the modules
@dataclass
class World:
    truss: Any
    principal: Any
    box: Any = None  # a throwaway's TrussBox, which closes it
    seeding: dict[str, float] = field(default_factory=dict[str, float])  # cold seed, in seconds

    def arras(self, *, warm: bool) -> tuple[Any, Sources]:
        from arras import Arras
        from arras.adapters.truss import create_backend
        from arras.model import Placement

        t = self.truss
        sources = Sources(t.endpoint, t.installer, t._installer_password, warm=warm)
        backend = create_backend(t.name, sources.person, sources.installing)
        h = Arras.start({t.name: backend}, default_placement=Placement(t.name))
        return h, sources

    def close(self) -> None:
        if self.box is not None:
            self.box.close()
        else:
            self.truss.close()


def load_world(url: str | None, throwaway: bool) -> World:
    from arras import graphfile
    from arras.adapters.truss.local import LocalTruss
    from arras.devtruss import TrussBox
    from arras.sandbox import read_steps

    seeding: dict[str, float] = {}
    if throwaway:
        began = time.perf_counter()
        box = TrussBox()
        seeding["cluster start and install"] = time.perf_counter() - began
        for name in MODULES:
            began = time.perf_counter()
            here = EXAMPLES / name
            graph = None
            if name == "catalog":
                graph = graphfile.loads((here / "catalog.graph.json").read_text(encoding="utf-8"))
            doc = (here / f"{name}.umf.json").read_text(encoding="utf-8")
            box.load(doc, read_steps(here / "seed.json"), graph)
            seeding[f"register, grant and seed {name}"] = time.perf_counter() - began
        truss, box_ = box.truss, box
    else:
        truss, box_ = LocalTruss("primary", url=url).open(), None
    who = truss.person(PERSON)
    for module in box_.modules if box_ is not None else truss.known_modules():
        for role in (truss.reader_role(module), truss.writer_role(module)):
            truss.membership(PERSON, role, grant=True)
    return World(truss, who, box_, seeding)


# -- the operations, each one call of the host interface
@dataclass
class Op:
    ac: str  # the acceptance criterion it measures, or "" for an extra
    name: str
    run: Callable[[int], Any]
    cleanup: Callable[[], None] = lambda: None
    target: float | None = None

    @property
    def label(self) -> str:
        return f"{self.ac or 'extra'} {self.name}"


class Ops:
    """The operations over one session, with the keys they need and what they leave behind."""

    def __init__(self, session: Any, run_id: str) -> None:
        from arras.entityread import entity_rows, entity_sql, relationships_of
        from arras.names import quoted

        self.o, self.run_id = session, run_id
        self._entity_rows, self._entity_sql = entity_rows, entity_sql
        mod = session.describe("catalog")[0]
        self.mod, self.t = mod, mod.entity_type("UseCase")
        self.rels = relationships_of(mod, self.t)
        self.shape = frozenset(p.name for p in self.t.properties) | {n for n, _ in self.rels}
        self.made: dict[str, list[str]] = {"coverage": [], "solution": []}
        self.where = f" WHERE x.{quoted(self.t.key)} = :key"
        self.use_cases = self.keys("catalog.UseCase", "UseCase")
        self.product = self.keys("catalog.Product", "Product")[0]
        base = LEFT.sub("", self.name_of(self.use_cases[0]))
        self.renamed = (self.use_cases[0], base)
        self.sweep()

    def keys(self, qualified: str, local: str) -> list[str]:
        """Every key of a type, in key order, a page of 100 at a time."""
        from arras.names import quoted, quoted_type

        module = qualified.split(".")[0]
        key = self.o.describe(module)[0].entity_type(local).key
        found: list[str] = []
        while True:
            after = f" WHERE x.{quoted(key)} > :after" if found else ""
            sql = f"SELECT x.{quoted(key)} FROM {quoted_type(qualified)} x{after} "
            sql += f"ORDER BY x.{quoted(key)} LIMIT 101"
            params = {"after": found[-1]} if found else None
            rows = self.o.query(module, sql, params, limit=100)
            found += [next(iter(r.values())) for r in rows.rows]
            if not rows.truncated:
                return found

    def name_of(self, key: str) -> str:
        rows = self.o.query("catalog", self.sql(1, None), {"key": key}, limit=1)
        return str(self.row(rows)["name"])

    def sql(self, count: int, wanted: frozenset[str] | None, where: str | None = None) -> str:
        return self._entity_sql(
            self.mod, self.t, self.where if where is None else where, count, wanted
        )

    def row(self, rows: Any) -> dict[str, Any]:
        out = self._entity_rows(self.mod, self.t, rows)
        return dict(out.rows[0])

    # AC1 and its variants: a record by its key
    def read_key(self, i: int, wanted: frozenset[str] | None = None) -> Any:
        key = self.use_cases[i % len(self.use_cases)]
        rows = self.o.query("catalog", self.sql(1, wanted), {"key": key}, limit=1)
        return self.row(rows)

    # AC3
    def describe(self, _: int) -> Any:
        return self.o.describe()

    # AC4: the console's list: one row more than the limit, the limit as the statement's cap
    def list_use_cases(self, count: int, wanted: frozenset[str] | None) -> Any:
        rows = self.o.query("catalog", self.sql(count + 1, wanted, ""), limit=count)
        return self._entity_rows(self.mod, self.t, rows)

    # AC2 and its variants
    def assert_coverage(self, i: int) -> Any:
        code = f"bench-{self.run_id}-{i}"
        inputs = {"code": code, "level": "partial", "product": self.product}
        r = self.o.invoke("catalog.AssertCoverage", {**inputs, "useCase": self.use_cases[0]})
        self.made["coverage"].append(code)
        return r

    def add_solution(self, i: int) -> Any:
        code = f"bench-{self.run_id}-s{i}"
        inputs = {"code": code, "name": "Bench", "deliveryMode": "chat"}
        r = self.o.invoke("catalog.AddSolution", {**inputs, "useCase": self.use_cases[0]})
        self.made["solution"].append(code)
        return r

    def rename(self, i: int) -> Any:
        key, _ = self.renamed
        return self.o.invoke(
            "catalog.RenameUseCase", {"useCase": key, "name": f"{self.renamed[1]} ~bench{i}"}
        )

    def add_country(self, i: int) -> Any:
        return self.o.invoke(
            "pizza.AddCountry", {"code": f"bench-{self.run_id}-c{i}", "name": "Bench"}
        )

    RETIRE = {
        "coverage": ("catalog.RetireCoverage", "coverageAssertion", "catalog.CoverageAssertion"),
        "solution": ("catalog.RetireSolution", "solution", "catalog.Solution"),
    }

    def sweep(self) -> None:
        """What an aborted run left: this harness's coverage assertions and solutions (their keys
        begin `bench-`) retired, and the renamed use case given its own name back."""
        left = False
        for kind, (_, _, qualified) in self.RETIRE.items():
            found = [
                k for k in self.keys(qualified, qualified.split(".")[1]) if k.startswith("bench-")
            ]
            self.made[kind] += found
            left |= bool(found)
        if left or LEFT.search(self.name_of(self.use_cases[0])):
            self.clean()

    def clean(self) -> None:
        for kind, (action, field_, _) in self.RETIRE.items():
            for code in self.made[kind]:
                self.o.invoke(action, {field_: code})
            self.made[kind].clear()
        key, name = self.renamed
        self.o.invoke("catalog.RenameUseCase", {"useCase": key, "name": name})

    def ops(self) -> list[Op]:
        full = None  # `x.*`: the declared fields, the facts and every relationship's keys
        n = 51
        return [
            Op(
                "AC1",
                "singleton read by key (record, with facts)",
                lambda i: self.read_key(i, full),
            ),
            Op("AC2", "three-effect action (AssertCoverage)", self.assert_coverage),
            Op("AC3", "type enumeration (describe)", self.describe),
            Op("AC4", f"{n}-record use case list", lambda _: self.list_use_cases(n, self.shape)),
            Op(
                "",
                "read by key (properties and relationships only)",
                lambda i: self.read_key(i, self.shape),
            ),
            Op("", "two-effect action (AddSolution)", self.add_solution),
            Op("", "one-effect update (RenameUseCase)", self.rename),
            Op("", "one-effect create (pizza.AddCountry)", self.add_country),
            Op("", "enumeration of the readable modules (modules)", lambda _: self.o.modules()),
            Op("", f"{n}-record use case list with facts", lambda _: self.list_use_cases(n, None)),
            Op(
                "",
                "the whole use case list (limit 100)",
                lambda _: self.list_use_cases(100, self.shape),
            ),
        ]


# -- the dev host's HTTP API
class Http:
    def __init__(self, base: str, person: str, run_id: str) -> None:
        parts = urlsplit(base)
        self.base = base.rstrip("/")
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.conn = http.client.HTTPConnection(
            parts.hostname or "127.0.0.1", parts.port or 80, timeout=30
        )
        self.person, self.run_id = person, run_id
        self.coverage: list[str] = []
        self.solutions: list[str] = []

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "content-type": "application/json",
            "x-arras-user": self.person,
            "origin": self.origin,
        }
        try:
            res, data = self._send(path, body, headers)
        except (ConnectionError, http.client.RemoteDisconnected):  # the host closed an idle socket
            self.conn.close()
            res, data = self._send(path, body, headers)
        if res.status != 200:
            raise RuntimeError(f"{path}: HTTP {res.status}")
        out = json.loads(data)
        if out.get("errors"):
            raise RuntimeError(f"{path}: {out['errors'][0]['message']}")
        return out

    def _send(
        self, path: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[http.client.HTTPResponse, bytes]:
        self.conn.request("POST", path, json.dumps(body), headers)
        res = self.conn.getresponse()
        return res, res.read()

    def gql(self, query: str, module: str | None = "catalog") -> dict[str, Any]:
        path = "/api/console/graphql" + (f"/{module}" if module else "")
        return self.post(path, {"query": query})

    def invoke(self, action: str, inputs: dict[str, Any]) -> dict[str, Any]:
        module, short = action.split(".")
        return self.post(f"/api/operate/actions/{module}/{short}/invoke", {"inputs": inputs})

    def reachable(self) -> bool:
        try:
            self.gql("{ modules { name } }", None)
        except (OSError, RuntimeError, http.client.HTTPException):
            return False
        return True


def http_ops(h: Http, ops: Ops) -> list[Op]:
    fields = " ".join(
        ["key", *(p.name for p in ops.t.properties if p.name != ops.t.key)]
        + [f"{n} {{ key }}" for n, _ in ops.rels]
    )
    facts = "version createdBy createdAt updatedBy updatedAt"
    enumerate_ = (
        "{ modules { name revision entityTypes { name key properties { name type required "
        "cardinality } capabilities } relationships { name source target } "
        "actions { name inputs } } }"
    )

    def read(i: int) -> Any:
        key = ops.use_cases[i % len(ops.use_cases)]
        return h.gql(f'{{ useCase(key: "{key}") {{ {fields} {facts} }} }}')

    def coverage(i: int) -> Any:
        code = f"bench-{h.run_id}-h{i}"
        inputs = {
            "code": code,
            "level": "partial",
            "product": ops.product,
            "useCase": ops.use_cases[0],
        }
        r = h.invoke("catalog.AssertCoverage", inputs)
        h.coverage.append(code)
        return r

    def solution(i: int) -> Any:
        code = f"bench-{h.run_id}-hs{i}"
        inputs = {
            "code": code,
            "name": "Bench",
            "deliveryMode": "chat",
            "useCase": ops.use_cases[0],
        }
        r = h.invoke("catalog.AddSolution", inputs)
        h.solutions.append(code)
        return r

    return [
        Op("AC1", "singleton read by key (GraphQL record)", read),
        Op("AC2", "three-effect action (operate invoke AssertCoverage)", coverage),
        Op("AC3", "type enumeration (GraphQL modules)", lambda _: h.gql(enumerate_, None)),
        Op(
            "AC4",
            "51-record use case list (GraphQL)",
            lambda _: h.gql(f"{{ useCaseList(limit: 51) {{ items {{ {fields} }} truncated }} }}"),
        ),
        Op("", "two-effect action (operate invoke AddSolution)", solution),
        Op(
            "",
            "one-effect update (operate invoke RenameUseCase)",
            lambda i: h.invoke(
                "catalog.RenameUseCase",
                {"useCase": ops.renamed[0], "name": f"{ops.renamed[1]} ~bench{i}"},
            ),
        ),
    ]


def http_clean(h: Http, ops: Ops) -> None:
    for code in h.coverage:
        h.invoke("catalog.RetireCoverage", {"coverageAssertion": code})
    for code in h.solutions:
        h.invoke("catalog.RetireSolution", {"solution": code})
    h.coverage.clear()
    h.solutions.clear()
    h.invoke("catalog.RenameUseCase", {"useCase": ops.renamed[0], "name": ops.renamed[1]})


# -- measuring
@dataclass
class Series:
    group: str
    op: Op
    ms: list[float]
    round_trips: float  # per call, the mean
    connects: float
    transactions: float  # per call: transactions settled, the mean
    db_ms: float  # per call: the time spent waiting on the database, connecting included
    cpu_ms: float  # per call: this process's own CPU time (Python and the driver, not Postgres)
    load: tuple[float, float]
    retries: int = 0  # runs asked again after Truss answered `busy`

    def pct(self, p: float) -> float:
        ordered = sorted(self.ms)
        return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]

    def row(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "operation": self.op.label,
            "runs": len(self.ms),
            "p50_ms": self.pct(50),
            "p95_ms": self.pct(95),
            "p99_ms": self.pct(99),
            "max_ms": max(self.ms),
            "mean_ms": statistics.fmean(self.ms),
            "round_trips": self.round_trips,
            "connects": self.connects,
            "transactions": self.transactions,
            "db_wait_ms": self.db_ms,
            "process_cpu_ms": self.cpu_ms,
            "target_p95_ms": self.op.target,
            "load_before_after": self.load,
            "busy_retries": self.retries,
            "not_quiet": max(self.load) > QUIET_LOAD,
        }


def attempt(op: Op, i: int) -> int:
    """Run the operation; a write Truss answers `busy` (another writer holds a row it needs) is
    asked again, up to three times, and the retries are counted. Returns how many there were."""
    retries = 0
    while True:
        try:
            op.run(i)
            return retries
        except (Unavailable, RuntimeError) as e:
            busy = getattr(e, "reason", "") == "busy" or "HTTP 503" in str(e)
            if not busy or retries >= 3:
                raise
            retries += 1


def measure(group: str, op: Op, runs: int, warmup: int) -> Series:
    ms: list[float] = []
    trips = connects = db_ms = cpu_ms = txs = 0.0
    retries = 0
    try:
        for i in range(warmup):
            attempt(op, i)
        start_load = os.getloadavg()[0]
        for i in range(runs):
            METER.reset()
            c = time.process_time_ns()
            t = PERF()
            retries += attempt(op, warmup + i)
            ms.append((PERF() - t) / 1e6)
            cpu_ms += (time.process_time_ns() - c) / 1e6
            trips += METER.round_trips
            connects += METER.connects
            txs += METER.transactions
            db_ms += METER.db_ns / 1e6
    finally:
        op.cleanup()
    n = max(runs, 1)
    return Series(
        group,
        op,
        ms,
        trips / n,
        connects / n,
        txs / n,
        db_ms / n,
        cpu_ms / n,
        (start_load, os.getloadavg()[0]),
        retries,
    )


def first_calls(world: World, run_id: str, repeats: int) -> list[dict[str, Any]]:
    """The first call of each operation on a new Arras and a new connection (the registry's
    documents are read afresh too). The first repeat also pays the process's own first-use costs;
    the later ones only the connection and the registry reads."""
    h0, sources0 = world.arras(warm=True)
    template = Ops(h0.session(world.principal), f"{run_id}f")
    sources0.close()
    firsts: dict[str, list[float]] = {}
    for r in range(repeats):
        for index, op in enumerate(template.ops()):
            h, sources = world.arras(warm=True)
            try:
                fresh = copy.copy(template)
                fresh.o = h.session(world.principal)
                fresh.run_id = f"{run_id}f{r}"
                fresh.made = {"coverage": [], "solution": []}
                target = fresh.ops()[index]
                METER.reset()
                t = PERF()
                target.run(r)
                firsts.setdefault(op.label, []).append((PERF() - t) / 1e6)
                fresh.clean()
            finally:
                sources.close()
                h.close()
    out: list[dict[str, Any]] = []
    for label, values in firsts.items():
        rest = values[1:]
        out.append(
            {
                "operation": label,
                "first_ever_ms": values[0],
                "later_median_ms": statistics.median(rest) if rest else None,
            }
        )
    return out


def _kilobytes(cursor: Any) -> float:
    """What the statement's answer weighs on the wire: the bytes of every value it returned."""
    result = cursor.pgresult
    if result is None or not result.ntuples:
        return 0.0
    total = sum(
        len(result.get_value(r, c) or b"")
        for r in range(result.ntuples)
        for c in range(result.nfields)
    )
    return total / 1024


@contextlib.contextmanager
def _logging_statements(log: list[tuple[float, float, str]]) -> Iterator[None]:
    """Every `Cursor.execute` of psycopg (the adapter's and Truss's own) logged with its time and
    the kilobytes it returned, for `--statements` only; libpq's protocol trace is not available on
    macOS."""
    import psycopg

    original = psycopg.Cursor.execute

    def execute(self: Any, query: Any, *args: Any, **kw: Any) -> Any:
        t = PERF()
        try:
            return original(self, query, *args, **kw)
        finally:
            took = (PERF() - t) / 1e6
            text = query.decode() if isinstance(query, bytes) else str(query)
            log.append((took, _kilobytes(self), " ".join(text.split())))

    rolled, committed = psycopg.Connection.rollback, psycopg.Connection.commit

    def settle(name: str, real: Callable[..., Any]) -> Callable[..., Any]:
        def call(self: Any, *args: Any, **kw: Any) -> Any:
            log.append((0.0, 0.0, name))
            return real(self, *args, **kw)

        return call

    psycopg.Cursor.execute = execute  # type: ignore[method-assign]
    psycopg.Connection.rollback = settle("ROLLBACK", rolled)  # type: ignore[method-assign]
    psycopg.Connection.commit = settle("COMMIT", committed)  # type: ignore[method-assign]
    try:
        yield
    finally:
        psycopg.Cursor.execute = original  # type: ignore[method-assign]
        psycopg.Connection.rollback = rolled  # type: ignore[method-assign]
        psycopg.Connection.commit = committed  # type: ignore[method-assign]


def statements_of(world: World, run_id: str) -> dict[str, list[tuple[float, float, str]]]:
    """The statements one warm call of each operation executes through psycopg, in order, with the
    milliseconds each took (text only: no parameter values, no credentials)."""
    h, sources = world.arras(warm=True)
    out: dict[str, list[tuple[float, float, str]]] = {}
    try:
        ops = Ops(h.session(world.principal), f"{run_id}s")
        for op in ops.ops():
            op.run(0)
            log: list[tuple[float, float, str]] = []
            with _logging_statements(log):
                op.run(1)
            out[op.label] = log
        ops.clean()
    finally:
        sources.close()
        h.close()
    return out


def phase(text: str, first_payload: int, index: int) -> str:
    """Which part of an import a statement belongs to: the setup before the first record is built
    (adoption of the transaction, the registrar gate, the catalog and document reads), the payload (the
    records built and imported), or the settlement (the deferred checks, then commit or rollback)."""
    if text in ("COMMIT", "ROLLBACK") or text.startswith("SET CONSTRAINTS"):
        return "settlement"
    return "setup" if index < first_payload else "payload"


def import_series(world: World, runs: int, run_id: str) -> list[dict[str, Any]]:
    """Imports of 128 and 1,024 records through the host interface (a registrar's `import_records`):
    the time, the round trips and the statements of each, the statements split by phase. The rows stay
    (an import is not undone), so this is for a throwaway only."""
    from dataclasses import replace

    truss = world.truss
    truss.membership(PERSON, truss.registrar_role, grant=True)
    who = replace(world.principal, admin=True, groups=("builders",))
    h, sources = world.arras(warm=True)
    out: list[dict[str, Any]] = []
    try:
        session = h.session(who)

        def load(size: int, tag: str) -> Any:
            records = [
                {"type": "Product", "key": f"imp-{run_id}-{tag}-{i}", "properties": {"name": "Imp"}}
                for i in range(size)
            ]
            return session.import_records("catalog", records, load_id=f"imp-{run_id}-{tag}")

        load(8, "warm")
        for size in (128, 1024):
            ms: list[float] = []
            trips: list[int] = []
            for r in range(runs):
                METER.reset()
                t = PERF()
                done = load(size, f"{size}-{r}")
                ms.append((PERF() - t) / 1e6)
                trips.append(METER.round_trips)
                assert done.created == size, done
            log: list[tuple[float, float, str]] = []
            with _logging_statements(log):
                load(size, f"{size}-log")
            texts = [text for _, _, text in log]
            first = next(
                (i for i, x in enumerate(texts) if "import" in x.lower() and "truss." in x), 0
            )
            phases: dict[str, int] = {}
            for i, x in enumerate(texts):
                name = phase(x, first, i)
                phases[name] = phases.get(name, 0) + 1
            settles = sum(1 for x in texts if x in ("COMMIT", "ROLLBACK"))
            out.append(
                {
                    "records": size,
                    "runs": runs,
                    "p50_ms": statistics.median(ms),
                    "max_ms": max(ms),
                    "round_trips": statistics.median(trips),
                    "statements_execute": len(texts) - settles,
                    "statements_settle": settles,
                    "by_phase": phases,
                    "load": os.getloadavg(),
                }
            )
    finally:
        sources.close()
        h.close()
    return out


def top_consumers() -> str:
    ps = subprocess.run(
        ["ps", "-Ao", "pcpu,comm", "-r"], capture_output=True, text=True, check=False
    )
    lines = [ln.split(None, 1) for ln in ps.stdout.splitlines()[1:4] if ln.strip()]
    return ", ".join(f"{os.path.basename(c)} {p}%" for p, c in lines)


def run_once(world: World, args: argparse.Namespace, run_id: str) -> list[Series]:
    results: list[Series] = []
    for warm, group in ((True, "in-process warm"), (False, "in-process cold")):
        if not warm and args.no_cold:
            continue
        h, sources = world.arras(warm=warm)
        try:
            ops = Ops(h.session(world.principal), run_id + ("w" if warm else "c"))
            for op in ops.ops():
                if (not warm and not op.ac) or (args.no_create and "create" in op.name):
                    continue
                op.target = TARGETS.get(op.ac) if warm else None
                op.cleanup = ops.clean
                results.append(measure(group, op, args.runs, args.warmup))
        finally:
            sources.close()
            h.close()
    if args.http:
        results += run_http(world, args, run_id)
    return results


def run_http(world: World, args: argparse.Namespace, run_id: str) -> list[Series]:
    http_client = Http(args.http, "alice", run_id)
    if not http_client.reachable():
        print(f"(no dev host answers at {args.http}: the HTTP series is skipped)")
        return []
    h, sources = world.arras(warm=True)
    out: list[Series] = []
    try:
        ops = Ops(h.session(world.principal), run_id + "h")
        for op in http_ops(http_client, ops):
            op.target = None
            op.cleanup = lambda: http_clean(http_client, ops)
            out.append(measure("http (dev host)", op, args.runs, args.warmup))
    finally:
        sources.close()
        h.close()
    return out


def table(results: list[Series]) -> str:
    head = f"{'operation':<58}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}{'mean':>8}  {'target':>7}  verdict  trips  txs  db ms  cpu ms"
    lines: list[str] = []
    group = ""
    for s in results:
        if s.group != group:
            group = s.group
            lines += ["", f"[{group}]  runs of {len(s.ms)} after warm-up", head]
        r = s.row()
        verdict = ""
        if s.op.target is not None:
            verdict = "met" if r["p95_ms"] <= s.op.target else "MISSED"
        target = f"{s.op.target:g}" if s.op.target is not None else "-"
        quiet = " (not quiet)" if r["not_quiet"] else ""
        quiet += f" ({s.retries} busy retries)" if s.retries else ""
        trips = (
            "     -     -      -       -"
            if s.group.startswith("http")
            else f"{s.round_trips:>6.1f}{s.transactions:>5.1f}{s.db_ms:>7.2f}{s.cpu_ms:>8.2f}"
        )
        lines.append(
            f"{s.op.label[:57]:<58}{r['p50_ms']:>8.2f}{r['p95_ms']:>8.2f}{r['p99_ms']:>8.2f}"
            f"{r['max_ms']:>8.2f}{r['mean_ms']:>8.2f}  {target:>7}  {verdict:<8}"
            f"{trips}{quiet}"
        )
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--runs", type=int, default=100, help="sequential runs per operation (100)")
    p.add_argument("--warmup", type=int, default=10, help="runs before the measured ones (10)")
    p.add_argument("--repeat", type=int, default=1, help="times to run the whole set (1)")
    p.add_argument(
        "--url", help="the persistent server (else ARRAS_TRUSS_DEV_URL as the dev host reads it)"
    )
    p.add_argument("--throwaway", action="store_true", help="a local PostgreSQL of its own, seeded")
    p.add_argument(
        "--http",
        nargs="?",
        const="http://127.0.0.1:8010",
        default=None,
        help="also measure the dev host's HTTP API (default http://127.0.0.1:8010)",
    )
    p.add_argument(
        "--no-create",
        action="store_true",
        help="skip the single-effect create, whose rows no declared action deletes",
    )
    p.add_argument("--no-cold", action="store_true", help="skip the connection-per-call series")
    p.add_argument(
        "--first-calls",
        type=int,
        default=0,
        metavar="N",
        help="measure the first call of each operation, N new Arras instances",
    )
    p.add_argument("--statements", action="store_true", help="print each operation's statements")
    p.add_argument(
        "--imports",
        type=int,
        default=0,
        metavar="N",
        help="N imports of 128 and of 1,024 records (a throwaway only: the rows stay)",
    )
    p.add_argument("--json", help="write the results to this file")
    p.add_argument(
        "--enforce", action="store_true", help="exit 1 when an AC's p95 misses its target"
    )
    return p


def missing(throwaway: bool) -> str | None:
    """Why this cannot run here: a throwaway needs the local PostgreSQL (`pgserver`) too."""
    from truss_harness import available

    if throwaway:
        return available()
    if importlib.util.find_spec("truss") is None or importlib.util.find_spec("psycopg") is None:
        return "the truss extra is not installed (uv run --extra truss ...)"
    return None


def seed_and_imports(
    world: World, args: argparse.Namespace, report: dict[str, Any], run_id: str
) -> int | None:
    """The cold seed's timing and the import series, printed and kept in the report; an exit
    code when the run cannot go on."""
    if world.seeding:
        report["cold_seed_s"] = world.seeding
        total = sum(world.seeding.values())
        print(f"cold seed (a new PostgreSQL, install, three ontologies): {total:.2f} s")
        for step, took in world.seeding.items():
            print(f"  {step:<42}{took:>8.2f} s")
    if args.imports:
        if not args.throwaway:
            print("--imports needs --throwaway", file=sys.stderr)
            return 2
        report["imports"] = import_series(world, args.imports, run_id)
        for row in report["imports"]:
            print(
                f"import of {row['records']:>5} records: p50 {row['p50_ms']:>9.1f} ms, "
                f"{row['round_trips']:.0f} round trips, {row['statements_execute']} execute + "
                f"{row['statements_settle']} settle, by phase {row['by_phase']}"
            )
    return None


def installed_versions() -> dict[str, str]:
    """The exact releases the run is made on."""
    from importlib import metadata

    found: dict[str, str] = {}
    for name in ("truss-toolkit", "weft-sql", "psycopg", "pgserver-pg18"):
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return found


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    reason = missing(args.throwaway)
    if reason is not None:
        print(f"the Truss harness cannot run: {reason}", file=sys.stderr)
        return 2
    url = None
    if not args.throwaway:
        from arras.devhost import truss_url

        found = truss_url(args.url)
        if found is None:
            print(
                "no persistent server: --url, ARRAS_TRUSS_DEV_URL, or --throwaway",
                file=sys.stderr,
            )
            return 2
        url = found[0]
    world = load_world(url, args.throwaway)
    run_id = uuid.uuid4().hex[:6]
    versions = installed_versions()
    report: dict[str, Any] = {
        "cpus": os.cpu_count(),
        "versions": versions,
        "runs_per_operation": args.runs,
        "warmup_runs": args.warmup,
        "runs": [],
    }
    print(f"versions {versions}; {args.runs} runs after {args.warmup} warm-up runs per operation")
    missed = False
    try:
        if args.first_calls:
            report["first_calls"] = first_calls(world, run_id, args.first_calls)
            for row in report["first_calls"]:
                later = row["later_median_ms"]
                print(
                    f"first call {row['operation']:<58} first {row['first_ever_ms']:>8.1f} ms"
                    + (f"  later median {later:>8.1f} ms" if later is not None else "")
                )
        if (refused := seed_and_imports(world, args, report, run_id)) is not None:
            return refused
        if args.statements:
            report["statements"] = statements_of(world, run_id)
            for name, found in report["statements"].items():
                total = sum(ms for ms, _, _ in found)
                settles = sum(1 for _, _, t in found if t in ("ROLLBACK", "COMMIT"))
                print(
                    f"\n{name}: {len(found) - settles} execute + {settles} rollback/commit = "
                    f"{len(found)} statements, {total:.1f} ms in them"
                )
                print(
                    "\n".join(
                        f"  {ms:7.2f} ms {kb:8.1f} KB  {text[:120]}" for ms, kb, text in found
                    )
                )
        for n in range(args.repeat):
            load = os.getloadavg()
            print(
                f"\n=== run {n + 1} of {args.repeat}: load average {load[0]:.2f} {load[1]:.2f} "
                f"{load[2]:.2f} on {os.cpu_count()} cpus; busiest: {top_consumers()}"
            )
            results = run_once(world, args, f"{run_id}{n}")
            print(table(results))
            report["runs"].append(
                {
                    "load_start": load,
                    "load_end": os.getloadavg(),
                    "busiest": top_consumers(),
                    "series": [s.row() for s in results],
                }
            )
            missed |= any(s.op.target is not None and s.pct(95) > s.op.target for s in results)
    finally:
        world.close()
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 1 if args.enforce and missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
