# SPDX-License-Identifier: MIT OR Apache-2.0
"""The registry operations of the Truss adapter (CONTRACT-002, CONTRACT-004): `catalog`, `document`,
`register` and `validate_register`, over Truss's reader catalog, accepted document and acceptance.

What Truss gives and what this module makes of it:

- A module's document is registered under its UMF root `id`; Truss reads it back verbatim. The module's
  revision is `source_catalog_revision`, the catalog revision at which the document's current bytes were
  accepted: stable while other documents register. The catalog head moves on any registration and is
  never a module's revision.
- Registering is the registrar's act, checked first and cheaply (a person who is no registrar is
  refused before any preparation, whatever the document holds, even an unchanged one: Truss's advisory
  registrar status says it, and acceptance reauthorizes). Equality with the held document is
  JSON-structural, like every backend: a rewritten but equal document registers nothing, because Truss
  would count it a new revision. When the caller named an expected revision it is compared with the held
  one before the accepting call, and the accepting call carries it as Truss's document-scoped
  expectation (the source revision the document was read at, zero for a document not yet held):
  a registration of that document that landed in between is Truss's typed conflict, a `Conflict`, never
  a lost update, and a registration of another document does not disturb it.
- The request key names the head the plan was read at, so registering earlier bytes again after a
  change in between is a new request (Truss replays a repeated key and applies nothing), and a retry
  after an unknown commit repeats the key and gets the replay.
- Reading a catalog is one read-only call: no lock on the catalog head is taken. The person's last
  snapshot is kept with its validator and the next read asks Truss whether it changed; Truss re-answers
  the person's access either way, so a revoked role is refused on its very next call.

Truss is reached through the `Call`'s assembly and its results are recognized by class name, so the
base install imports none of it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from arras import callscope
from arras.adapters.truss.cache import CatalogCache
from arras.adapters.truss.connection import Call, CommitUnknown, Connections, failure_error
from arras.errors import (
    ArrasError,
    Conflict,
    Invalid,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.model import UNPLACED, ModuleInfo
from arras.results import (
    RegisteredDocument,
    RegistrationCheck,
    RegistryResult,
    document_format,
    document_text,
)
from arras.types import Principal, Revision
from arras.umf import parse_module

ORIGIN = b'{"x-action":"register"}'  # Truss asserts the origin as a JSON object
READER_BYTES = 16 * 1024 * 1024  # Truss's default of 1 MiB would cut a large catalog short
_CODE_BYTES = 4096  # a Truss document id


def kind_of(value: Any) -> str:
    return type(value).__name__


def _unsupported(what: str) -> Unsupported:
    return Unsupported(what, ["a document Truss can accept"])


def mapped(backend: str, operation: str, failure: Any) -> ArrasError:
    """A Truss failure by its `catalog_code`; anything else as `failure_error` has it."""
    code = getattr(failure, "catalog_code", None)
    if code == "request_conflict":
        return Conflict("idempotency_key_reused", "Truss holds that request key for other input")
    if code == "unsupported_profile":
        return _unsupported("this change to a registered document")
    if code == "invalid_input":
        return Invalid([Violation("document", "invalid", "Truss refused the document")])
    if code == "observation":
        return Unavailable(backend, "busy", "the catalog is being changed")
    if code == "resource":
        return Unavailable(backend, "resource", "a Truss resource limit")
    if code == "installation":
        return Unavailable(backend, "not_configured", "Truss is not installed here")
    return failure_error(backend, operation, failure)


def accepting(backend: str, operation: str, failure: Any) -> ArrasError:
    """`mapped`, and the opaque `invalid_transaction` Truss gives every `ValueError` while it
    accepts as a document it does not take (a field with no `name`, a decimal other than 18,4)."""
    if getattr(failure, "code", None) == "invalid_transaction" and (
        getattr(failure, "catalog_code", None) is None
    ):
        return _unsupported("this document")
    return mapped(backend, operation, failure)


def _head_unavailable(backend: str, code: str) -> Unavailable:
    reason = {"profile": "unsupported_version", "installation": "not_configured"}.get(code)
    if reason is not None:
        return Unavailable(backend, reason, f"the catalog read is unavailable ({code})")
    return Unavailable(backend, "busy" if code == "observation" else "unreachable", code)


@dataclass(frozen=True)
class Held:
    """What the person can read of the module's registered document."""

    document_id: str
    content: bytes
    source: int
    info: ModuleInfo


@dataclass(frozen=True)
class _Plan:
    """A registration read and prepared, ready to accept."""

    head: int
    key: str
    prepared: Any
    held: Held | None
    document_id: str


class Registry:
    def __init__(self, backend: str, connections: Connections, cache: CatalogCache) -> None:
        self.name = backend
        self.connections = connections
        self.cache = cache

    # -- reads

    def reader_catalog(self, call: Call) -> Any | None:
        """The person's reader catalog, or None for a person who may read none of it (Truss refuses
        them as a value, not an error). Truss is asked whether the catalog changed since the one this
        person last read, with that read's validator; the answer is the person's access at this call,
        so an unchanged catalog is served from the snapshot and a refusal drops it."""
        who = call.principal.user
        held = self.cache.snapshot(who, call.read_only)
        out = call.unwrap(
            call.assembly.reader_catalog_if_changed_in_transaction(
                call.tx,
                validator=None if held is None else held[1],
                maximum_bytes=READER_BYTES,
            ),
            mapped,
        )
        kind = kind_of(out)
        if kind == "ReaderCatalogUnchanged" and held is not None:
            return held[0]
        if kind == "ReaderCatalogSnapshot":
            self.cache.keep_snapshot(who, call.read_only, out.catalog, out.validator)
            return out.catalog
        self.cache.drop_snapshot(who)
        if kind == "CatalogRefused":
            return None
        if kind == "CatalogUnavailable":
            raise _head_unavailable(self.name, out.code)
        if kind == "CatalogInvalid":
            raise Unavailable(self.name, "unreachable", "Truss refused the catalog read bounds")
        raise Unavailable(self.name, "unreachable", f"truss {kind}")

    def _scope_key(self) -> tuple[str, int]:
        return ("truss.reader_catalog", id(self))

    def call_catalog(self, call: Call) -> Any | None:
        """The reader catalog for a call that follows the operation's own catalog read: the one that
        read kept for this person in this operation's scope, else a read in `call`. The scope holds it
        until the operation returns and never serves another person or another operation, and the
        call's own statements still run as the person, so Truss refuses one whose access was revoked
        in between."""
        kept = callscope.kept(self._scope_key())
        if kept is not None and kept[0] == _who(call.principal):
            return kept[1]
        return self.reader_catalog(call)

    def scoped_modules(self) -> dict[str, ModuleInfo] | None:
        """The modules of the catalog this operation has read, for `describe`, or None."""
        kept = callscope.kept(self._scope_key())
        return None if kept is None else kept[2]

    def module_info(self, call: Call, head: int, entry: Any) -> ModuleInfo | None:
        """The parsed module of a reader-catalog entry, from the cache or the accepted document;
        None for one the person cannot read whole or this library cannot parse."""
        key = (
            entry["documentId"],
            entry["documentSha256"],
            entry.get("sourceCatalogRevision", head),
        )
        if (info := self.cache.get(key)) is not None:
            return info
        held = self._accepted(call, entry["documentId"])
        if held is None:
            return None
        self.cache.put(key, held.info)
        return held.info

    def _accepted(self, call: Call, document_id: str) -> Held | None:
        out = call.unwrap(
            call.assembly.accepted_document_in_transaction(call.tx, document_id=document_id),
            mapped,
        )
        kind = kind_of(out)
        if kind == "CatalogUnavailable":
            raise _head_unavailable(self.name, out.code)
        if kind != "AcceptedDocument":
            return None  # refused, or not a reading this module takes
        try:
            parsed = parse_module(out.content)
        except ArrasError:
            return None  # another tool's document: skipped, not fatal for the rest of the catalog
        info = replace(
            parsed,
            placement=UNPLACED,
            revision=Revision({self.name: out.source_catalog_revision}),
        )
        return Held(document_id, out.content, out.source_catalog_revision, info)

    def held_module(self, call: Call, module: str) -> Held | None:
        """What the person may read of `module`'s registered document, in this call: the document id,
        its accepted bytes (Truss binds a write to them) and the parsed module; None when the person
        may read no such module (Truss does not say which)."""
        catalog = self.call_catalog(call)
        if catalog is None:
            return None
        entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
        if entry is None:
            return None
        return self._accepted(call, entry["documentId"])

    def nothing_registered(self, principal: Principal, operation: str) -> bool:
        """Whether the install holds no catalog yet. Truss's reader catalog answers head 0 as a
        profile mismatch, the same code a release mismatch gives, so a read that failed that way asks
        the person's runtime status, which states `empty`: any enrolled person may ask it, and anyone
        else, or any failure, leaves the original failure standing."""
        try:
            with self.connections.read(principal, operation) as call:
                return self._empty(call)
        except ArrasError:
            return False

    def _empty(self, call: Call) -> bool:
        status = call.unwrap(call.assembly.person_runtime_status_in_transaction(call.tx), mapped)
        return (
            kind_of(status) == "PersonRuntimeStatus"
            and status.installation == "compatible"
            and status.catalog == "empty"
        )

    def catalog(self, principal: Principal) -> dict[str, ModuleInfo]:
        try:
            return self._catalog(principal)
        except Unavailable as exc:
            if exc.reason == "unsupported_version" and self.nothing_registered(
                principal, "catalog"
            ):
                return {}
            raise

    def _catalog(self, principal: Principal) -> dict[str, ModuleInfo]:
        with self.connections.read(principal, "catalog") as call:
            catalog = self.reader_catalog(call)
            if catalog is None:
                return {}
            modules: dict[str, ModuleInfo] = {}
            for entry in catalog.modules:
                info = self.module_info(call, catalog.catalog_revision, entry)
                if info is not None and info.name not in modules:
                    modules[info.name] = info
            callscope.keep(self._scope_key(), (_who(call.principal), catalog, modules))
            held = self.cache.snapshot(call.principal.user, True)
            if held is not None:
                self.cache.keep_shown(call.principal.user, held[1], modules)
            return modules

    def document(self, principal: Principal, module: str) -> RegisteredDocument:
        try:
            return self._document(principal, module)
        except Unavailable as exc:
            if exc.reason == "unsupported_version" and self.nothing_registered(
                principal, "document"
            ):
                raise Refused(self.name, "document", "no_access") from None
            raise

    def _document(self, principal: Principal, module: str) -> RegisteredDocument:
        with self.connections.read(principal, "document") as call:
            catalog = self.reader_catalog(call)
            entry = None
            if catalog is not None:
                entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
            held = self._accepted(call, entry["documentId"]) if entry is not None else None
            if held is None:
                # Truss cannot tell an unknown module from one the person may not read, and
                # does not reveal which
                raise Refused(self.name, "document", "no_access")
            self.cache.remember(held.info)
            return RegisteredDocument(
                module,
                held.info.revision,
                document_text(held.content),
                document_format(held.content),
            )

    # -- registering

    def _read(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        unknown_endpoint: str,
        expected: Revision | None,
        operation: str,
    ) -> _Plan | Held:
        """One read-only call: the grant, the document's id, the held document, the revision
        compare and, for a document that differs, Truss's preparation of it. Returns
        the held document when the registration would change nothing, else the plan to accept."""
        with self.connections.read(principal, operation) as call:
            # advisory (acceptance reauthorizes), and cheap: a person who is no registrar is refused
            # before any preparation, an absent install is `not_configured`
            self.require_registrar(call, operation)
            if module.metadata_profile != "legacy-arras/1":
                raise _unsupported("metadata profile")
            if unknown_endpoint not in ("reject", "provisional"):
                raise Invalid([Violation("unknown_endpoint", "value", "reject or provisional")])
            if unknown_endpoint == "provisional":
                raise Unsupported("unknown_endpoint provisional", ["reject"])
            root = _document_id(document)
            catalog, head = self._planning_catalog(call)
            held = self._held(call, catalog, module.name, root)
            if expected is not None:
                if held is None:
                    if (
                        catalog is None or not catalog.modules
                    ) and head > 0:  # a registrar who may read nothing cannot compare
                        raise Refused(self.name, operation, "no_access")
                    raise Conflict("revision", f"{module.name} is at another revision")
                if held.info.revision != expected:
                    raise Conflict("revision", f"{module.name} is at another revision")
            if held is not None and json.loads(held.content) == json.loads(document):
                return held
            sha = hashlib.sha256(document).hexdigest()
            prepared = self._prepare(call, root, sha, document)
            return _Plan(head, f"register:{head}:{sha}", prepared, held, root)

    def require_registrar(self, call: Call, operation: str) -> None:
        out = call.unwrap(call.assembly.registrar_status_in_transaction(call.tx), mapped)
        kind = kind_of(out)
        if kind == "CatalogRefused" or (kind == "RegistrarStatus" and not out.can_register):
            raise Refused(self.name, operation, "no_access")
        if kind == "CatalogUnavailable":
            raise _head_unavailable(self.name, out.code)
        if kind != "RegistrarStatus":
            raise Unavailable(self.name, "unreachable", f"truss {kind}")

    def _planning_catalog(self, call: Call) -> tuple[Any | None, int]:
        """The reader catalog the plan is read at and the head: a registrar who reads nothing is
        given the head with no modules, and an install with nothing registered (head 0) answers the
        conditional read as a profile mismatch, which the person's runtime status settles as empty."""
        try:
            catalog = self.reader_catalog(call)
        except Unavailable as exc:
            if exc.reason == "unsupported_version" and self._empty(call):
                return None, 0
            raise
        if catalog is None:  # a registrar's own status states the head
            status = call.unwrap(call.assembly.status_in_transaction(call.tx), mapped)
            return None, int(getattr(status, "revision", 0) or 0)
        return catalog, int(catalog.catalog_revision)

    def _held(self, call: Call, catalog: Any | None, module: str, root: str) -> Held | None:
        if catalog is None:
            return None
        entry = next((e for e in catalog.modules if e["moduleId"] == module), None)
        if entry is None:
            return None
        if entry["documentId"] != root:
            raise Invalid(
                [
                    Violation(
                        "id", "document_id", "the module is registered under another document id"
                    )
                ]
            )
        return self._accepted(call, root)

    def _prepare(self, call: Call, root: str, sha: str, document: bytes) -> Any:
        from truss import CatalogDocument

        try:
            prepared = call.assembly.prepare_catalog((CatalogDocument(root, sha, document),))
        except ValueError as exc:
            if kind_of(exc) != "PreparationRejected":
                raise
            reason = getattr(exc, "reason", "")
            if reason in ("invalid_input", "invalid_document"):
                raise Invalid(
                    _diagnosed(getattr(exc, "diagnostics", ()))
                    or [Violation("document", reason, "Truss refused the document as written")]
                ) from None
            if reason in ("runtime_unavailable", "producer_unavailable"):
                raise Unavailable(
                    self.name, "not_configured", "Truss's catalog producer is not available"
                ) from None
            raise _unsupported("this document") from None
        return prepared

    def _accept(
        self, principal: Principal, plan: _Plan, *, dry: bool, operation: str, race: bool
    ) -> tuple[Any, int | None]:
        """The accepting call: Truss's result as a value, committed (or rolled back for a dry
        run), and, for a committed `CatalogUnchanged`, the source revision of the accepted document
        read in the same call (Truss answers it only for bytes a stored request already holds, so
        when a document was held and differed, another registration of these bytes landed first and
        the held revision is stale). A refusal for incompatibility comes back as a value for the
        caller to report. `race` (the caller named an expected revision) sends Truss the document's
        expectation: its source revision when it was read (0, absent, when it was not held), so a
        registration of that document that landed since is Truss's `CatalogCASConflict`, a
        `Conflict`; Truss's retry codes are the execution errors they have always been."""
        from truss import CatalogDocumentExpectation

        expected = (
            (CatalogDocumentExpectation(plan.document_id, plan.held.source if plan.held else 0),)
            if race
            else ()
        )
        with self.connections.write(principal, operation) as call:
            call.rollback = dry
            out = call.unwrap(
                call.assembly.accept_in_transaction(
                    call.tx,
                    plan.prepared,
                    request_key=plan.key,
                    origin_bytes=ORIGIN,
                    expected_documents=expected,
                ),
                accepting,
            )
            if kind_of(out) == "CatalogCASConflict":
                raise Conflict("revision", "another registration landed first")
            if race and kind_of(out) == "CatalogUnchanged":
                raise Conflict("revision", "another registration landed first")
            source = None
            if kind_of(out) == "CatalogUnchanged" and not dry:
                accepted = self._accepted(call, plan.document_id)
                source = accepted.source if accepted is not None else None
            return out, source

    def _accept_committed(
        self, principal: Principal, plan: _Plan, op: str, race: bool
    ) -> tuple[Any, int | None]:
        try:
            return self._accept(principal, plan, dry=False, operation=op, race=race)
        except CommitUnknown:
            # the commit's outcome is not known: repeat the same request once; Truss replays it
            # when it was applied, and applies it when it was not
            return self._accept(principal, plan, dry=False, operation=op, race=race)

    def register(
        self,
        principal: Principal,
        document: bytes,
        module: ModuleInfo,
        *,
        unknown_endpoint: str,
        expected_revision: Revision | None = None,
    ) -> RegistryResult:
        plan = self._read(
            principal, document, module, unknown_endpoint, expected_revision, "register"
        )
        if isinstance(plan, Held):
            return RegistryResult(module.name, plan.info.revision, False)
        out, source = self._accept_committed(
            principal, plan, "register", expected_revision is not None
        )
        kind = kind_of(out)
        if kind == "CatalogAcceptanceRefused":
            raise Invalid(_violations(out))
        if kind == "CatalogUnchanged":
            # `out.revision` is the revision of a matching earlier registration request,
            # ambiguous when the same bytes were registered more than once; never used
            revision = Revision({self.name: source})
            if source is None:  # the accepted document could not be read: nothing to remember
                return RegistryResult(module.name, revision, False)
            self.cache.remember(replace(module, placement=UNPLACED, revision=revision))
            return RegistryResult(module.name, revision, False)
        revision = Revision({self.name: out.revision})
        self.cache.remember(replace(module, placement=UNPLACED, revision=revision))
        return RegistryResult(module.name, revision, True, ("accepted",))

    def validate_register(
        self, principal: Principal, document: bytes, module: ModuleInfo, *, unknown_endpoint: str
    ) -> RegistrationCheck:
        plan = self._read(principal, document, module, unknown_endpoint, None, "validate_register")
        if isinstance(plan, Held):
            return RegistrationCheck(plan.info.revision, False, current=plan.info)
        held = plan.held
        held_revision = held.info.revision if held is not None else None
        current = held.info if held is not None else None
        out, _ = self._accept(principal, plan, dry=True, operation="validate_register", race=False)
        if kind_of(out) == "CatalogAcceptanceRefused":
            return RegistrationCheck(held_revision, True, tuple(_violations(out)), current=current)
        return RegistrationCheck(
            held_revision, kind_of(out) != "CatalogUnchanged", report=("accepted",), current=current
        )


def _who(principal: Principal) -> tuple[str, str]:
    return (principal.user, principal.token)


def _diagnosed(diagnostics: Any) -> list[Violation]:
    """One violation for each diagnostic Truss's preparation gives, in its order. Truss requires an
    authored, nonempty `name` on every Record and Field (UMF itself does not) and gives all of the
    elements that lack one (`TRUSS-NAME-MISSING`): each is listed by its module and element id,
    so the author can fix them in one pass. Nothing is filled in here."""
    found: list[Violation] = []
    for raw in diagnostics:
        try:
            item = json.loads(raw)
            code = str(item["code"])
            where = f"{item['moduleId']}.{item['elementId']}" if "elementId" in item else None
        except (ValueError, KeyError, TypeError):
            continue
        if code == "TRUSS-NAME-MISSING" and where is not None:
            found.append(
                Violation(
                    f"elements.{where}.name",
                    "name_missing",
                    f"the {item.get('kind', 'element')} {where} needs an authored, nonempty name",
                )
            )
        else:
            found.append(Violation("document", code.lower(), "Truss refused the document"))
    return found


def _violations(refused: Any) -> list[Violation]:
    return [
        Violation(
            f"types.{v.record_id}.{v.field_id}",
            "incompatible_change",
            f"{v.rule}: {v.affected_object_count} objects",
        )
        for v in refused.violations
    ]


def _document_id(document: bytes) -> str:
    """The UMF document's own top-level `id`, which Truss requires as the document id."""
    try:
        root = json.loads(document).get("id")
    except (ValueError, AttributeError):
        raise _unsupported("a document that is not a JSON object") from None
    if not isinstance(root, str) or not 1 <= len(root.encode()) <= _CODE_BYTES:
        raise Invalid([Violation("id", "required", "a document registered on Truss names its id")])
    return root
