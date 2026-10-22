---
ddx:
  id: truss-group-mapping
  type: design-note
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-21
  authoring:
    home: repo
  links:
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: truss-requirements
      kind: informed_by
    - id: truss-catalog-mapping
      kind: informed_by
---

# Mapping an action's plan onto Truss's group API

How the Truss adapter's `apply` and `apply_batch` (CONTRACT-004) is built on `truss-toolkit` 0.0.45's group API (`apply_in_transaction` on the assembly, `truss.groups`, `truss.contracts`), as built and run against Truss on PostgreSQL 18.6. The adapter is `arras.adapters.truss` (`apply.py`, `plan.py`, `outcome.py`, `values.py`, `wire.py`); it is a `Provider`, so there is no `groups(selection)` indirection: the assembly of the person's call is asked directly. `import_records` is `load.py` on Truss's batched import route (calls of 128 records, as CONTRACT-004 states; R19 lists what it found) and the audit reads (`audit.py`) are Truss's mutation-group and load audit pages (`describe().audit` is true; R20). [truss-catalog-mapping.md](truss-catalog-mapping.md) covers the registry; what Truss should change is in [truss-requirements.md](truss-requirements.md) (R13, R18).

## The call

One read-write call per attempt, as the person, on the person's own connection (the connection layer, ADR-017):

```text
catalog   = assembly.reader_catalog_in_transaction(tx)                    # the person's modules; none: Refused
document  = assembly.accepted_document_in_transaction(tx, document_id)    # the exact accepted bytes
prepared  = assembly.prepare_group_in_transaction(tx, records=, relationships=)   # the group context and the definition pins the plan names, in one call
context   = prepared.context                                              # (group_context_in_transaction and the reference calls when it refuses)
lookups   = lookup_key_in_transaction / page_edges_in_transaction         # what exists
input     = context.input(operations, asserted_origin, preconditions)
request   = context.request(request_id)
result    = assembly.apply_in_transaction(tx, input, request, documents=(CatalogDocument(...),))
```

The module and its types are read in the call and never from the catalog cache, which grants nothing. The group context and the type and relationship references the plan names (the records of its effects, links and conditions, found before the planner runs) come from one `prepare_group_in_transaction`, whose references seed the planner's lookups so it asks Truss for none of them again; when Truss answers it with anything but a prepared group (a refusal), the planner asks for each as it always did and the refusal is told by the calls it replaces. Truss binds a write to the accepted document's exact bytes, so the call passes them; a registration that lands between the read and the apply is `invalid_input` and reported as `Unavailable(busy)`. The transaction is `READ COMMITTED` read-write. A person must be a current member of the writer role; a reader is answered `UnauthorizedPerson` before any other check, and a person who is a member of no module gets a raw `42501` from the first call and `CatalogRefused` from the catalog, both `Refused`.

A failure is raised inside the call, so the call rolls back and a failed group leaves no row, no journal row and no request record; a failed keyed request leaves the key usable. A first apply returns `AppliedPending`, which carries the receipt token.

## Plan to operations

A `Plan` has preconditions and ordered effects with concrete keys and values (CONTRACT-003). The planner (`plan.py`) reads what exists through the call's lookups and builds Truss's types through `wire.py` (the only place that names them).

| Arras | Truss |
|---------|-------|
| `Create(ref, properties)` | `CreateObject(pin, values, RootlessOwnership(), alias)` with the key property added to the values (a plan's properties exclude it); an alias for later effects |
| `Update(ref, set, unset)` | `UpdateObject(target, set, unset)`; `expected_version` is never sent (below); updates of one ref are merged into one operation, or into the create's values when the plan created the ref |
| `Delete(ref)` | the `delete_edge` operations the object needs, then `Delete('delete_object')` (below) |
| `Link(rel, source, target)` | `CreateEdge(pin, source, target, alias)`; the relationship id is the document's `id` for the relationship's `name` |
| `Unlink(...)` | `Delete('delete_edge')` of the edge found by paging the source's outgoing edges, or of the alias of an edge the plan made |
| values | `TextValue('string'\|'integer'\|'decimal'\|'timestamp'\|'binary')` and `BooleanValue`; a sequence, a structure or ownership is `Unsupported` |

Targets are `StoredObjectReference(identity)` for an existing object (the identity of the key lookup), `AliasObjectReference` for one the plan made, and a **ghost identity** (id `9223372036854775807`, a valid id no object holds) for a ref no object holds. A ghost makes Truss report a missing target in its own order (authority, then conditions, then effects) as `not_found` at that operation or as a failed condition, where an id Truss refuses (`0`, `-1`, a leading zero) fails the whole group as invalid input.

**Canonical spelling.** Truss stores and compares a number or a timestamp by the spelling of its token, so the adapter writes one spelling: a decimal quantized to the field's declared scale (`1.5` at scale 4 is `1.5000`, read from the registered document's facets), an integer in plain digits, a timestamp in UTC with microseconds and `Z`, binary as padded base64. A number outside its field's domain is `Invalid` (`effects.<name>`, `numeric_domain`) before Truss is asked.

**Validation Truss does not do.** Truss accepts an unknown property name, an update of the key property and any key; the adapter checks the effects with `check_effects` (the same check handler effects get) before any lookup, so `Invalid` carries paths. A leftover `invalid_input` is `Invalid` at the effect.

**Version.** Truss bumps a version once per update operation; Arras bumps once per touched ref per plan. Merging makes them agree. An update that changes nothing is `Unchanged` in Truss and keeps its version: it is not counted in `updated` and its ref is listed at the version it holds.

**Delete.** Truss refuses to delete an object that has an edge in either direction. The adapter pages the object's edges for every relationship its type takes part in (both directions), deletes each in the same group before the object, and deletes the edges the plan itself made. These operations are counted nowhere (no `unlinked`) and count against the group's 1,024 operations.

**Bounds.** A group holds 1 to 1,024 operations and at most 3,072 preconditions (1,025 operations are `resource`; Truss 0.0.45 takes 3,072 conditions for a group of 1,024 operations, and the input-byte, scope and deadline bounds still apply: a group is never silently split); a plan of more than 1,024 effects, a delete whose cascade passes the bound, a plan with no effects and a count compared with `!=` are `Unsupported` before the group is presented. Arras allows 1,000 effects.

**Cost.** Truss derives a key in PostgreSQL, so no create, update, `KeyAbsent` or key lookup runs a client key encoder, and the adapter passes no executable path to `apply_in_transaction` or `lookup_key_in_transaction`. On an idle macOS arm64 machine a create is about 0.15 s, a key lookup about 0.05 s and a create with a link about 0.18 s; on a machine under load (load average 11 to 16) the same calls took about 0.24 s (0.14 s of it Truss's group call), 0.055 s and 0.39 s. A group of 1,024 creates commits in 0.84 s and an update through the adapter is 32 statements in two transactions and 0.10 s (`truss-statement-overhead-spec.md`). Lookups are deduplicated, which saves a round trip, and a key lookup also locks the row until the transaction ends.

## Preconditions

All five kinds exist in Truss 0.0.45 and are evaluated against locked prestate; every failed condition is returned in the order given, with the caller's own id and reason, and a failed condition outranks a failing operation (truss-requirements R18.18), so the adapter reads no state of its own to rank them and maps `PreconditionFailed` as Truss gives it.

| Arras | Truss |
|---------|-------|
| `exists(ref)` | `ObjectExists(id, reason, target)`, a ghost target when no object holds the key |
| `absent(type, key)` | `KeyAbsent`, always sent whatever the lookups found (below) |
| `property_equals` | `PropertyEquals`, the value in the field's canonical spelling; a missing object or an absent property fails |
| `no_relationship(rel, source, target)` | `RelationshipAbsent`, the endpoints swapped when the relationship is named by its inverse |
| `no_relationship(rel, source)` | `RelationshipCount(maximum=0)` from the anchor, direction by whether the name is the inverse |
| `count(rel, source, cmp, n)` | `RelationshipCount` with one inclusive range: `=` is (n, n), `>` (n+1, none), `>=` (n, none), `<` (0, n-1), `<=` (0, n); `!=` is `Unsupported`, and `<` with n of 0 is false |

Truss answers a missing endpoint as a failed `RelationshipAbsent` or `RelationshipCount`, where an object that does not exist has no relationships; the planner decides those conditions itself (no object, or a type the relationship does not join: the count is 0) and merges its failures with Truss's in the plan's order. A condition the planner decided still fails the plan when Truss applies the group, and the failure comes back before any effect failure.

`KeyAbsent` also fails for a key a deleted object held, where an `absent` precondition holds for it and the create that follows is `Conflict(deleted)`. A failed `key_absent` is followed by a lookup in the same transaction (a failed group leaves the transaction usable): a key no object holds now is a retired key, the condition is left out and the group is presented again, once. A keyed retry presents the full input first and Truss answers it as a conflicting request (its probe runs before the conditions); the applier then looks the `absent` keys up again and presents the group once more with exactly those conditions left out, which is the input the first call committed, so it replays. A plan with `absent` conditions on both a never-existing key and a retired key cannot be rebuilt this way (both look alike: no object holds either) and is `Conflict(idempotency_key_reused)`.

## Request identity, replay and the receipt token

- **Request id.** The idempotency key scoped by the action (`catalog.AddUseCase:k1`), at most 1,024 bytes; one past it is shortened by a digest, never truncated. A keyless invocation gets a fresh id. A request is also scoped to the person: the same key from another person applies afresh (R18.3).
- **Generated keys** are derived from the request id and the effect's place (a UUID v5) and replace the resolver's random ones in every effect and condition, so a retry under the same key rebuilds identical input. Truss's fingerprint covers the whole input.
- **`expected_version` is never sent.** No plan carries a version, the lookup locks the row until the transaction ends (a concurrent writer is answered `observation`, not waited for), and a version taken at lookup changes the input a keyed retry rebuilds, which Truss answers `RequestConflict`. A stale `expected_version` is still mapped to `Conflict(version)` should Truss ever raise one.
- **The retry is rebuilt from what exists.** `KeyAbsent` is sent whatever the lookups found, so a retry of a create rebuilds the same input and Truss replays it. A keyed retry is answered from the receipt only when the rebuilt input is byte-identical, and the adapter keeps no input across invocations, so any retry whose rebuilt input names an object or edge that no longer resolves as the original named it is `Conflict(idempotency_key_reused)` (R18.3): an `Unlink` of an edge that existed (the original named the stored edge, the retry a ghost edge), a `Delete` (its target and its cascaded edges), any effect or condition whose target anyone has deleted since, and the mixed `absent` case above.
- **The token.** `AppliedPending` carries the receipt token, equal to the one the committed replay returns (verified), so a write is one call and one commit; the adapter returns that token once its commit has returned. The write stands whatever follows. An answer without a token (not seen on 0.0.45) is read by presenting the same input and request, the same objects, in a second read-write call that is rolled back and answered with `CommittedReceiptReplay(receipt_token)`.
- **A caller's retry** is answered `CommittedReceiptReplay` on its first call (the replay probe runs before the document and the conditions are checked): `Receipt(replayed=True)` with the original token and group.
- **An unknown commit.** `CommitUnknown` repeats the same request once on a new connection: `CommittedReceiptReplay` means the commit landed (reported `replayed=False`, this invocation did it); `AppliedPending` means it did not, and that call commits (a second unknown outcome is `Unavailable`, `outcome unknown`) and then reads the token. For a keyless invocation this is the only recovery.
- **`Receipt.group`** is the journal's (source epoch, transaction id) of the group's first event, which a replay returns unchanged; a group that changed nothing has no event and is named by a digest of its request. Two groups applied in one transaction share a transaction id; the adapter applies one group per transaction (R18.6).

## Results

`GroupSemanticResult.results` has one result per operation, in order. `created`, `updated`, `deleted`, `linked` and `unlinked` count the plan's effects (a merged update counts once per effect; an `Unchanged` update counts nowhere). `refs` has one entry per touched ref in first-touch order at its last version (`Created`, `Changed`, `Unchanged` version, or a `Deleted` `deletion_version`).

## Failure map

| Truss | Arras |
|-------|---------|
| `UnauthorizedPerson`, raw `42501` | `Refused(no_access)` |
| `PreconditionFailed` | `PreconditionFailed` with the caller's ids, plus those the planner decided, in the plan's order |
| `not_found` at an update, a delete or a link | `PreconditionFailed([_ref])`, `<type> <key> does not exist`, naming the ref the operation used; with no operation named by Truss (0.0.45 finds a missing target when the group finishes) the first operation that names a ghost, or a ref an earlier delete of the group removed |
| `not_found` at an unlink | `PreconditionFailed([_unlink])` |
| `key_conflict` at a create | `Conflict(exists)`, or `Conflict(deleted)` when no object holds the key now (a follow-up lookup) |
| `key_conflict` at a link | `Conflict(duplicate_relationship)` |
| `expected_version` | `Conflict(version)` |
| `dependencies` at a `delete_object` | `Unavailable(busy)`: the object gained an edge after its edges were read |
| `dependencies` at any other operation, or an index that names none | `Invalid(multiplicity)` at the effect: a relationship's minimum or maximum is not met (R18.16); Truss 0.0.45 names no operation for a failure it finds when the group finishes, and the adapter attributes the multiplicity failure to the group's last operation, as Truss reported it before |
| `invalid_input` | `Invalid` at the effect; `original_documents` is `Unavailable(busy)` |
| `RequestConflict` | `Conflict(idempotency_key_reused)` |
| `GroupUnavailable` `profile` / `resource` / `observation` / `receipt` | `Unsupported` / `Unavailable(resource)` / `Unavailable(busy)` / `Unavailable` |
| `Error` `retry` (`whole_transaction`) | the whole call is run again on a new connection, three times, then `Unavailable(busy)` |
| `Error` other (`cancelled`, `execution_obligation`, `transaction_unusable`) | `Unavailable`; a quarantined connection is closed by the connection layer |

Every failure is raised inside the call, so it rolls back. The failure artifact carries the code only as JSON (R18.1); the adapter decodes that JSON, never prose.

## Batches

`apply_batch` checks its shape before any connection (1 to 100 items, one action; `Invalid` `items` `bound` or `mixed_actions`), then the token (`Refused`), then every item's bounds (`Unsupported`), so no item is applied before another is found unsupported.

An atomic batch is one group: the items' operations in item order under one request id (`module.Action:key`, or a fresh UUID), one commit and the one receipt token `apply` takes. Each item has its own `Receipt` (its counts, its refs and versions), all with the group's token and group. The group is named from the first event of the whole group's result, never one item's slice: an item whose operations changed nothing has no event. What differs from one plan:

- One alias counter for the group; one `created` and one `removed` knowledge across items, so a later item may update, link, unlink or delete what an earlier one created. Updates merge into an operation only within an item, so two items updating one object are two operations and give versions v+1 and v+2, as on the memory adapter.
- Truss takes a condition id once in a group, so a batch's conditions are sent as `<item>:<id>` and told back under the caller's own id; only the first failing item's failures are told, as the memory adapter stops at it. An item's generated keys are derived from the request id and the item as well as the effect index.
- At most 1,024 operations and 3,072 preconditions in all (`Unsupported` before any call, as the splitting of an atomic batch into groups would break atomicity). The operation timeout is at most 60 s, so a batch that runs past it is answered `cancelled` and is `Unavailable` (nothing written).
- A failure names its item: `Invalid` paths read `items[i].effects[j]`, and the error carries the note `item i` (never a value or a token).
- Truss judges every condition against the state before the group, the memory adapter against the state earlier items left, so a condition of item k on a target an earlier item touched is never sent to Truss unchanged: the planner decides it from the planned operations (`exists` after a create or a delete, `absent` after a create or a delete, `property_equals` after a create, update or delete by the plan's own values, `count` and `no_relationship` from the edges earlier items linked or unlinked, the count sent as a range shifted by them) or refuses it as `Unsupported` when it cannot (a relationship condition after a delete of an object the relationship joins, which cascades). A second create of one key in the batch is `Conflict(exists)` (R18.15).
- A keyed repeat rebuilds the same merged input, so Truss answers it with the committed receipt (every item `replayed`); other items under the same key are `Conflict(idempotency_key_reused)`. A retired key left out of an `absent` condition is left out again, by the sent id.

An independent batch is the host's orchestration, as Truss's README says: each item is `apply` as its own call, group and request id `module.Action:key#index` (a fresh id when keyless; digested over the bound, the index kept), so a refused item (`PreconditionFailed`, `Conflict`, `Invalid`) is an `ItemResult.refusal` and the others commit. `stop_on_error` stops at the first refusal and `items` is the shorter list. Any other error (`Refused`, `Unavailable`, `Unsupported`) raises for the whole call, as on the memory adapter, so a keyless caller loses the receipts of items already committed and a keyed caller replays them. `token` is the last receipt's. A multiplicity violation (minimum or maximum) is Truss's `dependencies` code at the group's last operation and is told `Invalid(multiplicity)` unless that operation is a delete, which is told `Unavailable(busy)` (R18.16).

## Dry run

The same call with `call.rollback` set: nothing survives, including the request record, so the key stays unused. A keyed dry run presents its request, so a request already committed surfaces as `Validation(ok, replay=Receipt(replayed=True, token))` and the same key with other input as `Failure('conflict:idempotency_key_reused')`. `PreconditionFailed`, `Conflict` and `Invalid` are the answer (`failures`, `conflict:<reason>`, `violations`); `Refused`, `Unsupported` and `Unavailable` are raised. A dry run needs write authority. `Validation.freshness` is None: Truss gives no read position for a rolled-back group (R18.11).

Truss's deferred constraint checks run at COMMIT, which a rolled-back group never reaches. The connection layer therefore runs `SET CONSTRAINTS ALL IMMEDIATE` after the toolkit detaches and before it commits or rolls back, for every write call (the dry run and the receipt call included), so a check that fails surfaces inside the call as `Unavailable(unreachable)` with nothing committed, and a COMMIT that fails is only ever an unknown outcome. Every violation a caller can cause (a precondition, a key conflict, a multiplicity bound) is raised by `apply_in_transaction` itself, and no input of the conformance corpus makes a deferred check fail on 0.0.45, so no corpus case can compare a deferred violation with the real apply; the error shape of one is unobserved (R18.14).

## Order of checks

The person's catalog (`Refused` when the person reads none of the module), the effects against the module (`Invalid`), the bounds and `!=` (`Unsupported`), the lookups, then Truss: authority (`UnauthorizedPerson`), the replay probe, the conditions, the effects in order. A reader who sends a plan Arras finds malformed is told `Invalid` before Truss tells them they may not write.
