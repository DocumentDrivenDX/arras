---
ddx:
  id: US-059
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: FEAT-004
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-059: Check the contracts' rules against a model

**Feature**: FEAT-004 — Backends
**Feature Requirements**: BE-07
**PRD Requirements**: FR-51
**Priority**: P1
**Status**: Draft

## Story

**As a** Backend implementer
**I want** the contracts' strongest rules checked over arbitrary sequences of operations against an executable model
**So that** my adapter can run the same machine and I find a divergence from the contract before a client does

## Context

ADR-020. The model is plain Python over a dict; a `hypothesis` state machine drives invocations, validations, batches, replica feeds and outages and compares the interface to the model after every step. It must be able to fail: it is validated by breaking the fakes.

## Walkthrough

1. The machine runs random sequences against the in-memory backends.
2. After each step it compares the interface to the model.
3. A broken rule is reported with the shortest failing sequence.

## Acceptance Criteria

- [ ] **US-059-AC1** — Given the same key and inputs, when invoked again, then the change applies once and the original receipt is returned; with other inputs it is a `Conflict`.
- [ ] **US-059-AC2** — Given a failed invocation, when it ends, then nothing is recorded, including the key.
- [ ] **US-059-AC3** — Given `validate`, when it runs, then nothing is applied and the key is not spent.
- [ ] **US-059-AC4** — Given a non-atomic batch under a key, when items repeat, then each is idempotent as `key#index`.
- [ ] **US-059-AC5** — Given an atomic batch, when it ends, then all of it applied under one token or none.
- [ ] **US-059-AC6** — Given `at_least` on a replica, when it answers, then it had reached the token, and otherwise says `NotYetCurrent`.
- [ ] **US-059-AC7** — Given the record store down, when a change or a `latest` read is made, then it is `Unavailable`, never a precondition failure or an empty answer.
- [ ] **US-059-AC8** — Given a rule broken in the fakes, when the machine runs, then it fails.

## Edge Cases

- **Concurrent interleavings**: not explored by sequences; a model checker is written when the adapter's transaction design exists

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Idempotency | US-059-AC1 | same key twice, then other inputs | Run the machine | Replayed, then Conflict |
| Failure records nothing | US-059-AC2 | a precondition failure with a key | Run the machine | Key not held |
| Validate is free | US-059-AC3 | validate then invoke under one key | Run the machine | Invoke applies |
| Batch keys | US-059-AC4 | a keyed non-atomic batch repeated | Run the machine | Items replay by index |
| Atomic batch | US-059-AC5 | a batch with one failing item | Run the machine | None applied |
| Read your writes | US-059-AC6 | a read at a token before and after a feed | Run the machine | NotYetCurrent, then answers |
| Outage | US-059-AC7 | provider down | Run the machine | Unavailable only |
| Mutation | US-059-AC8 | idempotency check removed in the fakes | Run the machine | Fails |
