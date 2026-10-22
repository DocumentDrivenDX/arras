# SPDX-License-Identifier: MIT OR Apache-2.0
"""The memory adapter: an in-memory authority and replica that pass the conformance corpus.

They are real backends of their own kind, not stand-ins for another, and let the interface, the
console and the MCP binding be built and tested without a database. `MemoryStore` is written from the contract (CONTRACT-003, 004), not from
what Arras assumes: access is decided by its own grants and tokens, an action applies as one
unit, a key is honored by replaying the original receipt, and an outage is never an empty answer.
`MemoryReplica` serves `bulk` reads from a copy fed from an authority, states the position it
reflects, and refuses changes.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, cast

from arras.actions import (
    KEY_VALUE,
    Create,
    Delete,
    Effect,
    Link,
    Plan,
    Precondition,
    Ref,
    Update,
)
from arras.errors import (
    Conflict,
    Failure,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.fakes_domain import domains, stored_props
from arras.fakes_eval import evaluate
from arras.fakes_export import ExportRecords
from arras.fakes_import import ImportRecords
from arras.fakes_journal import JournalReads, record_change
from arras.fakes_plan import Plan as ReadPlan
from arras.fakes_profile import require_supported_write_profile
from arras.fakes_registry import RegisterModules
from arras.fakes_search import searchable_properties, text_matches, with_search
from arras.fakes_state import Counts as _Counts
from arras.fakes_state import Entity as _Entity
from arras.fakes_state import State as _State
from arras.fakes_state import canonical as _canonical
from arras.fakes_state import deep_copy as _copy
from arras.fakes_state import utcnow as _now
from arras.fakes_weft import WEFT, check_profiles, resolve
from arras.model import (
    COLUMN_SCALARS,
    Capabilities,
    EntityTypeInfo,
    ModuleInfo,
    SearchMode,
)
from arras.results import (
    Answer,
    BackendInfo,
    BackendStatus,
    BatchReceipt,
    ImportResult,
    ItemResult,
    Load,
    Reason,
    Receipt,
    RefVersion,
    RegisteredDocument,
    RegistryResult,
    Rejection,
    Role,
    Validation,
    WeftSupport,
    document_format,
    document_text,
)
from arras.searchplan import TextMatch
from arras.types import Freshness, Position, Principal, Statement

MAX_BATCH = 100
Mode = Literal["read", "write", "journal", "schema"]
Clock = Callable[[], datetime]


class FakeAccess:
    """Who the backend knows by token, and what each person may do in each module."""

    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}
        self.grants: dict[str, set[tuple[str, Mode]]] = {}
        self.admins: set[str] = set()

    def grant(
        self,
        user: str,
        module: str,
        *modes: Mode,
        token: str | None = None,
        admin: bool = False,
    ) -> Principal:
        token = token or f"token-{user}"
        self.tokens[token] = user
        self.grants.setdefault(user, set()).update((module, m) for m in modes)
        if admin:
            self.admins.add(user)
        return Principal(user=user, token=token, admin=admin)

    def expire(self, token: str) -> None:
        self.tokens.pop(token, None)

    def authenticated(self, principal: Principal) -> bool:
        return bool(principal.token) and self.tokens.get(principal.token) == principal.user

    def allowed(self, principal: Principal, module: str, mode: Mode) -> bool:
        held = self.grants.get(principal.user, set())
        return (module, mode) in held or ("*", mode) in held  # "*": every module


def _capabilities(t: EntityTypeInfo, mod: ModuleInfo, *, mutable: bool) -> Capabilities:
    cols = tuple(
        p.name
        for p in t.properties
        if p.scalar and p.type in COLUMN_SCALARS and (p.required or p.name == t.key)
    )
    rels = tuple(
        n
        for r in mod.relationships
        for n, ends in ((r.name, r.source), (r.inverse, r.target))
        if n and t.name in ends
    )
    return Capabilities(
        read=True,
        columns=cols,
        relationships=rels,
        count=True,
        mutable=mutable,
        latency_class="interactive" if mutable else "batch",
        search="substring",
        searchable=searchable_properties(t),
    )


class _Store:
    """The data and the read side the two fakes share."""

    roles: tuple[Role, ...]

    def __init__(self, name: str, access: FakeAccess, clock: Clock) -> None:
        self.name = name
        self.access = access
        self.clock = clock
        self.state = _State(at=clock())
        self.modules: dict[str, ModuleInfo] = {}
        self.outage: Reason | None = None
        self.weft: WeftSupport | None = WEFT  # the subset it serves; narrow it to refuse more
        # a type declared otherwise for search: its mode, and the searchable properties it lists
        self.search_modes: dict[str, tuple[SearchMode, tuple[str, ...] | None]] = {}

    @property
    def available(self) -> bool:
        return self.outage is None

    @available.setter
    def available(self, up: bool) -> None:
        self.outage = None if up else "unreachable"

    def down(self, op: str) -> None:
        if self.outage is not None:
            raise Unavailable(self.name, self.outage, f"{self.name} cannot serve {op}")

    def gate(self, principal: Principal, module: str | None, mode: Mode | None, op: str) -> None:
        """Token first (a call without one is refused before it is made), then reachability,
        then the backend's own grants."""
        if not self.access.authenticated(principal):
            raise Refused(self.name, op, "token_expired")
        self.down(op)
        if (
            module is not None
            and mode is not None
            and not self.access.allowed(principal, module, mode)
        ):
            raise Refused(self.name, op)

    def position(self) -> Position:
        return Position(f"fake:{self.state.seq}", self.state.at)

    def module(self, name: str) -> ModuleInfo:
        mod = self.modules.get(name)
        if mod is None:
            raise Invalid(
                [Violation("module", "unknown_type", f"{self.name} holds no module {name!r}")]
            )
        return mod

    def type_of(self, qualified: str) -> EntityTypeInfo:
        mod = self.module(qualified.split(".", 1)[0])
        t = mod.entity_type(qualified.split(".", 1)[1])
        if t is None:
            raise Invalid([Violation("type", "unknown_type", f"no type {qualified}")])
        return t

    def caps(self, t: EntityTypeInfo) -> Capabilities:
        """What it describes for a type; descriptive except `search`, which it holds `text` to."""
        caps = _capabilities(
            t, self.module(t.name.split(".", 1)[0]), mutable="provider" in self.roles
        )
        declared = self.search_modes.get(t.name)
        if declared is None:
            return caps
        mode, searchable = declared
        caps = with_search(caps, t, mode)
        return replace(caps, searchable=searchable) if searchable is not None else caps

    def declare_search(
        self,
        type_name: str,
        mode: SearchMode | None,
        *,
        searchable: tuple[str, ...] | None = None,
    ) -> None:
        """Make `type_name` declare `mode` for search, listing `searchable` when given (`None`
        restores what the fake declares)."""
        t = self.type_of(type_name)
        self.search_modes.pop(t.name, None)
        if mode is not None:
            self.search_modes[t.name] = (mode, searchable)

    def catalog(self, principal: Principal) -> Mapping[str, ModuleInfo]:
        self.gate(principal, None, None, "catalog")
        return {n: m for n, m in self.modules.items() if self.access.allowed(principal, n, "read")}

    def describe_roles(self) -> tuple[Role, ...]:
        return self.roles

    def describe(self) -> BackendInfo:
        self.down("describe")
        caps = {t.name: self.caps(t) for m in self.modules.values() for t in m.entity_types}
        return BackendInfo(self.name, self.roles, caps, self.weft)

    def reached(self, principal: Principal, token: str) -> bool:
        self.gate(principal, None, None, "reached")
        if not self.access.grants.get(principal.user):
            raise Refused(self.name, "reached")  # authenticated, but a member of nothing here
        prefix, _, n = token.partition(":")
        if not prefix or not n.isdigit():
            # not a position token at all: not "not yet reached", which would invite a wait
            raise Invalid([Violation("token", "malformed", "not a position token")])
        if prefix != "fake":
            return False  # another provider's position, which this fake cannot place
        if not getattr(self, "fed", True):
            return False  # nothing issued by the authority has been seen yet
        return self._reached(int(n))

    def _reached(self, seq: int) -> bool:
        return self.state.seq >= seq

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        return self._serve(self._statement(principal, module, statement, text), limit=limit)

    def _statement(
        self, principal: Principal, module: str, statement: Statement, text: TextMatch | None
    ) -> ReadPlan:
        """Token, reachability, then the named module, which must be one the principal may read
        (else `unknown_type`, so its existence is not revealed), then the statement over it, then
        the declared profiles: `unknown_type` comes before anything that depends on a type."""
        self.gate(principal, None, None, "query")
        held = self.modules.get(module)
        if held is None or not self.access.allowed(principal, module, "read"):
            raise Invalid([Violation("module", "unknown_type", f"no module {module!r}")])
        plan = resolve(statement, held, self._document(module))
        check_profiles(plan, self.weft)
        if text is not None:
            self._check_text(plan, text)
            plan = replace(plan, text=text)
        return plan

    def _document(self, module: str) -> bytes | None:
        """The module's registered document, whose numeric domains a statement is held to."""
        return None

    def _check_text(self, plan: ReadPlan, text: TextMatch) -> None:
        """A text match needs the type to declare `substring` and each property to be searchable."""
        caps = self.caps(self.type_of(plan.type))
        supported = [
            f"search: {caps.search}",
            f"searchable: {', '.join(caps.searchable) or 'none'}",
        ]
        if caps.search != "substring":
            raise Unsupported(f"text search of {plan.type}", supported)
        for p in text.properties:
            if p not in caps.searchable:
                raise Unsupported(f"text search on {p}", supported)

    def _serve(self, plan: ReadPlan, *, limit: int) -> Answer:
        """The statement evaluated over the rows (`fakes_eval`): its own LIMIT, then Arras's
        `limit` cap, with `truncated` saying the cap cut the result."""
        cols, rows, truncated = evaluate(
            plan, self.state, limit=limit, text_matches=lambda p, t: text_matches(p, cast(Any, t))
        )
        return Answer(columns=cols, rows=rows, truncated=truncated, as_of=self.position())


def _unsupported(op: str, kind: str) -> Unsupported:
    return Unsupported(op, [f"a {kind} does not support {op}"])


class MemoryStore(_Store, JournalReads, ImportRecords, ExportRecords, RegisterModules):
    """The authoritative backend: applies actions atomically, imports records, takes catalogs."""

    roles: tuple[Role, ...] = ("reader", "provider")

    def __init__(self, access: FakeAccess, name: str = "memory", clock: Clock = _now) -> None:
        super().__init__(name, access, clock)
        self.catalog_revision = 0
        self.documents: dict[str, bytes] = {}  # each module's document as registered, verbatim
        self.origin_actor: dict[str, str] = {}  # who registered its current revision
        self._journal: dict[tuple[str, str], tuple[str, Any]] = {}

    def status(self) -> BackendStatus:
        if self.outage is not None:
            return BackendStatus(False, self.outage, f"{self.name} is unavailable")
        return BackendStatus(True, position=self.position())

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        raise _unsupported("attach", "provider")  # a provider takes `register`

    # -- compat.RecordStats
    def count(self, type_name: str) -> int:
        return sum(1 for r in self.state.entities if r.type == type_name)

    def missing(self, type_name: str, prop: str) -> list[str]:
        return sorted(
            r.key
            for r, e in self.state.entities.items()
            if r.type == type_name and prop not in e.props
        )

    # -- registry: `register` and `validate_register` are in `RegisterModules`
    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        self.gate(principal, module, "read", "document")
        mod = self.module(module)
        raw = self.documents.get(module)
        if raw is None:
            raise Invalid([Violation("module", "unknown_type", f"{self.name} holds no document")])
        return RegisteredDocument(module, mod.revision, document_text(raw), document_format(raw))

    # -- actions
    def apply(
        self,
        principal: Principal,
        plan: Plan,
        *,
        idempotency_key: str | None,
        dry_run: bool = False,
    ) -> Receipt | Validation:
        return self._apply_scoped(principal, plan, idempotency_key, dry_run, None)

    def _apply_scoped(
        self,
        principal: Principal,
        plan: Plan,
        idempotency_key: str | None,
        dry_run: bool,
        scope: str | None,
    ) -> Receipt | Validation:
        """The journal's action part is the scope: a batch item's is not a single apply's."""
        module = plan.action.split(".", 1)[0]
        self.gate(principal, module, "write", "apply")
        mod = self.module(module)
        require_supported_write_profile(self.documents.get(module), module)
        if dry_run:
            return self._validate(principal, plan, mod, idempotency_key)
        journal_action = scope or plan.action
        replay = self._held(journal_action, idempotency_key, self._digest([plan]))
        if replay is not None:
            return replace(replay, replayed=True)
        work = copy.deepcopy(self.state)
        receipt = self._apply_group(work, principal, [plan], mod)[0]
        self._commit(work, journal_action, idempotency_key, self._digest([plan]), receipt)
        return receipt

    @staticmethod
    def _digest(plans: Sequence[Plan]) -> str:
        """Identifies the inputs; falls back to the plan itself for a plan built by hand."""
        parts = [p.inputs_digest or repr((p.action, p.preconditions, p.effects)) for p in plans]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def _replay(self, plan: Plan, key: str | None) -> Receipt | None:
        return self._held(plan.action, key, self._digest([plan]))

    def _held(self, action: str, key: str | None, digest: str) -> Any:
        if key is None:
            return None
        held = self._journal.get((action, key))
        if held is None:
            return None
        if held[0] != digest:
            raise Conflict("idempotency_key_reused", f"{key!r} was used with other inputs")
        return held[1]

    def _commit(self, work: _State, action: str, key: str | None, digest: str, result: Any) -> None:
        self.state = work
        if key is not None:
            self._journal[(action, key)] = (digest, result)

    def _validate(
        self, principal: Principal, plan: Plan, mod: ModuleInfo, key: str | None
    ) -> Validation:
        failures: list[Failure] = []
        violations: tuple[Violation, ...] = ()
        replay: Receipt | None = None
        try:
            replay = self._replay(plan, key)
        except Conflict as e:
            failures.append(Failure(f"conflict:{e.reason}", e.detail))
        if replay is None and not failures:
            work = copy.deepcopy(self.state)
            failures = self._failures(work, plan, mod)
            if not failures:
                try:
                    self._effects(work, principal, plan.effects, mod, self.clock(), _Counts(), {})
                except PreconditionFailed as e:
                    failures = list(e.failures)
                except Conflict as e:
                    failures = [Failure(f"conflict:{e.reason}", e.detail)]
                except Invalid as e:
                    violations = tuple(e.violations)
        return Validation(
            ok=not failures and not violations,
            violations=violations,
            failures=tuple(failures),
            effects=plan.effects,
            replay=replay,
            freshness=Freshness(self.name, self.position(), "latest"),
        )

    def _failures(self, st: _State, plan: Plan, mod: ModuleInfo) -> list[Failure]:
        return [Failure(p.id, p.reason) for p in plan.preconditions if not self._holds(st, mod, p)]

    def _holds(self, st: _State, mod: ModuleInfo, p: Precondition) -> bool:
        a = p.args
        if p.op == "exists":
            return a["ref"] in st.entities
        if p.op == "absent":
            return Ref(a["type"], str(a["key"])) not in st.entities
        if p.op == "property_equals":
            e = st.entities.get(a["ref"])
            return e is not None and e.props.get(a["property"]) == a["value"]
        others = self._instances(st, mod, str(a["relationship"]), a["source"])
        if p.op == "no_relationship":
            target = a.get("target")
            return not any(target is None or o == target for o in others)
        n, m = len(others), a["n"]
        return {
            "=": n == m,
            "!=": n != m,
            "<": n < m,
            "<=": n <= m,
            ">": n > m,
            ">=": n >= m,
        }[a["cmp"]]

    @staticmethod
    def _instances(st: _State, mod: ModuleInfo, name: str, source: Ref) -> list[Ref]:
        found = _canonical(mod, name)
        if found is None:
            return []
        rel, inverse = found
        if inverse:
            return [t[1] for t in st.relations if t[0] == rel.name and t[2] == source]
        return [t[2] for t in st.relations if t[0] == rel.name and t[1] == source]

    def _apply_group(
        self, work: _State, principal: Principal, plans: Sequence[Plan], mod: ModuleInfo
    ) -> list[Receipt]:
        """Apply `plans` to `work` as one group: one position, one time, one token."""
        now = self.clock()
        out: list[tuple[Plan, _Counts, dict[Ref, int]]] = []
        for i, plan in enumerate(plans):
            counts, touched = _Counts(), dict[Ref, int]()
            try:
                failures = self._failures(work, plan, mod)
                if failures:
                    raise PreconditionFailed(failures)
                self._effects(work, principal, plan.effects, mod, now, counts, touched)
            except (PreconditionFailed, Conflict, Invalid) as e:
                e.add_note(f"item {i}")  # the group changed nothing
                raise
            out.append((plan, counts, touched))
        work.seq += 1
        work.at = now
        token = f"fake:{work.seq}"
        record_change(
            work,
            group=f"g-{work.seq}",
            now=now,
            by=principal.user,
            backend=self.name,
            entries=[(plan, touched) for plan, _, touched in out],
        )
        return [
            Receipt(
                plan.action,
                tuple(RefVersion(r.type, r.key, v) for r, v in touched.items()),
                c.created,
                c.updated,
                c.deleted,
                c.linked,
                c.unlinked,
                token,
                group=f"g-{work.seq}",
            )
            for plan, c, touched in out
        ]

    def _effects(
        self,
        work: _State,
        principal: Principal,
        effects: Sequence[Effect],
        mod: ModuleInfo,
        now: datetime,
        counts: _Counts,
        touched: dict[Ref, int],
    ) -> None:
        for e in effects:
            if isinstance(e, Create):
                t = self._checked_create(e, mod)
                if e.ref in work.entities:
                    raise Conflict("exists", str(e.ref))
                if e.ref in work.tombstones:
                    raise Conflict("deleted", str(e.ref))
                props = {**_copy(self._stored(mod, t.local_name, e.properties)), t.key: e.ref.key}
                work.entities[e.ref] = _Entity(props, 1, principal.user, now, principal.user, now)
                counts.created += 1
                touched[e.ref] = 1
            elif isinstance(e, Update):
                ent = self._need(work, e.ref)
                self._checked_update(e, mod)
                fresh = e.ref not in touched
                ent.props.update(_copy(self._stored(mod, e.ref.type.split(".", 1)[1], e.set)))
                for u in e.unset:
                    ent.props.pop(u, None)
                if fresh:
                    ent.version += 1
                ent.updated_by, ent.updated_at = principal.user, now
                counts.updated += 1
                touched[e.ref] = ent.version
            elif isinstance(e, Delete):
                ent = self._need(work, e.ref)
                del work.entities[e.ref]
                work.tombstones.add(e.ref)
                work.relations = {t for t in work.relations if e.ref not in (t[1], t[2])}
                counts.deleted += 1
                touched[e.ref] = ent.version + 1
            else:
                self._checked_link(e.relationship, e.source, e.target, mod)
                self._need(work, e.source)
                self._need(work, e.target)
                triple = (e.relationship, e.source, e.target)
                if isinstance(e, Link):
                    if triple in work.relations:
                        raise Conflict("duplicate_relationship", str(triple))
                    work.relations.add(triple)
                    counts.linked += 1
                else:
                    if triple not in work.relations:
                        raise PreconditionFailed(
                            [Failure("_unlink", f"no such relationship {triple}")]
                        )
                    work.relations.discard(triple)
                    counts.unlinked += 1

    def _stored(self, mod: ModuleInfo, record: str, props: Mapping[str, Any]) -> dict[str, Any]:
        """The values as the record's fields hold them: a decimal at its declared scale; a number
        outside its field's numeric domain is `Invalid`, as a column would refuse it."""
        try:
            return stored_props(domains(self.documents.get(mod.name)), mod.name, record, props)
        except ValueError as e:
            name, why = e.args
            raise Invalid([Violation(f"effects.{name}", "numeric_domain", why)]) from None

    def _document(self, module: str) -> bytes | None:
        return self.documents.get(module)

    # effects are checked against the module's types, as the authority does once per group
    def _checked_create(self, e: Create, mod: ModuleInfo) -> EntityTypeInfo:
        t = (
            mod.entity_type(e.ref.type.split(".", 1)[1])
            if e.ref.type.startswith(mod.name + ".")
            else None
        )
        if t is None:
            raise Invalid([Violation("effects", "unknown_type", f"no type {e.ref.type}")])
        out: list[Violation] = []
        if not KEY_VALUE.fullmatch(e.ref.key):
            out.append(Violation("effects.key", "key", "not a key"))
        declared = {p.name for p in t.properties}
        for k in set(e.properties) - declared:
            out.append(Violation(f"effects.{k}", "unknown_field", f"{t.local_name} has no {k}"))
        for p in t.properties:
            if p.required and p.name != t.key and p.name not in e.properties:
                out.append(Violation(f"effects.{p.name}", "required", "a value is required"))
        if t.key in e.properties:
            out.append(Violation(f"effects.{t.key}", "key", "the key is not a property"))
        if out:
            raise Invalid(out)
        return t

    def _checked_update(self, e: Update, mod: ModuleInfo) -> None:
        t = self.type_of(e.ref.type)
        out: list[Violation] = []
        for k in {*e.set, *e.unset}:
            p = t.property(k)
            if p is None:
                out.append(Violation(f"effects.{k}", "unknown_field", f"{t.local_name} has no {k}"))
            elif k == t.key:
                out.append(Violation(f"effects.{k}", "key", "a key cannot change"))
            elif k in e.unset and p.required:
                out.append(
                    Violation(f"effects.{k}", "required", "a required value cannot be unset")
                )
        if out:
            raise Invalid(out)

    @staticmethod
    def _checked_link(name: str, src: Ref, tgt: Ref, mod: ModuleInfo) -> None:
        found = _canonical(mod, name)
        if found is None or found[1]:
            raise Invalid([Violation("effects", "unknown_type", f"{name} is not a relationship")])
        rel = found[0]
        if src.type not in rel.source or tgt.type not in rel.target:
            raise Invalid(
                [Violation("effects", "unknown_type", f"{src.type} -> {tgt.type} is not {name}")]
            )

    @staticmethod
    def _need(work: _State, ref: Ref) -> _Entity:
        e = work.entities.get(ref)
        if e is None:
            raise PreconditionFailed([Failure("_ref", f"{ref.type} {ref.key} does not exist")])
        return e

    def apply_batch(
        self,
        principal: Principal,
        plans: Sequence[Plan],
        *,
        atomic: bool,
        idempotency_key: str | None,
        stop_on_error: bool = False,
    ) -> BatchReceipt:
        if not 1 <= len(plans) <= MAX_BATCH:
            raise Invalid([Violation("items", "bound", f"a batch holds 1 to {MAX_BATCH} items")])
        action = plans[0].action
        if any(p.action != action for p in plans):
            raise Invalid([Violation("items", "mixed_actions", "a batch is one action")])
        module = action.split(".", 1)[0]
        self.gate(principal, module, "write", "apply_batch")
        mod = self.module(module)
        require_supported_write_profile(self.documents.get(module), module)
        if atomic:
            digest = self._digest(plans)
            held = self._held(f"{action}#atomic", idempotency_key, digest)
            if held is not None:
                return replace(
                    held,
                    items=tuple(
                        replace(i, receipt=replace(i.receipt, replayed=True)) for i in held.items
                    ),
                )
            work = copy.deepcopy(self.state)
            receipts = self._apply_group(work, principal, plans, mod)
            batch = BatchReceipt(
                action,
                True,
                tuple(ItemResult(i, r) for i, r in enumerate(receipts)),
                len(receipts),
                0,
                receipts[-1].token,
            )
            self._commit(work, f"{action}#atomic", idempotency_key, digest, batch)
            return batch
        items: list[ItemResult] = []
        for i, p in enumerate(plans):
            try:
                r = self._apply_scoped(principal, p, idempotency_key, False, f"{action}#{i}")
                assert isinstance(r, Receipt)
                items.append(ItemResult(i, r))
            except (PreconditionFailed, Conflict, Invalid) as e:
                items.append(ItemResult(i, refusal=e))
                if stop_on_error:
                    break
        ok = [it.receipt for it in items if it.receipt is not None]
        return BatchReceipt(
            action, False, tuple(items), len(ok), len(items) - len(ok), ok[-1].token if ok else None
        )

    # -- import
    def import_records(
        self,
        principal: Principal,
        module: str,
        records: Sequence[Mapping[str, object]],
        *,
        load_id: str,
        initiated_by: str,
    ) -> ImportResult:
        self.gate(principal, module, "write", "import_records")
        if principal.user not in self.access.admins:
            raise Refused(self.name, "import_records")
        if initiated_by != principal.user:
            raise Invalid([Violation("initiated_by", "attribution", "a load is the caller's own")])
        mod = self.module(module)
        require_supported_write_profile(self.documents.get(module), module)
        work = copy.deepcopy(self.state)
        now = self.clock()
        created = skipped = 0
        rejected: list[Rejection] = []
        found = domains(self.documents.get(mod.name))
        for r in (r for r in records if "type" in r):
            c, s, rej = self._import_entity(work, mod, r, load_id, initiated_by, now, found)
            created, skipped = created + c, skipped + s
            rejected += rej
        for r in (r for r in records if "type" not in r):
            c, s, rej = self._import_relation(work, mod, r)
            created, skipped = created + c, skipped + s
            rejected += rej
        work.loads.append(Load(load_id, initiated_by, now, module, created, skipped, len(rejected)))
        if created:
            work.seq += 1
            work.at = now
        self.state = work
        return ImportResult(created, skipped, tuple(rejected))


class MemoryReplica(_Store):
    """A replica: serves `bulk` reads from a copy fed from an authority, and refuses changes."""

    roles: tuple[Role, ...] = ("reader",)

    def __init__(
        self,
        source: MemoryStore,
        access: FakeAccess,
        name: str = "memory_replica",
        clock: Clock = _now,
    ) -> None:
        super().__init__(name, access, clock)
        self.source = source
        self.fed = False  # until its first feed it holds no position the authority issued
        self.state = _State(at=clock())

    def query(
        self,
        principal: Principal,
        module: str,
        statement: Statement,
        *,
        limit: int,
        text: TextMatch | None = None,
    ) -> Answer:
        rq = self._statement(principal, module, statement, text)
        if not self.fed:  # a replica states the position it reflects; before a feed it has none
            raise Unavailable(self.name, "unreachable", "no position yet: never fed")
        return self._serve(rq, limit=limit)

    def _document(self, module: str) -> bytes | None:
        return self.source.documents.get(module)  # the document the feed's types come from

    def feed(self) -> None:
        """Bring the copy up to the authority's current position."""
        self.state = copy.deepcopy(self.source.state)
        self.modules.update(self.source.modules)  # a registration reaches it through the feed
        self.fed = True

    def attach(self, principal: Principal, module: ModuleInfo) -> RegistryResult:
        self.gate(principal, module.name, "read", "attach")
        if principal.user not in self.access.admins:
            raise Refused(self.name, "attach")
        self.modules[module.name] = module
        return RegistryResult(module.name, module.revision, True)

    def status(self) -> BackendStatus:
        if self.outage is not None:
            return BackendStatus(False, self.outage, f"{self.name} is unavailable")
        if not self.fed:
            return BackendStatus(True, detail="no position yet: never fed")
        behind = self.state.seq < self.source.state.seq
        lag = (self.clock() - self.state.at).total_seconds() if behind else 0.0
        return BackendStatus(True, position=self.position(), lag=lag)

    # a replica changes only through its feed
    def apply(self, *_: object, **__: object) -> Any:
        raise _unsupported("apply", "replica")

    def apply_batch(self, *_: object, **__: object) -> Any:
        raise _unsupported("apply_batch", "replica")

    def import_records(self, *_: object, **__: object) -> Any:
        raise _unsupported("import_records", "replica")

    def export_records(self, *_: object, **__: object) -> Any:
        raise _unsupported("export_records", "replica")

    def register(self, *_: object, **__: object) -> Any:
        raise _unsupported("register", "replica")

    def validate_register(self, *_: object, **__: object) -> Any:
        raise _unsupported("validate_register", "replica")

    def document(self, *_: object, **__: object) -> Any:
        raise _unsupported("document", "replica")  # the registered document is the authority's
