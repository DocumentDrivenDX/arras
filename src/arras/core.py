# SPDX-License-Identifier: MIT OR Apache-2.0
"""The interface itself: `Arras`, a session per principal, and the registry (CONTRACT-001, 003, 005).

Arras holds no entity data and no access decision from one call to the next. Each call asks the
backends, as the caller, which modules exist and what they can do, picks the backend the
consistency level requires, and states what it did.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, cast

from arras import callscope, gqlschema, telemetry
from arras._catalogs import Catalogs as _Catalogs
from arras._catalogs import collect_catalogs
from arras.actions import ActionInfo, Effect, Plan, resolve
from arras.backend import Backend, Migrates, Provider
from arras.errors import (
    UNAVAILABLE_REASONS,
    ArrasError,
    Conflict,
    Invalid,
    NotYetCurrent,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.model import Capabilities, EntityTypeInfo, MetadataProfile, ModuleInfo, Placement
from arras.registration import as_revision as _revision
from arras.registration import check_document
from arras.results import (
    Answer,
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ChangesPage,
    ImportResult,
    LoadsPage,
    MigrationResult,
    Receipt,
    RecordsPage,
    RegisteredDocument,
    RegistryResult,
    Validation,
)
from arras.routing import Router
from arras.schema_admin import Schema
from arras.search import run_search
from arras.searchplan import Budget, SearchPage, TextMatch
from arras.types import Consistency, Freshness, Principal, Revision, Rows, Statement
from arras.view import ResolvedModule
from arras.viewcache import ViewCache

MAX_LIMIT = 100
MAX_BATCH = 100
MAX_ATOMIC_EFFECTS = 1000
_REASONS = UNAVAILABLE_REASONS
Handler = Callable[[Mapping[str, Any], "Context"], Sequence[Effect]]
Status = dict[str, BackendStatus]


def _of_batch(
    self: object, action: str, items: Sequence[object], **kw: object
) -> dict[str, object]:
    # Only a count and a flag are known before the action resolves; its name is added after.
    return {"items": len(items), "atomic": bool(kw.get("atomic"))}


def _of_rows(r: Rows) -> dict[str, object]:
    f = r.freshness
    return {
        "backend": f.backend,
        "consistency": f.consistency,
        "rows": len(r.rows),
        "truncated": r.truncated,
    }


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


@dataclass(frozen=True)
class Context:
    """What a handler may use: reads, at `latest`, through the interface."""

    ontology: Ontology

    def query(self, module: str, sql: str, params: Mapping[str, Any] | None = None) -> Rows:
        return self.ontology.query(module, sql, params, consistency="latest")


class Arras:
    """One instance per process: the configured backends, and sessions for principals."""

    def __init__(
        self,
        backends: Mapping[str, Backend],
        *,
        wait_bound: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        expected: Sequence[str] = (),
        admin: Principal | None = None,
        placement: Mapping[str, Placement] | None = None,
        default_placement: Placement | None = None,
        metadata_profile: MetadataProfile = "legacy-arras/1",
    ) -> None:
        if type(metadata_profile) is not str or metadata_profile not in (
            "legacy-arras/1",
            "umf-core-metadata/1",
        ):
            raise ValueError(f"unknown metadata profile: {metadata_profile!r}")
        self.backends = dict(backends)
        self.metadata_profile = metadata_profile
        self.placements = dict(placement or {})  # the host's, by module name (CONTRACT-002)
        self.default_placement = default_placement
        self.admin = admin  # the host's administrative principal, when it names one
        self.expected: tuple[str, ...] = tuple(expected)
        self.wait_bound = wait_bound
        self.sleep = sleep
        self.clock = clock
        self.handlers: dict[str, Handler] = {}
        self.views = ViewCache()  # resolved views by module and revision (CONTRACT-010)
        self._announce_lock = threading.Lock()
        self._announced: dict[
            str, tuple[bool, str | None]
        ] = {}  # the last state each was reported in

    @classmethod
    def start(
        cls,
        backends: Mapping[str, Backend],
        *,
        wait_bound: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        expected: Sequence[str] = (),
        admin: Principal | None = None,
        placement: Mapping[str, Placement] | None = None,
        default_placement: Placement | None = None,
        metadata_profile: MetadataProfile = "legacy-arras/1",
    ) -> Arras:
        """Never raises for an availability failure: `status()` reports each backend.

        `backends` are named by the host, any number of each kind. `placement` says, by module
        name, which reader is its record store, which others hold replicas and which provider runs
        which action; `default_placement` is for a
        module it does not list, and a module with neither is not served. The connection sources
        belong to the real adapters, which wrap their connections as `Backend`s; `start` installs
        nothing and has no budget (`migrate` has one).
        """
        return cls(
            backends,
            wait_bound=wait_bound,
            sleep=sleep,
            clock=clock,
            expected=expected,
            admin=admin,
            placement=placement,
            default_placement=default_placement,
            metadata_profile=metadata_profile,
        )

    def placement_of(self, module: str) -> Placement | None:
        """Where the host put `module`: its own entry, else the default, else nowhere."""
        return self.placements.get(module, self.default_placement)

    def status(self) -> Status:
        """Ask every backend; a probe never raises. A backend the host expected but did not
        supply is reported `not_configured`."""
        out: Status = {}
        for n in self.expected:
            if n not in self.backends:
                out[n] = BackendStatus(False, "not_configured", f"{n} is not configured")
        for name, b in self.backends.items():
            try:
                out[name] = b.status()
            except Unavailable as e:
                reason = e.reason if e.reason in _REASONS else "unreachable"
                detail = e.detail if reason == e.reason else f"{e.reason}: {e.detail}"
                out[name] = BackendStatus(False, cast(Any, reason), detail)
            except Refused:
                out[name] = BackendStatus(False, "access_denied", f"{name} refused the probe")
            except Exception as e:  # a broken probe is a backend that is not usable
                out[name] = BackendStatus(False, "unreachable", type(e).__name__)  # no driver text
        self._announce(out)
        return out

    def _announce(self, status: Status) -> None:
        """One event for each backend whose availability changed since it was last reported (and
        for its first report), so an outage and its end are each said once, not on every probe."""
        for name, s in status.items():
            reason = s.reason if s.reason in _REASONS else ("other" if s.reason else None)
            state = (s.available, reason)
            with self._announce_lock:  # concurrent probes announce a change once
                changed = self._announced.get(name) != state
                self._announced[name] = state
            if changed:
                telemetry.emit(
                    "arras.backend.status", backend=name, available=s.available, reason=reason
                )

    refresh = status  # no cache of availability: every status asks the backends

    @telemetry.traced("arras.migrate")
    def migrate(self, *, timeout: float | None = None) -> MigrationResult:
        """Install-or-verify of each backend that has a store to install (CONTRACT-005), on its
        installing connection and with no person. A backend with no `migrate` contributes nothing;
        a failure raises the backend's `Unavailable`. `timeout` (seconds, None waits) bounds each
        backend's wait for the install lock. The result is `ran` when any backend installed; its
        revision and role names are those of the backend that ran (the first, when several did:
        a host with several installing backends calls each backend's own `migrate` to keep every
        role pair), else the first backend's revision."""
        results: list[MigrationResult] = []
        try:
            for backend in list(self.backends.values()):
                if isinstance(backend, Migrates):
                    results.append(backend.migrate(timeout=timeout))
        except Unavailable:
            self.status()  # the failed backend now reports why, once (the status event)
            raise
        ran = [r for r in results if r.ran]
        if ran:
            return ran[0]
        return results[0] if results else MigrationResult(False, "none")

    def session(self, principal: Principal) -> Ontology:
        return Ontology(self, principal)

    def close(self) -> None:
        """Releases what Arras holds; the host's connections are the host's to close."""
        self.backends.clear()
        self.handlers.clear()


class Ontology:
    """Every operation, for one principal."""

    def __init__(self, arras: Arras, principal: Principal) -> None:
        self.h = arras
        self.principal = principal

    def require_token(self, op: str) -> None:
        if not self.principal.token:
            raise Refused("arras", op, "token_expired")  # refused before any backend call

    def _is_admin(self) -> bool:
        """Whether this session's principal is the host's administrator. When the host named one
        at `start`, only that principal is (the flag a caller sets is not trusted); otherwise the
        flag decides."""
        p, named = self.principal, self.h.admin
        if named is None:
            return p.admin
        return p.user == named.user and p.token == named.token

    def _is_administrators_token(self) -> bool:
        named = self.h.admin
        return named is not None and (
            self.principal.token == named.token or self.principal.user == named.user
        )

    def require_user(self, op: str) -> None:
        """Reads and actions are a person's: the administrative principal is refused (CONTRACT-005),
        whether or not it says so."""
        self.require_token(op)
        if self.principal.admin or self._is_administrators_token():
            raise Refused("arras", op)

    def require_admin(self, op: str) -> None:
        """Registry, handlers and imports belong to the host's administrative principal."""
        self.require_token(op)
        if not self._is_admin():
            raise Refused("arras", op)

    def _catalogs(self, op: str) -> _Catalogs:
        self.require_token(op)
        return collect_catalogs(self.h.backends, self.principal, self.h.placement_of)

    def _module(self, name: str, op: str) -> tuple[ModuleInfo, _Catalogs]:
        """A module the principal may read; a backend's outage is never reported as absence."""
        if not self.h.backends:
            raise Unavailable("arras", "not_configured", "no backend is configured")
        cats = self._catalogs(op)
        mod = cats.module(name)
        if mod is None:
            if (err := cats.failure()) is not None:
                raise err
            raise Invalid([Violation("module", "unknown_type", f"no module {name!r}")])
        return mod, cats

    def _backend(self, name: str) -> Backend:
        b = self.h.backends.get(name)
        if b is None:
            raise Unavailable(name, "not_configured", f"{name} is not configured")
        return b

    # -- discovery
    def modules(self) -> list[ModuleInfo]:
        """The modules the principal may read, from one pass over the catalogs (no capabilities,
        no status); a backend's outage or refusal is raised when nothing else answered."""
        self.require_user("modules")
        cats = self._catalogs("modules")
        mods = [m for n in cats.names() if (m := cats.module(n)) is not None]
        if not mods and (err := cats.failure()) is not None:
            raise err
        return mods

    @callscope.scoped
    def describe(self, module: str | None = None) -> list[ModuleInfo]:
        """One answer is of one revision: if a registration lands while it is assembled, it is
        assembled again from the new one, and if the registry will not hold still it says so. A
        backend that states its types from the catalog this call read (the call scope) cannot
        disagree with it, so only the others are read again to check."""
        self.require_user("describe")
        for _ in range(3):
            cats = self._catalogs("describe")
            out = self._describe(module, cats)
            unchecked = {
                n: c for n, c in cats.by_backend.items() if n not in callscope.consistent()
            }
            if not unchecked or self._unchanged(unchecked, module):
                return out
        raise Unavailable("arras", "busy", "the registry is changing; ask again")

    def _unchanged(
        self, before: Mapping[str, Mapping[str, ModuleInfo]], module: str | None
    ) -> bool:
        """Whether a fresh read of these backends' catalogs states the revisions they stated."""
        now = self._catalogs("describe").by_backend

        def revisions(held: Mapping[str, Mapping[str, ModuleInfo]]) -> dict[str, Any]:
            return {
                f"{n}:{m}": i.revision
                for n in before
                for m, i in held.get(n, {}).items()
                if module is None or m == module
            }

        return revisions(now) == revisions(before)

    def _describe(self, module: str | None, cats: _Catalogs) -> list[ModuleInfo]:
        if not self.h.backends:
            raise Unavailable("arras", "not_configured", "no backend is configured")
        if module is not None:
            found = cats.module(module)
            if found is None:
                if (err := cats.failure()) is not None:
                    raise err
                raise Invalid([Violation("module", "unknown_type", f"no module {module!r}")])
            mods = [found]
        else:
            mods = [m for n in cats.names() if (m := cats.module(n)) is not None]
            if not mods and (err := cats.failure()) is not None:
                raise err
        status = self.h.status()
        infos: dict[str, BackendInfo] = {}
        out: list[ModuleInfo] = []
        for m in mods:
            names = list(m.placement.readers)
            for n in names:
                if n in self.h.backends and n not in infos:
                    try:
                        infos[n] = self.h.backends[n].describe()
                    except Unavailable:
                        pass  # its capabilities are unknown while it is down; its status says so
            types = tuple(
                replace(t, capabilities=self._capabilities(t, names, infos)) for t in m.entity_types
            )
            out.append(
                replace(m, entity_types=types, status={n: status[n] for n in names if n in status})
            )
        return out

    @staticmethod
    def _capabilities(
        t: EntityTypeInfo, names: list[str], infos: Mapping[str, BackendInfo]
    ) -> dict[str, Capabilities]:
        return {
            n: infos[n].capabilities[t.name]
            for n in names
            if n in infos and t.name in infos[n].capabilities
        }

    def view_of(self, mod: ModuleInfo) -> ResolvedModule:
        """The module's resolved view (CONTRACT-010): its registered document's `arras.view`
        terms merged with the defaults, cached by module and revision. `mod` is one this
        session's principal was shown, so the cache grants nothing."""

        def fetch() -> RegisteredDocument:
            auth = self._record_provider(mod, f"the view of {mod.name}")
            return auth.document(self.principal, mod.name)

        return self.h.views.resolve(mod, fetch)

    # -- reads
    @telemetry.traced("arras.query", None, _of_rows)
    @callscope.scoped
    def query(
        self,
        module: str,
        sql: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int = 50,
        consistency: Consistency = "latest",
        at_least: str | None = None,
        text: TextMatch | None = None,
    ) -> Rows:
        """Run a read-only Weft statement over the named module's types. Arras never reads the
        statement: it checks the module, routes by its placement and the consistency level, waits
        for `at_least` on the chosen backend and states what it did (CONTRACT-001). `text` is a
        structured text match (CONTRACT-010) that `search` makes, passed to the backend beside the
        statement; it is never SQL text, and a backend that does not declare `substring` for the
        type answers `Unsupported`."""
        self.require_user("query")
        if not self.h.backends:
            raise Unavailable("arras", "not_configured", "no backend is configured")
        bad: list[Violation] = []
        if not isinstance(module, str) or not module:  # pyright: ignore[reportUnnecessaryIsInstance]
            bad.append(Violation("module", "type", "the module the statement reads"))
        if not isinstance(sql, str) or not sql.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
            bad.append(Violation("sql", "type", "one Weft statement, as text"))
        if params is not None and not isinstance(params, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            bad.append(Violation("params", "type", "an object of named values"))
        if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
            bad.append(Violation("limit", "bound", f"limit is an integer from 1 to {MAX_LIMIT}"))
        if consistency not in ("latest", "bulk"):
            bad.append(Violation("consistency", "value", "latest or bulk"))
        if bad:
            raise Invalid(bad)
        telemetry.annotate(consistency=consistency)  # checked above: latest or bulk
        statement = Statement(sql, params or {})
        if (
            current := self._read_current(module, statement, limit, consistency, at_least, text)
        ) is not None:
            return current
        mod, cats = self._module(module, "query")  # unknown_type for one the principal cannot read
        telemetry.annotate(module=mod.name)

        def wait(backend: Backend, name: str) -> None:
            if at_least is not None:
                self._await(backend, name, at_least)

        router = Router(
            self.h.backends, mod, self.principal, statement, limit=limit, wait=wait, text=text
        )
        name, ans = router.serve(consistency)
        served = cats.of(name, mod.name) or mod  # the revision the serving backend computed under
        return Rows(
            columns=ans.columns,
            rows=ans.rows,
            truncated=ans.truncated,
            freshness=Freshness(name, ans.as_of, consistency),
            revision=served.revision,
        )

    def _read_current(
        self,
        module: str,
        statement: Statement,
        limit: int,
        consistency: Consistency,
        at_least: str | None,
        text: TextMatch | None,
    ) -> Rows | None:
        """A `latest` read the module's record store answers together with the person's catalog, in
        one operation, when it offers that (`query_current`) and this person was shown the module
        before. The backend presents what the person was shown and answers only when that is still
        the person's current view, so access is the backend's answer to this very call, never a
        cache; None sends the read the ordinary way (the catalogs, then the query)."""
        if consistency != "latest" or at_least is not None or text is not None:
            return None
        placement = self.h.placement_of(module)
        if placement is None or placement.record not in placement.readers:
            return None
        name = placement.record
        backend = self.h.backends.get(name)
        ask = getattr(backend, "query_current", None)
        shown = getattr(backend, "shown", None)
        if ask is None or shown is None:
            return None
        held = shown(self.principal)
        if held is None or module not in held:
            return None
        telemetry.annotate(module=module, backend=name)
        ans: Answer | None = ask(self.principal, module, statement, limit=limit, text=text)
        if ans is None:
            return None
        return Rows(
            columns=ans.columns,
            rows=ans.rows,
            truncated=ans.truncated,
            freshness=Freshness(name, ans.as_of, consistency),
            revision=held[module].revision,
        )

    def _await(self, backend: Backend, name: str, token: str) -> None:
        clock = self.h.clock
        deadline = clock() + self.h.wait_bound
        while not backend.reached(self.principal, token):
            left = deadline - clock()
            if left <= 0:
                raise NotYetCurrent(token, name)
            self.h.sleep(min(0.05, left))

    @telemetry.traced(
        "arras.search", None, lambda p: {"rows": len(p.hits), "truncated": p.truncated}
    )
    def search(
        self,
        module: str,
        text: str,
        types: Sequence[str] | None = None,
        limit: int = 20,
        consistency: Consistency = "latest",
        at_least: str | None = None,
        *,
        budget: Budget | None = None,
        revision: Revision | Mapping[str, Any] | None = None,
    ) -> SearchPage:
        """Search one module's types for `text` (CONTRACT-010): ranked hits of the types that can
        be searched, and each type that was not, with the reason. `budget` and `revision` are a
        request's own (the console's `_search`). The text is never recorded in telemetry."""
        self.require_user("search")
        return run_search(
            self,
            module,
            text,
            types,
            limit,
            consistency,
            at_least,
            budget=budget,
            revision=revision,
        )

    # -- actions
    def _action(
        self, name: str, expected_revision: Revision | Mapping[str, Any] | None = None
    ) -> tuple[ActionInfo, ModuleInfo, Provider]:
        self.require_user("action")
        module = name.partition(".")[0]
        try:
            mod, _ = self._module(module, "action")
        except Invalid:
            mod = None
        action = next((a for a in mod.actions if a.name == name), None) if mod else None
        if mod is None or action is None:
            raise Invalid([Violation("action", "unknown_action", f"no action {name!r}")])
        if expected_revision is not None:
            want = _revision(expected_revision)
            # every backend the caller names must be where it says; the rest are not checked
            if any(mod.revision[b] != v for b, v in want.by_backend.items()):
                # nothing is planned or applied under another revision
                raise Conflict("revision", f"{module} is at another revision than the caller's")
        return action, mod, self._provider(mod, mod.placement.provider_of(action.name), name)

    def _provider(self, mod: ModuleInfo, backend: str, what: str) -> Provider:
        """The backend named `backend`, which must apply actions."""
        b = self._backend(backend)
        if not b.describe().provides:
            raise Unsupported(what, [f"{backend} does not apply actions"])
        return cast(Provider, b)

    def _record_provider(self, mod: ModuleInfo, what: str) -> Provider:
        """The module's record store as a provider: imports, journal and document are its own."""
        return self._provider(mod, mod.placement.record, what)

    def _journal_provider(self, mod: ModuleInfo, provider: str | None, what: str) -> Provider:
        """The provider whose journal an audit read opens: the record store by default, else one
        that applies the module's actions. Another name is `Invalid`, whether or not it exists."""
        if provider is None:
            return self._record_provider(mod, what)
        if provider not in {
            mod.placement.record,
            *mod.placement.providers.values(),
        }:
            raise Invalid([Violation("provider", "unknown_type", "no such provider")])
        return self._provider(mod, provider, what)

    def _plan(self, action: ActionInfo, mod: ModuleInfo, inputs: Mapping[str, Any]) -> Plan:
        fn = self.h.handlers.get(action.name) if action.handler else None
        if action.handler and fn is None:
            raise Unsupported(f"action {action.name}", [f"handler {action.handler!r} is not bound"])
        ctx = Context(self)

        def run_handler(values: Mapping[str, Any]) -> Sequence[Effect]:
            if fn is None:
                raise Invalid([Violation("effects", "handler", "no handler")])
            return fn(values, ctx)

        return resolve(action, inputs, mod, handler=run_handler if fn is not None else None)

    @telemetry.traced("arras.validate", None, lambda v: {"valid": v.ok})
    @callscope.scoped
    def validate(
        self,
        action: str,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        expected_revision: Revision | Mapping[str, Any] | None = None,
    ) -> Validation:
        a, mod, auth = self._action(action, expected_revision)
        telemetry.annotate(action=a.name, module=mod.name)
        try:
            plan = self._plan(a, mod, inputs)
        except Invalid as e:
            return Validation(False, tuple(e.violations), (), (), None, None)
        v = auth.apply(self.principal, plan, idempotency_key=idempotency_key, dry_run=True)
        if not isinstance(v, Validation):
            raise TypeError("a provider answers a dry run with a Validation")
        return v

    @telemetry.traced("arras.invoke", None, lambda r: {"replayed": r.replayed})
    @callscope.scoped
    def invoke(
        self,
        action: str,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        expected_revision: Revision | Mapping[str, Any] | None = None,
    ) -> Receipt:
        a, mod, auth = self._action(action, expected_revision)
        telemetry.annotate(action=a.name, module=mod.name)
        plan = self._plan(a, mod, inputs)
        r = auth.apply(self.principal, plan, idempotency_key=idempotency_key)
        if not isinstance(r, Receipt):
            raise TypeError("a provider answers an invocation with a Receipt")
        return r

    @telemetry.traced(
        "arras.invoke_batch",
        _of_batch,
        lambda b: {"succeeded": b.succeeded, "failed": b.failed},
    )
    def invoke_batch(
        self,
        action: str,
        items: Sequence[Mapping[str, Any]],
        *,
        atomic: bool = False,
        stop_on_error: bool = False,
        idempotency_key: str | None = None,
        expected_revision: Revision | Mapping[str, Any] | None = None,
    ) -> BatchReceipt:
        a, mod, auth = self._action(action, expected_revision)
        telemetry.annotate(action=a.name, module=mod.name)
        if not 1 <= len(items) <= MAX_BATCH:
            raise Invalid([Violation("items", "bound", f"a batch holds 1 to {MAX_BATCH} items")])
        plans: list[Plan] = []
        bad: list[Violation] = []
        for i, item in enumerate(items):
            try:
                plans.append(self._plan(a, mod, item))
            except Invalid as e:
                bad += [Violation(f"items[{i}].{v.path}", v.code, v.message) for v in e.violations]
        if atomic and not bad and sum(len(p.effects) for p in plans) > MAX_ATOMIC_EFFECTS:
            bad.append(Violation("items", "bound", "an atomic batch holds at most 1,000 effects"))
        if bad:
            raise Invalid(bad)
        return auth.apply_batch(
            self.principal,
            plans,
            atomic=atomic,
            idempotency_key=idempotency_key,
            stop_on_error=stop_on_error,
        )

    @telemetry.traced("arras.import_records")
    def import_records(
        self,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
    ) -> ImportResult:
        self.require_admin("import_records")
        mod, _ = self._module(module, "import_records")
        telemetry.annotate(module=mod.name)
        auth = self._record_provider(mod, f"import into {module}")
        return auth.import_records(
            self.principal,
            module,
            records,
            load_id=load_id,
            initiated_by=self.principal.user,  # a load is its caller's own
        )

    @telemetry.traced("arras.export_records")
    def export_records(
        self, module: str, *, limit: int = 500, after: str | None = None
    ) -> RecordsPage:
        """The module's graph as records that `import_records` takes, a page at a time, read as
        this person from the module's record store: entities in type order then key, then the
        relationship instances between them. A person sees only what their own grants let them
        read, so a page that names `omitted` types is not the whole graph."""
        self.require_user("export_records")
        mod, _ = self._module(module, "export_records")
        telemetry.annotate(module=mod.name)  # resolved, not what the caller typed
        auth = self._record_provider(mod, f"export of {module}")
        telemetry.annotate(backend=mod.placement.record)
        return auth.export_records(self.principal, mod.name, limit=limit, after=after)

    # -- audit reads (CONTRACT-001): what the record store's own journal holds
    @telemetry.traced("arras.changes")
    def changes(
        self,
        module: str | None = None,
        *,
        type: str | None = None,  # noqa: A002
        key: str | None = None,
        by: str | None = None,
        action: str | None = None,
        group: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        after: str | None = None,
        provider: str | None = None,
    ) -> ChangesPage:
        """The committed changes that match, newest first. Needs `module`, or `type` with `key`,
        or `group`. A refused attempt and a dry run leave no record, so none is listed.
        `provider` names which of the module's providers' journal is read (default: the record
        store); it only means something within a module."""
        self.require_user("changes")
        module = module or (type.partition(".")[0] if type and key else None)
        if provider is not None and module is None:
            raise Invalid([Violation("provider", "scope", "a provider is read within a module")])
        if module is None and group is None:
            raise Invalid(
                [Violation("module", "scope", "name a module, a type with its key, or a group")]
            )
        if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
            raise Invalid(
                [Violation("limit", "bound", f"limit is an integer from 1 to {MAX_LIMIT}")]
            )
        for name, t in (("since", since), ("until", until)):
            if t is not None and t.tzinfo is None:
                raise Invalid([Violation(name, "type", "a time needs an offset (RFC 3339)")])
        asked: dict[str, Any] = dict(
            type=type, key=key, by=by, action=action, group=group, since=since, until=until
        )
        if module is not None:
            mod, _ = self._module(module, "changes")
            telemetry.annotate(module=mod.name)  # resolved, not what the caller typed
            auth = self._journal_provider(mod, provider, f"changes of {module}")
            return auth.changes(self.principal, module=module, limit=limit, after=after, **asked)
        last: ChangesPage | None = None
        refused: Refused | None = None
        unsupported = False
        for backend in self.h.backends.values():  # a group id may be on any provider
            if not backend.describe().provides:
                continue
            try:
                page = cast(Provider, backend).changes(
                    self.principal, module=None, limit=limit, after=after, **asked
                )
            except Unsupported:
                unsupported = True
                continue  # a provider that keeps no journal does not hide another's
            except Refused as e:
                refused = e
                continue
            if page.items:
                return page
            last = page
        if last is not None:  # no such change, or none this person may read: an empty page
            return last
        if refused is not None:
            raise refused
        if unsupported:  # every provider keeps no journal: not "no such change"
            raise Unsupported("changes", [])
        raise Invalid([Violation("group", "unknown_type", "no such change")])  # never echo it

    @telemetry.traced("arras.loads")
    def loads(
        self,
        module: str,
        *,
        limit: int = 50,
        after: str | None = None,
        provider: str | None = None,
    ) -> LoadsPage:
        """The import loads recorded for `module`, newest first, by the module's record store or
        by the named `provider`."""
        self.require_user("loads")
        if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
            raise Invalid(
                [Violation("limit", "bound", f"limit is an integer from 1 to {MAX_LIMIT}")]
            )
        mod, _ = self._module(module, "loads")
        telemetry.annotate(module=mod.name)
        auth = self._journal_provider(mod, provider, f"loads of {module}")
        return auth.loads(self.principal, module, limit=limit, after=after)

    # -- registry reads (CONTRACT-001): the declared document, as the record store holds it
    @telemetry.traced("arras.document")
    def document(self, module: str) -> RegisteredDocument:
        """The module's UMF document exactly as it was registered, read as this person: a module
        they cannot read is the same `Invalid` as one that does not exist, and a module whose
        record store is read-only (attached, never registered) holds no document: `Unsupported`."""
        self.require_user("document")
        mod, _ = self._module(module, "document")
        telemetry.annotate(module=mod.name)  # resolved, not what the caller typed
        auth = self._record_provider(mod, f"the document of {module}")
        telemetry.annotate(backend=mod.placement.record)
        return auth.document(self.principal, mod.name)

    def registry(self) -> Registry:
        return Registry(self)

    def schema(self) -> Schema:
        """Validate and register a UMF document as this person, under the record store's `schema`
        grant (CONTRACT-002, ADR-026)."""
        return Schema(self)


class Registry:
    """Administrative: register and attach modules, bind handlers (CONTRACT-002, 003)."""

    def __init__(self, ontology: Ontology) -> None:
        self.o = ontology

    def _checked(self, document: bytes | str) -> tuple[bytes, ModuleInfo]:
        self.o.require_admin("registry")
        readable = self.o._catalogs("registry").names()  # pyright: ignore[reportPrivateUsage]
        return check_document(self.o.h, document, readable)

    @telemetry.traced("arras.register", None, lambda r: {"module": r.module})
    def register(
        self, document: bytes | str, *, unknown_endpoint: str = "reject"
    ) -> RegistryResult:
        raw, mod = self._checked(document)
        auth = self.o.h.backends[mod.placement.record]
        if not auth.describe().provides:
            raise Invalid([Violation("placement", "read_only_module", "use attach")])
        gqlschema.build_module_schema(mod)  # a module must be servable
        result = cast(Provider, auth).register(
            self.o.principal, raw, mod, unknown_endpoint=unknown_endpoint
        )
        # A replica learns of the module through its feed; telling it now is a courtesy, and a
        # failure to do so is reported with the result, never instead of it.
        report = list(result.report)
        stored = replace(mod, revision=result.revision)
        for r in mod.placement.replicas:
            try:
                self.o.h.backends[r].attach(self.o.principal, stored)
            except ArrasError as e:
                report.append(f"replica {r} not attached: {type(e).__name__}")
        return replace(result, report=tuple(report))

    @telemetry.traced("arras.attach", None, lambda r: {"module": r.module})
    def attach(self, document: bytes | str) -> RegistryResult:
        _, mod = self._checked(document)
        gqlschema.build_module_schema(mod)  # servable, as at register
        if mod.actions:
            raise Invalid(
                [Violation("actions", "read_only_module", "a read-only module has no actions")]
            )
        auth = self.o.h.backends[mod.placement.record]
        if auth.describe().provides:
            raise Invalid([Violation("placement", "invalid_placement", "use register")])
        result = auth.attach(self.o.principal, mod)
        report = list(result.report)
        for r in mod.placement.replicas:
            try:
                self.o.h.backends[r].attach(self.o.principal, mod)
            except ArrasError as e:
                report.append(f"replica {r} not attached: {type(e).__name__}")
        return replace(result, report=tuple(report))

    def bind_handler(self, action: str, fn: Handler) -> None:
        self.o.require_admin("bind_handler")
        module = action.partition(".")[0]
        mod, _ = self.o._module(module, "bind_handler")  # pyright: ignore[reportPrivateUsage]
        found = next((a for a in mod.actions if a.name == action), None)
        if found is None or found.handler is None:
            raise Invalid(
                [
                    Violation(
                        "action", "unknown_action", f"{action!r} is not an action with a handler"
                    )
                ]
            )
        self.o.h.handlers[action] = fn
