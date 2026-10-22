---
ddx:
  id: ADR-015
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
    - id: CONTRACT-003
      kind: informs
---

# ADR-015: Writes are UMF actions applied by providers

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-05 | Accepted | Erik LaBianca (architecture lead) | [ADR-013](ADR-013-arras-is-an-ontology-interface-over-named-backends.md), [ADR-014](ADR-014-reads-state-their-consistency-and-freshness.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology, a Python library embedded in praxis (an agent-harness Databricks app). Clients need to change the ontology in business terms, with validation, atomicity, attribution and audit, without exposing a store's write primitives. |
| Current State | The Ashlar build brief (Ashlar is an open-source toolkit for property-graph ontologies on a warehouse; owner: DocumentDrivenDX) assigns UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) a declarative action type: name, typed parameters, a result or handle, preconditions, effects and optional compensation. UMF has not defined it. Truss (an open-source, UMF-driven property-graph engine on Postgres; owner: DocumentDrivenDX) applies primitive operations and, with grouped operations, applies several atomically. |
| Requirements | A single, discoverable way to change data. Atomic multi-entity effects. Attribution of the person. Idempotency. Refusal without side effects. |
| Decision Drivers | Actions are the unit of write authorization and audit; effects that fit a closed set of primitive operations can be executed generically, and the rest need an escape hatch. |

## Decision

We will expose **writes only as actions** declared in UMF and executed by Arras on a **provider**: the backend the host's placement names for the action, and the module's record store by default (which must then have the provider role, else the action is `Unsupported`).

**Key Points**:
1. **A minimal subset of UMF's action contract.** Name, description, typed inputs, preconditions, effects, an optional handler hook (CONTRACT-003). Arras tracks UMF's definition and states its requirements to UMF.
2. **Effects are a closed list**: create, update and delete an entity, link and unlink. They apply as one atomic group on one provider; an action never spans backends.
3. **Preconditions** are checked first and every failure is reported with its reason; a refused action changes nothing.
4. **Attribution.** The person whose own token the backend authenticated, and the action's name, are recorded with the change; no service identity is the author (ADR-017).
5. **Idempotency.** An optional caller key makes a repeated invocation return the original receipt.
6. **Receipts** carry the identities and versions changed and a token (ADR-014).
7. **Bulk is part of the command side.** One action over a list (`foreach`), up to 100 invocations in one `invoke_batch` (atomic as one group or each independently idempotent), and a separate administrative import for volume (CONTRACT-003). Reads are fed by the provider's change feed, so a large change does not slow them.
8. **Read-only modules reject actions.** Import of seed records is a separate idempotent operation with its own provenance rules.
9. **Validate without applying.** A client can ask what an action would do: every input violation, every failed precondition and the effects it would apply, with nothing written, recorded or left locked. The answer is advisory; `invoke` checks again.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Expose entity create, update and delete to clients | Simple | No business-level validation or atomicity across entities; every client re-implements invariants | Rejected |
| An Arras-specific command vocabulary | Fast to start | Diverges from UMF's coming action type | Rejected: use a minimal subset of UMF's |
| A workflow engine with compensation | Handles long-running work | Large scope; the Ashlar build brief defers sagas (long-running work with compensating steps) | Rejected for now |
| **UMF actions, closed effects, optional handler** | Discoverable, auditable, bounded | Needs UMF's contract; handlers sit outside the declaration | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Every change is attributed and audited; clients cannot bypass invariants. |
| Negative | Arras must execute actions, mapping effects to the backend's grouped operations. |
| Neutral | A replica is read-only to clients; its data changes only through the feed from the providers' stores. Read-your-writes across providers is `at_least` on the receipt's token, and nothing else. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| UMF's action contract differs from the subset | M | M | Keep the subset minimal; map one-to-one; track UMF |
| Effects need logic the closed list cannot express | M | M | A named handler hook, declared in UMF, implemented by the module |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| No client write path exists outside actions | One is found |
| A refused action leaves no change | A change follows a refusal |

## References

- [CONTRACT-003](../contracts/CONTRACT-003-actions.md)
- Ashlar build brief (Actions; DocumentDrivenDX/ashlar repository)
- UMF: DocumentDrivenDX/umf repository (the action contract Arras requests of UMF)
