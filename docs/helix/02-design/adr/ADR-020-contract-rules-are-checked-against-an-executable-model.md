---
ddx:
  id: ADR-020
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: ADR-014
      kind: informed_by
    - id: ADR-015
      kind: informed_by
    - id: CONTRACT-001
      kind: informs
    - id: CONTRACT-003
      kind: informs
    - id: CONTRACT-004
      kind: informs
    - id: TD-001
      kind: informs
---

# ADR-020: Contract rules are checked against an executable model

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-09 | Accepted | Erik LaBianca (architecture lead) | [ADR-014](ADR-014-reads-state-their-consistency-and-freshness.md), [ADR-015](ADR-015-writes-are-umf-actions-applied-by-providers.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | The contracts state precise rules (an idempotency key applies once, an atomic batch is all or nothing, a read at a token never answers from before it, an outage is never an empty answer) and example tests check single cases. A rule that holds for the cases someone thought of can still fail in an order nobody tried. |
| Requirements | Each rule that carries the interface's promise is checked over arbitrary sequences of operations, and the same check can be run against a real backend. |
| Decision Drivers | The only implementations today are the single-threaded in-memory backends; the concurrency that matters belongs to Postgres inside adapters not yet built. |

## Decision

The slice's rigor is **precise specification with a randomized check of the implementation** (the `formal-methods` concern's lowest machine-assisted level; the specification is TD-001). The rules are written once as a small **executable model** in plain Python, and a `hypothesis` state machine drives the interface with random sequences of invocations, validations, batches, replica feeds and outages, comparing the interface with the model after every step. A model checker (TLA+ or Alloy) is deferred to the one question it answers better: concurrent invocations of one idempotency key across a lost connection, which is written when the Truss adapter's transaction design exists.

**Key Points**:
1. **The rules under check** (each cites its contract): the same key and inputs apply once and return the original receipt; the same key with other inputs is a `Conflict`; a failed invocation records nothing; `validate` applies nothing and costs the key nothing; a non-atomic batch's items are idempotent as `key#index`; an atomic batch applies entirely or not at all under one token; `at_least` on a replica answers only after it has reached the token; an outage of the record store is `Unavailable`, never a precondition failure or an empty list.
2. **The machine is an acceptance suite.** The conformance corpus runs over the fakes now and over each adapter when it exists; the machine is written against the interface, so it can be pointed at one.
3. **It must be able to fail.** The machine is validated by breaking the fakes in the ways the rules forbid and seeing it fail.
4. **Traceability.** Each rule is a property with an identifier in TD-001 (P1 to P9), a named step in `tests/test_properties.py`, and a row in the traceability matrix.
5. **Non-vacuity.** A test requires the machine to have reached each case it claims to check, so a rule that holds only because its interesting case never occurs is reported.
6. **The claim is bounded.** A pass is a completed randomized check on a bounded model, not an exhaustive search and not a proof; running-system verification of each adapter remains required.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| TLA+ or Alloy models now | Explores concurrency exhaustively | Models a design that does not exist yet; a second language to keep in step | Deferred to the adapter design |
| Example tests only | Already there | Cannot find an order no one tried | Rejected as sufficient |
| **Executable model with stateful property tests** | Same language; runs against any backend | Explores sequences, not interleavings | **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | The contracts' strongest sentences are executable; a contract gap shows as a counterexample. |
| Negative | A model can share a misreading with the contract it restates. |
| Neutral | `hypothesis` is a development dependency only. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The model drifts from a contract change | M | M | Each rule cites its contract section; a contract change names the step |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Breaking a rule in the fakes fails the machine | A broken fake passes |
| The same machine passes over each adapter (`tests/test_properties.py` over the fakes, `tests/test_truss_properties.py` over Truss; the rules an adapter has no part in, such as a replica or a journal, are replaced by what it states instead) | An adapter diverges |

## References

- [TD-001](../TD-001-contract-rules-formal-specification.md), [CONTRACT-003](../contracts/CONTRACT-003-actions.md), [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md), [CONTRACT-001](../contracts/CONTRACT-001-ontology-interface.md)
