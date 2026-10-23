---
ddx:
  id: CONTRACT-004
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-13
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
---

# Contract: Backend contract

**Contract ID**: CONTRACT-004
**Type**: library
**Version**: v6
**Status**: draft
**Related**: FEAT-004, FEAT-005, ADR-013, ADR-014, CONTRACT-001 to CONTRACT-003; Truss CONTRACT-001 to CONTRACT-006; Ashlar PRD

## Purpose

Defines what an adapter implements so Arras can serve the interface from it: the operations, the capability descriptor, status and positions, how the backend is reached with the person's own token, and the conformance corpus that proves it. A backend is a named store that declares its roles in `describe().roles`, a non-empty subset of `reader` and `provider`; the host configures any number of backends (CONTRACT-005), and a module's placement names which plays which part (CONTRACT-002). The current package implements the Truss adapter (reader and provider) and memory store/replica backends. An Ashlar reader adapter is part of this intended contract but is not implemented or qualified in Arras.

Terms. Truss is the hot mutable store, deployed on Lakebase (Databricks managed Postgres); its adapter is a reader and a provider. Lakebase is Arras's required deployment target. Ashlar is the toolkit for property-graph ontologies on Unity Catalog (Databricks' governance layer for tables and access); the planned Arras adapter is a reader over the ontology that the providers' changes reach. A gold Delta table is a curated table in the Delta Lake format that Ashlar publishes on Unity Catalog. A reader serves graph reads; a provider applies actions. A module's record store is the reader that is the system of record for its graph and serves `latest`; a replica is any other reader the placement lists, which serves `bulk` and may lag. The protocols are `Backend` (the reader operations, which every backend implements) and `Provider` (which adds the provider operations). ADR means architecture decision record. UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions.

## Scope and Boundaries

- In scope: the adapter operations, capabilities, status, positions and tokens, user-token access, the reference adapters' mappings, the conformance corpus.
- Out of scope: the backends' own storage, contracts and feeds (the stores' own), the client-facing operations (CONTRACT-001 to CONTRACT-003), startup (CONTRACT-005).
- Owning system or team: Arras. The stores behind the adapters are owned by their own projects, which Arras depends on and does not specify.

## Normative Surface

**Roles.** A reader serves `query`, `reached`, `catalog`, `describe`, `status` and `attach`. A provider applies actions (`apply`, `apply_batch`), `import_records` and, when it keeps them, `register`, `document`, `changes` and `loads`. A backend declares the roles it has; an operation of a role it lacks raises `Unsupported`. Reading and acting are independent: a provider need not be a reader, and an action may be provided by a backend other than the module's record store (CONTRACT-002, Placement); the record store must then see its effects.

**Adapter operations.** Each takes the caller's `Principal`. A read returns an `Answer` that carries the `Position` it reflects; Arras adds the consistency and the revision to make `Freshness`. An adapter implements the operations its `describe()` declares and raises `Unsupported` for the rest.

| Operation | Shape | Reader | Provider | Notes |
|-----------|-------|--------|----------|-------|
| `catalog(principal)` | `-> modules` | yes | no | The modules the backend holds that the principal may read, each with its revision, without placement (the host's placement is attached by Arras, CONTRACT-002); an outage or refusal is raised, never an empty answer. |
| `describe()` | `-> BackendInfo` | yes | yes | `name` (the name the host registered it under), `roles` (`reader`, `provider` or both), per-type `Capabilities`, and `weft`: `WeftSupport(version, profiles)`, the Weft SQL version and the named read profiles the backend has qualified. A backend that does not host Weft declares none. Capabilities are keyed by the module-qualified type name (`catalog.Solution`), so two modules that define a type of the same local name each keep their own columns and relationships and a reader of one never sees the other's. `audit`: whether it serves `changes` and `loads` (default true); a backend that keeps no group-scoped journal declares false, answers `Unsupported` to both before it opens a connection or asks for a token, and the corpus runner expects that answer to the two audit steps (and only those) of the journal cases. |
| `status()` | `-> BackendStatus` | yes | yes | `available`, `reason` (`not_configured`, `unreachable`, `access_denied`, `migration_failed`, `unsupported_version`), `detail`, and for a replica `position: Position` and `lag`. |
| `query(principal, module, statement, *, limit, text=None)` | `-> Answer` | yes | no | The one read operation for entities and relationships (CONTRACT-001). `statement` is `Statement(sql, params)`: Weft SQL and its parameters, exactly as the caller gave them, over the one `module` the caller named. The adapter compiles it against that module's types with Weft and executes the result as the principal, in a read-only transaction, never building a statement by string concatenation. `text`, when given, is a `TextMatch` that narrows the statement's rows (Capabilities, `search`). It raises `Unsupported` for what Weft or its profiles refuse, for a statement that reads outside `module`, and for a type of `module` the backend does not hold while it holds the module (so a `bulk` read passes to the next reader), and `Invalid` (`unknown_type`) for a module the principal may not read or the backend does not hold, before it decides anything type-dependent, so existence is not revealed. A whole-entity row carries the entity's own facts as columns the adapter appends and the result descriptor names: `_version`, `_created_by`, `_created_at`, `_updated_by`, `_updated_at`, and for an imported entity `_original_author`, `_original_at`, `_load_id` (`null` when the source held none). Arras answers `at_least` itself: it asks `reached(principal, token)` and chooses the backend from the module's placement. A reader that is not a module's record store serves only `bulk` for it. |
| `reached(principal, token)` | `-> bool` | yes | no | Whether the data this backend serves for the caller reflects the token, relative to the read snapshot the backend uses for that caller (the adapter supplies the person's read-only transaction), not to a later state. The principal is an argument because a backend may answer inside the person's own transaction and authorize the person: a call with no token raises `Refused` before any backend call, and a backend that refuses the person (it holds no grant that lets the person ask) raises `Refused`. `True` and `False` are answers the backend can prove: `False` means the token is a position the provider issued and this backend's data does not yet include it. A malformed token raises `Invalid`; a token no provider issued raises `Invalid` when the backend can tell and `Unavailable` when it cannot (the Truss row below is the case where it cannot); a backend that cannot tell otherwise (it cannot see the receipt, the evidence is missing, the position's source or epoch does not match, or the observation fails) raises `Unavailable`. Neither becomes `False`, which would read as "not yet" and invite a wait. |
| `apply(plan, *, idempotency_key, dry_run=False)` | `-> Receipt` or `-> Validation` | no | yes | `plan` is a module-scoped action's preconditions and ordered effects (CONTRACT-003). Evaluates preconditions and applies effects as one atomic unit, with the principal as origin, under the idempotency key; a returned `Receipt` always carries its token. With `dry_run` it evaluates the same preconditions and effects against the provider's current state and then discards them: it writes nothing and returns the resolved effects and every violation and failure (CONTRACT-003, `validate`). |
| `apply_batch(plans, *, atomic, idempotency_key, stop_on_error=False)` | `-> BatchReceipt` | no | yes | A list of plans: with `atomic`, one group; otherwise one group per plan, each with its own request id (`module.Action#index:key`) (CONTRACT-003, Bulk changes). |
| `import_records(module, records, *, load_id, initiated_by)` | `-> ImportResult` | no | yes | CONTRACT-003. Administrative principal only; `initiated_by` is the principal's own user, never another person's (the interface passes it). |
| `changes(principal, filter, *, limit, after)` | `-> ChangesPage` | no | yes | The committed groups of this provider's journal (Arras calls the provider the caller named, the record store by default, CONTRACT-001) that match `filter` (CONTRACT-001, Audit reads), read as the person in a read-only transaction. Access is the backend's own journal grant. A provider that keeps no journal raises `Unsupported`. |
| `export_records(principal, module, *, limit, after)` | `-> RecordsPage` | no | yes | CONTRACT-003, Export. The module's entities and relationship instances as records, in a stable order, read as the person under the module's `read` grant; a provider that cannot serve it answers `Unsupported`. |
| `loads(principal, module, *, limit, after)` | `-> LoadsPage` | no | yes | The import loads this provider recorded for the module (Arras calls the provider the caller named, the record store by default, CONTRACT-001). |
| `register(principal, document, module, *, unknown_endpoint)`, `attach(principal, module)` | `-> RegistryResult` | `register` | the registrar check first (Truss's advisory `registrar_status_in_transaction`: a person who is not a registrar is `Refused` before anything of the document is answered, an unchanged document included, and acceptance reauthorizes), then `prepare_catalog` (which prepares the module in Truss's embedded V8, spawning no process) and `accept_in_transaction` by the person, with the person as the revision's origin actor. The document id is the document's own top-level `id`. An equal document (JSON-structural, as on every backend) returns the held revision, changed false, without calling Truss to accept, because Truss counts a rewritten, equal document a new revision. The request key names the catalog head read just before, because Truss answers a repeated key with the original result and applies nothing. `expected_revision` is compared with the held document's revision before accepting and then sent to Truss as the document-scoped expectation (`CatalogDocumentExpectation` with the document's source revision, zero for a document not yet held): Truss checks it inside the accepting step, so a registration of that document that lands in between is Truss's typed `CatalogCASConflict`, which is `Conflict` (`revision`), nothing applied, while a registration of another document does not disturb it. A repeat after an unknown commit presents the same request and expectation. A catalog head of 0 (an install with nothing registered) answers Truss's conditional reader catalog as a profile mismatch, which is not a release mismatch: the person's runtime status (`person_runtime_status_in_transaction`, open to any enrolled person) says `empty`, the adapter keys the first registration `register:0:{sha256}`, answers `catalog` an empty mapping and `document` `Refused` (`no_access`), and a stated `expected_revision` is a `Conflict`. When Truss answers an unchanged registration, the revision returned is the accepted document's source revision read in the same call, never the catalog head (an unchanged answer for a document that differed from the held one means another registrar registered the same bytes meanwhile, so the held revision is stale; with a stated `expected_revision` that is a `Conflict`). Truss accepts the paired optional-field addition to an existing record in the `umf.ddd` form; a change to an extension it does not take is `unsupported_profile`, which is `Unsupported`, and so is a document it cannot take for another reason (a field with no `name`, a decimal other than precision 18 and scale 4). A registrar who may read none of the module cannot compare, so a stated `expected_revision` is `Refused`. Truss requires an authored, nonempty `name` on every Record and Field (UMF itself permits none) and, when a document has elements without one, refuses the preparation with a diagnostic for every one of them (`TRUSS-NAME-MISSING`, with the module, the element id, the kind and the JSON pointer): the adapter raises one `Invalid` with one violation for each, `elements.<module>.<element>.name` (`name_missing`), for `register` and `validate_register` alike, writes nothing and fills nothing in |
| `validate_register(principal, document, module, *, unknown_endpoint)` | `-> RegistrationCheck` | `register` | no | The dry run of `register`: the same grant (checked first, so a person without it is `Refused` whatever the document holds) and the same compatibility checks, reported and not applied. `RegistrationCheck` has `revision` (current, null if the module is not held), `changed`, `violations`, `report` and `current` (the module's `ModuleInfo` in force, or null); Arras builds the `SchemaPlan` (CONTRACT-002) from it. A provider that cannot do it raises `Unsupported`. It creates no revision and writes no journal row. |
| `document(principal, module)` | `-> RegisteredDocument` | no | yes | The module's UMF document as it was registered at the revision the provider holds, character for character, read as the person under the module's `read` grant (`Refused` without it). A module the provider does not hold is `Invalid`. A backend that is not a provider raises `Unsupported`: it is fed or attached, never registered. |

**Capabilities.** Per entity type and backend: `read` (bool; Arras does not route `bulk` to a replica that declares false), `mutable` (bool; true when this backend is a provider for the type), `latency_class` (`interactive` for key lookups and bounded lists, `batch` for counts and scans), the descriptive `columns` (the key and required scalar properties the backend serves), `relationships` (relationship names it serves) and `count` (bool, whether it serves `COUNT(*)` with `GROUP BY`), which tell a client what to build and decide nothing about `query`: Weft and the backend refuse what they do not serve; and `search` (`none`, or `substring`; `word` and `ranked` are reserved) and `searchable` (the string properties, optional ones included, that a `substring` backend can match for the type). A backend that declares `substring` accepts `query` with `text` (CONTRACT-010): `TextMatch(words, properties)`, passed beside the statement and never SQL text, and returns the statement's rows for which every word occurs, after the fold (`str.lower()`), in at least one of the named properties, in the order and within the bounds the statement states. It MUST treat `%`, `_` and `\` in a word as literal characters and accepts the cost of a scan on the type. A `text` over a type that declares `none`, or over a property not in `searchable`, is `Unsupported`. A backend MUST NOT declare a capability it cannot meet; Arras MUST NOT synthesize one the backend lacks.

**Weft hosting.** A backend that serves `query` hosts Weft's compiler boundary and the execution of what it compiles; Arras holds neither. `WeftSupport.version` is the Weft SQL version (for example `weft-sql/0.2.0`) and `profiles` the named read profiles (Weft's `readProfile` subsets) the backend has qualified. Weft's own contracts define their meaning; `profiles` is descriptive for clients, and Arras routes by the module's placement and by what `query` accepts.

**Positions and tokens.** A `Position` is opaque and issued by the backend. A receipt's token is a position the provider issues at commit, and every `Receipt` carries one (`Receipt.token` is required): a provider that cannot produce a token for a committed write does not return a receipt without it, it raises `Unavailable` with the outcome known or unknown. `reached(principal, token)` is true when the backend's data includes it; for a backend that issued the token it is true at once, and for another reader when its fed position is at or beyond the token; a replica whose feed has not yet carried another provider's token does not reach it, so a read at that token raises `NotYetCurrent`. A replica states the position it reflects and when it was recorded, in every answer and in `status()`. A read position (`Freshness.as_of`) and a receipt's token are different namespaces: a read position is never passed to `reached`.

`reached` has four outcomes, and a token's form is the backend's own, so the adapter maps the backend's classification and never infers one from a missing row: included (`True`), issued and not yet included (`False`), malformed, or never issued where the backend can tell (`Invalid`), and not determinable (`Unavailable`, with the reason the backend gives). A never-issued token the backend cannot tell from an unreadable or unobservable one is `Unavailable` (the Truss row in the adapter table is that case). A backend that answers inside the person's transaction authorizes the person there: a person it refuses is `Refused`, never `False`. An outcome of unknown commit is not turned into any of these; it is raised as `Unavailable`. Arras's wait (CONTRACT-001) retries only on `False`.

**Principal.** Every call is made over a connection authenticated with the principal's own token (ADR-017), so the backend's controls decide on the person. The adapter holds no role map, never sets a role and makes no access decision of its own, and a backend call with no token raises `Refused` before it is made.

**Outcomes.** An adapter distinguishes three: an empty answer, `Refused` (the backend's own controls deny the principal) and `Unavailable` (unreachable or failing). It MUST NOT turn an outage into an empty answer or a refusal.

### Metadata profile qualification

`BackendInfo` gains a final defaulted field
`metadata_profiles: tuple[str, ...] = ("legacy-arras/1",)`. It declares acceptance
or attachment, source preservation, enumeration and document/metadata readback;
it does not declare data mutability or value/action enforcement. A descriptor
without the field is legacy-only. Only the qualified memory store and replica
advertise `("legacy-arras/1", "umf-core-metadata/1")`; unchanged Truss and custom
providers remain legacy-only. `PolicyBackend` preserves the delegated descriptor.

For the new profile only, preflight MUST require an exact tuple whose entries
are exact strings and compare the requested profile by equality. A string,
substring, list, mapping or arbitrary truthy/mutable carrier never qualifies.
Do not normalize malformed data into support or add a general plugin validator.
CONTRACT-002 fixes authorization and placement precedence: unqualified placed
stores or replicas are refused before acceptance, dry-run, attachment,
preparation or CAS. Existing catalog/describe reads may occur. Direct provider
registration retains schema authorization first, then refuses unsupported
metadata before preparation or acceptance. A defensive Truss profile guard does
not change its accepted-document parser or qualify native core metadata support.

The official-admission guarantee belongs to Arras's source-taking Registry/Schema
routes. Direct provider registration continues to trust its host-supplied
ModuleInfo/source pairing after authorization; it does not certify official
validity or independently re-admit bytes. The new descriptor is not an admission
ticket. No memory-to-admission dependency is introduced by this profile.

Every accepted `umf-core-metadata/1` type reports `mutable=false`. This profile
has no implicit seed or write executor; direct writes are refused under
CONTRACT-003. The legacy memory numeric profile remains a separate capability.
No new Truss pin, native method, Ashlar adapter or feed behavior follows.

## Reference adapters

The core contract above names no store. The three adapters below map it onto one. A backend's name is the host's choice (`[a-z][a-z0-9_]{0,40}`); Arras defines none.

### Truss adapter

Roles: reader and provider. The adapter runs over Truss's public Python toolkit, pinned exactly with its driver tuple: `truss-toolkit[native,query]==0.0.45` (native runtime `0.72-candidate`, manifest SHA-256 `71c4c3d4c05a2229c4cdec1643cabe0da7055965f0b0d23195e83ad780042a2e`, `weft-sql` 0.4.49, UMF core 0.10.0 source), psycopg and psycopg-binary 3.3.6 with libpq 18.6 on PostgreSQL 18.6. No process is started and no Bun or Node is needed: Truss prepares a module in an embedded V8 (`prepare_catalog`, which `register` and the changed-document `validate_register` call), and a key is derived in PostgreSQL. It imports nothing private to the toolkit. Truss qualifies only that tuple: a connection to any other server version is refused when it is adopted, and Lakebase, Arras's required target, is that tuple (CONTRACT-005). Truss installs a fresh database only: it upgrades nothing.

Every call runs in a transaction the adapter begins on the person's connection and settles itself. A read runs in a read-only transaction. A write runs in a read-write transaction, and the adapter repeats the request in a new read-write transaction to obtain the receipt token.

| Interface operation | Truss |
|---------------------|-------|
| `query` | `query_in_transaction` with the statement's Weft SQL and parameters, unchanged, over the document of the named module, in a read-only transaction as the person, in one call with the person's own reader catalog (the one the same operation's `catalog` just read as that person, kept in the call scope until the operation returns and never across calls, else a read in the call; the module is `Invalid` (`unknown_type`) when that catalog does not name it, before text, parameters or Truss, and the cache never answers access). A statement holding an `alias.*` runs under the read profile `complete-entity`, the only way Truss appends the eight fact columns, and is never retried without it; any other statement runs with no profile and, when Truss asks for a page profile to continue a keyset, is retried in the same transaction under `entity-page`, `related-entity-page` and `count-summary`. Truss's `maximum_rows` is 10,000 at most and a result, its bytes or its scan (10,000 source rows, checked before filters and `LIMIT`) over a bound is a `limits` refusal, never a truncated result: the adapter asks for the ceiling, caps the rows at Arras's `limit` itself and maps `limits` to `Unsupported`, a declared bound of the backend. A parameter is a string, integer, decimal or boolean by exact type; any other is `Invalid` (`param_type`) before Truss, which refuses it with no reason. An `unauthorized` refusal (which Truss also gives for an unknown document) is `Invalid` (`unknown_type`); `unsupported_query` and a Weft refusal of a construct (`WFT-UNSUPPORTED`, `WFT-CAPABILITY`, `WFT-TYPE`, `WFT-PROFILE`) are `Unsupported`, and so is a source Weft does not find (a type outside the module); an unknown column, a parameter binding, a repeated output name and a value outside a field's numeric domain are `Invalid`; `stale_context` is `Unavailable` (`busy`), and a compile Truss cannot run is `Unavailable` (`not_configured`, `resource` or `busy`). Truss reports a syntax error under the same code as an unsupported construct, so a syntax error is `Unsupported`. The answer's position is Truss's read position: a conservative committed lower bound captured just before the data query, not a snapshot and not a receipt token (it is never passed to `reached` and is not ordered by its string or time). Columns are named by Truss and typed by the adapter (a fact by its fixed type, a property by the module, a relationship column as keys, anything else by its first value). Output names follow Weft, which lower-cases an unquoted alias. A whole-entity row also carries one column per relationship of the type, named as the relationship, which Truss appends; an absent optional property has no key and a projected one is `null`; the fact times are datetimes with their offset, timestamp values likewise and binary values their exact text. Two things Truss refuses for a whole entity, and the adapter does not work around: a relationship alias equal to the relationship's own name (`WFT-OUTPUT-NAME`; the statements Arras writes name the keys `_<relationship>`, CONTRACT-006), and an entity with more than 100 related keys on a relationship (`limits`). **The combined read.** A `latest` read whose module's record store is the Truss adapter and whose person was shown the module before (a `catalog` call of this process gave them a snapshot and its validator) is one operation in one read-only transaction: the adapter's `query_current`, which presents that validator with the statement to `query_with_catalog_in_transaction`, and core takes the answer in place of `catalog` then `query`. Truss answers the rows and the person's current catalog together and withholds both if the person's authority or a source moved; the adapter gives the answer only when the catalog is `unchanged` and the original source Truss returned (`QueryDocument`: the exact bytes and digest) is the document, at the digest, that the catalog entry names. A catalog that moved keeps its new snapshot and sends the read the ordinary way (the catalog, then the query: the rows of the combined read are discarded), nothing shown is kept for a person Truss refused, and a person who lost the reader role is refused by Truss on that very call as any query is (`Invalid`, `unknown_type`). The adapter holds no authorization: what it presents is what the person was shown, and whether that is still current is Truss's answer to this call. A `bulk` read, an `at_least` wait and a text match take the ordinary way. The byte bound of a result is the reader catalog's (16 MiB) on both routes, because Truss's validator binds the bound a catalog was read under. Measured on 0.0.45, a singleton read is 1 transaction, 18 round trips and 17 statements plus the rollback, of which the combined operation is 11 (Truss's published budget), the adoption 3 and the adapter's own transaction statements 3; the ordinary way is 2 transactions, 28 round trips |
| `apply` | one read-write call as the person: the person's catalog (the operation's own, as for `query`) and the accepted document's exact bytes read in the call, the effects checked against the module, then, in one call, `prepare_group_in_transaction` (the group context with the type and relationship references the plan names, which the planner then asks Truss for no more; a refusal there is told by the separate calls it replaces) and `apply_in_transaction` with the preconditions and ordered effects as one group of at most 1,024 operations and 3,072 preconditions (a larger plan, a count compared with `!=` and a plan with no effects are `Unsupported`), the person as the origin actor and the action's name in the origin's `x-action`. The request identity is the idempotency key's request id scoped by the action, or a fresh UUID when the caller gave none, at most 1,024 UTF-8 bytes (a longer id is shortened by a digest, never truncated); Truss scopes it to the person. Generated keys are derived from the request id and the effect index, because Truss's fingerprint covers the whole input and a repeat with a changed input is `RequestConflict`; `expected_version` is never sent (no plan holds a version, and a version taken at lookup changes the input a retry rebuilds). Updates of one object in a plan are one operation (Truss bumps a version once per update operation); an update that changes nothing keeps its version and is not counted. A delete first removes the object's edges in the same group. A missing target is named by a ghost identity so Truss reports it (`PreconditionFailed` with `_ref`); Truss names no operation for a failure it finds when the group finishes, so the adapter attributes a `not_found` to the first operation that names a ghost or a ref an earlier delete of the group removed, and a multiplicity failure to the group's last operation; a deleted key holds an `absent` precondition, so a create on it is `Conflict(deleted)`: Truss's `KeyAbsent` fails for it, so after a follow-up lookup in the same transaction that condition is left out and the group presented again, and a keyed retry, which Truss answers as a conflicting request when it presents the full input, is presented once more with the same conditions left out, so it matches the original and replays. A failed precondition carries the caller's own condition ids and reasons. The receipt token is read after the commit by presenting the same input and request again in a second call, which Truss answers with the committed receipt; a commit whose outcome is unknown is recovered by presenting the same request once on a new connection. `Receipt.group` is the journal's source epoch and transaction id of the group's first event |
| `validate` (`apply` with `dry_run`) | the same group in a transaction the adapter rolls back, after `SET CONSTRAINTS ALL IMMEDIATE` so Truss's deferred checks run inside the call (every write call runs it; a failure is `Unavailable(unreachable)` and nothing is committed; no corpus case can produce one on 0.0.45), so precondition and catalog failures surface exactly as an apply would raise them; the replay and request records vanish with the rollback and no token is returned. A keyed dry run presents its request, so a request already committed is the `replay`. Truss states no read position for a rolled-back group, so `freshness` is none |
| `import_records` | Truss's explicit batched route: the records of a call are built in one native call (`build_import_records_in_transaction`) and imported by `import_batched_in_transaction` as the person, whose result wraps the tagged import result and, for a literally empty load, how Truss settled it; both the outer outcome and the inner result are narrowed, and an `Ok` that holds a refusal is a refusal. It requires the writer role, and records the load in the origin (`x-initiated-by`) and each record's source facts (`at` as an exact RFC 3339 instant). The administrative principal is a registrar (CONTRACT-005), asked by Truss's advisory `registrar_status_in_transaction`. The adapter checks each record against the module before Truss sees it, because Truss accepts an undeclared property, any key text and any original time. A load is sent as the entities of the whole load first, then its relationships (an edge needs its ends' identities), each phase in calls of at most 128 records, every call one transaction of the person: Truss's batched profile takes 1,024 records, but Truss gives each record a subtransaction of its own and a call's time grows faster than its records (49 s for 1,024 in one transaction, against 14 s in eight calls of 128, measured, plan B8; the operation bound is 60 s), so a load is not atomic: a failure leaves the earlier calls stored (the error notes what they confirmed) and a repeat skips what is held. A commit of unknown outcome is `Unavailable`, closes the connection and is never replayed or inferred rolled back (an import has no token), and neither is an empty-load settlement of `commit_unknown` or `transaction_unresolved`. Truss keeps the load, including one that created nothing; it is listed by `loads` only as far as Truss's module-scoped discovery shows it (below) |
| `export_records` | The person's own Weft reads in one read-only transaction a page at a time, in the order the cursor names (entities by type in declaration order then key, then each relationship by source then target, under its declared name). A type's keys are listed by keyset on the key (Truss orders it bytewise, `COLLATE "C"`: a keyset continuation exists only under a page profile, which carries no facts) and each entity is then read whole by its key (`complete-entity`, the only read that carries the original author and time, and one that takes no continuation), so a page reads only the entities it gives; a relationship is read as each source type's related keys by keyset on the source key, merged by source then target. The cursor is the last record's own place, so a write between pages neither repeats nor skips a record; a page is one transaction and its freshness is that read's position. A person with no reader role on the module is `Refused`, never an empty page, and `omitted` is empty: a reader role covers the module. A type over 10,000 rows, an entity with over 100 related keys on a relationship, and a source with over 100 targets are `Unsupported` (R17.2 and R17.5), never cut. |
| `changes`, `loads` | Truss's audit pages, read as the person in a read-only call, under Truss's own audit grant (`ModuleAuditGrant`, which an administrator configures with `configure_access` through `ModuleAccess.auditor_role`; audit is separate from reader and writer membership: a person with neither can audit, and a reader or writer cannot, and a page needs current audit access across every owner the group or load touched, else `Refused`). `describe().audit` is true. **`changes`** is `page_mutation_group_audit_in_transaction`, a page of one group at a time, newest *observed* first at a committed visibility frontier that stays fixed through the cursors. `Change.group` is the source epoch and writer transaction id (`epoch:xid`), the id a `Receipt` of the same group carries; `by` is the person's role as Truss recorded it, `action` its asserted `x-action`, and `at` is the time Truss *observed* the group, which is not a commit time and not a commit order (neither the observation time nor the transaction id is one, so `since` and `until` filter on observation time and "newest first" is newest observed first). A group whose asserted action is not a module action (an import, or a group no action made) is not a change. Truss states no key, property or version: an op is `{kind, type, key: null, version: null, id}` (`{kind, relationship, source: null, target: null, id}` for an edge), `kind` being `create`, `update`, `delete`, `link` or `unlink`, `type` the module-qualified type and `id` Truss's entity id; the type is named from the module the person reads and is the native type id (`#2`) for a person who reads none. `key` as a filter is `Unsupported` (Truss's key filter needs the key's definition pin, which its public reads do not give the adapter); `type`, `action`, `since` and `until` are Truss's filters and `by` and `group` are matched by reading on (at most 500 groups a call, then `truncated` and a cursor). A `group` alone is looked for in the modules the adapter has served or was configured with. A page of `limit` groups is read with one more to say whether a next page exists; the cursor wraps Truss's typed cursor with a digest of the filters it was made for, and anything else is `Invalid` (`cursor`). **`loads`** is `page_import_load_audit_in_transaction`, one invocation summary per import call: calls of one load id and person are one `Load` with their counts added, `at` is the last observation, and a load Truss shows only in part (a summary it calls `partial`) is `Load.partial`, whose counts are of what Truss showed and never a statement about the whole load. Truss's module-scoped discovery lists the invocations that imported entities: an invocation that imported only relationships, and a literally empty load (which has no module scope and needs the registrar's disclosure path), are not listed, so a load's counts are those of its listed invocations (pinned limit, truss-requirements R20). Imports of Truss's legacy route are not in the load audit; the adapter imports by the batched route. `Arras.changes` by group alone answers `Unsupported` only when every provider does |
| `apply_batch` | `atomic`: one group of the items' operations, at most 1,024 operations and 3,072 preconditions in all (`Unsupported` over, before any call), one request id and one token; conditions are sent as `<item>:<id>` and told under the caller's ids (only the first failing item's); Truss judges a condition against the state before the group, so a condition of a later item on what an earlier item touched is decided in the planner from the planned operations, or refused as `Unsupported` when it cannot be (never sent to Truss unchanged). Otherwise one call and group per plan, each with its own request id (`module.Action#index:key`, digested when over the request-id bound). A key holds any text, so the scope is what a key cannot reach: the id is `<scope>:<key>`, the scope is the text before its first `:`, and an action's name holds neither `:` nor `#`. A single apply scopes by `module.Action`, an atomic batch by `module.Action#atomic` and an independent batch's item by `module.Action#<index>`, so no key of a single invocation (`k#1`, say) is another call's request and a batch is never replayed as, or refused against, another call's input; a refused item is its `refusal` and any other error raises for the call. Shape (1 to 100 items, one action) is `Invalid` before any connection |
| `register` | the registrar check first (registrar membership, installation-wide; a person who is not one is `Refused` before anything of the document is answered, an unchanged document included), then `prepare_catalog` (which prepares the module in Truss's embedded V8, spawning no process) and `accept_in_transaction` by the person, with the person as the revision's origin actor. The document id is the document's own top-level `id`. An equal document (JSON-structural, as on every backend) returns the held revision, changed false, without calling Truss to accept, because Truss counts a rewritten, equal document a new revision. The request key names the catalog head read just before, because Truss answers a repeated key with the original result and applies nothing. `expected_revision` is compared with the held document's revision before accepting and, when stated, the accepted revision must be the head read plus one (accepting takes the head's lock first and revisions are dense), else the adapter rolls back and raises `Conflict`: Truss has no such parameter, so the race is detected rather than prevented and the corpus records it in the `limits` field of `registry.register-checks-the-revision-it-was-planned-against`. A catalog head of 0 (an install with nothing registered) is not a release mismatch though Truss's reader catalog refuses it the same way: the adapter reads the head from the install state, skips the reader catalog, keys the first registration `register:0:{sha256}`, answers `catalog` an empty mapping and `document` `Refused` (`no_access`), and a stated `expected_revision` is a `Conflict`. A repeat after an unknown commit keeps the head-plus-one check. When Truss answers an unchanged registration, the revision returned is the accepted document's source revision read in the same call, never the catalog head (an unchanged answer for a document that differed from the held one means another registrar registered the same bytes meanwhile, so the held revision is stale; with a stated `expected_revision` that is a `Conflict`). Truss refuses a changed `umf.ddd` on an existing record (a new property in Arras's document form) as `unsupported_profile`, which is `Unsupported`; a document it cannot take for another reason (a field with no `name`, a decimal other than precision 18 and scale 4) is `Unsupported` too. A registrar who may read none of the module cannot compare, so a stated `expected_revision` is `Refused` |
| `validate_register` | the same preparation and acceptance in a transaction the adapter rolls back; a compatibility refusal is an answer (`violations`, code `incompatible_change`), an unsupported change is raised |
| `document` | `accepted_document_in_transaction`: the accepted bytes with their digest, read as the person, which requires read authority on every module of that document. A module that does not exist and one the person may not read are indistinguishable on Truss, and both are `Refused` (`no_access`). The revision is the document's `source_catalog_revision`, the catalog revision at which these bytes were accepted |
| `catalog` | `reader_catalog_if_changed_in_transaction`, as the person, in a read-only transaction: the adapter keeps each person's last snapshot with Truss's validator and presents it, and Truss answers `unchanged` (no catalog payload) or a new snapshot; the person's access is re-answered by Truss on every call, so a revoked role's very next call is refused (`CatalogRefused`, which drops the snapshot) whatever was cached, and a validator is one person's view and grants nothing (another person's first call presents none; snapshots are kept for at most 1,024 people). A person who may read no module is answered with no modules, not `Refused`. Each module is parsed from its accepted document and carries that document's `source_catalog_revision` (the entry's `sourceCatalogRevision`) as its revision (the catalog head moves on any registration and is no module's revision). A parse cache keyed by document id, accepted digest and source revision saves the re-read of a document a registration of another document did not change; it never answers who may read what. The operation (a read, a dry run, an action, `describe`) keeps what `catalog` read in its call scope for the backend calls it makes next, and nothing outlives it |
| `status` | `status_in_transaction` on the installing connection (a tampered or other release is `unsupported_version`). With no installing connection the install state cannot be read and a probe would need a person, so the status is what the last per-person call showed: `not_configured` (detail `no installing connection`) before any call; available when a call reached Truss and began its transaction; unavailable, with the call's reason (`unreachable`, `access_denied`, `unsupported_version`, `not_configured`) and detail, when a call could not get that far. A person's refusal (an expired token) and an error inside a call that reached Truss, among them a module-role grant Truss finds missing (which answers after the call reached Truss), are not recorded; a connect refusal by the database (`permission denied for database`, `Unavailable(access_denied)`) is recorded, because the adapter cannot tell a revocation from one role apart from one from PUBLIC (the server words both the same). No connection is made to learn it |
| `describe` | reader and provider; the Weft dialect Truss compiles and the profiles `query` proves (`entity-page`, `related-entity-page`, `count-summary` and `general`: Truss serves joins and ungrouped shapes with no profile, and its bound is rows, bytes and scan rather than a statement's `LIMIT`) when the pinned Weft is installed; per type, read, mutable, batch latency, the key and required scalar properties as columns, the relationships it is an end of, counts, and search `none`, from the modules the adapter has served |
| `reached` | `reached_in_transaction` in a read-only transaction, authorizing the person. Truss answers a non-member (and an unknown `consumer_id`) with `ReceiptVisibilityUnavailable`, reason `authorization`, which the adapter raises as `Refused`; `included` is the answer (Truss answers `False` only on a replica's feed path, never in authority mode, where a token this installation issued is included or its visibility is unavailable; the adapter never infers `False` from a missing row or an unavailable reason); `invalid_token` is `Invalid`; a token over 16,384 characters, which Truss classifies as `resource` before any backend call (`reached_in_transaction` in `catalog_runtime.py`), is `Invalid`, since no issued token can exceed the bound; every other unavailable reason (for example a `resource` reason that comes back from the backend, `epoch_profile`) is `Unavailable` (reason `unreachable`, the Truss reason in the detail; a backend `resource` keeps `resource`). Another installation's token is `epoch_profile`, so `Unavailable`, not `Invalid`. On Truss a well-formed token this installation never issued (an unknown `receiptStorageRowId`, or a position that does not match the stored attempt) and a token whose receipt the person cannot read (a member who lacks read on a module the receipt touched; `truss.runtime_receipt_can_read` in `_catalog_runtime/operations.sql`) both come back `observation_integrity`, which the adapter raises as `Unavailable` (retryable), not `Invalid` and not `Refused`: Truss gives one reason for a missing row, an unreadable receipt, a position or digest mismatch and a lock timeout (SQLSTATE 55P03/55000), and the adapter cannot tell them apart. That is why `observation_integrity` keeps reason `unreachable` rather than `busy` (the write path's `observation` is `busy` in `outcome.py` because there it is only contention). The order of a non-member's refusal and a token's classification is adapter-defined: Truss decodes the token before it authorizes (a non-member sending garbage is `Invalid`), the memory adapter refuses first; `test_truss_reached` pins it with a Truss-marked test (a non-member's garbage, empty and oversize tokens are `Invalid` on Truss and `Refused` on memory; a well-formed token is `Refused` on both). The call is always a read-only transaction (a read-write one is answered `epoch_profile`), never passes `consumer_id`, and never waits: the core's `at_least` wait polls it |
| token | the `receipt_token` Truss returns with the pending answer of the group, which is the token of its committed replay; the adapter returns it once its commit has returned, so a write is one transaction. No token exists for a keyless request that the caller can replay, so the adapter always keys. When the commit outcome is unknown, the adapter itself repeats the same request id once on a new connection before it raises: that repeat returns the original results or applies afresh, so a keyless invocation (whose request id the caller never sees) is recovered by the adapter or not at all. A repeat of a write whose commit outcome is unknown is the same repeat: it returns the original results, or applies afresh if the commit never happened. A group with no changes has a token too |
| `status()` | install state read on the installing connection (CONTRACT-005); with no installing connection the status is the last per-person call's (row `status` above); `position` is not applicable, the adapter reads its own database |

- Principal: the host's `ConnectionSource` yields a connection authenticated as the person (CONTRACT-005), and the person is the origin actor. A module's reader role reads and its writer role writes, by membership the administrator grants; Truss enforces both in the database. The adapter checks, after `SET TRANSACTION ISOLATION LEVEL READ COMMITTED` (`READ ONLY` for a read, `READ WRITE` for a write), the first statement of the transaction psycopg opens with it and before Truss adopts the transaction, that the connection's role is unset (`current_setting('role')` is `none`; Truss's adoption does not check it, and a person who set a module role would only be answered `unauthorized`) and that autocommit is off and no transaction is open. A connection that arrives otherwise raises `Unavailable(access_denied)` with a fixed detail (a connection with a session role is also closed, so the host's pool discards it), because it is a host misconfiguration rather than a person lacking access; the adapter never sets a role. A call with no token is `Refused(token_expired)` before any connection is requested. Writing requires the module's writer role; registering and `validate_register` require registrar membership, which is installation-wide, whereas Arras's `schema` grant is per module: a person with registrar membership can register any module, and the corpus tags the case that a per-module `schema` grant would need. Truss refuses business calls from an elevated installer and from members of its owner role, so the installing connection is never a person's (CONTRACT-005). Truss answers a non-member's group and direct-read calls with a bare permission error rather than a typed refusal; the adapter maps that error to `Refused` and a typed refusal where it exists.
- Receipts: the adapter keeps no table of its own. A repeated invocation is the same keyed request, which Truss answers from its durable receipt of the original, even after the original's preconditions no longer hold; the receipt's identities, versions and token come from that receipt, not from journal rows. CONTRACT-003 identifies a keyed request by (module, action, key). On Truss the request is also scoped to the person, so the same key repeated by another person is a new request: it applies afresh (and fails as a new request where the first's effects collide) rather than returning the original receipt or `Conflict(idempotency_key_reused)`. This is a documented limit of the Truss adapter, held by the corpus case `action.same-key-from-another-person-replays` in `TrussHarness.LIMITS`. A retry is answered from the receipt only when the input the adapter rebuilds is byte-identical to the original, and the adapter rebuilds it from what exists: any retry whose rebuilt input names an object or edge that no longer resolves as the original named it is `Conflict(idempotency_key_reused)`: an Unlink of an edge that existed (the original named the stored edge, the retry a ghost edge), a Delete (its target and its cascaded edges), any effect or condition whose target anyone has deleted since, and a plan with `absent` conditions on both a never-existing key and a retired key (the adapter cannot tell which the first call left out); the `Conflict`'s detail says so (the original's targets no longer resolve). The corpus cases `action.keyed-retry-of-a-delete-replays`, `action.keyed-retry-of-an-unlink-replays` and `action.keyed-retry-after-its-target-was-deleted-replays` hold the memory adapter's replay, and each ends on Truss at its `Conflict` in `TrussHarness.LIMITS` (truss-requirements R18.3), so the runner fails them when Truss replays. A retired key's `absent` condition is not one of these: the first call leaves it out after a follow-up lookup and the retry, when Truss answers it as a conflicting request, leaves out the same conditions, so both present the same input. Truss 0.0.45 documents no retention window for group receipts (its README states no cleanup for them), so CONTRACT-003's 24-hour minimum is not verified on Truss and is recorded as a gap; the adapter promises no window beyond what Truss retains.
- Installation: the adapter's install-or-verify runs when the host calls `Arras.migrate()` (CONTRACT-005), on the installing connection under the advisory lock; `start` does not install; Truss never upgrades an installation, so a database of another release is recreated. A database holding another Truss release is `Unavailable` (`unsupported_version`).
- Connect failures: psycopg reports no SQLSTATE for a failure to connect, so the adapter classifies from the driver's message: `password authentication failed` (a wrong token, an expired role and an unknown role are indistinguishable) is `Refused(token_expired)`; a role that may not log in is `Refused(no_access)`; `permission denied for database` is `Unavailable(access_denied)`, and is recorded as the backend's last observed status (the adapter cannot tell a revocation from one role apart from one from PUBLIC, so it never treats the refusal as only the person's); a missing socket, an unresolvable host, a refused or timed-out connection, a lost backend and anything unrecognized is `Unavailable(unreachable)`. The server and libpq word these, so a localized server may fall to `unreachable`. A driver, libpq or server other than the tuple Truss selects (adoption raises) is `Unavailable(unsupported_version)`. Details are fixed phrases: no token, SQL, socket path or host name.
- Commit: only a `COMMIT` whose outcome is unknown (the error is not a psycopg error, or has no SQLSTATE, or is of class 08 or `57P01` to `57P03`, or the connection is not idle, broken or closed after the error, a PANIC or a FATAL, whatever the SQLSTATE) closes the connection and raises `Unavailable(unreachable)` with detail `outcome unknown`, which the receipt replay recovers. A `COMMIT` the server refused (it reported the error with a SQLSTATE outside class 08 and `57P01` to `57P03` and the connection is back to idle, ReadyForQuery having arrived, which is Truss's own rule) rolled the transaction back: it is a definite failure of the write, `Unavailable(unreachable)` with detail `the commit was refused`, the connection stays open and the caller does not replay.
- Connections: a connection Truss quarantines (its `detach()` returns false, or a call reports the transaction unusable) is closed by Arras, and the host's pool discards closed connections (CONTRACT-005).
- Name: `BackendInfo.name`, `Revision` and `Freshness` carry the name the host registers the adapter under; the adapter's factory takes it and no module of Arras spells one.
- Truss ships and maintains the Python implementation and passes its own corpus; the adapter depends on that implementation's public capabilities and none of its internals. Where Truss lacks a behavior this contract requires (a typed refusal for a non-member on group and direct reads, a request key scoped to the keyed request rather than to the person, a documented receipt retention of at least 24 hours), the adapter follows the stated fallback and the corpus tags the case. Truss 0.0.45 gave the document-scoped `expected_revision`, the registrar status and the group audit; the fallbacks for those are gone.

### Memory adapter

An in-memory reader and provider and an in-memory reader (`arras.fakes`, `arras.testing.InMemory`) that implement the same operations over Python data. They are real backends, not stand-ins for a named one: the sandbox and the dev host register them as `memory` (reader and provider) and `memory_replica` (reader), and a console reading from them says `memory`. The replica is fed from the provider and reports a position and lag. The memory adapter passes the same conformance corpus.

**Bounded mutation profile (A2).** Memory MUST examine the current registered
source document before mutation, because `ModuleInfo` does not carry all declared
constraints. This is an execution-capability check, not UMF structural validation
or value evaluation. It inspects actual `modules[].elements[]` field definitions
and their semantic slots; it MUST NOT recursively treat an annotation/property
named `default` or `rules` as a declaration.

- Missing or empty field `facets` retain the existing legacy numeric behavior.
  On a directly served scalar integer field, only `integerWidth` is served;
  its only members are `bits` and `signed`. Present `bits` is a positive integer
  excluding booleans; present `signed` is boolean. Omitted members retain the
  legacy defaults of 64 bits and signed. These defaults are memory compatibility,
  not a claim of canonical UMF shape admission.
- On a directly served scalar decimal field, only the paired `precision` and
  `scale` facets are served: integers excluding booleans, `precision >= 1` and
  `0 <= scale <= precision`. Declaring only one is unsupported. Numeric facets
  on an array/map/item field or structured value are unsupported unless the
  existing direct numeric storage path actually consumes that definition.
- Other facet names (`length`, `range`, `collectionSize`, or unknown names),
  unknown nested numeric qualifiers, malformed numeric shapes, field `default`
  or `allowedValues` declarations, field `semanticTypes` other than missing/an
  empty list, and any explicit module/element `rules` slot make the whole module's mutation profile
  unsupported. Presence is checked even when a candidate value happens to meet
  the declaration. No rule or extension evaluator is introduced.

An unsupported profile MUST name the source paths/reasons in `Unsupported` for
`apply` (also dry run), both `apply_batch` modes and `import_records`, after the
existing principal/module and import administration/attribution checks and
before journal replay, state copying, clock/effect work or record iteration.
Nothing is committed or journaled, and no receipt is returned. Unrelated types
in that module are conservatively covered by the refusal; authorized reads and
registered bytes remain available. Missing source on manually constructed test
modules retains the historical fixture behavior and establishes no constraint
support. This profile does not certify unknown extension semantics, replace
existing parser refusals or qualify Truss/Ashlar runtime behavior.

| Interface operation | Memory adapter |
|---------------------|----------------|
| `query` | It cannot host Weft (Weft gives no plan without a registered backend binding), so it evaluates a declared subset of Weft SQL 0.2 itself, as a small relational pipeline over the named module's rows: sources `[module.]Type [AS] alias`; `[INNER] JOIN ... ON a.x = b.y [AND ...]`, at most 16, as a bag (every matching combination, duplicates kept), hashed on the pairs that link a source to an earlier one; `WHERE` predicates joined by `AND`: `=` and `>` against a literal, a parameter or a column, a tuple keyset `(a.x, b.y) > (v, w)`, and `HAS_RELATED`; `GROUP BY` one or more columns; `COUNT(*)` over the bag and an exact `SUM` of an integer or decimal, a decimal sum at its argument's scale; `ORDER BY ... [ASC]`; `LIMIT` from 1 to 1,000; projections of columns (an absent-allowed one as a nullable column), `alias.*` with its appended facts, `RELATED_KEYS` and `AS`. Names and types are resolved as Weft resolves them: an unknown member or alias, a repeated alias, a repeated output name (compared case-folded unless quoted), an ungrouped projection, a comparison across families (an integer is no decimal), an integer parameter for a decimal field and a literal or parameter outside its field's numeric domain (a decimal's precision and scale, an integer's width, read from the registered document) are `Invalid`; a reserved word names a member, an alias or a parameter only when quoted, and parameter names are case-folded. Every other construct (`OR`, `DISTINCT`, `OFFSET`, outer and comma joins, subqueries, `DESC`, `IN`, functions), a decimal field without precision and scale, and a statement over another module are `Unsupported`, carrying the subset. A `TextMatch` narrows the first source only. It holds a number at its field's domain: a decimal at its declared scale, and a value outside the domain is refused on import and in an action (`numeric_domain`) |
| `describe().weft` | `WeftSupport("weft-sql/0.2.0+memory-subset", ("entity-page", "related-entity-page", "count-summary", "general"))`: the version marks it a fake. It classifies each statement to one profile: a page (one source in key order with a `LIMIT`, equality filters on values or columns and a keyset on the key; `related-entity-page` when it reads or filters a relationship), a count summary (`COUNT(*)` with grouped scalars and equality filters, inner joins admitted, a grouped count ordered by its whole grouping with a `LIMIT`), else `general`. It serves a statement whose profile it declares, and any bounded statement when it declares `general`: a declared `general` covers every named profile, since each is a bounded shape of the general dialect, and the corpus runner holds a backend that declares `general` to every case. Weft does not bound the general dialect, so the memory adapter does: a general statement names a `LIMIT` or is a global aggregate (one row), and its joins may not do more than 10,000 rows of work, counting the rows produced and, for a join with no pair linking it to an earlier source, every combination it would compare, charged before it starts. That bound is the data's, not the request's, so a statement over it is `Unsupported`. A narrower declaration answers `Unsupported` for what it leaves out |

The memory adapter is not Weft and makes no claim for it beyond its tests. `tests/test_weft_relational.py` holds two batteries against Weft's own parser: every statement of the accepted battery the memory adapter serves and Weft reads, and every statement of the refused battery Weft refuses and the memory adapter refuses. Outside the batteries the two may differ; where a difference is known it is narrower (the memory adapter refuses what Weft reads), and the build plan lists it. `tests/test_weft_parser.py` puts every statement the corpus and Arras's callers write through Weft's parser under the profile it is written to.

### Ashlar adapter

Roles: reader.

| Interface operation | Ashlar |
|---------------------|--------|
| `query` | Weft SQL compiled for the Databricks target and run as a bounded statement over gold Delta tables through a SQL warehouse, as the user; the shapes served are the profiles Ashlar qualifies |
| `apply`, `import_records`, `register` | not supported: Ashlar changes only through the feeds into it |
| `attach` | records a module's types for discovery |
| `status().position` | the feed position Ashlar publishes for each source, and when it was recorded |
| token | `reached(principal, token)` compares the token with the published position of the feed that carries the providers' changes |

- Principal: the adapter passes `principal.token` so Unity Catalog applies the user's own row and column policy. It does not use a service identity for a user's read.
- Open: which of Ashlar's reads are interactive (the Ashlar project has not set budgets), and how it publishes a feed position are Ashlar's to define; the adapter's capabilities follow them.

## Conformance corpus

A corpus held as data, shared by every adapter, gives each case's setup (modules, entities, relationships, principals, positions), calls, and expected results, errors and freshness. An adapter passes a corpus version when every case for the operations it declares yields the expected result. Cases cover:

- key lookups, bounded lists, filters, relationship predicates, whole-entity reads, counts and the page contract, each against the profiles the adapter declares, and `Unsupported` for the rest; a whole-entity row's appended fact columns, `unknown_type` for a module the principal may not read, and `Unsupported` for a statement that reads outside the named module;
- `latest` served only by the module's record store and `bulk` never silently becoming `latest`;
- `at_least` with a token reached and not reached, and `reached`, asked as a named person, for a token that is malformed (`Invalid`), or that the backend can tell was never issued (`Invalid`), or that the backend cannot determine (`Unavailable`), each distinct from `False`;
- empty, `Refused` and `Unavailable` kept distinct;
- an action's atomicity, preconditions, idempotency and receipt (a keyed retry of a create, a delete, an unlink and of a plan whose target was deleted since returns the original receipt, replayed, as does the same key from another person), bulk changes (atomic and per-item, partial results, repeats), and that a refused action changes nothing (provider only);
- a call made without a token or with another person's token being refused, never answered from a shared identity;
- import identity, skipping, deleted records staying deleted, and provenance (provider only);
- the group a receipt names (a replay names the original's; an atomic batch is one group, an independent one a group per item) and the journal reads `changes` and `loads`: committed groups only, newest first, with the person and the action, paged by cursor, and refused without the journal grant, or `Unsupported` from a backend that declares `audit` false (provider only; corpus version 2);
- validate-only registration changes nothing and reports the refusal `register` would raise, and `register` and `validate_register` are refused without the `schema` grant (a `write` grant is not enough); the registered document read back exactly as installed, by a reader, and kept when the same document is registered again; refused without the read grant or a token, unavailable when the backend is down; and `Unsupported` from a backend that is not a provider (corpus version 3);
- text search: every word in some named property, case-folded, `%`, `_` and `\` literal, in the statement's order and bounds, `Unsupported` over a property that is not searchable, refused and unavailable kept distinct; a case names the capability it needs (`requires.search`) and a backend that declares `none` is held to `Unsupported` (corpus version 6);
- relational reads: an inner join as a bag in the statement's order and `LIMIT`, ordering by several columns (`general`), and `COUNT(*)` over a join grouped by several columns and ordered by the whole grouping (`count-summary`); a backend that does not declare the profile is held to `Unsupported` (corpus version 7);
- export: `export_records` yields entities by type then key and then relationships, writes a property that is not set as absent and an author or time the record never had as absent, is `Refused` to a person with no read grant or token (never an empty page) and `Unavailable` when the backend is down, bounds `limit` and the cursor, resumes by the last record's place so a write between pages neither repeats nor skips a record, and is `Unsupported` from a backend that is not a provider (corpus version 11);
- the position and lag a replica reports.

The corpus runs at the adapter's operations: it cannot hold the router to account, so `latest` served only by the module's record store, `bulk` never becoming `latest`, and `at_least` waiting or raising `NotYetCurrent` are Arras's own cases, run against the memory adapter and any set of adapters in the core test suite. A read case may name the Weft profiles it needs; a backend that declares neither them nor `general` is held to answering `Unsupported`. Positions, tokens and group ids are opaque: a case never spells one, it saves a receipt's token or group and asks the backend whether it has `reached` the token or compares the group with a later answer. `expected_revision` is not a corpus case: the interface checks the module's revision before it plans, so no adapter operation takes it, except that a provider's own serialized check is that provider's test. The runner reports a corpus newer than the adapter claims instead of passing it, and an adapter's own failure against the case that met it.

Cases are tagged by role; a provider is tested for `apply` and `import_records` and a reader for read behavior. A host-specific case is tagged and outside the pass rule.

A backend may declare documented limits: a case id, the step (as the runner names it, `step 2 (query)`) at which a limit of the engine ends that case, and the refusal it ends in (the error class and, optionally, a fragment of its reason, construct or violation codes). The runner records such a case as `limit`, which passes the run, only when it fails at exactly that step with exactly that refusal, matched on the error the backend raised; a limited case that passes (the limit is gone), that fails at another step, that fails at the step with another error class or detail, or a limit that names no case fails the run. The corpus is not weakened for a backend: each limited case carries the engine's ask in its `limits` note. The packaged native helper declares its case-specific limits in `arras.conformance.truss.TrussHarness.LIMITS`. The installed cohort receipt must establish which cases pass or reach those exact documented limits; helper availability or a selected smoke run does not establish a full corpus pass.

### Installed downstream conformance

A downstream adapter supplies an explicitly imported host-owned callable factory
for the public `run_corpus`/`Harness` protocol; documents and configuration do not
name executable imports. The harness owns isolated test resources, people,
installation and cleanup. The packaged corpus is the authority for expectations;
consumers MUST NOT copy or weaken repository tests to claim conformance.

**Optional harness lifecycle.** A factory-created harness MAY supply a callable
`close()`; it is not a required member of `Harness`. The runner MUST close each
acquired probe and each acquired case harness exactly once, including newer
corpus, setup/step failure and early-return paths. Legacy harnesses without
`close` retain their behavior. Cleanup failure MUST fail the report: preserve
an existing primary failure's status/text and append safe cleanup diagnostics;
otherwise record `harness_error`. Cleanup MUST NOT hide the primary failure or
turn a failed/limited run into success. No acquired resource may depend on the
next case or garbage collection for disposal.

**Packaged native testing resource.** `arras.conformance.truss.TrussHarness()`
is a lazy, isolated testing harness over the production local Truss resource
lifecycle. Its constructor accepts no persistent URL, personal directory or
credential source. A probe allocates no server; a case owns its fresh temporary
server and closes it. People authenticate with their own real roles/tokens.
A foreign-position control obtains an actual receipt from a separately owned
resource, never a fabricated token encoding. Any installation-marker mutation
used solely to simulate `unsupported_version` is a named testing deviation on
that owned database, restored on recovery and never used on a caller endpoint.
No full-native support follows from source/helper availability: installed
cohort/corpus qualification is required and missing dependencies refuse without
memory fallback.

An installed runner/report MUST name actual backend roles and corpus version,
separate passing, failed, harness-error, documented-limit, host-specific and
skipped outcomes, and fail an empty/incompatible/applicably failing run. A memory
store/replica run establishes only that profile; it MUST NOT advertise native
Truss, Ashlar, managed deployment, renderer or theme qualification. A documented
factory protocol is distinct from a delivered installed native harness. Optional
backend jobs require their own explicit resources, artifact cohort and evidence;
unavailable native prerequisites MUST NOT silently fall back to memory.

**Caller setup.** The reusable installed job MAY accept explicit
`consumer_setup_path` and `theme_setup_path` Python files under the caller
workspace. Consumer setup runs in the isolated environment after verified Arras
installation and before installing the consumer with `--no-deps`; the caller is
responsible for its own public dependency cohort. Theme setup runs only with a
selected theme target and does not itself establish rendered qualification.
Each setup is trusted caller code, executed without shell/eval; record its path,
digest and the resulting distribution names/versions. Before claiming a stage
against the supplied wheel, revalidate the installed Arras payload against that
verified artifact after setup/consumer installation. A setup path without its
applicable target is refused rather than executed. These inputs are test-job
composition, never document-driven or runtime plug-in discovery.

**Reusable optional jobs.** A native test job MUST explicitly provision its
selected public, hash-pinned native cohort or run a trusted caller-owned Python
setup script through the isolated interpreter. Setup and test paths are resolved
beneath the caller workspace; no free-text shell/eval is accepted. Record the
script identity and actual installed cohort. The native test process sets
`ARRAS_REQUIRE_TRUSS=1`; missing native dependencies fail rather than skip or
select memory. Any selected pytest job fails on a nonzero process status and
requires a JUnit result with at least one test and zero failures, errors or skips
before it is reported passed. Later logging/status commands MUST NOT mask an
earlier failure. An omitted optional job is `not_run`. A caller theme pytest
result alone establishes neither browser rendering, accessibility nor visual
qualification; those claims require the corresponding actual runner/evidence.


**Strict installed native artifact gate.** `tools/verify_native.py` verifies an
explicit cohort; its input is a reviewed selection, not evidence that the cohort
already passed. It accepts `--wheel`, `--cohort`, `--find-links` (a local HTML
index), `--output-json` and an optional interpreter path `--python`. A fresh
Python 3.11 environment outside the checkout runs the installed public
`python -I -m arras.conformance --backend truss`; no copied repository pytest,
shared-site path or memory fallback may supply native evidence. The caller runs
unprivileged; the gate must not attempt privilege escalation.

Cohort schema version 1 has exactly these top-level declarations:
`schema_version` (integer 1), `arras` (`version`, `sha256`), `runtime` (`python`, `sys_platform`, `machine`),
`find_links` (`sha256`), `native_wheels` and `corpus`. Every native wheel records
`distribution`, `version`, flat `filename`, credential-free HTTPS `url` and
`sha256`. The corpus records `version`, `roles` and an explicit `limits` object
mapping case IDs to the complete `step`, `error`, nullable `detail` declaration.
The default strict all-pass selection uses an empty mapping; no prospective
release's limits may be invented. Digests are 64 hexadecimal characters,
distribution identities are unique after normalization and actual runtime must
match the selected Python/platform/architecture. Input shape and wheel metadata
must agree before installation.

Verify the local index digest and exact selected URL/SHA-256 anchor membership,
then download each selected wheel into a private temporary wheelhouse and check
its bytes before importing/installing. Install those exact paths, including the
selected toolkit's `native,query,local` extras, plus the exact Arras wheel; do not
let resolution choose an alternative same-version native artifact. Base
dependencies resolve through the explicit public index with configuration/path
isolation. Record origin declarations, artifact digests, all installed versions,
installed import locations and wheel-payload parity. Inventory current-platform native binary paths/digests for every installed
distribution, including transitive native packages: ELF/`.so` on Linux,
Mach-O/`.dylib`/`.so` on macOS and PE/`.dll`/`.pyd`/`.exe` on Windows. Dormant
foreign-platform installer launchers do not become runtime cohort requirements.
Every current-platform native-bearing distribution must be explicitly selected
and verified against its independent wheel payload; an undeclared native/cache
library fails the claimed qualification rather than being hidden behind three
headline version numbers. This inventory covers distribution-declared payloads;
system dynamic linking is not independently audited and must be qualified as
such in the receipt. Declared origins alone do not establish public
accessibility or prior native qualification.

The auxiliary installed-metadata probe derives the complete applicable ID set
from the installed corpus and role-tag selection, without fixed case counts.
Compare its installed harness limit dataclasses exactly with the complete cohort
mapping; the corpus runner remains responsible for exact step/error/detail
matching, with no diagnostic-message reinterpretation. The CLI must exit zero,
produce one nonempty compatible report, have unique result IDs equal to the
applicable set and skipped IDs equal to its exact complement, and report counts
that match all outcomes. Failed, harness-error, unknown or incompatible outcomes
fail. A run with documented limits is labeled with those limits; an all-pass
claim requires none. Preserve failed attempts and cleanup errors as failures,
not later logging success. Keep CLI status/stdout/stderr and the partial input/
probe evidence when validation fails. Receipt output must not overwrite a
selected input, including through an alias or the failure path. Timeouts require
bounded cancellation and owned-resource checks before temporary directories are
removed; never inspect or terminate unrelated PostgreSQL instances. The output records pending/failed/passed qualification
and the actual artifact/runtime/corpus scope; no other platform, managed host or
semantic profile follows from it.

## Precedence and Compatibility

- Versioning: v6, the operations and shapes this contract states; `arras.CONTRACT_VERSIONS["backend"]`. The conformance corpus is version 13.
- Ordering or precedence: the backend's own access controls decide access and win over everything; the capability descriptor decides what Arras offers.
- Backward compatibility: adding an optional operation or capability is compatible; removing or changing one is breaking.
- Deprecation: as CONTRACT-001.

## Error Semantics

| Condition | Outcome | Retry | Recovery |
|-----------|---------|-------|----------|
| The backend is unreachable | `Unavailable` with the reason | yes | See CONTRACT-005 |
| The backend's controls deny the principal | `Refused` | no | Request access |
| A statement Weft or the backend's declared profiles do not serve | `Unsupported` | no | Read `describe().weft` |
| A token the backend has not reached | `NotYetCurrent` after the bound | yes | Retry or read `latest` |
| A malformed token | `Invalid` | no | Use a receipt's token |
| A token the backend can tell was never issued | `Invalid` | no | Use a receipt's token |
| A well-formed token the backend cannot classify (on Truss: another installation's token, an unissued same-installation token, an unreadable receipt) | `Unavailable` | yes, raised at once | Use a receipt's token, or retry |
| Whether a token is reached cannot be determined (no evidence, source or epoch mismatch, observation failure) | `Unavailable` with the reason | yes | Retry; read `latest` |
| The database holds a Truss release other than the pinned one | `Unavailable` (`unsupported_version`) | no | Recreate the database (Truss 0.0.45 installs runtime 0.72 on an empty database only and refuses `upgrade_in_transaction` for every source) or use an Arras that pins the matching Truss |
| The principal may not ask `reached` (a non-member) | `Refused` | no | Request access |
| Truss quarantined the connection | the call raises `Unavailable`; Arras closes the connection | yes, on a new connection | The host's pool discards it |
| The same idempotency key is repeated by another person | applied as a new request (documented limit), not a replay | n/a | Use a key per person |
| The commit of a write is unknown | `Unavailable`, with the outcome unknown; repeating the same request id returns the original or applies afresh | yes, with the same request id | The adapter repeats the request id once on a new connection; a keyed caller may then repeat the invocation with its key; for a keyless invocation an `Unavailable` raised after the adapter's own repeat is final and the outcome is unknown |
| A committed write's token cannot be obtained | `Unavailable`; the write stands | yes, with the same request id | Keyed callers repeat the invocation with its key; a keyless caller gets the adapter's single repeat of the request id and no other |

## Examples

```text
describe() -> BackendInfo(name="memory_replica", roles=("reader",),
  capabilities={"catalog.UseCase": Capabilities(read=True, columns=["code", "workArea"], relationships=["uses"],
                count=True, mutable=False, latency_class="batch")},
  weft=WeftSupport(version="weft-sql/0.2.0", profiles=("count-summary",)))
```

## Non-Normative Notes

The adapter operations are the ones the client interactions need once reads are a single `query`. Because the stores behind the adapters may change, the contract is the stable part: the corpus is written first, then each adapter is built to pass it. Whether Arras should wait inside `query` for a replica to reach a token, or leave the wait to the caller, is open (CONTRACT-001).

## Later public 0.0.49 adoption — separate unqualified tranche

This amendment governs the later adoption branch only. It does not change the
independent frozen release's 0.0.48/0.4.51 cohort or its historical evidence.
Public Truss 0.0.49 has native digest
`288801f7177338328441b5d3ce9328af31740ebf513f04ea45e30ae316a9f3a4`;
its shared `0.74-candidate` release label alone does not identify those bytes.
Its exact server admission remains PostgreSQL `180006`; Lakebase correspondence
requires actual target evidence, not a hostname, product label or local pass.

`create_backend` and `TrussBackend` gain keyword-only
`tolerated_grantees: tuple[str, ...] = ()`. Arras accepts an immutable exact tuple
with at most 32 exact nonempty UTF-8 names, each at most 63 bytes and without NUL.
It preserves the names without coercion, patterns, discovery or normalization.
Upstream Truss owns native identity/reserved-role/ACL interpretation. Only fresh
installation forwards the tuple; an installed/reconnected backend uses stored
policy and cannot widen trust from fresh host configuration. Empty remains strict.
Tolerance preserves existing platform authority; it creates no platform grants,
membership or ordinary-person access and weakens no protected-profile refusal.

A contained public `InstallRefused(third_party_grant)` maps to
`Unavailable(migration_failed)` with the bounded JSON-escaped role name and closed
object-class/phase context. Arbitrary server or ValueError text is not exposed.
Malformed context yields a fixed safe refusal. A typed grant refusal cannot be
relabeled by the legacy opaque CREATEROLE fallback. Original rollback,
cancellation, unknown settlement and quarantine meanings retain precedence.

Actual managed qualification is separate: the adapter requires idle supplied
connections and owns each operation's transaction. Caller-active transaction and
savepoint claims require separately labelled direct public Truss-host evidence.
The metadata-only UMF profile remains unsupported by Truss; this adoption does
not introduce an official value/action runtime or Ashlar support.
