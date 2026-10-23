---
ddx:
  id: CONTRACT-003
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: FEAT-003
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-004
      kind: informs
---

# Contract: Actions and import

**Contract ID**: CONTRACT-003
**Type**: library
**Version**: v2
**Status**: draft
**Related**: FEAT-003, ADR-013, ADR-014, ADR-015, CONTRACT-001, CONTRACT-002, CONTRACT-004; UMF CONTRACT-900 (declarations), CONTRACT-079 (generated transport)

## Purpose

Defines how a module declares the changes a client may make, how a client invokes one, what a refusal and a receipt are, and how seed records are imported. Actions are the only write path Arras exposes (ADR-015, an architecture decision record).

Terms. UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions. A provider is a backend that applies actions; the module's provider for an action is the one the host's placement names for it, the module's record store by default (CONTRACT-002); a replica is a reader that serves `bulk` and may lag (CONTRACT-004). MCP (Model Context Protocol) is Anthropic's open protocol for agent tools.

## Scope and Boundaries

- In scope: the action declaration, invocation, validation, atomic effects, idempotency, attribution, receipts, handlers, and import.
- Out of scope: reads (CONTRACT-001), how a backend applies a group of operations (CONTRACT-004), compensation and sagas, actions that span backends.
- Owning system or team: Arras owns invocation and backend coordination; UMF owns declaration and recipe semantics. Where this legacy declaration surface differs, UMF governs.

## Normative Surface

**Declaration boundary.** UMF's canonical action vocabulary is `umf.actions`
0.1.0, governed by its CONTRACT-900. The `module.actions` shape described below
is Arras's legacy declaration subset, not that canonical vocabulary. Accepting
the core version or a legacy declaration MUST NOT advertise support for canonical
recipes, selectors or rule versions. Canonical adoption and generated transport
qualification follow the [Arras integration plan](../../04-build/arras-integration-plan-20261022.md);
unsupported meaning must be named and refused before effects. This clarification
does not add a second evaluator or change existing legacy invocation semantics.

**Memory profile refusal.** For the bounded memory profile (CONTRACT-004),
`apply` including dry run, atomic and independent `apply_batch`, and
`import_records` MUST refuse an unserved module profile as `Unsupported` before
replay, effect execution or input-record iteration. This is a capability refusal:
both a value within an unserved string-length bound and one violating it are
refused. Existing authorization checks retain precedence; import also retains
its administrative/attribution checks. Refusal creates no receipt, journal or
load entry and leaves graph state, versions, position and idempotency unchanged.
Registration/read access is not itself refused by this write safeguard.

**Core metadata profile.** `umf-core-metadata/1` (CONTRACT-002) declares no
actions and permits metadata registration/readback and authorized empty-graph
reads only. Direct memory `apply`, including dry run, both atomic and independent
`apply_batch`, and `import_records` MUST raise `Unsupported` after their existing
authentication, shape, administrative and attribution checks, but before clock,
replay, record iteration or effects. No receipt, validation success or load result
is returned; source, revision, graph, object versions, journal, loads, position
and replay state stay unchanged. A forged direct plan cannot bypass this guard.
High-level unknown-action resolution keeps its existing precedence. Official
validity/completeness enables no execution: the legacy parser and unchanged
canonical `umf.actions` probe remain outside this metadata profile. The existing
legacy numeric and unsupported-profile safeguards remain independently in force.

**Legacy declaration.** An action is defined in its module document (CONTRACT-002). Its elements:

| Element | Rules | Notes |
|---------|-------|-------|
| `name` | Module-scoped, matching the name rules of CONTRACT-002; referred to as `module.Action`. | |
| `description` | Text a client can show. | |
| `inputs` | An ordered list of named parameters. A parameter's type is a scalar family, a structured value, or `ref(Type)`, an entity of a declared type named by its key. A parameter may be optional or a list. | |
| `preconditions` | A list of named conditions, each with an `id`, a failure `reason` and a predicate: `exists(ref)`, `absent(type, key)`, `property_equals(ref, property, value)`, `no_relationship(relationship, source[, target])`, or `count(relationship, source) op n`, over the inputs and the current state. | The closed list is a v1 limit; other conditions need a handler. |
| `effects` | An ordered list of operations, each with an optional alias a later operation can name: `create(type, key, properties)`, `update(ref, set, unset)`, `delete(ref)`, `link(relationship, source, target, properties)`, `unlink(relationship, source, target)`, and `foreach(list_input) { effects }`, which repeats the effects inside it for each item of a list-typed input, naming the item. A violation inside a `foreach` is named by its effect and item, as `effects[2].each[5].body[0].key`; a key is an input or `generate(uuid)`; property values are inputs, literals, an item's fields or an earlier alias's key. An action's effects total at most 1,000 after expansion. | A `foreach` is how one action changes many entities. |
| `handler` | Optional name of a handler bound by the module (below). When present, `effects` MAY be empty and the handler supplies them. | |

**Noted gap: a delete and links.** What a `delete` effect does to the links of the deleted entity (remove them, leave them dangling, or refuse the delete while any exist) is not specified here or in CONTRACT-004, and validation reports only the delete. A client must not assume one behaviour; Explore's Retire confirmation (SD-013) names the entity's links from the page's own read until this is specified.

**Handlers.** A module binds a handler with `registry().bind_handler("module.Action", fn)`, where `fn(inputs, ctx)` returns a list of effects in the same closed vocabulary. A handler never writes: Arras applies the effects it returns, with the same atomicity, attribution and receipt. `ctx` gives read access through the interface at `latest`.

**Invocation**

| Element | Shape | Rules |
|---------|-------|-------|
| `invoke(action, inputs, *, idempotency_key=None, expected_revision=None)` | `-> Receipt` | Runs for the session's principal. Steps, in order: resolve the action; resolve the action in a module with a provider for it (a module whose record store is not a provider and whose placement names none declares no actions, so an action of one is `Invalid` with `unknown_action`); validate every input and report all violations (`Invalid`); apply preconditions, effects and the idempotency record as one unit on the module's provider (below); return the receipt. A failure at any step changes nothing. |
| `validate(action, inputs, *, idempotency_key=None, expected_revision=None)` | `-> Validation` | Runs the same steps as `invoke` up to applying, for the session's principal, and applies nothing. It requires the write access `invoke` does, because it evaluates preconditions against the provider's current state. It resolves the effects that `invoke` would apply. It writes no change, no change record and no idempotency record, returns no token, and leaves no lock once it returns. |
| `invoke_batch(action, items, *, atomic=False, stop_on_error=False, idempotency_key=None, expected_revision=None)` | `-> BatchReceipt` | Invokes the action once per item of `items`, a list of inputs, as the session's principal. `1 ≤ len(items) ≤ 100`. Every item's inputs are validated before any item is applied, and a violation is reported against its item index. See Bulk changes. |

**Validation.** The result of `validate`:

| Field | Rules |
|-------|-------|
| `ok` | True when the inputs are valid and every precondition holds. |
| `violations` | Every input violation (`Invalid`'s list), empty when `ok`. |
| `failures` | Every failed precondition the authority could evaluate independently, with its `id` and `reason`, empty when `ok`. A precondition that depends on another that failed, or that the authority could not evaluate, is not reported as false. |
| `effects` | The resolved effects in order, for a client to show before the person confirms: operation, type, key, the properties and links. A key that would be generated is shown as `generated`, never reserved. |
| `replay` | The original receipt when `idempotency_key` was already used with these inputs; otherwise none. |
| `freshness` | The provider that applied the action and the time the state was read. |

A validation is advisory. State can change between `validate` and `invoke`, so `ok` does not promise that `invoke` will succeed; `invoke` checks again. A validation never changes the outcome of a later `invoke` and costs the idempotency key nothing.

**Atomicity and preconditions.** The provider applies the whole action in one transaction. Preconditions are evaluated inside it, against the entities it locks, so a precondition cannot be true at the check and false at the change. If any precondition fails, none of the effects applies and `PreconditionFailed` lists every failed precondition the provider could evaluate independently, in the order the provider states, with its `id` and `reason`. The list is complete for those and makes no claim about a condition that was not evaluated; it never reports a failure of the database or of a dependent operation as a failed precondition. Effects apply in order; a later effect may name an earlier alias. The unit commits with one origin and one catalog check (CONTRACT-004).

**Idempotency.** With an `idempotency_key`, the provider treats the invocation as a request identified by `(module, action, key)` with a hash of the inputs. Invoking again with the same key and the same inputs changes nothing and returns the original receipt, from the provider's durable record of the original result. The same key with different inputs raises `Conflict` (`idempotency_key_reused`). Concurrent invocations with one key apply once. A key is honored as long as the provider retains that durable result, and at least 24 hours, independently of how long it retains the change's own journal.


**Attribution.** The change is attributed to `principal.user`, the person whose own token the provider was reached with (ADR-017), and records the action's name. No service identity stands in for the person, so there is no author a caller can assert that the backend did not authenticate. A change by an import records the load and its initiator instead (below).

**Expected revision.** A caller that built its inputs from a registry revision (a form generated from the action's declaration) MAY pass it as `expected_revision`, the module's revision from `describe`, an object keyed by backend name (CONTRACT-002). Every backend the caller names must be at the stated revision, and a backend it does not name is not checked. If a named backend's revision differs when the call runs, the call raises `Conflict` (`revision`) and applies nothing. Without it the call runs under the current revision.

**Receipt**

| Field | Rules |
|-------|-------|
| `action` | The action's name. |
| `refs` | The entities created, changed or deleted, each with its new version. |
| `created`, `updated`, `deleted`, `linked`, `unlinked` | Counts per operation. |
| `token` | Opaque; a later read passes it as `at_least` (CONTRACT-001). |
| `group` | Opaque; identifies the atomic group the change committed in, and is the `group` of the `Change` that `changes` returns (CONTRACT-001). |
| `replayed` | True when the receipt is the original of an earlier identical invocation. |

**Bulk changes.** Changes arrive in bulk as a seed, a reclassification or an agent's list of corrections. Three mechanisms apply, by size:

| Size | Mechanism | Semantics |
|------|-----------|-----------|
| One action over a list | `foreach` in the declaration | One invocation, one atomic group, at most 1,000 effects. The action itself defines the bulk operation, so its preconditions and effects are declared and reviewable. |
| Up to 100 invocations of one action | `invoke_batch(action, items)` | With `atomic=True`, all items apply as one atomic group (at most 1,000 effects in all) or none do. With `atomic=False` (the default), each item is its own atomic group applied in order, independently idempotent (on a provider that scopes by request, one request per item, named by the action and the item's index so that no key of a single invocation can name it; on the Truss adapter `module.Action#index:key`), and the result lists each item's receipt or its refusal; items continue past a refusal unless `stop_on_error` is true. |
| Records in volume | `import_records` | Administrative and resumable: identity-based and idempotent, applied in batches, safe to repeat. Not for a client or an agent. |

`BatchReceipt` has `action`, `atomic`, `items` (each a `Receipt` or the refusal that item met, with its index), `succeeded` and `failed` counts, and `token`, the position after the last applied group. A bulk change is never partially applied inside one atomic group; across independent items the result says exactly which applied. A caller that needs the read side to see the whole batch passes `token` as `at_least`.

**Refusals.** A refusal is complete: `Invalid` (inputs), `PreconditionFailed` (conditions), `Refused` (the principal lacks write access to the module, decided by the provider's own controls), `Unsupported` (`import_records` into a module with no provider), `Unavailable` (the provider is unreachable), `Conflict` (see below). Arras writes no change for any of them.

**Downstream resource loading.** A host-owned seed/graph loader MUST call the
same public `import_records` operation as other administrative imports, with the
explicit module, principal and load identity. An example-specific resource
envelope remains that consumer's format; it MUST NOT be advertised as a new
public UMF or Arras graph-file API. Loading no seed/graph resource loads no
records. It MUST NOT import default fixtures or bypass profile, attribution,
validation, idempotency or authorization checks.

**Import**

| Element | Shape | Rules |
|---------|-------|-------|
| `import_records(module, records, *, load_id)` | `-> ImportResult` | Administrative principal only (CONTRACT-005); never an MCP tool. A record is an entity (`type`, `key`, `properties`, `original_author`, `original_at`) or a relationship instance (`relationship`, `source`, `target`, `properties`, `original_author`, `original_at`). An entity is identified by its type and key, a relationship instance by its relationship, source and target. A record whose identity is held, or was held and deleted, is skipped without change. Entities are applied before relationship instances across the whole input. A record that fails validation or names a missing endpoint is rejected and stored nowhere. A property's value must be of its declared scalar type (an object, a list or a number in a string field is rejected, naming the property); a decimal is a finite decimal or its text, and a timestamp, a property's or an `original_at`, is RFC 3339 text that names its offset (a time with none is rejected). Each stored record commits with its change. The load's own provenance (`load_id`, `initiated_by`) is recorded apart from each record's original author and time; absent facts stay absent; the person running the load is never recorded as an original author. Importing the same records again changes nothing. |
| `ImportResult` | `created`, `skipped`, `rejected: list of Rejection` | `Rejection` has `kind`, the identity, and `reason`. |

**Export**

| Element | Shape | Rules |
|---------|-------|-------|
| `export_records(module, *, limit=500, after=None)` | `-> RecordsPage` | A read, as the person, from the module's record store under the module's `read` grant; a module only a replica serves, or a backend that cannot serve it, is `Unsupported`. It yields every entity of the module as an entity record (`type`, `key`, `properties`), then every relationship instance between them as a relationship record (`relationship`, `source`, `target`), the shapes `import_records` takes. A property that is not set is absent. `original_author` and `original_at` are written only on a record that has them: an export never invents a provenance, and the person exporting is never recorded as an author. `1 ≤ limit ≤ 500`, otherwise `Invalid`; `after` is the previous page's `next_cursor`, opaque, and a cursor that is not one is `Invalid`. A cursor names a place in the canonical order (the last record the page gave), not a count of records, so a page resumes after that record whatever has been written since: a write between two pages never repeats a record already given and never skips a record that sorts after the cursor, and the export of a graph that is not written to meanwhile is exactly its pages in order. A record written behind the cursor is not in this export, and one deleted ahead of it is not given; a whole-graph export is a snapshot only to the extent the backend reads one. |
| Order | | The same each time: entities by type in declaration order then key, relationship records by relationship in declaration order then source then target; a relationship is written under its declared name, never its inverse. |
| `RecordsPage` | `items`, `next_cursor`, `omitted`, `freshness` | `omitted` names the types the person could not be given (not readable, or the backend could not serve them); a page that names any is not the whole graph. |
| Graph file | `arras.graphfile` | `{format: "arras.graph", version: 1, module, complete, records, omitted?}` as JSON with keys sorted by code point, two-space indent, `ensure_ascii` off and a final newline, so the same graph is the same bytes; nothing in it varies between runs (no time, person or revision). `complete` is false, and `omitted` lists the types, when any page named some. `loads` reads it and `dumps` writes it; the interface's Export control writes the same bytes (`tests/vectors/graphfile.json` is checked by both). A number in the file is an integer, read exactly at any size, because a decimal travels as a string: `loads` and the interface's reader refuse a number written with a fraction or an exponent (`1.0`, `1.5`, `1e3`, and `NaN`, `Infinity` or `-Infinity`, which are not JSON), each with an error that names its path (`records[3].properties.n: 1.5 is not an integer (a decimal is written as a string)`), and the vectors' `rejected` cases are checked by both. `dumps` and the interface's `graphText` refuse to write such a number (a Python float, or a JavaScript number whose text is not an integer, `NaN` and `Infinity` among them) with the same message and path, so a file the readers would refuse is never made; the vectors' `unwritable` cases are checked by both. A file loads with `import_records` (and the dev host's `--records`): entities then relationships, idempotent, creating what is missing and skipping what exists. A file read without `complete: true` (or with `complete: false`) is not known to be the whole graph: it still loads, and the dev host's `--records` and `Sandbox.load` say so (a `warnings` entry on the sandbox and a warning on the `arras.sandbox` log). |

**Errors** (additions to CONTRACT-001's)

| Error | Fields | Raised when |
|-------|--------|-------------|
| `PreconditionFailed` | `failures: list of {id, reason}` | One or more preconditions are false. |
| `Conflict` | `reason: "exists" or "deleted" or "version" or "duplicate_relationship" or "idempotency_key_reused" or "revision"`, `detail` | An effect collides with existing state. |

## Precedence and Compatibility

- Versioning: v2. The contract version is `arras.CONTRACT_VERSIONS["actions"]`.
- Ordering or precedence: access is the provider's own; preconditions precede effects; effects apply in order within one unit.
- Backward compatibility: adding an optional element to the declaration, a predicate form, an effect form or a receipt field is compatible. Removing or renaming one, or changing a meaning, is breaking.
- Deprecation: as CONTRACT-001.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|-----------------|-------|----------------------|
| Unknown action | `Invalid` (code `unknown_action`) | no | Check the name against the registry |
| An input breaks its type | `Invalid` listing every violation | after correcting | Fix the inputs |
| A precondition is false | `PreconditionFailed` listing every independently evaluable failure | after the state changes | Satisfy it |
| `validate` finds a problem | a `Validation` with `ok` false and the violations and failures; not an error | after correcting | Fix the inputs or the state, then validate again |
| The principal lacks write access | `Refused` | no | Request the grant |
| An action of a module with no provider for it | `Invalid` (`unknown_action`): such a module declares no actions (CONTRACT-002) | no | The change belongs to the provider's own process |
| `import_records` into a module with no provider | `Unsupported` | no | The change belongs to the source system's own process |
| Another change takes the same key concurrently | `Conflict` (`exists`) | after reading | Read, then decide |
| Same idempotency key, different inputs | `Conflict` (`idempotency_key_reused`) | no | Use a new key |
| The provider is unavailable | `Unavailable`; nothing is applied | yes | See CONTRACT-005 |
| The connection is lost after a commit was requested | `Unavailable` with `detail` stating the outcome is unknown | yes, with the same idempotency key | Re-invoke with the key; the receipt answers |

## Examples

An action, shown as the fields it needs (the concrete UMF syntax is UMF's):

```text
action catalog.CreateCandidateSolution
  description  "Create a candidate Solution from one coverage assertion"
  inputs       coverageAssertion: ref(catalog.CoverageAssertion)
               useCase:           ref(catalog.UseCase)
  preconditions
    assertion_exists   "The coverage assertion does not exist"            exists(coverageAssertion)
    use_case_exists    "The use case does not exist"                       exists(useCase)
    no_candidate_yet   "A candidate already exists for this assertion"     no_relationship(derivedFrom, in coverageAssertion)
  effects
    s = create(catalog.Solution, key=generate(uuid), properties={status: "candidate", coverageLevel: coverageAssertion.coverageLevel})
    link(addresses, s, useCase)
    link(derivedFrom, s, coverageAssertion)
```

```python
check = ontology.validate("catalog.CreateCandidateSolution",
                         {"coverageAssertion": "ca-0042", "useCase": "uc-pipeline-mapping"})
# Validation(ok=True, effects=[create(catalog.Solution, key=generated, ...), link(addresses, ...), link(derivedFrom, ...)], ...)
receipt = ontology.invoke("catalog.CreateCandidateSolution",
                          {"coverageAssertion": "ca-0042", "useCase": "uc-pipeline-mapping"},
                          idempotency_key="ui-7f3a")
# Receipt(action=..., refs=[Ref("catalog.Solution", "…")], created=1, linked=2, token="…", replayed=False)
```

## Non-Normative Notes

The action shape follows the UMF build brief's description of UMF's action type: a name, a description, typed parameters, a result or handle, preconditions and effects, and optional compensation. The brief's caution applies: the declaration is the contract and a loss report, and the implementation remains the accurate semantics, so the declared effects are claims that the module's tests verify. Compensation and long-running work (sagas) are deferred.

Open points: whether the closed set of predicates and effects is enough for the catalog, or a handler is needed in the first release; and how an action's declared authorization (which roles may invoke it) is expressed once UMF defines it, since v1 relies on the provider's module write access alone.

## Planned one-action/constraint execution cut

The next cut targets one module, one record with a required direct STRING key,
one constrained scalar and one explicit-key SET action from the exact admitted
generation source. The proposed first subset follows CONTRACT-902 at the named
UMF source, subject to the owner's package/binding confirmation. It has empty
conditions/outputs/failures and
no handlers or relationships; nonempty conditions or failure declarations MUST
refuse. Postcondition
execution is a later profile, not a prerequisite for this bounded subset.
The existing STRING key carrier is retained. It MUST use a separately qualified
opt-in execution profile; the read-only metadata profile and legacy dialect keep
their present meaning. Canonical source MUST NOT be lowered by the legacy parser
or by a new Arras rule, literal, selector or recipe evaluator.

UMF CONTRACT-049/900/901 owns value, declaration and invocation meaning;
CONTRACT-079 owns the generated wire. A session-bound synchronous
`execute(request) -> Mapping` remains the planned integration point. Its current
wire uses `contract: "umf.access/1"`, exact source digest `schema`, and
`kind: "apply"` with action identity, inputs and optional idempotency key.
The selected CONTRACT-079 source also defines `kind: "validate"`, omits an
idempotency key for validation and returns `{schema, valid: true}` on success.
Wire fields/codes MUST follow that exact source cohort; no additional kind is
inferred from Arras method names.
Source mismatch and unsupported meanings MUST stop before planning or effects.

The qualified engine/provider MUST enforce the selected inputs, constraints and
frames under current person authority. Unsupported condition meanings refuse
instead of being dropped. Dry run uses the source-qualified validation wire or
host callable. It is advisory and leaves source, graph, revisions, journal,
replay and position
unchanged. Commit and idempotency state are atomic; same-key/same-input retry
returns the original result on an explicit caller reissue, changed input
conflicts, and uncertain settlement MUST NOT cause automatic retry or be treated
as known rollback. Changed identities/counts and consistency tokens MUST follow
the official wire, with complete fixed-code error mapping. Broader conditions,
batch execution and durable restart/recovery are later qualifications; unsupported
requests refuse before dispatch. Memory replay proves only its stated process
lifetime. A post-dispatch unknown outcome remains unknown, never a safe retry.

The executable API, exact profile/version and fixture/vector handoff remain
unresolved. Metadata extension registration or `executionVerified:false`
assessment alone cannot satisfy this gate. No action implementation or public
support is asserted by this planned cut.
