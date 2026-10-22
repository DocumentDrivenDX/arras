---
ddx:
  id: CONTRACT-011
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
    - id: FEAT-002
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
    - id: CONTRACT-009
      kind: informed_by
---

# Contract: Schema administration surface

**Contract ID**: CONTRACT-011
**Type**: HTTP API
**Version**: v1
**Status**: draft
**Related**: FEAT-010, FEAT-002, ADR-026, ADR-017, CONTRACT-002, CONTRACT-004, CONTRACT-009

## Purpose

Defines the JSON endpoints through which a person validates and registers a UMF module document as themselves, so the Operator Console can offer schema import without Arras deciding who may. It binds two library operations, `validate` and `register` on `session.schema()` (CONTRACT-002). It is a separate surface from CONTRACT-009, which writes nothing but declared actions, and a host mounts it only when it wants it. Reading and exporting a registered document are not here: they are CONTRACT-009's schema catalog.

Terms. A registration accepts a UMF document as a new revision of a module's types on the module's record store (CONTRACT-002). A plan is the answer to validating a registration: what it would change and what it would be refused for, with nothing applied. The `schema` grant is the record store's own permission to register a revision of a module (CONTRACT-004); Arras does not define who holds it.

## Scope and Boundaries

- In scope: mounting, the two endpoints, the host's approval hook, request and answer shapes, limits, status codes.
- Out of scope: the registration rules and compatibility rules (CONTRACT-002); the grant (the backend's); placement (the host's configuration); reading and exporting documents (CONTRACT-009); `attach`, handlers and `import_records` (administrative, never on an HTTP surface); who authenticates the viewer.
- Owning system or team: Arras.

## Normative Surface

**Mounting**

| Element | Type / Shape | Required | Rules | Notes |
|---------|---------------|----------|-------|-------|
| `arras.operate.create_schema_app(arras, *, principal_for_request, authorize_schema=None, public_origin=None, allowed_origins=(), base_path="", authorize_operator=None)` | `-> ASGI application` | yes | As CONTRACT-009's `create_app`: `principal_for_request` returns the viewer's `Principal` or `None`; every operation runs through `arras.session(principal)`; Arras holds no credential and decides no access. The application is a different mount from the operator surface and can be mounted without it, or the reverse. | A host that does not call it has no schema write path over HTTP. |
| `authorize_schema(principal, module) -> bool` | host hook | no | Called first for `validate` and `register`, before the library is asked anything. `module` is the name in the document, which the host reads without trusting the document's other contents; when it returns false the answer is 403 and nothing reaches the library. It can only narrow what the backend permits. | A document that does not parse is answered 400 before the hook runs. The host's other checks are answered only after the backend's grant has been checked. |

The origin, content-type, preflight, `Cache-Control`, error-body and scrubbing rules are CONTRACT-009's, unchanged, and apply to every `POST` here. Schema administration is an operator's act: `authorize_operator(principal) -> bool` is the host's decision that a principal is an operator, as for the operator surface (CONTRACT-010, section E; `arras.operate.operators_in_groups` builds it). A principal who is not an operator is refused before the body is read or anything else is asked, on every path but `GET /version`. Without the hook every principal is an operator and the start says so.

**Endpoints** (paths relative to `base_path`; bodies and answers are JSON)

| Element | Request | Response | Rules |
|---------|---------|----------|-------|
| `GET /version` | | `{contracts: {schema}}` | The `CONTRACT_VERSIONS["schema"]` of this deployment. No principal needed. A console probes it to learn whether import is offered. |
| `POST /validate` | `{document, unknown_endpoint?}` | `SchemaPlan` | `session.schema().validate`. Applies nothing, creates no revision and no journal row. Needs the `schema` grant `register` needs. `document` is the UMF text (JSON, as Arras reads UMF), at most 1 MiB after decoding. The record store's grant is checked before any other host rule is mentioned in an answer; the one exception is that a module the host placed nowhere, or whose record store takes no revisions, has no store to ask and is 400 `invalid_placement`. |
| `POST /register` | `{document, unknown_endpoint?, expected_revision?}` | `RegistryResult` | `session.schema().register`. `expected_revision` is the `revision` a plan answered with, as in CONTRACT-009; a record store at another revision answers 409 `Conflict` (`revision`) and applies nothing. The principal's user is the revision's origin actor. |
| Any other method or path | | 404 or 405 | `GET` to the two `POST` paths is 405 with `Allow: POST`. |

**Encoding**

| Element | JSON shape |
|---------|------------|
| `unknown_endpoint` | `"reject"` (default) or `"provisional"` (CONTRACT-002); anything else is 400. |
| `SchemaPlan` | `{module, ok, violations: [{path, code, message}], changed, revision, changes: [SchemaChange], report}`. `ok` is false when the document cannot be registered; `violations` then lists every reason, a compatibility refusal naming its rule and the count or offenders (CONTRACT-002). `changed` is false when the document's derived rows equal those in force (a registration would create no revision). A plan with `ok: false` may still list `changes`, so a client can show what the document does beside why it is refused. `revision` is the module's current revision, a `Revision` object, null for a module the record store does not yet hold. `report` is the backend's acceptance report. |
| `SchemaChange` | `{kind, element, name, detail}`: `kind` is `added`, `changed` or `retired`; `element` is `type`, `property`, `relationship` or `action`; `name` is module-qualified (`catalog.Solution.notes`); `detail` is short text that carries no record value. |
| `RegistryResult` | `{module, revision, changed, report}` as CONTRACT-002. |

**Limits**

| Element | Rules |
|---------|-------|
| Body size | The document is at most 1 MiB after decoding (the size the schema catalog shows) and the JSON body at most 4 MiB, which carries a fully escaped document; larger is 413. CONTRACT-009's 256 KiB limit does not apply here. |
| Concurrency | At most 2 requests in flight per principal and 4 across all principals; beyond that 429 with `Retry-After`. Registrations are serialized on the record store (CONTRACT-002). |

**Authorization.** Every operation runs as the viewer's principal with the viewer's own token (ADR-017). The record store's `schema` grant decides; `authorize_schema` can refuse and never allow what the backend refuses. A caller without the grant is 403 `no_access`; an expired token is 401. The administrative principal is refused as for every user operation (403).

**Status codes**

| Condition | Status |
|-----------|--------|
| Validated or registered (a plan for a parsed document with `ok: false` is still 200: it is an answer) | 200 |
| A document that does not parse or that names a module the host placed nowhere (on either endpoint: there is no module or record store to ask); an invalid name, placement or cross-module reference or an incompatible change on `register` (`Invalid`, with the violations) | 400 |
| `principal_for_request` returned `None`, or `Refused` with `reason: token_expired` | 401 |
| `Refused` with `reason: no_access`, `authorize_schema` false, an origin not allowed, or a principal who is not an operator (`{error: "REFUSED", reason: "not_operator"}`) | 403 |
| Wrong method; unknown path | 405; 404 |
| `Conflict` on `expected_revision` | 409 |
| Body too large | 413 |
| Too many requests in flight | 429 |
| The record store cannot validate or register (a backend with no dry run, a read-only module) | 501 `Unsupported` |
| No backend available, `Unavailable` | 503 |

## Precedence and Compatibility

- Versioning: v1, in `arras.CONTRACT_VERSIONS["schema"]` and `GET /version`; `arras-ui` offers import only when it reads a version it supports.
- A plan for a module the record store does not yet hold has no `revision`, so its `register` sends no `expected_revision` and a module created in between is not caught as a conflict; the create-or-conflict form is a follow-up.
- A compatibility violation names up to 10 record keys, which the grant holder sees; a backend that grants `schema` without `read` should send the count only.
- Ordering: a plan is computed against one revision of the record store; `register` with that revision as `expected_revision` accepts only if it still holds.
- Backward compatibility: adding an optional field, a `SchemaChange` kind or an error code is compatible; removing or renaming one, or adding an endpoint that writes anything but a registration, is breaking.
- Deprecation: `Deprecation` and `Sunset` headers for one minor release.

## Error Semantics

| Condition | Error / Outcome | Retry | Recovery Expectation |
|-----------|-----------------|-------|----------------------|
| The person lacks the `schema` grant | 403 `no_access` | no | Ask the backend's owner for the grant |
| The change is incompatible (CONTRACT-002) | `validate`: 200 `ok: false` with the rule and count; `register`: 400 `Invalid` (`incompatible_change`) | no | Add as optional, fill, then make required |
| The host placed no such module (no record store to ask) | 400 `Invalid` (`invalid_placement`), on both endpoints | no | The host adds a placement or a default |
| The module is placed but the host or the document says no (an unreadable module, a replica that is not configured, a name rule) | `validate`: 200 `ok: false` with the violations, after the grant has been checked; `register`: 400 | no | Fix the document or the host's configuration |
| The record store has moved on since the plan | 409 `Conflict` (`revision`); when the document is also invalid, 400 `Invalid` comes first | yes, after a new validate | Validate again |
| The record store offers no dry run | 501 `Unsupported` on `validate`; `register` still works if it offers registration | no | Use a record store that offers it |

## Examples

```http
POST /api/schema/validate
{"document": "{ ...catalog UMF... }"}
-> 200 {"module": "catalog", "ok": true, "violations": [], "changed": true,
        "revision": {"memory": 3},
        "changes": [{"kind": "added", "element": "property", "name": "catalog.Solution.notes", "detail": "optional string"}],
        "report": []}

POST /api/schema/register
{"document": "{ ... }", "expected_revision": {"memory": 3}}
-> 200 {"module": "catalog", "revision": {"memory": 4}, "changed": true, "report": ["accepted"]}
```

## Testing

Contract tests derive from the tables: validate changes nothing (the document read back and the journal are unchanged); a plan for an incompatible change is `ok: false` naming the rule and count, and `register` of the same is 400; two principals, one with the `schema` grant and one with only `write`, get the backend's own answer; `authorize_schema` false is 403 and the library is not called; a stale `expected_revision` is 409 and nothing is applied, including when two registrations race; the surface is absent when not mounted (CONTRACT-009's openapi still lists no write other than actions); a foreign origin is 403; a backend error echoing an input is scrubbed.
