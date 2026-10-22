---
ddx:
  id: CONTRACT-001
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-001
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-003
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-007
      kind: informs
---

# Contract: Ontology interface

**Contract ID**: CONTRACT-001
**Type**: library
**Version**: v2
**Status**: draft
**Related**: FEAT-001, FEAT-005, ADR-013, ADR-014, ADR-017, CONTRACT-002 (types and placement), CONTRACT-003 (actions and import), CONTRACT-004 (backends), CONTRACT-005 (embedding), CONTRACT-007 (MCP binding)

## Purpose

Defines the operations a client uses to read the ontology, and what every answer states about itself. It is the Python library interface that other Python code uses directly and that the MCP binding (CONTRACT-007) is built on. It names no store. Writes are CONTRACT-003; the types a client sees are CONTRACT-002; the backends that answer are CONTRACT-004.

Terms. An ADR is an architecture decision record. UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions. MCP (Model Context Protocol) is Anthropic's open protocol for agent tools. Weft is the SQL project (DocumentDrivenDX/weft) that owns the language `query` takes. P0 is the Must Have priority of the product requirements document (`docs/helix/01-frame/prd.md`). A backend is a named store the host configures (CONTRACT-004); a backend has the role `reader` (serves reads) or `provider` (applies actions) or both; a module's record store is the reader that is the system of record for its graph, and a replica is another reader that serves `bulk` and may lag. The host's placement names them for each module (CONTRACT-002). praxis is the Databricks app that embeds Arras. GraphQL is the API query language that CONTRACT-006 binds.

## Scope and Boundaries

- In scope: `describe`, `query`, the value types, consistency levels, freshness, the query language boundary, the principal, and the errors.
- Out of scope: actions and import (CONTRACT-003), type declaration and placement (CONTRACT-002), the backend contract (CONTRACT-004), startup and migration (CONTRACT-005), the console's GraphQL surface (CONTRACT-006), the MCP tools (CONTRACT-007).
- Owning system or team: Arras (Erik LaBianca). Consumers: the praxis catalog module, plug-ins that use Arras from Python, and the MCP binding.
- Interface style: synchronous Python on the `arras` package. The operations and their semantics are language-neutral.

## Normative Surface

**Caller context.** Every operation runs for a principal, and every backend is reached with that principal's own token (ADR-017). `Arras.session(principal)` returns an `Ontology` whose methods are the operations below.

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| `Principal` | `user: str`, `token: str`, `groups: tuple[str]`, `admin: bool` (default `False`) | yes | `user` is the person the call is for. `token` is that person's credential, which each backend uses to authenticate as the person; it is required, and Arras never substitutes a service identity for a user's read or action. Arras does not issue or validate the token; the backends do. Arras keeps no entity data and no access decision from one call to the next. `admin` is `True` only for the administrative principal that the host names to `Arras.start` (CONTRACT-005); it is never the principal of a read or an action. |

**Value types** (immutable dataclasses)

| Element | Shape | Rules |
|---------|-------|-------|
| `Rows` | `columns: list of Column`, `rows: list of dict`, `truncated: bool`, `freshness: Freshness`, `revision: Revision` | A `Column` has `name`, `scalar` and `type`. Each row is a dict keyed by column name. Values are exact: integers as `int`, decimals as `Decimal`, timestamps with their offset. |
| `Freshness` | `backend: str`, `as_of: Position`, `consistency: "latest" or "bulk"` | Every answer carries one. |
| `Position` | `value: str`, `at: datetime` | An opaque feed or transaction position and the time it was recorded. Only the adapter that issued it interprets `value`. A read position (`Freshness.as_of`) is not a receipt's token and is never passed as `at_least`. |
| `Revision` | as CONTRACT-002 | The ontology revision the answer was computed under. |
| `Receipt` | as CONTRACT-003 | Always carries a token, the one passed as `at_least`. |

**Consistency.** Every read takes `consistency` (default `"latest"`) and optionally `at_least`, a receipt's token.

- `latest` is served by the module's record store.
- `bulk` MAY be served by a replica, and by the record store if no replica serves the type.
- The answer's `freshness.backend` and `freshness.consistency` state what was done. Arras MUST NOT serve `latest` from a replica, and MUST NOT serve a different level than asked.
- With `at_least=token`: if the serving backend has not reached the token (a replica whose feed has not yet carried another provider's token does not reach it), Arras serves from the record store, or waits up to a bound the deployment sets, or raises `NotYetCurrent`. Arras asks the serving backend `reached(principal, token)` as the person (CONTRACT-004): a principal with no sign-in token is `Refused` (`token_expired`) before any backend call, a malformed token, or one the backend can tell was never issued, is `Invalid` with no wait; one it cannot classify or determine is `Unavailable`, raised at once, and a backend that refuses the person is `Refused`. Read-your-writes across providers is `at_least`; Arras promises it no other way. It MUST NOT return an answer older than the token.
- If the backend a level requires is unavailable the call raises `Unavailable` with the backend and reason; there is no silent fallback.

**Operations** (on `Ontology`; keyword parameters after `*`)

| Operation | Shape | Rules |
|-----------|-------|-------|
| `describe(module=None)` | `-> list of ModuleInfo` | The modules the principal may read, or one: entity types, properties, keys, relationships (with their inverse names), actions, the host's placement and per-backend capabilities, from one ontology revision (CONTRACT-002). Each `ModuleInfo` includes `status`, the `BackendStatus` of each backend its placement names (CONTRACT-002, CONTRACT-004). |
| `query(module, sql, params=None, *, limit=50, consistency="latest", at_least=None, text=None)` | `-> Rows` | The one read operation for entities and relationships: a read-only Weft statement over one module's types (see Query language). `1 ≤ limit ≤ 100`. A statement Weft or the serving backend does not serve raises `Unsupported`. The keyword-only `text` is a structured text match (CONTRACT-010, `TextMatch(words, properties)`) that `search` makes: it travels to the backend beside the statement and narrows the statement's rows to those that match; it is never SQL text, Arras reads neither, and a type whose serving backend does not declare `substring`, or a property it does not list as searchable, is `Unsupported`. |
| `changes(module=None, *, type=None, key=None, by=None, action=None, group=None, since=None, until=None, provider=None, limit=50, after=None)` | `-> ChangesPage` | What changed, newest first: the committed changes one provider's journal holds, read as the principal. See Audit reads. |
| `loads(module, *, provider=None, limit=50, after=None)` | `-> LoadsPage` | The import loads one provider recorded for a module, read as the principal. See Audit reads. |
| `document(module)` | `-> RegisteredDocument` | The module's UMF document exactly as it was registered. See Registry reads. |
| `search(module, text, types=None, limit=20, consistency="latest", at_least=None)` | `-> SearchPage` | A composed read over one module's types: ranked hits of the types that can be searched and, for each that was not, why (CONTRACT-010). It makes one `query` per searched type with a structured `text` match, one after another, under one registry revision; it is not a backend operation. Two keyword-only arguments belong to a caller that has its own request, as the console's `_search` does: `budget` (its entity budget) and `revision` (the revision it began under; another one now is a `Conflict` of reason `revision`). The text and its words are never telemetry. |
| `view_of(mod)` | `-> ResolvedModule` | The module's resolved `arras.view` (CONTRACT-010), read from its registered document and cached by module and revision; `mod` is a `ModuleInfo` this principal was shown. |
| `export_records(module, *, limit=500, after=None)` | `-> RecordsPage` | The module's graph as records of the shapes `import_records` takes, a page at a time (`1 ≤ limit ≤ 500`), read as the principal from the module's record store. See CONTRACT-003, Export. |
| `validate`, `invoke`, `invoke_batch`, `import_records` | | CONTRACT-003. |
| `registry()` | `-> Registry` | Called only by the host's administrative principal, at startup, for `register`, `attach` and `bind_handler` (CONTRACT-002, CONTRACT-003, CONTRACT-005). |
| `schema()` | `-> Schema` | Called as a person: `validate` and `register` a UMF document under the record store's `schema` grant, with no administrative principal (CONTRACT-002, ADR-026). The administrative principal is refused. |

**Audit reads.** `changes` and `loads` read the records the providers themselves keep of what it committed; Arras keeps no audit or data table of its own, and they are not forms of `query`. Both are made with the principal's own token, so the backend's grants decide who may read which rows (`Refused` otherwise), and both are bounded (`1 ≤ limit ≤ 100`; `changes` needs `module`, or `type` with `key`, or `group`). A `group` alone is looked up on every provider in turn; a group that matches nothing, or nothing the principal may read, is an empty page. If no page was found and a provider refused, the answer is that `Refused`; if every provider asked answered `Unsupported` (none keeps a journal; `describe().audit` is false), the answer is `Unsupported`; `Invalid` (`unknown_type`), worded without the group, is only for a deployment with no provider at all. **Which provider.** A module's changes may be committed by several providers (CONTRACT-002, Placement), each keeping its own journal. `provider` names the backend whose journal is read. Omitted (`None`), it is the module's record store, which must then be a provider, else `Unsupported`. A named `provider` must be the record store or a value of the module's `Placement.providers`; any other name is `Invalid` (`unknown_type`, path `provider`) and the answer does not say whether a backend of that name exists elsewhere. A named backend that lacks the provider role is `Unsupported`. A `group` lookup with no `module` still scans every provider, and a `provider` given without a `module` is `Invalid` (`scope`), since a provider only means something within a module. Journals are not merged: one call reads one provider's journal, its pages and cursors are that provider's, and a caller that wants every provider's changes to a module makes one call per provider.

`since` and `until` carry an offset and are inclusive bounds; a cursor the backend did not issue, including a negative one, is `Invalid` (`cursor`).

| Record | Fields | Rules |
|--------|--------|-------|
| `Change` | `group` (the id a `Receipt` carries), `at`, `by`, `action` (`module.Action`), `module`, `ops` (each `{kind, type, key, version}` or `{kind, relationship, source, target}`), `backend` | One atomic group that committed. A provider whose journal withholds values (Truss's audit pages) states `key`, `version`, `source` and `target` as null, and `at` is the time it recorded the group (observed), not necessarily its commit time or order (CONTRACT-004, Truss adapter). `by` is the identity the backend authenticated for the change, which under ADR-017 is the person; it is never asserted by a caller. Refused attempts and validate-only runs leave no record, so none appears. The action's input values are not part of the record (they may hold matter content, ADR-005). |
| `ChangesPage` | `items`, `next_cursor`, `truncated`, `freshness` | Newest first within one provider's journal. |
| `Load` | `load_id`, `initiated_by`, `at`, `module`, `created`, `skipped`, `rejected`, `partial` | One run of `import_records` (CONTRACT-003), kept by the provider. `partial` is true when the provider can show the load only in part (some of its chunks are not yet visible): the counts are then of what it showed, and a consumer never reads them as the whole load. Only a provider that accepts imports has loads; a replica's own feed is reported by `status` (position and lag), and a module whose provider keeps no journal answers `Unsupported` to `changes` and names `status`. |
| `LoadsPage` | `items`, `next_cursor`, `truncated`, `freshness` | |

**Registry reads.** `document(module)` returns `RegisteredDocument(module, revision, text, format)`: `text` is the UMF document the provider holds for the module at `revision`, exactly as it was registered (the same characters; never parsed and written again), and `format` is `json` or `yaml`. It is read as the principal: a module the principal cannot read answers as one that does not exist (`Invalid`, `unknown_type`), a missing or expired token is `Refused` (`token_expired`), the administrative principal is refused as for every read, and an outage is `Unavailable`. A module whose record store is not a provider was attached, not registered, so it has no registered document: `Unsupported`. Only the record store is asked.

| Record | Fields | Rules |
|--------|--------|-------|
| `RegisteredDocument` | `module`, `revision`, `text`, `format` | One document per revision (CONTRACT-002, Ontology revision). Bindings send `text` unchanged; the operator surface's explorer catalog is built from it (CONTRACT-009). |

**Query language.** `query` takes a statement in Weft SQL (DocumentDrivenDX/weft). Weft owns the language: its grammar, name resolution, join and aggregate semantics, parameters, result bounds, ordering and paging, and its refusals. Arras defines no dialect and neither parses nor restricts the text. The serving backend owns the hand-off to Weft: it compiles the statement against the UMF modules it holds and executes the compiled result with the principal's own token (Truss does so through its Weft compiler boundary; the backend contract, CONTRACT-004, carries the statement and parameters to it). Arras never builds a backend statement, and a backend never builds one by string concatenation.

- **What Arras owns.** The principal and token, the choice of serving backend from the module and the consistency level (below), the wait for `at_least`, the answer's `freshness` and `revision`, and the mapping of backend outcomes to the errors below. Arras never reads the statement.
- **Module.** The caller names the module the statement reads, as `describe`, `changes` and `loads` do. A module the principal may not read, or that does not exist, is `Invalid` (`unknown_type`), so its existence is not revealed. A statement that reads anything outside the named module is refused by the serving backend as `Unsupported`, naming the construct, because an answer carries one revision and one placement. A join within the module is unaffected.
- **Statement and parameters.** `sql` is one read-only Weft statement. `params` is a mapping from name to value for the statement's `:name` markers; Arras passes both unchanged, and Weft decides how a value is typed and whether a marker is unbound or unused.
- **Version and profile.** A backend declares the Weft SQL version and the named read profiles it has qualified (CONTRACT-004). A statement outside what the serving backend declared, or one Weft refuses, raises `Unsupported` carrying Weft's construct and what the backend does support. Joins, aggregates, relationship predicates and whole-entity projections are available exactly where a backend declares a profile that admits them; this contract does not list them.
- **Serving backend.** `latest` is served by the module's record store. `bulk` is served by the first replica of the module's placement, in placement order, that declares `read` for one of the module's types (Arras does not read the statement, so it cannot know which type it reads) and whose `query` accepts the statement; a replica that answers `Unsupported` falls through to the next and finally to the record store, and any other outcome, including a replica's outage, is raised. A reader the placement names that the host did not configure is `Unavailable` (`not_configured`, naming it). The wait for `at_least` runs on each backend before Arras asks it to `query`: a replica that has not reached the token within the bound raises `NotYetCurrent` (naming it) rather than falling through, and a replica that answers `Unsupported` after its wait passes to the next, which waits again, so each backend asked may wait up to the bound.
- **Rows.** The backend returns the columns Weft's result descriptor names, as `Column(name, scalar, type)`, with exact values. `limit` caps the rows returned (`1 ≤ limit ≤ 100`), and `truncated` states that the cap cut the result. Ordering, bounds and continuation belong to the statement under the profile: `ORDER BY`, `LIMIT` and a keyset predicate in the SQL. The answer carries no cursor; a client continues by writing the next page's predicate.
- **Whole-entity reads.** `alias.*` is Weft's projection of an entity's declared fields. A client reads an entity's relationships with Weft's `RELATED_KEYS(alias.relationship, n)` projection and filters by them with `HAS_RELATED(alias.relationship, KEY(...))`; their bounds are the statement's. A backend appends the entity's own facts to a whole-entity row as columns, described in the result: `_version` and the attribution `_created_by`, `_created_at`, `_updated_by`, `_updated_at`, and for an imported entity `_original_author`, `_original_at` and `_load_id` (CONTRACT-003, CONTRACT-004). A fact the source did not hold is `null`, never defaulted, and an imported entity's `_created_by` is the load's `initiated_by`, never its `_original_author`. These columns cannot be selected by name. The change history is `changes` and `loads`.

**Access.** A read is made with the principal's own token. A backend that cannot answer because the principal lacks access raises `Refused`, except that a `query` of a module the principal may not read answers as one that does not exist (`Invalid`, `unknown_type`), as `describe` and `document` do; one that cannot answer because it is unreachable raises `Unavailable`; one with nothing to return answers empty. A caller can rely on the three being distinct. `Refused` carries a `reason`: `no_access`, or `token_expired` when the token is missing, expired or invalid, so a binding can tell "sign in again" from "request access". An expired or missing token is `Refused`, never `Unavailable`.

**Errors** (all subclass `ArrasError`)

| Error | Fields | Raised when |
|-------|--------|-------------|
| `Invalid` | `violations: list of Violation` | A parameter or literal breaks a rule or bound. `Violation` has `path`, `code`, `message`. All violations are reported, not only the first. |
| `Refused` | `backend`, `operation` | The principal lacks access, or its token is missing or expired. A failed precondition is `PreconditionFailed`, never `Refused` (CONTRACT-003). |
| `Unavailable` | `backend`, `reason`, `detail` | The backend cannot answer. `reason` is a `status()` reason (CONTRACT-004) or `busy` (CONTRACT-002). |
| `Unsupported` | `construct`, `supported` | The query or the type's capabilities do not include the request; `supported` lists the query shapes or capabilities that are available. |
| `NotYetCurrent` | `token`, `backend` | `at_least` was not reached within the bound. |

A query for a key that does not exist is not an error: it returns no rows.

**References.** A `RELATED_KEYS` column holds the keys of the entities on the other end. When those entities are of a type held by another module or another backend, the column still holds their keys; Arras never fetches them implicitly. The key's type is available from `describe`. A client reads one with its own `query`, using the relationship's target type from `describe`.

## Precedence and Compatibility

- Versioning: v2, the operations and shapes this contract states. The contract version is `arras.CONTRACT_VERSIONS["interface"]`, an integer.
- Ordering or precedence: access is decided by the backends' own controls, and takes precedence over everything; a refused read returns nothing. The consistency level is honored or the call fails.
- Backward compatibility: adding an optional keyword parameter, an error subclass of an existing error, a value-type field, or a Weft construct a backend newly serves is compatible. Removing or renaming a name, changing a parameter's meaning, or tightening a bound is breaking and requires v2.
- Deprecation: a deprecated name keeps working for one minor release and raises `DeprecationWarning`.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|-----------------|-------|----------------------|
| No entity matches | no rows | n/a | |
| `limit` over a bound, or a parameter Weft rejects | `Invalid` | after correcting | Correct it |
| A statement Weft refuses, one outside the Weft version or profiles the serving backend declares, or one that reads outside the named module | `Unsupported` carrying the construct and what is supported | no | Rewrite the statement, or ask for a backend that declares the profile |
| The principal lacks access, or its token is expired | `Refused` | no (after renewing a token) | Request access, or renew the token |
| The required backend is unreachable | `Unavailable` | yes | See CONTRACT-005 |
| `at_least` not reached within the bound | `NotYetCurrent` | yes | Retry, or read `latest` |
| `at_least` names a malformed token | `Invalid`, with no wait | no | Use a receipt's token |
| `at_least` names a token the serving backend can tell was never issued | `Invalid`, with no wait | no | Use a receipt's token |
| `at_least` names a well-formed token the serving backend cannot classify (on Truss, another installation's token, an unissued token of this installation, or a receipt the person cannot read; see CONTRACT-004) | `Unavailable`, raised at once and not waited on; only a `False` answer is waited on | yes | Use a receipt's token, or retry |
| `latest` asked, record store down, a replica up | `Unavailable`, never a replica answer | yes | Wait for the backend |

## Examples

```python
ontology = arras.session(Principal(user="jsmith", token=tok, groups=("catalog-editors",)))

ontology.describe("catalog")        # types, relationships, actions, capabilities

# the whole entity by key, with the keys it relates to
rows = ontology.query("catalog", "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE s.code = 'sol-pipeline-01' ORDER BY s.code LIMIT 1")
rows.rows[0]   # {"code": "sol-pipeline-01", "name": "...", "coverageLevel": "partial", "addresses": ["uc-pipeline-mapping"], "_version": 2, ...}

# a bounded page of columns
ontology.query("catalog", "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.workArea = 'data' ORDER BY u.code LIMIT 50", limit=50)

# the Solutions that address a use case
ontology.query("catalog", "SELECT s.code, s.name FROM catalog.Solution s WHERE HAS_RELATED(s.addresses, KEY('uc-pipeline-mapping')) ORDER BY s.code LIMIT 50")

ontology.query("catalog", "SELECT u.* FROM catalog.UseCase u WHERE u.name = 'x' OR u.name = 'y'")
# raises Unsupported(construct="OR", supported=[...the Weft version and profiles the serving backend declared...])

receipt = ontology.invoke("catalog.CorrectSolution", {"solution": "sol-pipeline-01", "coverageLevel": "substantial"})
ontology.query("catalog", "SELECT s.* FROM catalog.Solution s WHERE s.code = 'sol-pipeline-01' ORDER BY s.code LIMIT 1", at_least=receipt.token)
```

## Non-Normative Notes

Weft owns the language, so the shapes a client may write grow when Weft adds them and a backend qualifies them, with no change here. Traversal and change feeds are not operations: a client opens an entity with Weft's whole-entity projection and its relationship columns. What changed, and who changed it, is read with `changes` and `loads`, which read the backends' own records and are not `query` forms.  The page limit of 100 is a proposed starting value. Whether Arras itself should wait for a replica to reach a token, or only report that it has not, is an open question; the contract allows both within a deployment's bound.

## Open Questions

- **One feed across providers.** `changes` and `loads` read one provider's journal. A single feed that merges the journals of every provider of a module needs an order across providers that Arras does not have (positions are opaque and not comparable across backends) and a merged cursor. Whether to offer it, ordered by each change's commit time and with what stated skew, is undecided.

- **Earlier registered revisions.** `document(module)` returns the current registered document only. UMF's schema browser can show a module's earlier revisions and compare them structurally (its `revisions` entries: `{id, label?, format, text | url}`), and the Operator Console supplies none because the registry has none to give. A `document(module, revision=r)` read, and a listing of the revisions at which the module's document was registered, would need the record store to keep each registered document text by revision (not only the current one) and to answer it under the same read rules as `document(module)`: as the principal, `Invalid` for a module or revision the principal cannot see, `Unavailable` on an outage. Whether a record store keeps that history, for how long, and whether a revision whose document was superseded by a compatible change is still readable, are undecided.
