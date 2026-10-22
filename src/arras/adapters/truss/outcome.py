# SPDX-License-Identifier: MIT OR Apache-2.0
"""What a Truss group answered, as Arras says it (CONTRACT-003, CONTRACT-004, plan TR-07).

Truss's results are recognized by class name, so the base install imports none of it. A group fails
in typed carriers (`PreconditionFailed`, `GroupOperationFailure`, `InvalidGroupInput`,
`RequestConflict`, `UnauthorizedPerson`, `GroupUnavailable`); a failed operation carries only its
index and an artifact whose JSON holds the stable `code`, so this module decodes that JSON.

Failure map, in the order Truss and Arras both check:

| Truss | Arras |
| --- | --- |
| `UnauthorizedPerson`, raw 42501 | `Refused(no_access)` |
| `PreconditionFailed` | `PreconditionFailed` with the caller's ids, plus those decided in the planner |
| `not_found` at an update, delete or link | `PreconditionFailed([_ref])` naming the ref the operation used |
| `not_found` at an unlink | `PreconditionFailed([_unlink])` |
| `key_conflict` at a create | `Conflict(exists)`, or `Conflict(deleted)` when no object holds the key now |
| `key_conflict` at a link | `Conflict(duplicate_relationship)` |
| `expected_version` | `Conflict(version)` (the adapter sends no version) |
| `dependencies` at a `delete_object` | `Unavailable(busy)`: the object gained an edge after its edges were read |
| `dependencies` at any other operation | `Invalid(multiplicity)` at the effect: a relationship's minimum or maximum is not met |
| `invalid_input` | `Invalid` at the effect |
| `RequestConflict` | `Conflict(idempotency_key_reused)` |
| `GroupUnavailable` | `profile`: `Unsupported`; `resource`: `Unavailable(resource)`; `observation`: `Unavailable(busy)` |
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from arras.actions import Plan, Ref
from arras.adapters.truss.connection import failure_error
from arras.adapters.truss.plan import Built, Op
from arras.adapters.truss.registry import kind_of
from arras.errors import (
    ArrasError,
    Conflict,
    Failure,
    Invalid,
    PreconditionFailed,
    Refused,
    Unavailable,
    Unsupported,
    Violation,
)
from arras.results import Receipt, RefVersion


class Retry(ArrasError):
    """Truss asked for the whole transaction to be run again (a serialization failure or a deadlock).
    Never leaves the adapter: `apply` runs the call again, a bounded number of times."""


def mapper(backend: str, operation: str, failure: Any) -> ArrasError:
    """`failure_error`, except that a retry the transaction must be restarted for is `Retry`."""
    if getattr(failure, "code", None) == "retry":
        return Retry("retry")
    return failure_error(backend, operation, failure)


def artifact(carrier: Any) -> dict[str, Any]:
    """The JSON object inside a Truss artifact (`inner_error`, `diagnostic`); {} when unreadable."""
    try:
        value: Any = json.loads(base64.b64decode(carrier.bytes_base64))
    except (ValueError, AttributeError, TypeError):
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _no_ref(ref: Ref) -> Failure:
    return Failure("_ref", f"{ref.type} {ref.key} does not exist")


def unavailable_group(backend: str, reason: str) -> ArrasError:
    if reason == "profile":
        return Unsupported(
            "a value or operation Truss 0.0.45 groups do not take",
            ["scalar values, rootless objects and edges"],
        )
    if reason == "resource":
        return Unavailable(backend, "resource", "a Truss group bound")
    if reason == "observation":
        return Unavailable(backend, "busy", "another write holds what this one needs")
    return Unavailable(backend, "unreachable", f"truss group {reason}")


def _where(op: Op | None, built: Built) -> str:
    """The path of the effect an operation came from; `effects` when it came from none."""
    if op is None or not op.effects:
        return "effects"
    where = f"effects[{op.effects[0]}]"
    return f"items[{op.item}].{where}" if built.batch else where


def _noted(err: ArrasError, op: Op, built: Built) -> ArrasError:
    """`err`, with the batch item the failed operation came from."""
    if built.batch:
        err.add_note(f"item {op.item}")
    return err


def _conflicting_create(op: Op, built: Built, exists_now: Callable[[Ref], bool]) -> Op:
    """The create that a `key_conflict` is about. Truss 0.0.45 inserts a run of independent creates as
    one set-based statement and reports the run's first operation whichever create collided, so the
    run is read again: the first create whose key an earlier create of the group made or an object
    holds now. When none does (a deleted key's tombstone), the operation Truss named stands."""
    if op.kind != "create_object":
        return op
    start = built.ops.index(op)
    made: set[tuple[Ref, ...]] = {o.refs for o in built.ops[:start] if o.kind == "create_object"}
    for later in built.ops[start:]:
        if later.kind != "create_object":
            break
        if later.refs in made or exists_now(later.refs[0]):
            return later
        made.add(later.refs)
    return op


def attributed(failure: Any, built: Built, code: object) -> Op | None:
    """The operation a failure is about. Truss 0.0.45 names none (`operation_index` is absent) for
    a failure found when the group finishes: a `not_found` is then the first operation that names
    what is not there (a ghost the adapter found missing, or a ref an earlier delete of the group removed), and a multiplicity `dependencies`
    the group's last operation, where Truss reported it before."""
    try:
        return built.ops[int(failure.operation_index)]
    except (ValueError, IndexError):
        return None
    except TypeError:  # `Absent`
        pass
    if code == "not_found":
        deleted: set[Ref] = set()
        for o in built.ops:  # in the plan's order, the first operation that names what is not there
            if o.missing or o.ghost or (o.kind != "delete_edge" and deleted & set(o.refs)):
                return o
            if o.kind == "delete_object":
                deleted.update(o.refs)
        # none: an edge a delete cascaded to changed in between
        return next((o for o in built.ops if o.kind == "delete_edge" and o.cascade), None)
    if code == "dependencies" and built.ops:
        return built.ops[-1]
    return None


def operation_failure(
    backend: str, failure: Any, built: Built, exists_now: Callable[[Ref], bool]
) -> ArrasError:
    """The error for a failed operation of the group (`GroupOperationFailure`)."""
    code = artifact(failure.inner_error).get("code")
    op = attributed(failure, built, code)
    if code == "expected_version":
        return Conflict("version", "the object changed since it was read")
    if code == "dependencies":
        # P1005 is the delete-with-edges check at the delete's step (a race: the object gained an
        # edge after its edges were read) and the multiplicity check (minimum and maximum) that
        # `object_group_finish` runs inside the apply, reported at the group's LAST operation. So the
        # operation's kind tells them apart; a group that ends in a delete whose cascaded edge
        # removals break a multiplicity is told busy (the ambiguity is recorded, R18.16).
        if op is not None and op.kind == "delete_object":
            return Unavailable(
                backend, "busy", "the object gained a relationship while it was deleted"
            )
        return Invalid(
            [
                Violation(
                    _where(op, built), "multiplicity", "the relationship's multiplicity is not met"
                )
            ]
        )
    if code == "invalid_input":
        return Invalid([Violation(_where(op, built), "invalid", "Truss refused the effect")])
    if op is None:
        return Unavailable(backend, "unreachable", f"truss {code or 'group failure'}")
    if code == "not_found":
        if op.kind == "delete_edge":
            if not op.cascade:
                return PreconditionFailed(
                    [Failure("_unlink", f"no such relationship {(op.relationship, *op.refs)}")]
                )
            return Unavailable(backend, "busy", "an edge changed while its object was deleted")
        ref = (op.missing or op.refs)[0]
        return PreconditionFailed([_no_ref(ref)])
    if code == "key_conflict":
        if op.kind == "create_edge":
            return _noted(
                Conflict("duplicate_relationship", str((op.relationship, *op.refs))), op, built
            )
        op = _conflicting_create(op, built, exists_now)
        ref = op.refs[0]
        earlier = built.ops[: built.ops.index(op)]
        if any(o.kind == "create_object" and o.refs == op.refs for o in earlier):
            return _noted(Conflict("exists", str(ref)), op, built)  # an earlier item made it
        return _noted(Conflict("exists" if exists_now(ref) else "deleted", str(ref)), op, built)
    return Unavailable(backend, "unreachable", f"truss {code or 'group failure'}")


def invalid_input(backend: str, failure: Any) -> ArrasError:
    code = artifact(failure.diagnostic).get("code")
    if code in ("original_documents", "catalog"):
        return Unavailable(backend, "busy", "the accepted catalog changed during the write")
    if code in ("shape", "transport"):
        return Unavailable(backend, "unreachable", f"truss {code}")
    return Invalid([Violation("effects", "invalid", "Truss refused the group as input")])


def merge_failures(
    sent: Sequence[Any],
    static: Sequence[tuple[int, Failure]],
    order: dict[str, int],
    *,
    names: Mapping[str, str] | None = None,
    owner: Sequence[int] | None = None,
) -> list[Failure]:
    """Truss's failed conditions and those the planner decided, in the plan's order. For a batch
    `names` gives the caller's id of each id sent and `owner` the item of each condition: only the
    first failing item's failures are told, as the memory adapter stops at it."""
    names = names or {}
    rows: list[tuple[int, Failure]] = []
    for f in sent:
        cid: str = f.condition_id
        rows.append((order.get(cid, len(order)), Failure(names.get(cid, cid), f.reason)))
    rows.extend(static)
    rows.sort(key=lambda row: row[0])
    if owner and rows and rows[0][0] < len(owner):
        first = owner[rows[0][0]]
        rows = [r for r in rows if r[0] < len(owner) and owner[r[0]] == first]
    return [f for _, f in rows]


# -- success


def _version(result: Any) -> int:
    value = getattr(result, "version", None)
    if value is None:
        value = result.deletion_version
    return int(value)


def group_of(semantic: Any, request: str) -> str:
    """The group a change committed in: Truss names none, so it is the journal's (source epoch,
    transaction id) of the group's first event, which a replay returns unchanged; a group that
    changed nothing has no event and is named by its request."""
    for result in semantic.results:
        for event in getattr(result, "events", ()):
            return f"{event.source_epoch}:{event.xid}"
    return "request:" + hashlib.sha256(request.encode()).hexdigest()[:24]


def receipt(
    plan: Plan,
    built: Built,
    semantic: Any,
    token: str,
    *,
    replayed: bool,
    request: str,
) -> Receipt:
    """The receipt of a group: counts per effect, a ref once at its last version in first-touch
    order. A merged update counts once per effect; an update Truss found to change nothing does not
    count (its ref is listed at the version it holds)."""
    results = semantic.results
    index = {id(op): i for i, op in enumerate(built.ops)}
    created = updated = deleted = linked = unlinked = 0
    for i, effect in enumerate(plan.effects):
        kind = type(effect).__name__
        if kind == "Create":
            created += 1
        elif kind == "Update":
            if kind_of(results[index[id(built.effect_op[i])]]) != "Unchanged":
                updated += 1
        elif kind == "Delete":
            deleted += 1
        elif kind == "Link":
            linked += 1
        else:
            unlinked += 1
    refs = tuple(
        RefVersion(ref.type, ref.key, _version(results[index[id(op)]]))
        for ref, op in built.touched.items()
    )
    return Receipt(
        plan.action,
        refs,
        created,
        updated,
        deleted,
        linked,
        unlinked,
        token,
        replayed=replayed,
        group=group_of(semantic, request),
    )


def refused(backend: str) -> Refused:
    return Refused(backend, "apply", "no_access")
