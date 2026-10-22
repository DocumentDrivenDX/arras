---
ddx:
  id: ADR-026
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-010
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-002
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-005
      kind: informs
    - id: CONTRACT-011
      kind: informs
---

# ADR-026: Schema administration runs as the person, on a surface of its own

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-11 | Proposed | Erik LaBianca (architecture lead) | [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [FEAT-002](../../01-frame/features/FEAT-002-type-registry.md), [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md), [ADR-017](ADR-017-backends-are-reached-with-the-users-own-token.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [CONTRACT-011](../contracts/CONTRACT-011-schema-administration-surface.md) | Medium |

Proposed records the direction under review; it does not claim implementation is complete.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | A module's types change by registering a new UMF document (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions). Today only the host's administrative principal may do it, in a library call at startup, so an operator who needs a type changed on a running deployment needs a developer and a restart, and the one place that offers a file picker (the dev UI) is a loopback sandbox. The Operator Console should offer schema import and export, but its surface may write nothing except declared actions (CONTRACT-009), and ADR-017 gives registration to a service-like administrative identity, not to the person. |
| Current State | `Registry.register` requires the administrative principal; `Registry` rejects it for every read and action. Backends already gate `register` on the caller's own grant (the fake backend checks the module's `write` grant). The registered document is already readable by the person (`document`). There is no validate-only registration, so a console could not show a refusal before applying. |
| Requirements | Use the upstream system's permissions as the access decision: Arras adds no role of its own. Show a change's effect (what is added, what a compatibility rule refuses and with what count) before applying it. Keep CONTRACT-009's guarantee that its surface writes only declared actions. Keep the administrative principal for what is truly administrative (attach, handlers, import, startup registration). |
| Decision Drivers | ADR-017 (the person's own token is the access path); ADR-015 (data changes only by actions: a schema revision is not data); the compatibility rules already refuse what would rewrite records (CONTRACT-002), so a validate-only call can report them without new rules. |

## Decision

We will let a person register a UMF document as themselves, on a schema surface separate from the operator surface.

1. **The person registers, the backend decides.** A new library operation set, `session.schema()`, offers `validate(document)` and `register(document)` as the person's own principal (CONTRACT-002). The record store grants it with a `schema` grant, distinct from `write`, so being allowed to change data does not allow changing types. On the Truss adapter the grant is the backend's own role grant; on the in-memory backend it is a grant mode. Arras keeps no role table and takes no access decision. The administrative principal is refused here as for every user operation; its `Registry` stays for what only a host does at startup (`attach`, `bind_handler`, `import_records`), and its `register` stays and is checked by the same grant.
2. **Validate-only registration.** `validate(document)` runs everything `register` runs (parse, names, placement, cross-module readability, the servable GraphQL schema, the compatibility rules on the backend) and applies nothing. It answers what would change (types, properties, relationships and actions added, changed or retired), the revision it was computed against, and every violation with its count or offenders, so a refusal is seen before it is attempted. It needs the same grant as `register`. A provider gains one operation for it (CONTRACT-004), so the rules the backend applies are the rules it reports.
3. **A separate HTTP surface.** The endpoints are in a new contract, CONTRACT-011, mounted by `arras.operate.create_schema_app` only when a host asks for it. CONTRACT-009 keeps its guarantee that nothing on it writes except invoking a declared action. The schema surface reuses CONTRACT-009's origin, content-type, concurrency and error rules, refuses a non-operator before anything else as the operator surface does (ADR-025's `authorize_operator`), and adds `authorize_schema`, a host hook that can only narrow what the backend permits. A deployment that does not mount it has no schema write path over HTTP.
4. **Export is a read.** The registered document is already read as the person (`document`, and the schema catalog of CONTRACT-009). Export adds no operation: the console downloads the text it already holds.
5. **Placement stays the host's.** A document carries none (CONTRACT-002). A module the host did not place is refused `invalid_placement`, as at startup; a host that wants operators to add modules sets a default placement.

**Key Points**: Access is the backend's own grant, never an Arras role | A schema revision is not an action and not data; it is a separate, explicit, previewable write | Validate-only shows compatibility refusals before the attempt | A separate contract keeps CONTRACT-009's "only actions write" invariant intact | Off unless the host mounts it.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Keep registration administrative and add a file picker that calls the host | No new surface | The administrative principal is a deploy identity or an operator's token chosen at startup; every host rebuilds the endpoint, the preview and the origin rules; nothing attributes the change to the person except the host | Rejected |
| Add registration to CONTRACT-009 | One surface | CONTRACT-009's compatibility rule makes any further writing endpoint breaking, and its guarantee is what the console's safety claims rest on | Rejected |
| Treat a schema change as an action (a `registry.Register` action) | Reuses validate, invoke and the journal | An action is declared by the document it would replace; ADR-015's actions are a module's, not the registry's; effects would have no shape | Rejected |
| An Arras-side role table (who may register) | Easy to build | A second source of access truth beside the backends; ADR-017 and FR-28 forbid it | Rejected |
| **The person registers under a backend `schema` grant, with validate-only, on CONTRACT-011** | Upstream permissions decide; preview before apply; CONTRACT-009 unchanged | A new grant and a new provider operation in the backend contract; Truss must map the grant | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Operators change a module's types from the console with a preview and the backend's own authorisation; every revision's origin actor is the person; loading a schema file is a console feature, so the dev host serves the console alone. |
| Negative | The backend contract gains a grant and an operation (corpus version bump); Truss must provide the dry run and the grant mapping; a schema write surface needs its own security review. |
| Neutral | The administrative principal keeps `attach`, `bind_handler`, `import_records` and startup registration; install belongs to the installing connection. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Truss offers no dry run or no separate grant | M | M | Specified in CONTRACT-004 as the provider's operation; until Truss has it the surface answers `Unsupported` (501) and the console hides import; the fake backend carries both so the contract is testable |
| A schema revision made while others use the module breaks a client | M | H | Only compatible changes are accepted (CONTRACT-002); `expected_revision` on register refuses a stale preview; the revision's text is kept |
| A reviewer mistakes this for a governed-write path (ADR-005 P3) | L | H | Off by default; no approval or reversal is claimed; `authorize_schema` lets a host require its own approval; the audience stays administrators and builders |
| A new module name carries no grant to check | M | M | The backend's right to create modules is the grant; the fake models it as a wildcard `schema` grant |
