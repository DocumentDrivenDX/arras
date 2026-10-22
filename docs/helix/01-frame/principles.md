---
ddx:
  id: principles
  type: principles
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: product-vision
      kind: informed_by
    - id: concerns
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-013
      kind: informed_by
    - id: ADR-014
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: ADR-016
      kind: informed_by
    - id: ADR-017
      kind: informed_by
---

# Project Principles

These principles guide judgment calls when two options both satisfy the PRD, the feature specifications, the concerns and the ADRs (architecture decision records). They are not requirements, concerns, ADRs, workflow rules or process enforcement. Arras is the interface through which an organization's applications read and change the ontology; it is a Python library embedded in a host app such as a workflow application (a Databricks app) over named backends with the roles reader and provider. In production these are two stores: Truss (an open-source property-graph engine, running on Lakebase, Databricks' managed Postgres) and Ashlar (an open-source toolkit for property-graph ontologies on a warehouse, running on Unity Catalog, Databricks' governance layer for tables and access). Types and actions are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions).

## Principles

1. **Clients depend on the interface, never on a store.** When a client needs something a backend offers, extend the interface or a backend's declared capabilities instead of letting the client call the backend. This changes decisions when a direct store call would be faster to write (ADR-013).

2. **Every answer says how current it is, and a missing answer says why.** When a read cannot be served at the level asked, fail with the backend and the reason instead of serving a fresher or staler answer. This changes decisions when a replica could answer a `latest` read while the record store is down (ADR-014).

3. **Changes are named actions, never store primitives.** When a client wants to write, add or extend a UMF action with its preconditions and effects instead of exposing create, update or delete. This changes decisions when an invariant would otherwise be re-implemented by each client (ADR-015).

4. **The backend decides access, as the person.** When a service identity, a role map or a cache would be cheaper, choose the person's own token on every call and let Postgres role grants and Unity Catalog decide. This changes decisions when pooling or latency tempts a shared connection (ADR-017).

5. **Arras owns the interface; the stores and UMF own the rest.** When a gap appears in a backend or in UMF, raise it upstream as a generic requirement and use a minimal subset meanwhile, instead of adding storage or a schema format to Arras. This changes decisions when a local extension would unblock a client sooner (ADR-013, ADR-015).

6. **Arras is a guest in its host.** When an Arras convenience would touch host behavior, choose the option that leaves the host starting and serving: connections and settings come from the host, nothing is imported from the host, and a failing backend is reported, not fatal. This changes decisions about ambient environment variables, startup failures and migration timing (ADR-006, ADR-016).

7. **Defer durable structure until a workload requires it.** When a feature would add durable structure over sensitive source records, defer it and draft the interaction instead, because ADR-005's preconditions P1 to P3 gate it. This changes decisions when an entitlement read or a read of derived structure looks cheap to add.

## Tension resolution

- Principle 2 vs. Principle 6. A backend outage can threaten host startup. At startup the host's continued operation wins: Arras reports each backend unavailable with a reason and the host continues. At call time principle 2 wins: an operation that needs the unavailable backend raises `Unavailable` and does not fall back (CONTRACT-005, CONTRACT-001).
- Principle 3 vs. Principle 5. Effects the closed list of primitives cannot express would pull logic into Arras or UMF. Keep effects to the closed list; a named handler hook declared in UMF and implemented by the module carries the rest, and compensation stays deferred (ADR-015).
- Principle 4 vs. latency. Per-person connections cost more than a shared pool. Keep per-person connections and pool per principal in the host; do not reuse a connection across people (ADR-017, CONTRACT-005). Whether the latency targets hold is measured on a Lakebase branch (PRD, Risks).
- Principle 1 vs. Principle 7. Interface-first design invites drafting interactions for every client need. Draft the interaction (the entitlement read is drafted and blocked) and build only what ADR-005's gate allows (concerns.md).

## Open questions

- [ ] Should the HELIX default principles (design for change, simplicity, validate your work, spec is the contract) be retained alongside these seven? This file, once present, is the sole active source. Ask Erik LaBianca.
