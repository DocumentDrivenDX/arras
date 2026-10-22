---
ddx:
  id: truss-catalog-mapping
  type: design-note
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-21
  authoring:
    home: repo
  links:
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: truss-requirements
      kind: informed_by
    - id: truss-group-mapping
      kind: informed_by
---

# Mapping `catalog`, `document`, `register`, `validate_register`, `describe` and `status` onto Truss

How the Truss adapter's registry operations (CONTRACT-002, CONTRACT-004) sit on `truss-toolkit` 0.0.45 (native runtime `0.72-candidate`), as built in `arras.adapters.truss.registry`, `cache` and `describe`, and verified against a real Truss on PostgreSQL 18.6. [truss-group-mapping.md](truss-group-mapping.md) covers writes.

## Calls

Every call runs inside a `Call` of the connection layer: one person's connection, one transaction, one Truss host and assembly, settled by the layer. Truss returns `Outcome` (`Ok(value)` or `Error(ExecutionFailure)`); a reader call's typed refusal is an `Ok` value, so the adapter checks the class of every value it unwraps. Truss never commits; the layer does.

```text
assembly.reader_catalog_if_changed_in_transaction(tx, validator=, maximum_bytes=)
        -> ReaderCatalogSnapshot(catalog, validator) | ReaderCatalogUnchanged(validator)
         | CatalogRefused | CatalogUnavailable | CatalogInvalid
assembly.query_with_catalog_in_transaction(tx, sql=, document_ids=, catalog_validator=, maximum_bytes=)
        -> QueryCatalogRead(result, catalog, documents) | QueryRefused | QueryUnavailable   # a read's one operation
assembly.accepted_document_in_transaction(tx, document_id=) -> AcceptedDocument | CatalogRefused | CatalogUnavailable
assembly.registrar_status_in_transaction(tx)             -> RegistrarStatus(can_register) | CatalogRefused | CatalogUnavailable
assembly.person_runtime_status_in_transaction(tx)        -> PersonRuntimeStatus(installation, catalog) | LifecycleRefused
assembly.status_in_transaction(tx)                        -> CatalogRuntimeStatus   # a registrar's read, kept for the head of one with no read
assembly.prepare_catalog((CatalogDocument,)) -> PreparedAcceptance   # raises PreparationRejected
assembly.accept_in_transaction(tx, prepared, request_key=, origin_bytes=, expected_documents=(CatalogDocumentExpectation,))
        -> CatalogRegistration | CatalogUnchanged | CatalogAcceptanceRefused | CatalogCASConflict
```

## Identity and revision

- **Document id.** Truss requires a document's id to equal the UMF document's own top-level `id`; a document with none, or another, is refused at preparation. The adapter derives it from the bytes and refuses a document with no string `id` as `Invalid` (`id`, `required`). It is not the module name. The module's id is the document's one module.
- **Module name and document id.** Truss accepts the same module id under two document ids and refuses a different module under an existing document id (`unsupported_profile`). The adapter refuses (`Invalid`, `document_id`) a registration whose module the person can read under another document id.
- **Revision.** Truss revisions are global and dense: each changed registration adds exactly one to the catalog head, an unchanged one adds none. A module's revision is `AcceptedDocument.source_catalog_revision`, the head at which the document's current bytes were accepted (the reader catalog's entry states it too, as `sourceCatalogRevision`): it stays put while other documents register. It is the revision `catalog`, `document` and `register` return, as `Revision({backend name: n})` (the host's name, never `truss` by default), so an `expected_revision` taken from `document` matches the catalog's. The head is never a module's revision, because core re-reads the catalog when a revision changes.
- **Document revision string.** The adapter passes the document's sha256 hex as `document_revision`. Truss calls a document unchanged only for the same bytes and the same revision string.

## `catalog(principal)`

One read-only call: `reader_catalog_if_changed_in_transaction` (with `maximum_bytes` 16 MiB, since the default 1 MiB cuts a large catalog short), then for each entry the accepted document, parsed with Arras's own reader for types, relationships and actions (the reader catalog carries no actions). Modules are returned unplaced: placement is the host's.

**The conditional read.** The adapter keeps each person's last snapshot with the validator Truss gave it (at most 1,024 people, the oldest dropped) and presents the validator on that person's next call. Truss answers `ReaderCatalogUnchanged` (no catalog payload) or a new snapshot. The answer is the person's access at that call: Truss re-answers it as the connected person every time, a validator names one person's view and grants nothing (another person's first call presents none, and Truss answers a person with a stranger's validator a snapshot of that person's own catalog), and a refusal with a validator in hand is `CatalogRefused`: the snapshot is dropped and the call is answered as a person with no modules. A revoked role is therefore refused on its very next call, whatever was cached. What the snapshot saves is the catalog payload (41.7 KB at three modules), not the call or the access check: every operation still makes one conditional read as the person.

A person who may read none is answered `CatalogRefused`, which the adapter turns into an empty mapping so core's `unknown_type` path stays; a document Truss will not show whole (a multi-module document partly readable) or Arras cannot parse is skipped. On an install with nothing registered (head 0) the conditional read answers `CatalogUnavailable('profile')` (`0A000`, the code a release mismatch gives), so a read that failed that way asks the person's runtime status (`person_runtime_status_in_transaction`, open to any enrolled reader, writer or auditor): `catalog = empty` is an empty mapping for `catalog` and `Refused` (`no_access`) for `document`, and `register` and `validate_register` take head 0 from it (the first registration is keyed `register:0:{sha256}`). A person who is enrolled in nothing gets `unauthorized` there and sees `unsupported_version` on an empty install. `CatalogUnavailable` is `Unavailable` (`profile` is `unsupported_version`, `installation` is `not_configured`, `observation` is `busy`, `resource` is `unreachable`).

**The combined read.** A `latest` read of a module the person was shown does not read the catalog in a transaction of its own: the `catalog` call keeps, beside the snapshot's validator, the modules it parsed (`CatalogCache.keep_shown`), and `query_current` presents that validator to `query_with_catalog_in_transaction`. Truss's answer carries the rows, `ReaderCatalogUnchanged` or a new snapshot, and the original `QueryDocument` bytes and digest of the module's document; the adapter takes it only for `unchanged` and for a digest equal to the catalog entry's, else it keeps the new snapshot and the read goes the ordinary way. Truss's validator binds the `maximum_bytes` the catalog was read under, so the combined read passes the catalog's 16 MiB bound (measured: with the default 1 MiB every presented validator answers a new snapshot). Nothing is cached that answers access: what is presented is what the person was shown, and Truss's answer to the call says whether it is still the person's current view.

The parse cache (plan D8) keeps the parsed module per (document id, accepted digest, source catalog revision), the revision the entry states: a registration of another document leaves it valid, and a document registered, changed and registered back has the same digest at a new revision. It never answers who may read what: the catalog is asked of Truss, as the person, on every call. Reads are read-only transactions: a read-write reader call takes a share lock on the catalog head that makes a concurrent registration fail with `observation`.

## `document(principal, module)`

The reader catalog names the document that holds the module, then the accepted document returns its exact bytes. Truss cannot tell a module that does not exist from one the person may not read, and does not say which: both are `Refused` (`no_access`), not `Invalid`.

## `register` and `validate_register`

Order, matching the memory adapter:

1. **The registrar gate, first and cheap.** `registrar_status_in_transaction` as the person is `RegistrarStatus(can_register=True)` for a registrar, `can_register=False` for an enrolled person who is not one and `CatalogRefused` for anyone else, in one three-statement call. It is advisory (acceptance reauthorizes), and without it the refusal arrives after the preparation (about 0.5 to 0.9 s) and an unchanged document would never be gated. A person who is no registrar is `Refused` whatever the document holds. (The schema grant is registrar membership, installation-wide; Arras's is per module, a documented limit, D3.)
2. `unknown_endpoint`: `reject` only (`provisional` is `Unsupported`; another value `Invalid`).
3. The held document, in a read-only transaction, with the head (the conditional read's catalog revision; a registrar who may read nothing is given the head and no modules, and, if Truss refuses her the catalog, her own `status_in_transaction` states it). At head 0 there is no held document and a stated `expected_revision` is `Conflict` (`revision`). A registrar who may read none of the module cannot compare, so a stated `expected_revision` is `Refused`; without one Truss compares the bytes it holds.
4. `expected_revision` against the held document's revision is `Conflict` (`revision`), before the unchanged shortcut, as in memory.
5. Equality is JSON-structural, as in memory. An equal document returns the held revision with `changed` false and calls neither `prepare_catalog` nor `accept`: Truss would count a rewritten document a new revision. Arras does not compare `ModuleInfo`, because a view-only edit does not appear in it.
6. `prepare_catalog` (the producer in an embedded V8) runs in the same read-only call; a `PreparationRejected` is `Invalid` (`invalid_document`, `invalid_input`), `Unavailable` (`not_configured`: the producer's sources are unavailable) and any other reason (`resource`, `unsupported_profile`) is `Unsupported` ("this document"). The evidence of a registration is under 2.4 KB for every sample document (truss-registration-evidence-spec).
7. `accept_in_transaction` in a read-write transaction. `register` commits; `validate_register` rolls back, so the dry run leaves no revision and returns what Truss says in the transaction: `changed`, and `violations` for a `CatalogAcceptanceRefused`.

**Request key.** `register:{head}:{sha256}`. A key repeated with the same input returns the original result and applies nothing, so a key from the digest alone would silently lose a revert (bytes A, then B, then A again). The head read just before is in it, so a revert is a new request, and a retry after an unknown commit repeats the identical key and gets the replay (`CatalogRegistration(replayed=True)`, still `changed`).

**`expected_revision`.** The held revision is compared before accepting; when the caller states one, the accepting call carries it as Truss's document-scoped expectation, `CatalogDocumentExpectation(document_id, source_catalog_revision)` with the source revision the document was read at (zero, which requires the document absent, for one not yet held). Truss checks it inside the accepting step, under its own serialization of publication: a registration of that document that landed since is `CatalogCASConflict`, which the adapter raises as `Conflict` (`revision`) with nothing applied, and a registration of any other document does not disturb it. An exact authorized replay of the same request precedes the expectation check, so a retry after an unknown commit is answered as the replay. A call that names no revision sends no expectation (Truss's own global `expected_revision` is not used: the head moves with every document). Truss's real serialization and deadlock retries stay the execution errors they are (`Unavailable` `busy`) and are never read as a conflict. Registrations serialize on the head row without waiting: a second concurrent one is `Unavailable` (`busy`).

### Failure mapping

| Truss | Arras |
|-------|---------|
| `unauthorized`, `42501` | `Refused` (`no_access`) |
| `invalid_input` | `Invalid` |
| `request_conflict` | `Conflict` (`idempotency_key_reused`) |
| `CatalogCASConflict` (an `Ok` value) | `Conflict` (`revision`) |
| `unsupported_profile` (`0A000`) | `Unsupported` |
| `invalid_transaction` with no code, while accepting | `Unsupported`: Truss turns every `ValueError` into that one message, and a document it cannot take (a field with no `name`, a decimal other than precision 18 and scale 4, structured values) lands here |
| `observation` | `Unavailable` (`busy`) |
| `resource` | `Unavailable` (`resource`) |
| `installation` | `Unavailable` (`not_configured`) |
| `CatalogAcceptanceRefused` | `Invalid` for `register`, an answer (`violations`) for `validate_register`; each violation is `types.{record}.{field}`, `incompatible_change`, with the rule and the object count |
| anything else | `Unavailable` (`unreachable`) with Truss's code |

### What Truss 0.0.45 accepts for an existing document

New records and relationships, a new or edited action, relaxing a field's presence on the field element, and the paired optional addition to an existing record (a member, its field element and its entry in the record's `umf.ddd` `fields`, which is Arras's form of a new optional property; the original validation of the UMF producer still runs and unknown extension content is kept). It refuses (`0A000`, `unsupported_profile`) a *required* property added in that form and any other change to an extension it does not know. Those are `Unsupported` for both `register` and `validate_register`: the corpus's `registry.validate-reports-without-applying` ends at its first dry run, whose edit adds a required property, and stays a pinned limit (R16.5). Removing a record or property, key changes and retiring are refused likewise. The corpus case that registers an optional property against a revision (`registry.register-checks-the-revision-it-was-planned-against`) passes whole, and its pin is gone.

## `describe()`

Roles `reader` and `provider`, and `audit` true (the adapter serves `changes` and `loads` from Truss's audit pages: CONTRACT-004); `WeftSupport` names the dialect Truss compiles (`weft-sql/0.2.0`) when the Weft release its queries need (0.4.49) is the installed one, and no read profile: the query slice declares the profiles it proves. Capabilities per type are `read` and `mutable` with `batch` latency (reads about 0.1 to 0.2 s, writes 0.35 to 0.5 s), no columns, relationships or count and no search, until `query` serves them. `describe` takes no principal and makes no call, so it states the types the adapter has served (`catalog`, `document`, `register`); core reads the catalog before it describes, and a process that has served none states no types yet.

## `status()`

The install state is read on the installing connection (a read-only call that checks no token): Truss refuses an installer every business call but answers `status_in_transaction` for it. With no installing connection the status is the last per-person call's: `not_configured` before any call, available when a call reached Truss, unavailable with the call's reason when it could not.

| `BackendStatus` | Truss |
|-----------------|-------|
| available | `installed=True` |
| `not_configured` | `installed=False`, or no installing connection and no per-person call yet |
| `unsupported_version` | `unsupported_profile` (another release or a tampered install marker) |
| `access_denied` | `42501`, or the connection layer's `access_denied` |
| `unreachable` | a connect failure, or any other failure |

`position` and `lag` do not apply: the authority is current. `status` reports and does not raise.

## What still needs Truss

Listed with the other asks in [truss-requirements.md](truss-requirements.md): compatible evolution of an existing record's `umf.ddd` fields for a required property; a typed refusal in place of `invalid_transaction` for a document the profile cannot take; the install state for a person enrolled in nothing. Met by 0.0.45 and no longer asked: an expected revision on registration (document-scoped, R16.1), a cheap documented registrar check (R16.2), a per-module revision in the reader catalog (R16.3), a cheap conditional catalog read, and the empty-install state of an enrolled person (R16.6).
