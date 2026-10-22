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
**Version**: v1
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
| Unsupported UMF | A construct Arras or the provider does not support is refused as `invalid_document`, naming the construct. | Agreement with the reference validator is tested by the corpus's `umf` cases. |
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

`ModuleInfo` has `name`, `placement`, `revision`, `entity_types`, `relationships`, `actions`, `value_types` (the structured values) and `status`.

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

- Versioning: ontology revisions are the backends' own (CONTRACT-004). A record states the revision under which it was last written.
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

Arras has no `default` for a property, no per-type switch for accepting undeclared properties, and no float or arbitrary-JSON type, because UMF core as the backends use it has no construct for them that Arras can rely on; a module that needs one models it in UMF.

Open points: a primary key declared in UMF as several fields is refused in v1; whether a retired name may be redeclared once the backend defines it; and who supplies the Python UMF reader (a port of UMF's validator, or an adapter), which must pass the corpus's `umf` cases before Arras can claim conformance.
