---
ddx:
  id: CONTRACT-006
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-007
      kind: informed_by
    - id: ADR-011
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-005
      kind: informed_by
---

# Contract: Console GraphQL surface

**Contract ID**: CONTRACT-006
**Type**: HTTP API
**Version**: v2
**Status**: draft
**Related**: FEAT-007, ADR-011, CONTRACT-001, CONTRACT-002, CONTRACT-005

## Purpose

Defines the read-only GraphQL endpoints, generated schemas and GraphiQL page that the administration console serves, so a host can mount the console and a test can verify it without reading the implementation. It is a read binding of the ontology interface (CONTRACT-001); it adds no operation of its own: every resolver is one `query` call.

Terms. GraphQL is an API query language (graphql.org); SDL is its schema definition language; GraphiQL is the in-browser GraphQL explorer that the console serves. ASGI (Asynchronous Server Gateway Interface) is the Python standard for asynchronous web applications. An ADR is an architecture decision record; ADR-011 records the choice of read-only GraphQL generated from the type registry. A backend is a named store with the roles reader and provider, configured by the host; a module's placement names its record store, replicas and providers (CONTRACT-002, CONTRACT-004).

## Scope and Boundaries

- In scope: mounting, endpoints, the authentication hook, the meta schema, the schema generated per module, limits, errors.
- Out of scope: writes (none exist), actions, the page's visual design, any REST surface, agent tools (CONTRACT-007).
- Owning system or team: Arras.

## Normative Surface

**Mounting**

| Element | Type / Shape | Required | Rules | Notes |
|---------|---------------|----------|-------|-------|
| `arras.console.create_app(arras, *, principal_for_request, base_path="", asset_base=…, integrity=…)` | `-> ASGI application` | yes | `principal_for_request(request)` takes the console's `Request` (method, path, headers, query) and returns the viewer's `Principal` (CONTRACT-001), or `None` if the viewer is not signed in. Every resolver runs through `arras.session(principal)`, so the backends, reached with the viewer's own token, decide what the viewer sees. Arras MUST NOT authenticate viewers itself. | The host maps its identity to a principal. |

**Endpoints** (paths relative to `base_path`)

| Element | Type / Shape | Required | Rules |
|---------|---------------|----------|-------|
| `GET /` | HTML | yes | The GraphiQL page. Accepts an optional query `module` to pre-select. Asset versions are pinned; the asset base is configurable (ADR-011). The page MUST address the `/graphql` endpoints relative to its own location, so it works under any host path prefix or proxy. The host's content-security policy MUST allow the page's script, style and worker origins; the page documents them. |
| `POST /graphql` | JSON `{query, variables?, operationName?}` | yes | Executes against the meta schema. |
| `POST /graphql/{module}` | JSON as above | yes | Executes against that module's generated schema. |
| `GET` on either `/graphql` path | | no | MUST be refused with 405; queries are POST only. |
| `POST` origin proof | | yes | The same rule as CONTRACT-009 (`arras.http.post_origin_ok`, shared by every binding). A `POST` whose `Origin` is `public_origin` or in `allowed_origins` is accepted. A `POST` carrying `Sec-Fetch-Site: same-origin`, the browser's own statement that the page is this origin, is accepted whatever `Host` the app was asked, so a host behind a proxy that rewrites `Host` and does not know its public URL at start needs no setting; an `Origin` sent with it need not be listed but MUST be one well-formed origin (not `null`, not a path, not a list). A `Sec-Fetch-Site` of `cross-site` is refused 403 `REFUSED` whatever the `Origin`. Otherwise, when the host named no origins, an `Origin` equal to the request's `Host` (default port and case normalized) is accepted; when it named some, only those. A request that repeats `Origin` or `Sec-Fetch-Site` is refused 403, neither copy believed. Ports and case are normalized, the scheme is compared, and an IPv6 host keeps its brackets (`http://[::1]` equals `http://[::1]:80`). A caller that sends neither header (not a browser) is not affected; the console, unlike CONTRACT-009's surface, does not require proof from it. |
| Response | JSON `{data?, errors?}` | yes | GraphQL standard. Each error has `extensions.code`. |
| Status codes | | yes | 200 for any executed query, including those with GraphQL errors; 400 for a malformed request; 401 if `principal_for_request` returns `None`, or if the backends refuse the viewer's token as expired (`Refused` with `reason: token_expired`) on either path, whether while the module is looked up or in any resolver, with the body `{errors: [{message, extensions: {code: "REFUSED", reason: "token_expired"}}]}` and no `data`; 404 for an unknown module or one the viewer cannot read (`Refused` with `reason: no_access`), decided before any query runs; 405 for GET on a graphql path; 503 if no backend is available. On the meta path a `no_access` refusal stays an error on its field with 200. |

**Meta schema** (SDL)

```graphql
scalar JSON
scalar DateTime        # RFC 3339 text, offset as authored
scalar BigInt          # a 64-bit integer as decimal text, because GraphQL Int is 32-bit
scalar Decimal         # a decimal as plain text, exactly as stored
scalar Base64

type Query {
  modules: [Module!]!            # only modules the viewer can read
  status: [BackendStatus!]!
}
type BackendStatus { backend: String!  available: Boolean!  reason: String  detail: String  position: String  lag: String }
type Module {
  name: String!
  record: String!
  replicas: [String!]!
  providers: JSON!               # action name to provider backend name (CONTRACT-002)
  revision: JSON!                # the ontology revision: an object keyed by backend name (CONTRACT-002)
  entityTypes: [EntityTypeInfo!]!
  relationships: [RelationshipInfo!]!
  actions: [ActionInfo!]!
  view: ModuleView!              # CONTRACT-010: the resolved arras.view, read from the registered document at this revision
}
type EntityTypeInfo {
  name: String!  key: String!  properties: [PropertyInfo!]!
  capabilities: JSON!            # by backend name; each entry adds `search` (none or substring) and `searchable` (CONTRACT-010)
  view: View!                    # CONTRACT-010: the resolved view; its types and the rest of the meta additions are defined there
}
type RelationshipInfo { name: String!  source: [String!]!  target: [String!]!  sourceMultiplicity: String!  targetMultiplicity: String!  lifecycle: String!  inverse: String }
type PropertyInfo { name: String!  type: String!  required: Boolean!  cardinality: String! }
type ActionInfo { name: String!  description: String!  inputs: JSON!  inputSpecs: [InputSpec!]!  preconditions: JSON!  effects: JSON! }
type InputSpec { name: String!  type: String!  kind: String!  cardinality: String! }   # kind: scalar, record or ref; a form is built from these
```

**Generated schema per module.** For the module's registry at its current revision, the schema MUST contain:

| Element | Shape | Rules |
|---------|-------|-------|
| Interface `Entity` | `{ key: String!, type: String!, version: BigInt, freshness: Freshness!, createdBy: String, createdAt: DateTime, updatedBy: String, updatedAt: DateTime }` | The attribution fields come from the `_created_*` and `_updated_*` columns the backend appends to the entity's row (CONTRACT-001) and are null for an entity of another module. |
| Object type per entity type `T` | `implements Entity`, plus one field per declared property: `string` → `String`, `integer` → `BigInt`, `decimal` → `Decimal`, `boolean` → `Boolean`, `binary` → `Base64`, `timestamp` → `DateTime`, a structured value → `JSON`; a list field is a list. A required property is non-null. One field per relationship the type takes part in, named by the relationship (or its inverse), returning `[Ref!]!` of at most 100 keys. | The relationship fields are read in the entity's own row with Weft's `RELATED_KEYS(x.relationship, 100) AS "_relationship"` (CONTRACT-001): the output name is never the relationship's own name, because a backend may append that column to `alias.*` itself (Truss does) and refuses a second output of the name (`WFT-OUTPUT-NAME`); the console gives the row back with the keys under the relationship's name. The list is bounded: an entity with more than 100 keys on a relationship shows the first 100 in key order, and the field does not say it was cut; a client that needs every key reads them with its own `query` (`HAS_RELATED` on the other end). |
| `Query.<t>(key: String!, consistency: Consistency = LATEST, atLeast: String)` | `T` | `<t>` is `T` with its first letter lowercased. One `query` of the type's module (every generated name a Weft quoted identifier, `x."code"`, so a declared name that Weft reserves, such as `order` or `group`, reads as the name): `SELECT x.*` (the declared fields and the entity facts the backend appends, which `version` and the attribution fields read) with one `RELATED_KEYS(x.relationship, 100) AS "_relationship"` per relationship, when the request selects a fact (`version`, `createdBy`, `createdAt`, `updatedBy`, `updatedAt`) or the selection cannot be read, and otherwise a projection of the key, the selected properties and one `RELATED_KEYS` for each selected relationship (a backend that appends the facts pays for them per row: truss-requirements R17.8), `WHERE x.<key property> = :key ORDER BY x.<key property> LIMIT 1` (CONTRACT-001; Weft's page profiles require the order and the limit). Null if absent. |
| `Query.<t>List(filter: JSON, limit: Int = 50, consistency: Consistency = LATEST, afterKey: String)` | `TPage` | One page of at most `limit` entities ordered by key, read with one `query` of the same two forms (the whole entity when `items` selects a fact, a projection of what `items` selects otherwise), `ORDER BY x.<key property> LIMIT limit + 1` under the `limit` cap, so `truncated` says the cap cut the result and another page follows. Nullable, so a list that fails (a down backend, a limit) errors on its own field and leaves the request's other fields their data. `filter` is equality on the type's declared `columns` and relationships: a property filter is an equality, a relationship filter is `HAS_RELATED(x.relationship, KEY(:p))`. `afterKey` reads the next page: the entities whose key follows it, as the keyset predicate `x.<key property> > :after` beside the filter (the value always a parameter). A page carries no cursor: a client passes the last key of a truncated page as the next page's `afterKey`, so paging stays the statement's own keyset. |
| Page types | `TPage { items: [T!]!, truncated: Boolean!, freshness: Freshness! }` | |
| `Freshness` | `{ backend: String!, asOf: String!, at: DateTime!, consistency: Consistency! }` | Every answer states it. |
| `Ref` | `{ module: String!, type: String!, key: String!, target: Entity }` | `module` and `type` name the entity on the other end, so a client can address the right endpoint. `target` opens it: the entity with the key, read with one by-key `query` (CONTRACT-001) as the viewer's principal. For a type of this module, `target` is that type's object (`... on Solution { name }`), so a client follows a relationship in one request. For a type of another module, `target` is a `ForeignEntity`, an `Entity` with only the interface fields, and the client reads the rest from that module's endpoint. `target` is null if the entity is absent or the viewer cannot read it, and the answer does not say which. It is resolved only when selected. |
| `enum Consistency` | `LATEST, BULK` | |
| `Query._search(text: String!, types: [String!], limit: Int = 20, consistency: Consistency = LATEST, atLeast: String)` | `_SearchPage!` | The search read of CONTRACT-010, section C, with its `_`-prefixed types (`_SearchPage`, `_SearchHit`, `_Segment`, `_TypeCount`, `_NotSearched`); a leading underscore is forbidden in a declared name (CONTRACT-002), so they cannot collide with a module's. It reserves 50 entities per searched type from the request's budget and runs under the request's revision; its errors are `BAD_QUERY` (text or `types`), `LIMIT_EXCEEDED` (`limit` outside 1 to 50), `COST_EXCEEDED`, `UNSUPPORTED`, `UNAVAILABLE` and `REVISION_CHANGED`. |
| `Mutation`, `Subscription` | | MUST NOT exist. Introspection MUST show neither. |

**Limits**

| Element | Rules |
|---------|-------|
| Page size | `limit` MUST be 1 to 100; a value outside the range returns `LIMIT_EXCEEDED`. |
| Query depth | Maximum depth 6 from `Query`; deeper queries return `DEPTH_EXCEEDED`. A `target` adds one level, so a client follows at most two relationships from a listed entry. |
| Principal | Every resolver reads through the interface as the viewer's principal; no resolver uses another identity. |
| Snapshot | One request MUST state the ontology revision it ran under, and every resolver in it MUST use that revision's schema. |
| Cost | A request MUST resolve at most 1,000 entities, reserved before each query runs so none is read past the budget, and use at most 50 field selections including aliases; beyond that it returns `COST_EXCEEDED`. Relationship fields (the keys) MUST be answered from the same `query` row, not issued one per entity. `Ref.target` is the one exception: each selected `target` costs one by-key `query` and one entity of the budget, and a request MUST resolve at most 100 targets; beyond that the `target` field returns `COST_EXCEEDED` and the request's other fields keep their data. |
| Execution | Execution is synchronous and MUST NOT block the host's event loop: it runs in a worker thread. |

**Error codes** (`extensions.code`): `REFUSED` (with `reason`: `no_access`, or `token_expired`, which is always answered with HTTP 401), `UNAVAILABLE`, `UNSUPPORTED`, `NOT_YET_CURRENT`, `LIMIT_EXCEEDED`, `DEPTH_EXCEEDED`, `COST_EXCEEDED`, `BAD_QUERY`, `NOT_FOUND` (an unknown path or module), `REVISION_CHANGED` (a backend answered under a revision other than the one the request stated) and `INTERNAL_ERROR` (a fault of Arras's, with no detail).

## Precedence and Compatibility

- Versioning: v2, the shape this contract states. Version in `arras.CONTRACT_VERSIONS["console"]`.
- Ordering or precedence: a schema is built from the registry revision in force when the request begins and is the same for that whole request; a registration takes effect on the next request. The backends' access decides visibility before any query runs.
- Backward-compatibility rules: adding a field, type or error code is compatible. Removing or renaming a field, changing a type, tightening a limit or adding a Mutation is breaking. Generated names follow the declaration, so a module's type rename is that module's breaking change.
- Deprecation rules: use GraphQL `@deprecated` for one minor release.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|------------------|-------|----------------------|
| Viewer not signed in, or the viewer's token expired | HTTP 401 (`REFUSED`, `reason: token_expired` for an expired token) | after signing in | Host authenticates |
| Unknown module, or the viewer cannot read it | HTTP 404 | no | Check the name or request access |
| `limit` outside 1 to 100 | `LIMIT_EXCEEDED` | after correcting | Lower the limit |
| Query deeper than 6 | `DEPTH_EXCEEDED` | after simplifying | Flatten the query |
| Entity not found | `data` null for the field; no error | no | |
| Request over the cost limit, or over 100 `target` lookups | `COST_EXCEEDED` | after simplifying | Request fewer entities, fields or targets |
| A relationship target absent or unreadable | `target` null; no error | no | |
| A needed backend unavailable | the field errors with `UNAVAILABLE` and the backend; HTTP 503 only if no backend is available | host decides | See CONTRACT-005 |
| Malformed query | HTTP 400 or `BAD_QUERY` | after fixing | |

## Examples

```graphql
# POST {base}/graphql/catalog
query {
  solutionList(limit: 2) {
    items { key name coverageLevel addresses { key } }
    truncated freshness { backend asOf consistency }
  }
}

# The next page: the entities after the last key of a truncated page
query {
  solutionList(limit: 2, afterKey: "sol-pipeline-02") { items { key name } truncated }
}

# Follow a relationship: the use cases a solution addresses
query {
  solution(key: "sol-pipeline-01") {
    name
    addresses { module type key target { ... on UseCase { name workArea } } }
  }
}
```

## Non-Normative Notes

Contract tests derive from the tables: introspect each generated schema and assert no Mutation or Subscription; request `limit: 101` and a depth-7 query; call a module the viewer cannot read and expect 404; stop one backend and confirm only the fields that need it error. Contract tests also select `target` on a same-module relationship and expect the typed fields; on a cross-module one and expect interface fields only; on an absent key and expect null; on 101 refs and expect `COST_EXCEEDED` on the 101st; and a `target` chain past depth 6 and expect `DEPTH_EXCEEDED`. A relationship whose target type belongs to another module returns the target as an `Entity` with only the interface fields. The GraphQL layer relies on no Weft key-list predicate or join, so each target is one by-key `query`; the 100-target bound keeps that cost explicit, and it can rise when backends declare a Weft profile with a key-list predicate and Arras batches a field's targets into one `query`. The generated statements are the whole entity or a projection of the selected fields (above), with `RELATED_KEYS(x.relationship, 100)` for each relationship. The 100-target bound is a proposed starting value. The depth cap, page maximum and the asset source (a public content delivery network for JavaScript modules, in the style of `esm.sh`) are proposed starting values (ADR-011).
