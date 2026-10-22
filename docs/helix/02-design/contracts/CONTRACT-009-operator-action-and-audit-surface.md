---
ddx:
  id: CONTRACT-009
  type: contract
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
    - id: CONTRACT-007
      kind: informed_by
---

# Contract: Operator action and audit surface

**Contract ID**: CONTRACT-009
**Type**: HTTP API
**Version**: v2
**Status**: draft
**Related**: FEAT-010, ADR-021, ADR-015, ADR-017, CONTRACT-001, CONTRACT-003, CONTRACT-004, CONTRACT-006, CONTRACT-007

## Purpose

Defines the JSON endpoints through which the Operator Console validates and invokes the actions a module declares and reads the audit records the backends keep, so `arras-ui` and a test can be built against it without reading the implementation. It is an HTTP binding of operations the library defines: `validate`, `invoke` and `invoke_batch` (CONTRACT-003), `changes`, `loads`, `export_records` and `query` (CONTRACT-001), and `modules` with `document` (CONTRACT-001, Registry reads), shaped as the catalog UMF's schema explorer reads. It adds no operation of its own, no write other than invoking a declared action, and no table; `query` is a read. Entity reads are CONTRACT-006.

Terms. An action is a change a module declares in its UMF document (UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions); it is the only way data changes (ADR-015). A provider is a backend that applies actions and keeps the journal that the audit reads come from; a reader serves graph reads, and a replica is a reader other than the module's record store (CONTRACT-004). ASGI (Asynchronous Server Gateway Interface) is the Python standard for asynchronous web applications. CORS (cross-origin resource sharing) is the browser rule for requests between sites. A preflight is the `OPTIONS` request a browser sends before a cross-origin request it considers unsafe.

## Scope and Boundaries

- In scope: mounting, endpoints, the authentication and approval hooks, cross-origin rules, request and response encoding, limits, status codes and errors.
- Out of scope: entity and registry reads (CONTRACT-006); the action declaration and the semantics of validate, invoke and batch (CONTRACT-003); the audit records' meaning (CONTRACT-001); the journal's layout (the provider's own contract); registering modules (CONTRACT-011); `import_records`; any raw write; the UI's visual design; who authenticates the viewer.
- Owning system or team: Arras.

## Normative Surface

**Mounting**

| Element | Type / Shape | Required | Rules | Notes |
|---------|---------------|----------|-------|-------|
| `arras.operate.create_app(arras, *, principal_for_request, authorize_action=None, public_origin=None, allowed_origins=(), base_path="", authorize_operator=None)` | `-> ASGI application` | yes | `principal_for_request(request)` returns the viewer's `Principal` (CONTRACT-001) or `None`, as in CONTRACT-006. Every operation runs through `arras.session(principal)`. Arras MUST NOT authenticate viewers, hold a credential or decide access. | May be mounted beside the console. |
| `authorize_operator(principal) -> bool` | host hook (CONTRACT-010, section E) | no | Whether a principal is an operator, who may use Operate. Default `None`: every principal `principal_for_request` accepts is one (this contract's behaviour before CONTRACT-010), and the surface logs that once at start. A hook that raises refuses. | Arras never infers it from `Principal.groups` or `admin`. |
| `authorize_action(principal, module, action) -> bool` | host hook | no | Called first for `validate`, `invoke` and `batch`, before the library is asked anything, including whether the action exists. When it returns false the answer is 403 and nothing reaches the library (so an action that is not offered and one that does not exist answer alike). It lets a host apply its own per-action approval (the embedding host classifies each action; ADR-016). It can only narrow what the provider permits. | The provider's grants still decide everything it allows. |
| `public_origin`, `allowed_origins` | origin strings | no | The app's own origin is `public_origin`, set by the host; it is never derived from `Host` or a forwarded header. A request's `Origin` is listed when it equals `public_origin` or one of `allowed_origins`, compared as scheme, host and port: the scheme's default port is filled in, case is ignored, and an IPv6 host keeps its brackets (`http://[::1]` equals `http://[::1]:80`). | Behind a proxy that rewrites `Host`, the host sets `public_origin`. |

**Cross-origin and request rules**

| Rule | Detail |
|------|--------|
| Content type | A `POST` body MUST be JSON (`Content-Type: application/json`), otherwise 400 (the status CONTRACT-006 uses); a body over 256 KiB is 413. |
| State-changing requests | A `POST` is accepted when its `Origin` is listed (above), or when it carries `Sec-Fetch-Site: same-origin`, the browser's own statement that the page making the request is this origin. With that statement an `Origin` need not be listed (a host may leave `public_origin` unset), but if one is sent it MUST be a single well-formed origin (not `null`, not a list). A `POST` whose `Sec-Fetch-Site` is `cross-site`, `same-site` or `none` and whose `Origin` is not listed, or that carries neither, is refused 403. A request that repeats the `Origin` or the `Sec-Fetch-Site` header is refused 403 and its origin gets no CORS headers: neither copy is believed. |
| Preflight | `OPTIONS` on any path is answered 204 with `Access-Control-Allow-Origin` set to the request's `Origin`, `Access-Control-Allow-Methods: POST, GET`, `Access-Control-Allow-Headers: content-type`, `Access-Control-Allow-Credentials: true` and `Access-Control-Max-Age: 600`, only when that `Origin` is in `allowed_origins` or is `public_origin`. For any other origin it answers 403 with no CORS headers. |
| Responses | The same CORS headers accompany each answer to an allowed origin. `Cache-Control: no-store`. |
| Credentials | The surface never reads or sets a cookie. The host's `principal_for_request` reads whatever session credential the host uses. |

**Endpoints** (paths relative to `base_path`; bodies and answers are JSON)

| Element | Request | Response | Rules |
|---------|---------|----------|-------|
| `GET /version` | | `{contracts: {interface, actions, console, operate}}` | The `CONTRACT_VERSIONS` of this deployment. No principal needed. |
| `GET /viewer` | | `{user, modes: ["user"] \| ["user", "admin"]}` | The request's principal and the modes the shell offers: `admin` exactly when `authorize_operator` is `None` or returns true. 401 without a principal; no origin proof (a read). The one endpoint besides `GET /version` and `GET /openapi.json` that answers a non-operator (CONTRACT-010, section E). |
| `GET /openapi.json` | | OpenAPI 3.1 document of this table | Published so a client is generated from it, and lists itself. Each operation declares the status codes it can answer: `validate` declares no 422 (it reports a false precondition in its 200), and the audit reads declare no 409 or 422. Per-module entity types are not in it: a client reads those by introspecting CONTRACT-006's schema at runtime. |
| `POST /actions/{module}/{action}/validate` | `{inputs, idempotency_key?, expected_revision?}` | `Validation` | Applies nothing. Needs the write access `invoke` needs. |
| `POST /actions/{module}/{action}/invoke` | `{inputs, idempotency_key?, expected_revision?}` | `Receipt` | The console always sends a key. |
| `POST /actions/{module}/{action}/batch` | `{items, atomic?, stop_on_error?, idempotency_key?, expected_revision?}` | `BatchReceipt` | `1 ≤ len(items) ≤ 100`. |
| `POST /audit/changes` | `{module?, type?, key?, by?, action?, group?, since?, until?, provider?, limit?, after?}` | `ChangesPage` | `changes` (CONTRACT-001). `provider` is an optional string naming the provider whose journal is read, with the rules of CONTRACT-001 (Which provider): omitted, the record store; a name that is not the record store or one of the module's providers is 404 `Invalid` (`unknown_type`, path `provider`, as for an unknown module, so it never says whether the backend exists), and `provider` without `module` is 400 `Invalid` (`scope`). A read made with `POST` so a key or a person's name is never in a URL or an access log. |
| `POST /audit/loads` | `{module, provider?, limit?, after?}` | `LoadsPage` | `loads` (CONTRACT-001), with `provider` as for `/audit/changes`. |
| `POST /export` | `{module, limit?, after?}` | `ExportPage` | `export_records` (CONTRACT-001, CONTRACT-003 Export): one page of the module's graph as records, run as the viewer. `limit` is 1 to 500 (default 500), otherwise 400; `after` is the previous page's `nextCursor`, a place in the export's canonical order, so a write between pages neither repeats nor skips a record (CONTRACT-003, Export). A read made with `POST` so the module and the cursor are never in a URL. `ExportPage` is `{items, nextCursor, omitted, freshness}`: `omitted` names the types the viewer could not be given, so a page that names any is not the whole graph. It never answers 409 or 422. |
| `POST /query` | `{module, sql, params?, consistency?, at_least?, limit?}` | `QueryResult` | `query` (CONTRACT-001): one read-only Weft statement over the named `module`, run as the viewer; Arras does not parse it. `sql` is a string of at most 4,000 characters (a longer one is 400, and one over 16 KiB of bytes is refused before it reaches a backend); `module` is required (400 without it); `params` an object of named parameters (as `inputs`, text for decimals, timestamps and 64-bit integers); `consistency` is `latest` (default) or `bulk`; `at_least` a receipt token; `limit` 1 to 100 (default 50), otherwise 400, and `truncated` in the result says it cut the rows; a next page is the statement's own (`ORDER BY` the key, `LIMIT`, a keyset predicate), so there is no cursor. A statement the backend cannot read is 400 `Invalid` with its violations; a `module` the viewer cannot read, or one that does not exist, is 404 with an `Invalid` body carrying an `unknown_type` violation, the same for both; a construct the backend does not serve, a statement outside the named module, or a type the module's backend does not hold is 501; the text of the query is never in an error `message`, a log or a telemetry attribute (a violation may quote the offending token back to the caller who typed it, never a value from a column or a parameter). A read with `POST` so query text is never in a URL or an access log. Needs no origin proof beyond a `POST`'s own (the rules above), changes nothing. |
| `GET /explorer/schema-catalog.json` | | `SchemaCatalog` | The catalog for UMF's schema browser for this viewer: `{version: 1, entries}`, one entry per module the viewer may read (`modules`), each `{id: "arras:<module>", title: <module>, category: "domain", path: "<module>.umf.json"` (or `.umf.yaml`)`, text, format, description, schemaFormat: "umf"}`, where `text` is the module's registered document from `document`, unchanged, and `description` is `Registered at revision <revision>; record store <name>; replicas <names or none>.` Runs as the viewer (`principal_for_request`); a `GET` changes nothing, so it needs no origin proof, and it carries CORS headers only for a listed origin and `Cache-Control: no-store`. A module whose document cannot be read (`Unsupported`, as for a replica-only module, or `Refused` with `no_access`, or `Invalid`) is left out; a viewer who reads no module gets `{version: 1, entries: []}`. A document over 1 MiB, or past 8 MiB for the whole catalog, is replaced by a note entry (`schemaFormat: "json-schema"`, `path` `<module>.not-shown.json`) that says it is not shown. Nothing but registered documents is in it: no entity, input or audit record. |
| Any other method or path | | 404 or 405 | `POST` to the catalog is 405 with `Allow: GET`. |

**Schema browser hosting.** The console reads this catalog itself, with the client that carries the host's credentials, and passes its entries to UMF's schema browser package (`mountSchemaBrowser`, host contract 1.1), so the catalog needs no second route and the browser's frame makes no request for it; it marks the entries with annotations derived from the meta query, never from this catalog. A host serves the installed package's whole `assets/` directory (its lazily loaded chunks included) at the console's `explorerBase` (`/umf-explorer/` in the dev host) and gives the console's page a Content-Security-Policy the browser can run under, since its `srcdoc` frame inherits that policy: UMF's strict profile, `default-src 'none'; base-uri 'none'; script-src 'self'; style-src 'self'; img-src 'self'; frame-src 'self' about:; connect-src 'self'`, plus the host's own needs (the dev host adds `frame-ancestors 'self'`). No `'unsafe-eval'` is needed (`arras-ui`'s README states the policy and how it was measured).

**Paths.** `{module}` is the module's name and `{action}` is the action's name without its module prefix: the action `catalog.CorrectCoverage` is at `/actions/catalog/CorrectCoverage/invoke`.

**Encoding.** A binding that receives text converts it before the library sees a value; this surface uses the converter CONTRACT-007 defines (`convert_inputs`), shared by both bindings.

| Element | JSON shape |
|---------|------------|
| `expected_revision` | an object with arbitrary string keys (backend names) and integer, text or null values; any other type is 400. Every backend named must be at the stated revision and a backend not named is not checked (CONTRACT-002). `atomic` and `stop_on_error` are true or false; any other type is 400. |
| `inputs` | An object by input name. A decimal, a timestamp, a 64-bit integer and a `ref` are text; binary is base64; a boolean is a JSON boolean; a structured value is an object; a list input is an array. The text forms are exact, and the console's UI checks the same ones (the shared vectors in `tests/vectors/inputs.json`): an integer is ASCII digits with an optional sign (`+3`, `-7`; no spaces, `_`, exponent or hexadecimal); a decimal is digits with an optional sign, point and exponent (`12.50`, `.5`, `1e3`; never `NaN` or `Infinity`); a timestamp is an RFC 3339 date-time with a calendar date, hour 0 to 23, minute and second 0 to 59 and a required offset (`Z` or `±hh:mm`), where `t`, `z` and a space for `T` are accepted and seconds may be left out; binary is padded base64. A value the converter rejects is a violation at its path (`inputs.x`, `inputs.x.field`, `items[i].inputs.x`), as for the MCP binding, and it is refused even where the library alone would take the value (an integer past 53 bits sent as a JSON number). |
| `Validation` | `{ok, violations: [{path, code, message}], failures: [{id, reason}], effects: [Effect], replay: Receipt or null, freshness}`. `validate` answers 200 with `ok: false` for invalid inputs and for false preconditions; it raises only for a refusal, an unknown action, a conflict of revision or an outage. |
| `Effect` | One of `{kind: "create", ref, properties}`, `{kind: "update", ref, set, unset}`, `{kind: "delete", ref}`, `{kind: "link", relationship, source, target}`, `{kind: "unlink", relationship, source, target}`; a `ref`, `source` and `target` are `{type, key, generated}`. |
| `Receipt` | `{action, refs: [{type, key, version}], created, updated, deleted, linked, unlinked, token, group, replayed}` |
| `BatchReceipt` | `{action, atomic, items: [{index, receipt} or {index, refusal}], succeeded, failed, token}`; a `refusal` is the error body below. |
| `QueryResult` | `{columns: [{name, scalar, type}], rows: [object], truncated, freshness, revision}`: `freshness` as in `Validation` except that `consistency` is lower case (`latest`, `bulk`), as the library states it; `revision` an object keyed by backend name, a row an object by column name whose values are JSON (a property with no value may be absent from an `alias.*` row although its column is listed: read it as null) (a decimal, a timestamp, a 64-bit integer and a `ref` as text, binary as base64, a list as an array). |
| `Change`, `Load`, pages | As CONTRACT-001, Audit reads, with `next_cursor` written `nextCursor`. A `since` or `until` is a timestamp by the rule for `inputs` above (an offset is required); any other text is 400. Both bounds are inclusive. A cursor this surface did not issue (`-1`, `abc`) is 400. A `group` lookup that matches nothing, or nothing the person may read, is an empty page; one every provider answers `Unsupported` (none keeps a journal) is 501 `Unsupported`, and a provider's refusal with no page found is 403; 404 `Invalid` (`unknown_type`), worded without the group, is only for a deployment with no provider at all. |
| Validation failures | A declared precondition's `reason` is the module's own text; a conflict's failure (`id` `conflict:<reason>`) is worded `conflict (<reason>)` and never echoes a key or an input. |
| Error body | `{error: {type, message, ...}}`: `type`, and of `reason`, `backend`, `operation`, `token`, `construct`, `supported`, `violations` and `failures` those the error carries. A backend's `detail` and `notes` are never sent, since they may echo an input, and the server logs them at debug level only (an unexpected fault's traceback aside); `message` is rebuilt from the type and reason alone (`conflict (exists)`, `memory is unavailable (unreachable)`, `sign in again`, `no access`). The same holds for a batch item's `refusal`. An unexpected fault is `{type: "InternalError", message: "internal error"}` with status 500, its traceback in the server log. |

**Limits**

| Element | Rules |
|---------|-------|
| Body size | At most 256 KiB. |
| Page size | `limit` 1 to 100; otherwise 400 `Invalid`. |
| Batch | At most 100 items; at most 1,000 effects after expansion (CONTRACT-003). |
| Concurrency | At most 4 requests in flight per principal and 16 across all principals; beyond that 429 with `Retry-After`. A request holds its place until its work ends, even if the caller goes away. A client therefore validates on blur and before confirming, never on every keystroke. |
| Execution | Synchronous work, including the host's `principal_for_request`, runs off the host's event loop. |
| Body | Read whole, in as many chunks as the server delivers; a client that disconnects before the end is 400, as is a body that is not UTF-8 JSON or that holds `NaN` or `Infinity`. |
| Mounting | `base_path` is a whole path segment (`/api/operate` does not answer `/api/operatefoo`); a mount's ASGI `root_path` is removed from the path first. |

**Authorization.** Every operation runs as the viewer's principal with the viewer's own token (ADR-017). `authorize_action` can refuse; it can never allow what the provider refuses. The provider's controls decide whether the viewer may validate or invoke, and which journal rows the viewer may read. A module or action the viewer cannot read is answered as an unknown one (404).

**Status codes**

| Condition | Status |
|-----------|--------|
| Executed. `validate` always, with `ok: false` when it finds violations or failures | 200 |
| Malformed body, an `Invalid` input to `invoke` or `batch`, a limit out of range | 400 |
| `principal_for_request` returned `None`, or `Refused` with `reason: token_expired` (also when it is met while asking whether the module exists, or while building the explorer catalog) | 401 |
| `Refused` with `reason: no_access`, `authorize_action` false, an origin not allowed | 403 |
| Unknown or unreadable module or action; a `group` lookup on a deployment with no provider at all | 404 |
| Wrong method | 405 |
| `Conflict` (including `revision` and `idempotency_key_reused`), `NotYetCurrent` | 409 |
| Body too large | 413 |
| `PreconditionFailed` from `invoke` or `batch` | 422 |
| Too many requests in flight | 429 |
| `Unsupported` | 501 |
| No backend available, `Unavailable` | 503 |

## Precedence and Compatibility

- Versioning: v2, the surface this contract states. Version in `arras.CONTRACT_VERSIONS["operate"]` and in `GET /version`; `arras-ui` reads it at load and refuses a version it does not support, naming both.
- Ordering or precedence: a request runs under one registry revision. A caller that built a form from a revision passes it as `expected_revision`; a named backend at a different current revision answers 409 `Conflict` (`revision`) and applies nothing. `changes` and `loads` are newest first within one provider's journal; a response reads one provider, and the console chooses which in the request body, never in a URL.
- Backward-compatibility rules: adding an optional field, a filter or an error code is compatible. Removing or renaming one, changing a type, tightening a limit, or adding any endpoint that writes anything other than invoking a declared action is breaking.
- Deprecation rules: `Deprecation` and `Sunset` response headers for one minor release.

## Error Semantics

A typed `arras.policy.PolicyRefused` (CONTRACT-005) remains HTTP 403 with
`error.type: "Refused"`, canonical `reason: "no_access"` and the existing rebuilt
safe message. Add only its validated `policy_code` identifier; ordinary backend
refusals omit it. The same rule applies to a batch item's refusal and shared schema
error serialization. Authentication/operator checks retain their existing order
and outcomes; the field never turns policy allow into a backend grant. No policy
inputs, annotations, credential values, callback text or arbitrary exception
attributes are included. This is an additive field, not a new wire error type.
Test an actual policy-wrapped action through HTTP and direct Python, safe-code
redaction, no mutation on refusal and native refusal after policy allow.

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|------------------|-------|----------------------|
| Not signed in, or token expired | 401 | after signing in | The host authenticates again |
| No access to the module, action or journal | 403 `Refused` | no | Request the grant from the backend's owner |
| Unknown or unreadable module or action | 404 | no | Check the name or request access |
| Invalid inputs to `invoke` | 400 `Invalid` with every violation | after correcting | Fix the form |
| Precondition false on `invoke` | 422 `PreconditionFailed` with each `{id, reason}` | after the state changes | Read the reasons |
| Same key, different inputs | 409 `Conflict` (`idempotency_key_reused`) | with a new key | |
| Entity already exists, deleted or at another version | 409 `Conflict` | after reading | Reopen the entity |
| A named backend's revision changed since the form was built | 409 `Conflict` (`revision`) | after rebuilding | Reload the module and the form |
| Reader not yet at the token | 409 `NotYetCurrent` | after a short wait | |
| Provider unreachable | 503 `Unavailable` naming the backend | host decides | CONTRACT-005 |
| `changes` on a module whose provider keeps no journal (`describe().audit` false, as a Truss provider declares), or a group lookup that every provider answers `Unsupported` | 501 `Unsupported` | no | Read `status` for the feed position; the console hides the audit area on this answer |
| The schema catalog when the record store holding a readable module is down | 503 `Unavailable`, never an empty or shortened catalog | host decides | CONTRACT-005 |
| The schema catalog for a viewer who reads no module | 200 `{version: 1, entries: []}` | | |
| Origin not allowed, a `POST` with no origin proof, or a repeated `Origin` or `Sec-Fetch-Site` | 403 | no | The host adds the origin |
| A principal for whom `authorize_operator` is false calls any endpoint but `GET /version`, `GET /openapi.json` and `GET /viewer` | 403 `{"error": "REFUSED", "reason": "not_operator"}` (`error` is the plain string here), before the body is read or the library or `authorize_action` is asked | no | Use Explore |
| More than 4 requests in flight | 429 | after `Retry-After` | |

## Examples

```http
POST {base}/actions/catalog/CorrectCoverage/validate
{"inputs": {"solution": "sol-1", "coverageLevel": "partial"}, "expected_revision": {"memory": 3}}
→ 200 {"ok": true, "violations": [], "failures": [], "effects": [{"kind": "update", "ref": {"type": "catalog.Solution", "key": "sol-1", "generated": false}, "set": {"coverageLevel": "partial"}, "unset": []}], "replay": null, "freshness": {"backend": "memory", "asOf": "…"}}

POST {base}/actions/catalog/CorrectCoverage/invoke
{"inputs": {"solution": "sol-1", "coverageLevel": "partial"}, "idempotency_key": "7d1c…", "expected_revision": {"memory": 3}}
→ 200 {"action": "catalog.CorrectCoverage", "refs": [{"type": "catalog.Solution", "key": "sol-1", "version": 3}], "created": 0, "updated": 1, "deleted": 0, "linked": 0, "unlinked": 0, "token": "…", "group": "g-481", "replayed": false}

POST {base}/audit/changes
{"module": "catalog", "type": "catalog.Solution", "key": "sol-1", "limit": 20}
→ 200 {"items": [{"group": "g-481", "at": "2026-10-09T14:02:11Z", "by": "ana", "action": "catalog.CorrectCoverage", "module": "catalog", "ops": [{"kind": "update", "type": "catalog.Solution", "key": "sol-1", "version": 3}], "backend": "memory"}], "nextCursor": null, "truncated": false, "freshness": {"backend": "memory", "asOf": "…"}}
```

## Non-Normative Notes

Contract tests derive from the tables: invoke a declared action as two principals and expect the provider's answer for each; repeat an invoke with one key and expect `replayed`; send `expected_revision` of an older revision and expect 409, and one naming only some of the module's backends and expect only those checked; send a `POST` with a foreign `Origin`, with no `Origin`, and answer a preflight from an allowed and from a disallowed origin; read changes as a person without the journal grant and expect 403, and with an expired token and expect 401; read changes for a module whose provider keeps no journal and expect 501; read changes naming each of a module's providers and expect that provider's journal, and naming a backend outside the module's placement and expect 400 `unknown_type`; make a request that makes a backend echo an input in `detail` and expect the body to omit it; introspect `GET /openapi.json` and assert no path writes except the three action endpoints; and make every request the surface can answer and assert each status is one the document declares for that operation and each body names only properties its schema declares (`tests/test_openapi_contract.py`). Three things are open and need other projects: the journal grant (who may read whose rows: PRD open questions), the provider's journal read itself (its own contract), and a provider's agreement that `by` is the identity its connection authenticated. The audit shows committed changes only; a refused attempt and a validate-only run leave nothing in the journal and appear nowhere. A host that wants attempts logs them on its own side. A browser sends only `content-type` in a preflight this surface answers; a host that adds its own header (an `authorization` header, say) reaches it through a same-origin proxy. The 4-request bound, the page size and the batch size are proposed starting values.
