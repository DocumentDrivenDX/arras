# SPDX-License-Identifier: MIT OR Apache-2.0
"""The backend conformance corpus and the runner that holds an adapter to it (CONTRACT-004).

The corpus is data (`corpus.json`): a fixture of principals, a module and records, and cases made
of steps with expected results, errors and state. An adapter supplies a `Harness` (how to make
principals, install the module, seed records, cut the backend off); the runner turns each step
into the adapter's operations. Both adapters run the same cases, and the in-memory fakes are the
first to pass.

The runner is strict on purpose: every operation step states what it expects, an unknown
expectation is a failure, a row must carry exactly the keys it should, and an adapter's own
exception is reported against the case instead of ending the run.

A statement is passed to the backend as written (`Statement`), over the module the step names (the
corpus module by default); the runner parses none. A whole-entity row (a step marked `whole`) must
carry the entity facts the backend appends as columns, for every adapter.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from typing import Any, Protocol

from arras.actions import Plan, resolve
from arras.backend import Backend
from arras.errors import ArrasError
from arras.model import ModuleInfo
from arras.results import (
    BatchReceipt,
    ChangesPage,
    ImportResult,
    LoadsPage,
    Receipt,
    RecordsPage,
    RegisteredDocument,
    RegistrationCheck,
    Validation,
)
from arras.searchplan import TextMatch
from arras.types import Principal, Revision, Statement
from arras.umf import parse_module

from . import _checks

_Fail = _checks.Failure
_check_capabilities = _checks.check_capabilities
_check_refs = _checks.check_refs
_check_row_len = _checks.check_row_len
_check_rows = _checks.check_rows
_check_weft = _checks.check_weft
_eq = _checks.eq

KNOWN_TAGS = frozenset({"store", "reader", "reader-only", "host-specific"})
SETUP_OPS = frozenset({"grant", "install", "seed", "seed_many", "sync", "outage", "expire"})
STEP_OPS = frozenset(
    {
        "query",
        "status",
        "reached",
        "describe",
        "apply",
        "apply_batch",
        "import",
        "register",
        "validate_register",
        "attach",
        "provider_write",
        "changes",
        "loads",
        "document",
        "export",
    }
)


def tags(roles: tuple[str, ...]) -> set[str]:
    """The corpus tags a backend with these roles is held to: `reader` for the reads every reader
    serves, `store` for a reader that is also a provider, `reader-only` for one that is not."""
    out: set[str] = set()
    if "reader" in roles:
        out.add("reader")
        out.add("store" if "provider" in roles else "reader-only")
    return out


def _edited(text: str, edit: str | None) -> str:
    """The module's document with one change a registration could make: `add-optional-property`
    or `add-required-property` adds `UseCase.notes`, `add-record-type` adds a second record
    type, and `rewrite` re-serializes the same document with different bytes (compact, keys sorted)
    and no other change."""
    if edit is None:
        return text
    if edit == "rewrite":
        return json.dumps(json.loads(text), separators=(",", ":"), sort_keys=True)
    if edit == "add-record-type":  # a compatible change: a second record type, `Pattern`
        doc = json.loads(text)
        els = doc["modules"][0]["elements"]
        clone = [e for e in els if e["id"] == "Solution" or e["id"].startswith("Solution.")]
        els.extend(json.loads(json.dumps(e).replace("Solution", "Pattern")) for e in clone)
        # compact, since Truss refused a registered change to an indented document of 14,699
        # bytes and took one of 14,599, and the corpus module's own text is near that size
        return json.dumps(doc, separators=(",", ":"))
    if edit not in ("add-optional-property", "add-required-property"):
        raise _Fail(f"unknown edit {edit!r}")
    required = edit == "add-required-property"
    doc = json.loads(text)
    els = doc["modules"][0]["elements"]
    rec = next(e for e in els if e["id"] == "UseCase")
    rec["members"].append({"module": "catalog", "element": "UseCase.notes"})
    rec["extensions"]["umf.ddd"]["fields"]["notes"] = {
        "type": {"kind": "scalar", "name": "string"},
        "cardinality": "one" if required else "optional",
    }
    if required:  # the module's own action must set it, or the document is not valid
        add = next(a for a in doc["modules"][0]["actions"] if a["id"] == "AddUseCase")
        add["effects"][0]["properties"]["notes"] = {"literal": "none"}
    els.append(
        {
            "id": "UseCase.notes",
            "kind": "field",
            "name": "notes",
            "nullability": "required" if required else "absent-allowed",
            "cardinality": "one",
            "scalarType": "string",
            "extensions": {},
        }
    )
    return json.dumps(doc, indent=2)


class Harness(Protocol):
    """What an adapter supplies so the runner can drive it as a test."""

    @property
    def roles(self) -> tuple[str, ...]:
        """What the backend does: "reader" and/or "provider"."""
        ...

    corpus_version: int  # the newest corpus this adapter claims to meet

    # Optional: `limits`, case id -> a `Limit`: the step (as the runner names it, "step 2 (query)")
    # at which the backend's documented limit ends that case, and the refusal it ends in (error
    # class and an optional detail fragment). See `run_corpus`.

    def install(self, module: ModuleInfo, document: bytes) -> None:
        """Make the module known to the backend (registered on a provider, attached on a
        reader that is not one). It comes before any grant: a module's roles exist only once it does."""
        ...

    def grant(self, user: str, modules: Mapping[str, Sequence[str]], admin: bool) -> None:
        """Make `user` a person the backend knows by token, with `read`, `write`, `journal` or `schema` on each module
        (none at all when `modules` is empty); `admin` is the administrative principal."""
        ...

    def principal(self, name: str) -> Principal:
        """The person's principal; `anon` has no token."""
        ...

    def borrowed(self, user: str, token_owner: str) -> Principal:
        """`user` presenting `token_owner`'s token."""
        ...

    def foreign_token(self) -> str:
        """A position token this backend did not issue (from another instance)."""
        ...

    def seed(self, user: str, records: Sequence[Mapping[str, object]]) -> None:
        """Load records as `user`'s own import (so `_created_by` is `user`); a reader that is not a provider gets them
        through a provider and a sync."""
        ...

    def write(self, user: str, plan: Plan) -> str:
        """Apply a change on a provider, whichever backend is under test; returns the token."""
        ...

    def sync(self) -> None:
        """Bring a reader up to its provider (nothing to do for one that is both)."""
        ...

    def outage(self, reason: str | None) -> None: ...

    def expire(self, user: str) -> None: ...

    def backend(self) -> Backend: ...


def load_corpus() -> dict[str, Any]:
    root = resources.files("arras.conformance")
    corpus = json.loads(root.joinpath("corpus.json").read_text())
    corpus["_module_text"] = root.joinpath(corpus["module"]).read_text()
    return corpus


@dataclass
class Result:
    case: str
    status: str  # passed, failed, harness_error, host_specific, limit
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("passed", "host_specific", "limit")


@dataclass(frozen=True)
class Limit:
    """A documented limit of a backend: the step it ends a case at and the refusal it ends in."""

    step: str  # as the runner names it: "step 2 (query)"
    error: str  # the class name of the error the backend raises there
    detail: str | None = None  # a fragment of its reason, construct or violation codes

    def __str__(self) -> str:
        tail = f"({self.detail})" if self.detail else ""
        return f"{self.step}: {self.error}{tail}"


def _detail(e: ArrasError) -> str:
    """What an error says about itself: its reason, its construct, else its violation codes, else its message."""
    reason = getattr(e, "reason", None)
    if reason:
        return str(reason)
    construct = getattr(e, "construct", None)
    if construct:
        return str(construct)
    codes = [v.code for v in getattr(e, "violations", [])]
    return ", ".join(codes) if codes else str(e)


def _matches(limit: Limit, e: ArrasError | None) -> bool:
    if e is None or type(e).__name__ != limit.error:
        return False
    return limit.detail is None or limit.detail in _detail(e)


@dataclass
class Report:
    roles: tuple[str, ...] = ()
    corpus_version: int = 0
    newer_corpus: bool = False
    results: list[Result] = field(default_factory=list[Result])
    skipped: list[str] = field(default_factory=list[str])

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok]

    @property
    def passed(self) -> bool:
        """The pass rule: a corpus the adapter knows, and every case for its roles passing.
        A host-specific case is tagged and outside the rule; a case ending at the step its backend
        declares as a documented limit is recorded as `limit` and passes only while it ends there
        in the refusal the limit names."""
        return not self.newer_corpus and not self.failed and bool(self.results)


@dataclass(frozen=True)
class _Written:
    token: str


class _HarnessError(Exception):
    pass


def run_corpus(make_harness: Callable[[], Harness], *, only: Sequence[str] | None = None) -> Report:
    """Run every case for the harness's roles on a fresh harness each; a newer corpus than the
    adapter claims is reported, never passed.

    A harness may declare `limits`: case id -> a `Limit`, the step at which a documented limit of the
    backend ends that case and the refusal (error class, optional detail) it ends in. Such a case is
    `limit` (recorded, not failing) only when it fails at exactly that step with exactly that
    refusal, matched on the error the backend raised; it fails when it passes (the limit is gone,
    remove it), fails at another step or with another refusal, or is named for no case of the corpus."""
    corpus = load_corpus()
    probe, limits, report = _probe_harness(make_harness, corpus["version"])
    if probe is None or report.results or report.newer_corpus:
        return report
    for c in corpus["cases"]:
        if bad := set(c["tags"]) - KNOWN_TAGS:
            report.results.append(Result(c["id"], "failed", f"unknown tags {sorted(bad)}"))
            continue
        if not (tags(report.roles) & set(c["tags"])) or (only is not None and c["id"] not in only):
            report.skipped.append(c["id"])
            continue
        harness = _case_harness(make_harness, c["id"], report)
        if harness is None:
            continue
        _run_case(harness, corpus, c, limits, report)
    _check_limit_names(corpus, limits, only, report)
    return report


def _check_limit_names(
    corpus: Mapping[str, Any],
    limits: Mapping[str, Limit],
    only: Sequence[str] | None,
    report: Report,
) -> None:
    if only is not None:
        return
    known = {c["id"] for c in corpus["cases"]}
    for case in sorted(set(limits) - known):
        report.results.append(Result(case, "failed", "a limit names no case of the corpus"))


def _run_case(
    harness: Harness,
    corpus: Mapping[str, Any],
    case: Mapping[str, Any],
    limits: Mapping[str, Limit],
    report: Report,
) -> None:
    case_id = case["id"]
    try:
        try:
            _Runner(harness, dict(corpus), dict(case)).run()
            if case_id in limits:
                msg = f"passes, so its limit ({limits[case_id]}) is gone: remove it"
                report.results.append(Result(case_id, "failed", msg))
                return
            status = "host_specific" if "host-specific" in case["tags"] else "passed"
            report.results.append(Result(case_id, status))
        except _Fail as error:
            report.results.append(_failed_case(case_id, error, limits.get(case_id)))
        except _HarnessError as error:
            report.results.append(Result(case_id, "harness_error", str(error)))
        except Exception as error:
            report.results.append(
                Result(case_id, "harness_error", f"harness failed: {type(error).__name__}")
            )
    finally:
        _close_harness(harness, report, f"{case_id}.cleanup")


def _failed_case(case: str, error: _Fail, want: Limit | None) -> Result:
    if want is None:
        return Result(case, "failed", str(error))
    if str(error).startswith(want.step) and _matches(want, error.cause):
        return Result(case, "limit", f"{error} [{want}]")
    if str(error).startswith(want.step):
        got = (
            f"{type(error.cause).__name__}({_detail(error.cause)})"
            if error.cause
            else f"no refusal ({error})"
        )
        msg = f"{want.step}: expected {want.error}({want.detail or ''}), got {got}"
        return Result(case, "failed", msg)
    return Result(case, "failed", f"{error} (the documented limit ends it at {want})")


def _case_harness(make_harness: Callable[[], Harness], case: str, report: Report) -> Harness | None:
    try:
        return make_harness()
    except Exception as error:
        report.results.append(
            Result(case, "harness_error", f"factory failed: {type(error).__name__}")
        )
        return None


def _probe_harness(
    make_harness: Callable[[], Harness], corpus_version: int
) -> tuple[Harness | None, Mapping[str, Limit], Report]:
    report = Report(corpus_version=corpus_version)
    limits: Mapping[str, Limit] = {}
    try:
        probe = make_harness()
    except Exception as error:
        report.results.append(
            Result("harness-probe", "harness_error", f"factory failed: {type(error).__name__}")
        )
        return None, limits, report
    try:
        report.roles = probe.roles
        limits = dict(getattr(probe, "limits", {}))
        report.newer_corpus = corpus_version > probe.corpus_version
    except Exception as error:
        report.results.append(
            Result("harness-probe", "harness_error", f"probe failed: {type(error).__name__}")
        )
    finally:
        _close_harness(probe, report, "harness-probe")
    return probe, limits, report


def _close_harness(harness: Harness, report: Report, case: str) -> None:
    """Close an optional acquired harness once and make cleanup failure visible."""
    try:
        close = getattr(harness, "close", None)
        if not callable(close):
            return
        close()
    except Exception as error:
        report.results.append(
            Result(case, "harness_error", f"close failed: {type(error).__name__}")
        )


# The facts a backend appends to a whole-entity row as columns (CONTRACT-001, CONTRACT-004).
FACTS = frozenset(
    {"_version", "_created_by", "_created_at", "_updated_by", "_updated_at"}
    | {"_original_author", "_original_at", "_load_id"}
)

_SAVE = {"token": "token", "cursor": "next_cursor", "group": "group"}


class _Runner:
    def __init__(self, h: Harness, corpus: dict[str, Any], case: dict[str, Any]) -> None:
        self.h = h
        self.case = case
        self.corpus = corpus
        self.text: str = corpus["_module_text"]
        self.module = parse_module(self.text)
        self.vars: dict[str, Any] = {}
        n = itertools.count()
        self.new_key: Callable[[], str] = lambda: f"gen-{next(n)}"

    # -- driving
    def run(self) -> None:
        fixture = self.corpus["fixtures"][self.case["fixture"]]
        for i, step in enumerate(fixture):
            try:
                self.setup(step)
            except _Fail:
                raise
            except Exception as e:  # the harness could not build the world
                raise _HarnessError(
                    f"fixture step {i} ({step['op']}): {type(e).__name__}: {e}"
                ) from None
        for i, step in enumerate(self.case["steps"]):
            try:
                self.step(step)
            except _Fail as e:
                raise _Fail(f"step {i} ({step['op']}): {e}", e.cause) from None
            except _HarnessError:
                raise
            except Exception as e:
                raise _Fail(
                    f"step {i} ({step['op']}): unexpected {type(e).__name__}: {e}"
                ) from None

    def sub(self, v: Any) -> Any:
        """`$name` is a saved value; `$roles` and `$mutable` describe the backend under test."""
        if isinstance(v, str) and v.startswith("$"):
            name = v[1:]
            if name == "roles":
                return sorted(self.h.roles)
            if name == "mutable":
                return "provider" in self.h.roles
            if name == "foreign" and name not in self.vars:
                try:
                    self.vars[name] = self.h.foreign_token()
                except Exception as error:
                    raise _HarnessError(
                        f"foreign token setup failed: {type(error).__name__}"
                    ) from None
            if name not in self.vars:
                raise _Fail(f"{v} was never saved")
            return self.vars[name]
        if isinstance(v, dict):
            return {k: self.sub(x) for k, x in v.items()}  # type: ignore[reportUnknownVariableType]
        if isinstance(v, list):
            return [self.sub(x) for x in v]  # type: ignore[reportUnknownVariableType]
        return v

    def setup(self, s: dict[str, Any]) -> None:
        op = s["op"]
        if op == "grant":
            self.h.grant(s["user"], s["modules"], s.get("admin", False))
        elif op == "install":
            self.h.install(self.module, self.text.encode())
        elif op == "seed":
            self.h.seed(s["as"], s["records"])
        elif op == "seed_many":
            self.h.seed(s["as"], self.expand(s))
        elif op == "sync":
            self.h.sync()
        elif op == "outage":
            self.h.outage(s["reason"])
        elif op == "expire":
            self.h.expire(s["user"])
        else:
            raise _Fail(f"unknown setup op {op!r}")

    def step(self, s: dict[str, Any]) -> None:
        op = s["op"]
        if op in SETUP_OPS:
            try:
                self.setup(s)
            except Exception as e:
                raise _HarnessError(f"{op}: {type(e).__name__}: {e}") from None
            return
        if op not in STEP_OPS:
            raise _Fail(f"unknown op {op!r}")
        if "expect" not in s:
            raise _Fail("an operation step states what it expects")
        if op == "reached" and "as" not in s:
            raise _Fail("a reached step names a person (as)")
        no_audit = self.audit_undeclared(s)
        outcome = self.attempt(s)
        if no_audit:  # nothing is read, so nothing is saved; a later `$var` is a placeholder
            self.check({"error": "Unsupported"}, outcome, s)
            saves: dict[str, str] = s.get("save") or {}
            for var in saves.values():
                self.vars[var] = "unsupported"
            return
        expect = self.sub(s["expect"])
        unsupported = self.needs_missing_profile(s)
        if unsupported:
            expect = {"error": "Unsupported"}
        self.check(expect, outcome, s)
        save: dict[str, str] = s.get("save") or {}
        for name, var in save.items():
            attr = _SAVE.get(name)
            got = (
                getattr(outcome, attr, None)
                if attr and not isinstance(outcome, ArrasError)
                else None
            )
            if got is None:
                raise _Fail(f"nothing to save as {var!r}: {name} of {type(outcome).__name__}")
            self.vars[var] = got

    def attempt(self, s: dict[str, Any]) -> Any:
        try:
            return self.act(s)
        except ArrasError as e:
            return e
        except _HarnessError:
            raise
        except _Fail:
            raise
        except Exception as e:
            raise _Fail(f"unexpected {type(e).__name__} from the backend: {e}") from None

    def audit_undeclared(self, s: dict[str, Any]) -> bool:
        """A backend that declares no journal (`describe().audit` false) must answer
        `Unsupported` to the audit reads; the other steps of the case still run."""
        if s.get("op") not in ("changes", "loads"):
            return False
        return not self.h.backend().describe().audit

    def needs_missing_profile(self, s: dict[str, Any]) -> bool:
        """A read step may name the Weft profiles it needs; a backend that does not declare them
        (`describe().weft`) must answer `Unsupported`, so the case holds a backend to its own
        declaration. A declared `general` covers every profile: each named profile is a shape of
        the general one, so a backend that serves it serves them."""
        need = s.get("requires")
        if not need:
            return False
        info = self.h.backend().describe()
        declared: set[str] = set(info.weft.profiles) if info.weft is not None else set()
        if "general" not in declared and not set(need.get("profiles", [])) <= declared:
            return True
        if need.get("search") is True:  # a text match needs the type to declare `substring`
            caps = info.capabilities.get(need["type"])
            return caps is None or not caps.read or caps.search != "substring"
        return False

    @staticmethod
    def expand(s: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        for i in range(s["count"]):
            key = s["key"].format(i)
            recs.append({"type": s["type"], "key": key, "properties": s["properties"]})
            recs.append({**s["link"], "source": key})
        return recs

    # -- operations on the backend under test
    def principal(self, s: dict[str, Any]) -> Principal:
        who = s["as"]
        if "@" in who:  # `carol@alice`: carol presenting alice's token
            user, owner = who.split("@", 1)
            return self.h.borrowed(user, owner)
        return self.h.principal(who)

    def act(self, s: dict[str, Any]) -> Any:
        op, b = s["op"], self.h.backend()
        if op == "status":
            return b.status()
        if op == "describe":
            return b.describe()
        who = self.principal(s)
        if op == "reached":
            return b.reached(who, self.sub(s["token"]))
        if op == "query":
            statement = Statement(s["sql"], s.get("params") or {})
            module = s.get("module", self.module.name)
            match = None
            if (text := s.get("text")) is not None:  # a structured match beside the statement
                match = TextMatch(tuple(text["words"]), tuple(text["properties"]))
            ans = b.query(who, module, statement, limit=s.get("limit", 50), text=match)
            self.check_answer(ans, s.get("whole", False))
            return ans
        if op == "provider_write":
            return _Written(self.h.write(s["as"], self.plan(s["action"], s["inputs"])))
        auth: Any = (
            b  # the operations below are a provider's; a reader that is not one must refuse them
        )
        if op == "apply":
            plan = self.plan(s["action"], s["inputs"])
            return auth.apply(
                who, plan, idempotency_key=s.get("key"), dry_run=s.get("dry_run", False)
            )
        if op == "apply_batch":
            plans = [self.plan(s["action"], i) for i in s["items"]]
            return auth.apply_batch(
                who,
                plans,
                atomic=s["atomic"],
                idempotency_key=s.get("key"),
                stop_on_error=s.get("stop_on_error", False),
            )
        if op == "import":
            return auth.import_records(
                who,
                self.module.name,
                s["records"],
                load_id=s["load_id"],
                initiated_by=s.get("initiated_by", who.user),
            )
        if op in ("register", "validate_register"):
            text = _edited(self.text, s.get("edit"))
            args = (who, text.encode(), parse_module(text))
            if op == "validate_register":  # the dry run (CONTRACT-004, corpus 4)
                return auth.validate_register(*args, unknown_endpoint="reject")
            return auth.register(
                *args,
                unknown_endpoint="reject",
                expected_revision=self.expected_revision(auth, who, s.get("expected_revision")),
            )
        if op == "attach":
            return auth.attach(who, self.module)
        if op == "changes":  # the journal: `module`, or a `group` alone (CONTRACT-001, Audit reads)
            group = self.sub(s.get("group"))
            return auth.changes(
                who,
                module=None if group is not None else self.module.name,
                type=None,
                key=None,
                by=s.get("by"),
                action=s.get("action"),
                group=group,
                since=None,
                until=None,
                limit=s.get("limit", 50),
                after=self.sub(s.get("after")),
            )
        if op == "document":  # the registered document, as written (CONTRACT-004, corpus 3)
            return auth.document(who, s.get("module", self.module.name))
        if op in ("export", "loads"):
            return self.paged(auth, who, s)
        raise _Fail(f"unknown op {op!r}")

    def paged(self, auth: Any, who: Principal, s: dict[str, Any]) -> Any:
        """A page of the graph as records (`export`, 500 by default), or of the loads (`loads`, 50)."""
        after = self.sub(s.get("after"))
        if s["op"] == "export":
            return auth.export_records(
                who, self.module.name, limit=s.get("limit", 500), after=after
            )
        return auth.loads(who, self.module.name, limit=s.get("limit", 50), after=after)

    def expected_revision(self, auth: Any, who: Principal, which: str | None) -> Revision | None:
        """`current` is the revision the backend holds now; `stale` is one it does not."""
        if which is None:
            return None
        held = auth.document(who, self.module.name).revision
        if which == "current":
            return held
        return Revision(
            {k: (v if isinstance(v, int) else 0) + 1000 for k, v in held.by_backend.items()}
        )

    def plan(self, action: str, inputs: Mapping[str, Any]) -> Plan:
        a = next((a for a in self.module.actions if a.name == action), None)
        if a is None:
            raise _HarnessError(f"the corpus module declares no action {action!r}")
        return resolve(a, inputs, self.module, new_key=self.new_key)

    # -- what every answer must carry
    @staticmethod
    def check_answer(ans: Any, whole: bool) -> None:
        """A whole-entity row carries the facts the backend appends; any other row carries
        exactly its columns."""
        pos = ans.as_of
        if not isinstance(pos.value, str) or not pos.value:
            raise _Fail("an answer states the position it reflects")
        if not isinstance(pos.at, datetime) or pos.at.tzinfo is None:
            raise _Fail("an answer states when that position was recorded, with an offset")
        if whole:
            for row in ans.rows:
                missing = FACTS - set(row)
                if missing:
                    raise _Fail(f"alias.* rows carry {sorted(missing)}")
            undescribed = FACTS - {c.name for c in ans.columns}
            if undescribed:
                raise _Fail(f"the result descriptor names {sorted(undescribed)}")
        else:
            names = [c.name for c in ans.columns]
            for row in ans.rows:
                if sorted(row) != sorted(names):
                    raise _Fail(f"a row has keys {sorted(row)}, the columns are {sorted(names)}")

    # -- expectations
    def check(self, expect: dict[str, Any], out: Any, step: dict[str, Any]) -> None:
        if isinstance(out, ArrasError):
            try:
                self.check_error(expect, out)
            except _Fail as f:
                if f.cause is None:
                    f.cause = out
                raise
            return
        if "error" in expect:
            raise _Fail(f"expected {expect['error']}, got {type(out).__name__}")
        self.check_value(expect, out)

    def check_error(self, expect: dict[str, Any], e: ArrasError) -> None:
        if "error" not in expect:  # a value was expected and an error came
            raise _Fail(f"expected {sorted(expect)}, got {type(e).__name__}({_detail(e)}): {e}", e)
        unknown = set(expect) - {"error", "reason", "code", "failure_ids"}
        if unknown:
            raise _Fail(f"unknown error expectation {sorted(unknown)}", e)
        if expect.get("error") != type(e).__name__:
            raise _Fail(f"expected {expect.get('error')}, got {type(e).__name__}: {e}")
        if "reason" in expect and getattr(e, "reason", None) != expect["reason"]:
            raise _Fail(f"reason {getattr(e, 'reason', None)!r} != {expect['reason']!r}")
        if "code" in expect and expect["code"] not in [
            v.code for v in getattr(e, "violations", [])
        ]:
            raise _Fail(f"no violation {expect['code']!r} in {e}")
        if "failure_ids" in expect:
            ids = [f.id for f in getattr(e, "failures", [])]
            if ids != expect["failure_ids"]:
                raise _Fail(f"failures {ids} != {expect['failure_ids']}")

    def check_value(self, expect: dict[str, Any], out: Any) -> None:
        checkers = self.value_checkers()
        for key, want in expect.items():
            if key == "ok":
                continue  # the outcome was not an error, and its type is checked below
            if key not in checkers:
                raise _Fail(f"unknown expectation {key!r}")
            checkers[key](want, out)
        if "ok" in expect:
            self.check_type(out, expect["ok"])

    def value_checkers(self) -> dict[str, Callable[[Any, Any], None]]:
        return {
            "rows": _check_rows,
            "row_count": lambda w, o: _eq("row count", len(list(o.rows)), w),
            "columns": lambda w, o: _eq("columns", [c.name for c in o.columns], w),
            "truncated": lambda w, o: _eq("truncated", o.truncated, w),
            "row_len": _check_row_len,
            "receipt": self.check_receipt,
            "refs": _check_refs,
            "validation": self.check_validation,
            "batch": self.check_batch,
            "import": self.check_import,
            "available": lambda w, o: _eq("available", o.available, w),
            "reason": lambda w, o: _eq("reason", o.reason, w),
            "has_position": lambda w, o: _eq("has position", o.position is not None, w),
            "value": lambda w, o: _eq("value", o, w),
            "roles": lambda w, o: _eq("roles", sorted(o.roles), w),
            "capabilities": _check_capabilities,
            "weft": _check_weft,
            "token_is": lambda w, o: _eq("token", getattr(o, "token", None), w),
            "changed": lambda w, o: _eq("changed", o.changed, w),
            "changes": lambda w, o: self.check_page(w, o, ChangesPage, "group"),
            "loads": lambda w, o: self.check_page(w, o, LoadsPage, "load_id"),
            "document": self.check_document,
            "export": self.check_export,
            "registration": self.check_registration,
        }

    @staticmethod
    def check_type(out: Any, want: str) -> None:
        types = {"receipt": Receipt, "answer": object, "batch": BatchReceipt, "written": _Written}
        if want in types and not isinstance(out, types[want]):
            raise _Fail(f"expected {want}, got {type(out).__name__}")

    def check_receipt(self, want: dict[str, Any], out: Any) -> None:
        if not isinstance(out, Receipt):
            raise _Fail(f"expected a receipt, got {type(out).__name__}")
        if not out.token:
            raise _Fail("a receipt carries a token")
        derived = {
            "token_is": out.token,
            "has_group": bool(out.group),
            "group_is": out.group,
        }
        known = {"created", "updated", "deleted", "linked", "unlinked", "replayed", *derived}
        if set(want) - known:
            raise _Fail(f"unknown receipt expectation {sorted(set(want) - known)}")
        for k, v in want.items():
            got = derived[k] if k in derived else getattr(out, k)
            if got != v:
                raise _Fail(f"receipt.{k}: {got!r} != {v!r}")

    def check_validation(self, want: dict[str, Any], out: Any) -> None:
        if not isinstance(out, Validation):
            raise _Fail(f"expected a validation, got {type(out).__name__}")
        checks = {
            "ok": out.ok,
            "failure_ids": [f.id for f in out.failures],
            "effects": [type(e).__name__ for e in out.effects],
            "replay": out.replay is not None,
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown validation expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"validation.{k}: {checks[k]!r} != {v!r}")

    def check_import(self, want: dict[str, Any], out: Any) -> None:
        if not isinstance(out, ImportResult):
            raise _Fail(f"expected an import result, got {type(out).__name__}")
        checks = {
            "created": out.created,
            "skipped": out.skipped,
            "rejected": len(out.rejected),
            "rejected_kinds": sorted(r.kind for r in out.rejected),
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown import expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"import.{k}: {checks[k]!r} != {v!r}")

    @staticmethod
    def check_registration(want: dict[str, Any], out: Any) -> None:
        """What a dry run reported: whether it would be accepted and the codes it would refuse with."""
        if not isinstance(out, RegistrationCheck):
            raise _Fail(f"expected a registration check, got {type(out).__name__}")
        checks = {
            "ok": not out.violations,
            "codes": sorted({v.code for v in out.violations}),
            "has_revision": out.revision is not None,
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown registration expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"registration.{k}: {checks[k]!r} != {v!r}")

    @staticmethod
    def check_export(want: dict[str, Any], out: Any) -> None:
        """A page of records: exactly these, in this order (`records`), and whether a next page
        is named (`more`)."""
        if not isinstance(out, RecordsPage):
            raise _Fail(f"expected a records page, got {type(out).__name__}")
        if out.freshness.as_of.at.tzinfo is None:
            raise _Fail("a page states when its position was recorded, with an offset")
        checks = {
            "records": [dict(r) for r in out.items],
            "more": out.next_cursor is not None,
            "omitted": list(out.omitted),
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown export expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"export.{k}: {checks[k]!r} != {v!r}")

    def check_document(self, want: dict[str, Any], out: Any) -> None:
        """`verbatim`: the text is the installed document, character for character."""
        if not isinstance(out, RegisteredDocument):
            raise _Fail(f"expected a registered document, got {type(out).__name__}")
        checks = {
            "verbatim": out.text == self.text,
            "format": out.format,
            "module": out.module,
            "has_revision": any(v is not None for v in out.revision.by_backend.values()),
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown document expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"document.{k}: {checks[k]!r} != {v!r}")

    def check_page(self, want: dict[str, Any], out: Any, kind: type, id_attr: str) -> None:
        """A journal page: the ids in order (newest first), who and what, and whether it names
        a next page."""
        if not isinstance(out, kind):
            raise _Fail(f"expected a {kind.__name__}, got {type(out).__name__}")
        if not isinstance(out.freshness.as_of.at, datetime):
            raise _Fail("a page states the position it reflects")
        checks = {
            "ids": [getattr(i, id_attr) for i in out.items],
            "by": [getattr(i, "by", getattr(i, "initiated_by", None)) for i in out.items],
            "actions": [getattr(i, "action", None) for i in out.items],
            "next_cursor": out.next_cursor is not None,
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown page expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"page.{k}: {checks[k]!r} != {v!r}")

    def check_batch(self, want: dict[str, Any], out: Any) -> None:
        if not isinstance(out, BatchReceipt):
            raise _Fail(f"expected a batch receipt, got {type(out).__name__}")
        items = out.items
        checks = {
            "succeeded": out.succeeded,
            "failed": out.failed,
            "items": len(items),
            "one_token": len({i.receipt.token for i in items if i.receipt}) == 1,
            "refusals": {str(i.index): type(i.refusal).__name__ for i in items if i.refusal},
            "replayed": [i.index for i in items if i.receipt and i.receipt.replayed],
            "groups": len({i.receipt.group for i in items if i.receipt}),
        }
        if set(want) - set(checks):
            raise _Fail(f"unknown batch expectation {sorted(set(want) - set(checks))}")
        for k, v in want.items():
            if checks[k] != v:
                raise _Fail(f"batch.{k}: {checks[k]!r} != {v!r}")
