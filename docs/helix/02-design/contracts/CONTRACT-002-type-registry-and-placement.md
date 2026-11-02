---
ddx:
  id: CONTRACT-002
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-002
      kind: informed_by
    - id: ADR-013
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-003
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-006
      kind: informs
    - id: ADR-011
      kind: informed_by
---

# Contract: Type registry and placement

**Contract ID**: CONTRACT-002
**Type**: library
**Version**: v2
**Status**: draft
**Related**: FEAT-002, ADR-011, ADR-013, CONTRACT-001, CONTRACT-003, CONTRACT-004, CONTRACT-006

## Purpose

Defines the document a module supplies to define its types, relationships and actions; how the host places a module (which backend is its record store, which are replicas, which provide its actions); how the registry accepts it; and how a client enumerates what the ontology holds and what each backend can do with it.

Terms. UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions. A backend is a named store the host configures (CONTRACT-004) with the roles `reader` (serves graph reads) and `provider` (applies actions). A module's record store is the reader that is the system of record for its graph; a replica is another reader that serves `bulk` and may lag. A placement is the host's statement of a module's record store, replicas and providers. An ADR is an architecture decision record. GraphQL is the API query language that CONTRACT-006 binds.

## Scope and Boundaries

- In scope: the module document and its constraints, placement, registration (as the administrator and as the person), validate-only registration and attachment, the ontology revision, enumeration, capabilities, name rules, compatibility rules.
- Out of scope: what the types mean (the owning module), how a backend stores them (CONTRACT-004), the action contract (CONTRACT-003), the GraphQL schema built from the registry (CONTRACT-006).
- Owning system or team: Arras. Documents are owned by each module.

## Normative Surface

**Module document.** A module is defined by one UMF document and nothing else. Arras has no schema format of its own. The document is UMF core 0.10.0 (the version the providers accept), passed to the registry as received bytes or text, never as a re-serialized object, because the backend records its bytes and digest.

**Declared vocabulary version.** The supported DDD interpretation is `umf.ddd`
0.1.0. When the document declares `umf.ddd`, its declaration MUST be an object
whose `version` is exactly `0.1.0`; an absent, malformed or different version is
`invalid_document` at `vocabularies.umf.ddd.version`, before registration changes
anything. A recognized vocabulary name alone MUST NOT establish interpretation
support. This rule does not require DDD on every core record or establish support
for other vocabulary versions, constraints or action profiles.

**Explicit host resources.** A downstream host MAY package its own module,
seed and graph resources and load them through the public registration/import
operations. The host selects those resources explicitly; registration MUST NOT
implicitly load bundled demonstration modules or discover/execute Python from a
document. A Python shim re-exports deliberate public APIs without changing their
canonical identity. Source bytes and unsupported-meaning refusals remain governed
by this contract; using an own namespace does not establish a new UMF profile.

**Admission and executable capability.** Official UMF model validity, validation
completeness and a backend's ability to execute a declared profile are separate
results. `valid` and `complete` MUST NOT alone advertise runtime constraint or
action support. Registered source bytes remain authoritative and preserved;
a reduced `ModuleInfo` projection MUST NOT erase an obligation before capability
selection. The bounded memory mutation profile in CONTRACT-004 may refuse writes
while registration and authorized metadata/graph reads remain available. This
interim safeguard does not replace official admission or add a constraint evaluator.

### Official source admission and core metadata profile

The additive programmatic surface is `arras.umf_admission`; it does not replace
the default legacy reader. `admit_document(document: bytes | str)` returns an
immutable `AdmissionReport`. `project_document(document: bytes | str)` admits
SOURCE afresh and returns a `ProjectionReport`, never accepting a report as an
authority ticket. Other input types raise `TypeError`; text that cannot encode
as strict UTF-8 raises `ValueError` before a report exists.

| Public value | Fields and invariants |
| --- | --- |
| `UmfDiagnostic` | `authority` (`umf` or `arras-source`), `code`, `path`, `message`, `severity`; copied in official order without semantic reinterpretation |
| `AdmissionReport` | Exact immutable `source: bytes` with `field(repr=False)`, `source_sha256`, `engine_distribution`, `engine_version`, `validation_profile`, `validation_status`, `valid`, `complete`, immutable `diagnostics` tuple |
| `ProjectionIssue` | `path`, `code`, safe `message`; consumer projection issues, not official validity diagnostics |
| `ProjectionReport` | `admission`, `profile`, `supported`, immutable `issues` tuple, fresh unplaced `module: ModuleInfo | None` |

The selected authority is the released pure `umf-core` 0.10.0 wheel from public
tag `umf-v0.5.4`, SHA-256
`49633924b45a3c8499d4fcc1a24c30d5a8fcb34d974ab019bbda987cb47da0f9`.
Every production admission creates a fresh internally owned EMPTY official
`Registry`, profile `umf-core-empty-registry/1`. No host registry, schema-only
DDD/view registration, document-driven callback, codegen or semantic fallback is
accepted. Engine identity names the selected distribution/version; an expected
digest compiled into Arras is not observed installed-artifact evidence.

Official JSON reading precedes `validate_document(raw, registry)`. Only its
returned Validation establishes `validation_status="completed"`: `valid` and
`complete` are the exact official booleans and diagnostics remain ordered.
Lexically valid structural negatives therefore retain official diagnostics,
instead of being replaced by a typed-reader exception. `read_document` or
`checked_copy()` MUST NOT substitute for semantic validation.

An Arras source bound of 16 MiB, strict UTF-8 decoding refusal or official JSON
reader refusal yields `validation_status="not_run"`, `valid=None`, `complete=None`
and a safe `arras-source` diagnostic (`source_limit` or `source_profile`, path
`document`). This means official `validate_document` did not run, not that UMF
found the document invalid. Constructors reject inconsistent combinations.
Unexpected engine exceptions remain failures, not fabricated invalid reports.
Missing optional engine support raises `Unsupported` naming the extra/profile.
No replacement decoding, exception-prose parsing or second validator is added.

The public values expose no mutable official Document, Registry or shared raw
mapping. Mutating a returned metadata summary cannot alter later admission or
registration. Source-only repr redaction does not make official diagnostic text
safe: it remains untrusted source-derived content, not automatically emitted to
logs, telemetry or transport errors.

Projection `umf-core-metadata/1` requires completed admission with `valid is True`
and `complete is True`, then these separately checked consumer limits:

- Exactly one module, one core record, all its explicit direct-field members and
  exactly one explicit primary key referencing one required STRING field of
  cardinality one. No alternate/composite key or unprojected element.
- Other fields use only the existing string/integer/decimal/boolean/binary/
  timestamp families, explicit cardinality one and required or absent-allowed
  nullability. Missing/unspecified requiredness, containers, references, value
  records and relationships are outside this profile.
- No actions, nonempty facets or nonempty semantic types are projected. The
  presence of a default, allowed-values or rules declaration is unsupported,
  including an empty/null declaration where official admission permits it.
  Other empty slots are accepted only where official admission accepts them.
  No constraint or action evaluator is introduced.
- Actual module/record/field IDs determine identity and still satisfy Arras and
  GraphQL name rules. Namespace/title/display name never renames an opaque ID.
  Descriptions, aliases, examples and unknown content remain in original source;
  ModuleInfo is an explicitly reduced summary.

Issues use `invalid_name`, `missing_key`, `incomplete_interpretation` and
`unsupported_projection` with source pointers. A valid but unprojectable
document remains officially valid. Unknown meaning can be valid/incomplete and
is refused by projection. The existing STRING key VALUE carrier remains
`[A-Za-z0-9._:-]{1,128}`; metadata admission executes no keys and promises no
broader UMF key carrier.

Hosts explicitly select `metadata_profile="legacy-arras/1"` (default) or
`"umf-core-metadata/1"` on the Arras constructor/start. The model's
`MetadataProfile` literal names those choices; unknown choices raise constructor
`ValueError` without engine import or I/O. No TOML/environment/CLI selection,
mixed-dialect auto-detection or change to legacy `parse_module` is added.

ModuleInfo gains final defaulted `metadata_profile="legacy-arras/1"`. Changing
an existing module's profile is `incompatible_change`, never a silent
interpretation switch. New-profile placement requires explicit CONTRACT-004
qualification by its record store and every replica before acceptance, dry-run,
attach, preparation or CAS; otherwise `Invalid(invalid_placement)` at `placement`.
This is the no-applicable-store placement exception, not an official invalidity
or a claim that schema authorization ran on a provider deliberately not called.

Existing authority/order remains: admin Registry checks admin/token/current
catalogs before parsing and placement. Person Schema checks require-user, parses,
resolves record placement and provider role, then checks profile qualification
before backend `validate_register`. Once qualified, current schema authorization,
host/GraphQL checks, revision handling and acceptance/CAS keep their order.
Catalog/descriptor reads remain permitted; legacy precedence is unchanged.

The first qualified integration is metadata-only memory registration/dry-run,
description, document readback and authorized empty-graph reads. No implicit seed
or data mutation is enabled. RegisteredDocument exposes lossless UTF-8 text:
`registered.text.encode("utf-8") == admission.source`. Rewritten-equal documents
retain the held revision/source; meaning changes follow existing revision rules.

Official admission/projection is guaranteed by the source-taking Arras Registry
and Schema routes, which rederive metadata from source. Direct provider
`register(document, ModuleInfo)` / `validate_register` remain trusted host-metadata
operations: their caller supplies the source-to-summary correspondence. They do
not independently attest official validity, and a hand-built ModuleInfo or report
is not such an attestation. The memory backend does not gain an admission import
or reinterpret the source. Its descriptor promises preservation/readback of
host-derived metadata, not another validation boundary.

| Element | Rules | Notes |
|---------|-------|-------|
| Module | The document MUST define exactly one module and its `id` is the module name, matching `[a-z][a-z0-9_]{0,40}`. A document may reference other modules' types but MUST NOT define them. | The module is the unit of ownership, access and placement. |
| Entity type | A UMF record with identity. Its fields are its properties. | A record without identity is a structured value inside its owner. |
| Key | Exactly one named key marked primary, of exactly one field, a required string field. | The key is the entity's identity. A key value is 1 to 128 characters matching `[A-Za-z0-9._:-]+`. |
| Properties | A field's type is a scalar family (string, integer, decimal, boolean, binary, timestamp) or a structured value; its cardinality is one, optional or many. | No float and no arbitrary JSON; use a decimal, or model a structured value as a record. |
| Relationship | A UMF relationship defined in the module, with its `source` and `target` types, multiplicities, lifecycle, direction and inverse. | The relationship belongs to this module whatever modules its endpoint types are in. An instance is unique by relationship, source and target. |
| Cross-module endpoints | A relationship may name a type in another module. | The registering principal MUST be able to read that module (`unreadable_module` otherwise). A relationship whose endpoint is held by another record store is a reference (CONTRACT-001). |
| Actions | UMF actions defined in the module (CONTRACT-003). | |
| Placement | None. The document carries no placement; where a module lives is host configuration (Placement, below). | A module is defined by its UMF document alone. |
| Unsupported UMF at registration | The selected reader/profile refuses unsupported constructs with their named source paths; legacy registration retains `invalid_document`. | Independent official admission validity/completeness remains distinct from projection or provider capability. |
| Presentation vocabulary | A document may declare the vocabulary `arras.view` 0.1.0 (CONTRACT-010). Its terms are checked at registration with their own codes (`view_*`) and paths, and the registry is unchanged on any fault; they change no type, relationship or action, so a document registers to the same registry with and without them. | The `arras.view` cases (`arras.conformance.views`). |

**Placement.** The host passes `placement={"<module>": Placement(record, replicas=(), providers={})}` and optionally `default_placement=Placement(...)` to `Arras.start` (CONTRACT-005). The MCP process builds the same placements from the committed configuration files (`[placement]` and `[modules.<module>]`, CONTRACT-007), never from environment variables.

- `record` is the module's record store: a backend with the reader role that is the system of record for the module's graph. It serves `latest`, holds the registered document and the catalog revision, and must see the effects of the module's providers. Each module has exactly one record store; different modules may have different ones.
- `replicas` are other readers, in preference order, possibly none. They serve `bulk` and may lag.
- `providers` maps an action name (`module.Action`) to the name of the backend that applies it. An action with no entry runs on the record store, which must then be a provider, else the action is `Unsupported`.
- A placement is valid when the record store is a configured reader, each replica is a configured reader, every provider named is a configured backend with the provider role, and no reader is named twice. Otherwise the module is refused as `invalid_placement` at `register` or `attach` and is not served. A module with neither an entry nor a default is refused the same way. A configured backend that is down is a status, not a refusal.
- The document carries no placement; there is no compatibility rule about changing one. Changing a module's placement is a host reconfiguration, not a registration; moving a module's record store is a data migration outside Arras, and the new record store must hold the module.
- A backend's `catalog()` returns the modules it holds without placement (CONTRACT-004); Arras attaches the host's placement when it answers. A backend's copy of a module counts only if that backend is in the module's placement; a module with no placement is not served. `ModuleInfo.placement` carries `record`, `replicas` and `providers`.

**Placement semantics.**

- Routing: `invoke`, `validate`, `invoke_batch` and imports go to the provider the placement names for the action, the record store by default (CONTRACT-003). `latest` reads go only to the record store (CONTRACT-001). `bulk` goes to the first replica that serves the statement, else the record store. An unavailable backend raises; there is no silent fallback.
- A receipt's token is the providing backend's opaque position; `at_least(token)` waits on the serving reader's `reached(principal, token)`, asked as the person. A replica whose feed has not yet carried another provider's token does not reach it, so the read raises `NotYetCurrent`. Read-your-writes across providers is `at_least`; Arras promises it no other way.
- A module whose record store is not a provider cannot have actions unless the placement names a provider for them, and is attached rather than registered.

**Operations** (on `Registry`, from `Ontology.registry()`). `registry()` is called only by the host's administrative principal (CONTRACT-005), at startup, for `register`, `attach` and `bind_handler`.

| Operation | Shape | Rules | Notes |
|-----------|-------|-------|-------|
| `register(document, *, unknown_endpoint="reject")` | `-> RegistryResult` | For a module whose record store is a provider that accepts catalog revisions. Accepts the document as an ontology revision on the record store, with the principal's user recorded as the revision's origin actor, following the backend's acceptance rules: one transaction, a rejected document changes nothing. Before accepting, `register` MUST build the GraphQL schema for the module (CONTRACT-006) and refuse with `invalid_name` on any error, and MUST apply the compatibility rules below. If the derived rows equal those in force it returns the current revision and creates none. `unknown_endpoint` is the backend's policy for an endpoint no document defines: `reject`, or `provisional`. | `RegistryResult` has `module`, `revision`, `changed: bool` and `report`, the backend's acceptance report. Requires the record store's `schema` grant (CONTRACT-004) for the principal that calls it; `Ontology.registry()` is administrative (CONTRACT-001, CONTRACT-005). |
| `session.schema().validate(document, *, unknown_endpoint="reject")` | `-> SchemaPlan` | Runs everything `register` runs (parse, names, placement, cross-module readability, the servable GraphQL schema, the compatibility rules on the record store) and applies nothing: no revision, no journal row. The record store's grant is checked before any of it is answered, so a person without the `schema` grant is `Refused` whatever the document holds and learns nothing of the host's placement, except that where the host placed the module nowhere, or its record store takes no revisions, there is no store to ask and the answer is `Invalid` (`invalid_placement`). A document that does not parse is `Invalid`. A parsed document that cannot be registered is an answer (`ok: false`, every violation with its rule and count or offenders), not an error; a refusal, an outage or a record store with no dry run is raised as for any operation. Runs as the person, under the `schema` grant. | `SchemaPlan` has `module`, `ok`, `violations`, `changed` (false when the derived rows equal those in force), `revision` (the module's current revision, null for a module the record store does not hold), `changes` (`SchemaChange`: `kind` `added`, `changed` or `retired`; `element` `type`, `property`, `relationship` or `action`; module-qualified `name`; short `detail`, never a record value) and `report`. |
| `session.schema().register(document, *, unknown_endpoint="reject", expected_revision=None)` | `-> RegistryResult` | As `registry().register`, run as the person under the `schema` grant. `expected_revision` is the revision a plan answered with; it is passed to the record store, which checks it in the same serialized step as the acceptance, so a record store at another revision is `Conflict` (`revision`) and applies nothing. | The surface that binds `validate` and `register` over HTTP is CONTRACT-011. |
| `attach(document)` | `-> RegistryResult` | For a module whose record store is not a provider. Records the module's types and placement so clients can discover and read them, without changing the record store. | The document is the record store's own export. |

`ModuleInfo` has `name`, `placement`, `revision`, `entity_types`, `relationships`, `actions`, `value_types` (the structured values), `status` and final defaulted `metadata_profile`.

In v1 a relationship has one type at each end, because the console and the MCP binding name the type on the other end of a key; a document with several is refused as `invalid_name` at `register`.

- `status`: per backend named in the placement, the backend's `BackendStatus` (CONTRACT-004): `available`, `reason` (`not_configured`, `unreachable`, `access_denied`, `migration_failed`, `unsupported_version`), `detail`, and for a replica `position` and `lag`. `detail` never contains credentials.

- `EntityTypeInfo`: `name` (module-qualified), `key` (the primary key property), `properties` (each `name`, `scalar` or structured value, `required`, `cardinality`), `capabilities`.
- `RelationshipInfo`: `name`, `source` and `target` (lists of module-qualified type names), `source_multiplicity`, `target_multiplicity`, `lifecycle`, `inverse`.
- `ActionInfo`: `name`, `description`, `inputs`, `preconditions`, `effects` (CONTRACT-003).
- `Capabilities`: per backend serving the type, `read`; `mutable`; and `latency_class` (`interactive` or `batch`), which Arras uses; and `columns`, `relationships` and `count`, which describe what a client can build on (the properties and relationship names the backend serves, and whether it serves counts) and do not decide what `query` accepts. What a statement may contain is Weft's and the serving backend's to decide (CONTRACT-001, Query language; CONTRACT-004). It is the descriptor a backend supplies (CONTRACT-004); `Ontology.describe` returns it (CONTRACT-001).

**Registered document.** The record store keeps the document it accepted at each revision, byte for byte, and `Ontology.document(module)` returns it (CONTRACT-001, Registry reads; CONTRACT-004). Registering a document whose derived rows equal those in force creates no revision, so the text kept is the one first registered at that revision, even when the new bytes differ in whitespace, key order or escapes; any change of meaning (a description included) is a new revision with its own text. Arras reads only the current revision's document; reading an earlier revision's is not part of v1.

**Ontology revision.** `Revision` is a map keyed by backend name. A module's revision is the one its record store's catalog entry carries: the record store names itself, `{"memory": 3}`, and its value is the record store's catalog revision, which may be one number for the whole store and advance when any module registers a change. A record store that keeps a revision per document (Truss) states each module's own: the catalog revision at which the module's current bytes were accepted, which does not move when another module registers. Arras does not compose a revision across the placement. A backend that publishes a release of its own (a replica, for instance) may add its own entry; a replica holds the record store's revision for the module it was attached. A value is an integer, text, or null while unknown, and is opaque and not comparable across backends. On the wire it is a JSON object keyed by backend name, `{"memory": 3, "memory_replica": null}`. An answer states the revision it was computed under. A caller that states an `expected_revision` names the backends it checks (CONTRACT-009): every backend named must be at the stated revision, and a backend not named is not checked.

**Names**: a type, property, relationship or action name MUST match `[A-Za-z][A-Za-z0-9_]{0,63}`, MUST NOT begin with `_`, and MUST NOT be a reserved name: `Query`, `Mutation`, `Subscription`, `Entity`, `Page`, `Ref`, `Freshness`, `Revision`, `Module`, `Status`, `JSON`, `DateTime`, `BigInt`, `Decimal`, `Base64`, `String`, `Int`, `Float`, `Boolean`, `ID`, `ref`, `key`, `type`, `version`, `revision`, `freshness`, `references`. A type name MUST NOT end in `Page` or `List`, because generated names use those suffixes. Two names in one module MUST NOT differ only by case or generate the same GraphQL field name (CONTRACT-006). A name is also a UMF element name, unique within its module.

## Precedence and Compatibility

- Versioning: this contract is v2 in the public API catalog; it has no separate runtime contract key. Ontology revisions are the backends' own (CONTRACT-004). A record states the revision under which it was last written.
- Ordering or precedence: a registration is atomic on the record store and serialized with every other registration there; a replica learns of it through the feed. The previous revision stays in force if a registration fails.
- Compatibility rules, applied at registration. They are stricter than a backend's, so no accepted change rewrites records:
  - Adding an entity type, a relationship, an action or an optional property MUST be accepted.
  - Adding a required property MUST be refused while records of that type exist, with their count. Add it as optional, fill it, then make it required.
  - Making an optional property required MUST be refused while any record lacks it, listing the offenders.
  - Changing a property's type or cardinality MUST be refused.
  - Changing, adding or removing an entity type's key MUST be refused.
  - Removing a type or property while records of it exist MUST be refused with the count. With none, the backend retires it, its identifier stays reserved, and declaring the same name again is refused.
  - Removing an entity type that a relationship or action names MUST be refused.
  - Changing a relationship's endpoints MAY widen them and MUST NOT narrow them while instances exist.
- Contract compatibility: accepting a further UMF construct is compatible. Refusing one Arras accepted, or changing a constraint above, is breaking and requires v2.
- Deprecation: as CONTRACT-001.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|-----------------|-------|----------------------|
| Invalid, reserved or colliding name | `Invalid` (code `invalid_name`) | no | Rename |
| Relationship names an undefined type | `Invalid` (code `unknown_type`) | no | Define the type, or use `provisional` |
| Relationship names a module the principal cannot read | `Invalid` (code `unreadable_module`) | no | Be granted read access to that module |
| An entity type has no key, or the key is not a required string | `Invalid` (code `missing_key`) | no | Declare the key |
| The document fails UMF validation, defines other than one module, or uses an unsupported construct | `Invalid` (code `invalid_document`) with the backend's violations | no | Correct the document |
| An incompatible change | `Invalid` (code `incompatible_change`) naming the rule and the count or offenders | no | Add the property as optional, or migrate records first |
| No usable placement: none for the module and no default, a backend not configured, of the wrong kind, or named twice | `Invalid` (code `invalid_placement`) | no | Configure the placement with a reader as record store, readers as replicas and providers with the provider role |
| The record store is not a provider and `register` was called | `Invalid` (code `read_only_module`) | no | Use `attach` |
| The catalog lock is not granted in time | `Unavailable` (reason `busy`) | yes | Retry later |
| The principal lacks writer access to the module | `Refused` | no | Request the grant |

## Examples

```python
doc = open("catalog.umf.json", "rb").read()      # module "catalog", records UseCase and Solution; the host places it on record store "memory", replica "memory_replica"
registry = ontology.registry()
registry.register(doc)          # RegistryResult(module="catalog", revision={"memory": 1}, changed=True)
[m.name for m in ontology.describe()]           # ["catalog"]
ontology.describe("catalog")[0].entity_types[0].capabilities["memory"].columns   # ["code", "name"]
```

[`examples/catalog.umf.json`](examples/catalog.umf.json) is the document. It follows the shape of the sales model that UMF's library validated in SPIKE-002 (records with a `umf.ddd` entity extension, field elements with facets, a primary key, and an authored relationship) but it has not itself been run through UMF's validator; the corpus's `umf` cases are where such a document gets its expected diagnostics. The example's field names are checked against UMF before the contract is final. The examples in CONTRACT-001, CONTRACT-003, CONTRACT-005 and CONTRACT-007 also use properties and types that this document does not declare (`workArea` on `UseCase`, `status` on `Solution`, the `CoverageAssertion` type and its `derivedFrom` relationship).

## Non-Normative Notes

The name rules exist so every declared type can become a GraphQL type without renaming (ADR-011). The record store owns UMF's meaning, document ordering and the derivation of catalog rows; Arras does not restate them. A document another tool produced as UMF is registered as it is, provided it meets the constraints; unknown endpoints are the case `provisional` exists for. A helper that builds a UMF document from Python objects can exist outside this contract and `arras.__all__`.

Arras's current executable profiles do not supply field defaults, a per-type
switch accepting undeclared properties, or float/arbitrary-JSON values. Official
admission may preserve a default or other meaning that the selected metadata or
execution profile refuses; preservation is not execution support.

Open points: a primary key declared in UMF as several fields is refused in v1; whether a retired name may be redeclared once the backend defines it; and who supplies the Python UMF reader (a port of UMF's validator, or an adapter), which must pass the corpus's `umf` cases before Arras can claim conformance.

## Planned bounded action-source binding

The next action slice MUST bind the same exact source bytes used for generation
and registration to its module, source SHA-256, trusted owner scope and current
provider registration revision. A caller-supplied owner label or digest is not
authority. Current ownership and authorization come from the qualified
provider/host registration boundary; a process-local identity registry cannot
stand in for native ownership or CAS.

The first Arras-owned candidate profile is `arras-umf-set/1`. It qualifies one
dedicated memory store and one immutable source registration. The first
authenticated schema principal owns that source. Exact same bytes and same
owner are idempotent; another owner is refused. Every source change, including
an upgrade, downgrade or equivalent JSON with different bytes, is unsupported
before effects. Broader upgrade/retirement/dependency policy remains later work.
The host source pin is `sha256:<lowercase exact-source SHA-256>`; it is distinct
from UMF core version, publisher version and the provider's opaque catalog
`Revision`. None implies an ordering of another.

The selected host registration path derives metadata from original source
through the official bridge. Caller-provided reports or `ModuleInfo` values
cannot establish admission or ownership. Registration, source rebinding,
administrative import and action commit share the candidate store's lock and
CAS boundary; a host-only earlier check cannot replace it. Mixed legacy and
candidate write paths in this dedicated store are unsupported.

This is an implementation contract for the candidate, not a change to
`umf-core-metadata/1` or an assertion of qualified execution. Existing
admin/token/catalog, person-schema, placement and provider authorization
precedence remains unchanged. Qualification requires the actual official
action/value binding and whole-path evidence in the integration plan.
