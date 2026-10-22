---
ddx:
  id: ADR-017
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: ADR-013
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: CONTRACT-005
      kind: informs
---

# ADR-017: Every backend is reached with the user's own token

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-05 | Accepted | Erik LaBianca (architecture lead) | [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-016](ADR-016-mcp-stdio-binding-over-the-library.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology, a Python library embedded by a workflow host, over Truss (an open-source property-graph engine on Lakebase, Databricks' managed Postgres) and Ashlar (a property-graph toolkit on Unity Catalog, Databricks' governance layer for data); both are owned by DocumentDrivenDX. Access to the ontology's data must be the person's and a shared service's access is the wrong basis. A service identity that reads on a person's behalf makes the application the access control. |
| Requirements | Every read and every change is made as the person; the backends' own controls decide; changes are attributed to an identity the backend authenticated. |
| Decision Drivers | Unity Catalog applies row and column policy to the caller; Truss's module isolation is Postgres role grants; neither should be bypassed by a pooled identity. |

## Decision

Every call to a backend is made over a connection authenticated with **the user's own token**. Arras has no service-identity read path and no role map.

**Key Points**:
1. **A `Principal` carries a token**, which is required (CONTRACT-001). A call without one is refused before any backend is contacted.
2. **Connections are per principal.** The host's connection source yields a connection for a given principal (CONTRACT-005); Arras never reuses a connection across people.
3. **Each backend decides on the person by its own controls.** The Truss adapter's store decides by the connecting role's membership in a module's reader or writer role; the Ashlar adapter's store (Unity Catalog) applies the user's policy.
4. **Attribution is authenticated.** The person recorded on a change is the one the backend authenticated, not a name the caller supplied.
5. **Administration is separate and explicit**: install runs on the separate installing connection (CONTRACT-005), never as the administrative principal; attachment, handler binding, imports and startup registration use an administrative principal the host names, never used to serve a read or an action. Registering a module's types may also be done by a person under the backend's own `schema` grant (ADR-026).

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Service identity, with a role set per request | One pool | The application becomes the access control; attribution is asserted | Rejected |
| Service identity for a record store, user token for a replica | Simpler pooling at the record store | Two models, and writes not authenticated as the person | Rejected |
| **User token everywhere** | One model; backend enforces and attributes | Per-user connections; token refresh | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | No access logic in Arras; authenticated attribution. |
| Negative | Truss's module isolation must decide by role membership, with no match on one exact role (a requirement to raise on Truss); pooling is per person. |
| Neutral | Embedded local development uses a local role per test user. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Token expiry mid-session | M | M | Host refreshes; a refused call tells the caller to re-authenticate |
| Per-user connections exhaust Lakebase connections | M | M | Host-side pooling per principal with short idle times; measured as in SPIKE-005 |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| No backend call is made without a user token | One is found |
| A user reads only what their own grants allow | A read exceeds them |

## References

- [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md), [CONTRACT-005](../contracts/CONTRACT-005-embedding-and-lifecycle.md)
