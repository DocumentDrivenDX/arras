---
ddx:
  id: TD-001
  type: technical-design
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-09
  authoring:
    home: repo
  links:
    - id: US-059
      kind: informed_by
    - id: FEAT-004
      kind: informed_by
    - id: ADR-020
      kind: informed_by
    - id: CONTRACT-001
      kind: informed_by
    - id: CONTRACT-003
      kind: informed_by
    - id: CONTRACT-004
      kind: informed_by
---

# Technical Design: TD-001 Contract rules, formal specification

**User Story**: [US-059](../01-frame/user-stories/US-059-check-the-contracts-rules-against-a-model.md) | **Feature**: [FEAT-004](../01-frame/features/FEAT-004-backends.md) | **Governing decision**: [ADR-020](adr/ADR-020-contract-rules-are-checked-against-an-executable-model.md)

## Scope

This design holds the Formal Specification of one slice: the rules of action invocation and of reads at a consistency level, as the interface states them. It formalizes internal behavior only. The exact surfaces stay in CONTRACT-001, CONTRACT-003 and CONTRACT-004, and the properties below derive from them; where a property and a contract differ, the contract governs and the property is corrected.

Slices not covered, with the reason no analysis applies: the memory adapter's Weft-subset reader and the UMF reader (deterministic parsing, covered by examples and the shared fixtures; Arras itself parses no SQL), the console and the MCP binding (translation layers with no rule of their own), telemetry and configuration (no ordering or rule combinations at risk).

## Formal Specification

**Selected concern and level.** `formal-methods`, for this slice. Level: **precise specification**, with a **randomized check of the implementation against an executable model**. The model is exercised on generated bounded sequences (a fixed set per run), not exhaustively, so no property here is claimed as machine-checked in the sense of an exhaustive search. Raising the slice to executable analysis (an exhaustive bounded explorer, or TLA+/Alloy) is deferred to the Truss adapter's transaction design, where concurrent interleavings and a lost connection after commit become the open risk (ADR-020).

**Why this slice.** A client may rely on every property below: a wrong answer misleads every caller (a duplicated change, a stale read presented as current, an outage shown as an empty list). Ordinary examples check one case each; the properties interact across orderings of keys, failures, batches, feeds and outages.

### State

| Element | Domain | Initial |
|---------|--------|---------|
| `applied` | use cases of the provider: code to name | empty |
| `held` | idempotency records: key to (inputs, token of the first receipt) | empty |
| `issued` | tokens in the order the record store issued them | empty |
| `replica` | the use cases the replica held at its last feed | empty |
| `reached` | how many of `issued` the replica had reached at its last feed | 0 |
| `fed` | whether the replica has ever been fed | false |
| `available` | whether the record store answers | true |

### Transitions

Each transition is atomic in the model, as the contract requires of the provider.

| Transition | Guard | Effect | Rejected |
|------------|-------|--------|----------|
| `invoke(code, name, key?)` | provider available | if `key` is held with the same inputs: no change, the original receipt, `replayed`. If held with other inputs: none. Otherwise if `code` is in `applied`: none. Otherwise `applied[code] = name`, the token is issued, and `key` is held | `PreconditionFailed` (code exists); `Conflict(idempotency_key_reused)`; `Unavailable` when the provider is down |
| `retry(key)` | a key is held | `invoke` with the held inputs | none: the original receipt |
| `validate(code, name, key?)` | provider available | none | the result says whether `invoke` would apply |
| `batch(items, key?)` independent | provider available | each item as `invoke` with key `key#index` | an item's failure leaves the others |
| `batch(items)` atomic | provider available | every item applies under one token, if the codes are distinct and none exists | otherwise none applies |
| `feed` | record store available | `replica = applied`; `reached = len(issued)`; `fed = true` | |
| `availability(up)` | | `available = up` | |
| `read(consistency, at_least?)` | | `latest`: the record store's state, or `Unavailable`. `bulk`: the replica's state once `fed`; with `at_least`, only if the token is among `issued[:reached]` | `NotYetCurrent` below the token |

### Properties (all safety)

| ID | Property | Authority | Level |
|----|----------|-----------|-------|
| P1 | The same key with the same inputs applies once, and a repeat returns the original receipt, flagged `replayed`, with the original token | CONTRACT-003 Idempotency; US-016 | randomized check |
| P2 | The same key with other inputs is `Conflict` (`idempotency_key_reused`) and changes nothing | CONTRACT-003 Idempotency | randomized check |
| P3 | A failed invocation changes nothing and holds no key | CONTRACT-003 Atomicity; US-015 | randomized check |
| P4 | `validate` changes nothing, spends no key, and reports `ok` exactly when `invoke` would not fail a precondition | CONTRACT-003 Validation; US-045 | randomized check |
| P5 | The items of an independent batch are idempotent as `key#index`, and one item's failure does not affect another | CONTRACT-003 Bulk changes; US-048 | randomized check |
| P6 | An atomic batch applies entirely under one token or not at all | CONTRACT-003 Bulk changes; US-047 | randomized check |
| P7 | A read at a token on the replica answers only once the replica has reached it, with the state it holds, and otherwise says `NotYetCurrent`; it never answers from before the token | CONTRACT-001, CONTRACT-004; US-006 | randomized check |
| P8 | With the record store down, a change and a `latest` read say `Unavailable`; they are never applied, refused as a precondition, or answered empty | CONTRACT-004; US-028 | randomized check |
| P9 | A `latest` read states the record store's state, and a `bulk` read the replica's state at its last feed, with the backend and consistency named | CONTRACT-001; ADR-014 | randomized check |

**Liveness.** None is specified or checked. That a replica eventually catches up, that a retry eventually succeeds and that a down backend eventually returns are environmental and unverified obligations, not properties of this model.

### Assumptions, abstraction and bounds

- One session, single-threaded in-memory backends (`arras.fakes`). No concurrency, no crash between commit and reply, no network: a client's retry (`retry`) stands for an unknown outcome, and the model assumes the original change committed.
- One module and one action (`catalog.AddUseCase`, which creates a use case under a precondition that its code is absent) stand for the action vocabulary. The properties are about keys, preconditions, tokens and availability, which this action exercises; other effect kinds (update, link, delete, `foreach`) are outside the model.
- Finite domains: four codes, two names, two keys, batches of one to four items. Sequences of up to 25 steps, 60 examples per run, derandomized. The domains are small enough that every pair of operations on one code or key recurs, and large enough for a batch to mix successes and failures.
- Tokens are opaque and ordered by issue. Key retention (24 hours or the change record's life) is not modeled: a held key is held forever.
- The Truss adapter's run (`tests/test_truss_properties.py`) uses the same model over a real Truss on PostgreSQL 18.6 as a writer who is not an administrator. Truss has no replica, so P7 and the bulk half of P9 do not apply to it; its journal is its audit pages under an audit grant of their own, so the journal reads are checked as an auditor who reads and holds the grant (each applied change one record, newest first, its group the receipt's, no key or version; the pages continue by cursor to the same sequence) and a writer with no grant is `Refused`, with one group per applied change; P8 names the host's registered backend. A step costs one to two seconds, so a run is 12 examples of up to 16 steps, derandomized; an outage lasts the one step that checks it.
- Excluded behavior: access control (the fakes' grants), the query language (Weft's), capability descriptors, migrations, real replica lag.

### Non-vacuity

- **Witnesses (P-W1).** `test_the_machine_reaches_every_case_it_claims_to_check` runs the machine and requires that it has reached an applied change, a replay, a key conflict, a failed precondition, a valid and a refused validation, a partly applied batch, an atomic batch applied and refused, a feed, a read at a token answered and `NotYetCurrent`, and an outage refusal. Writing the witness list found that replay was never reached by chance; the `retry` rule exists because of it.
- **Negative controls.** Nine tests break the fakes or the interface and require the machine to fail. The three controls for P1, P2, P7 and P8 accept any failed assertion or interface error the model did not predict; the six for P4, P5, P6 and P9 require the failure in the named rule or invariant, not in setup or in an interface error. P3 has no breaking variant of its own: it is checked by the rules and invariants after every failed invocation. A forgotten idempotency key (P1, P2); a replica that claims to have reached any token (P7); a record store that does not raise when down (P8); a `validate` that also applies the plan and spends the key (P4, caught by `latest_is_the_model`); batch items that share one key (P5, caught in `batch_independently`); a batch in which one refused item makes the later ones refused (P5, the same rule); an atomic batch applied item by item under several tokens (P6, caught in `batch_atomically`); a `latest` read served by the replica (P9, caught by `latest_is_the_model` on the backend named); a `bulk` read served by the record store (P9, caught by `bulk_is_what_the_replica_last_held`). Each control runs the machine derandomized with 200 examples of up to 20 steps. A setup or tooling error never counts as a failure. The conformance corpus covers P1, P2, P4, P5 and P6 at the adapter level (`action.idempotent-retry-returns-the-original`, `action.key-reused-with-other-inputs-conflicts`, `action.dry-run-writes-nothing-and-keeps-the-key`, `action.independent-batch-reports-each-item`, `action.atomic-batch-is-all-or-nothing`). On Truss three controls break the adapter and require the failure in a named rule: a retried key that is a new request (P1, P2), batch items that share one request (P5), and every change naming one group (the group-per-change check, or the journal's own rule that each group is the receipt's). The Truss witness test requires an applied change, a replay, a key conflict, a failed precondition, a valid and a refused validation, a partly applied batch, an atomic batch applied and refused, an outage refusal and the journal refused without its grant. The key conflict is a rule of its own on Truss (a held key with other inputs), since the search rarely reaches it.

### Evidence record

| Field | Content |
|-------|---------|
| Identity | P1 to P9, P-W1; model and mapped source in this repository at the commit that carries this document |
| Tool | `hypothesis` 6.168.5 (`uv.lock`), Python 3.11 to 3.13 (CI matrix) |
| Reproduction | `uv run pytest tests/test_properties.py`; for the Truss adapter `uv run --extra truss --group truss-test pytest -m truss tests/test_truss_properties.py`; settings are in the files. The machine, the witness test and every control are derandomized (the same examples on every run), with no example database. The machine and the witness test run 60 examples of up to 25 steps; each control runs 200 of up to 20 |
| Scope | The state, transitions and bounds above |
| Outcome | Completed bounded randomized check; no counterexample. Not an exhaustive search and not a proof |
| Non-vacuity | Witness test and the nine negative controls above; for Truss its witness test and three controls |
| Review | Reviewed 9 October 2026 against CONTRACT-001, 003 and 004. Recheck when any of those, the model, the fakes or `hypothesis`'s major version changes |

### Correspondence

| Property / model element | Requirement provider | Code / enforcing mechanism | Tests | Gap or reviewed limitation |
|--------------------------|-----------------------|----------------------------|-------|-----------------------------|
| P1, P2, P3 `invoke` | CONTRACT-003 | `core.Ontology.invoke`; `fakes.MemoryStore.apply`, `_held`, `_commit` | `test_properties` rules `invoke`, `retry_a_keyed_invocation` | G1, G2, G3, G4 |
| P4 `validate` | CONTRACT-003 | `core.Ontology.validate`; `MemoryStore.apply(dry_run=True)` | rule `validate` | G4 |
| P5 independent batch | CONTRACT-003 | `core.Ontology.invoke_batch`; `MemoryStore.apply_batch` | rule `batch_independently` | G4 |
| P6 atomic batch | CONTRACT-003 | `MemoryStore.apply_batch` over a deep copy committed once | rule `batch_atomically` | G4 |
| P7 read at a token | CONTRACT-001, 004 | `core.Ontology._await`; `FakeReplica.reached` | rule `read_your_writes` | G4 |
| P8 outage | CONTRACT-004 | `MemoryStore.down`, `gate`; Truss: `Connections` and the failure map | rule `an_outage_is_not_a_refusal_or_an_empty_answer`; invariants | G4 |
| P9 reads state their source | CONTRACT-001, ADR-014 | `core.Ontology.query`, `_serving` | invariants `latest_is_the_model`, `bulk_is_what_the_replica_last_held` | G4 |

### Residual gaps and recheck triggers

| ID | Gap | Owner or trigger |
|----|-----|------------------|
| G1 | Concurrent invocations of one key ("apply once" under concurrency) are not explored, on Truss as on the fakes | Write the exhaustive model for the Truss adapter's transaction design (one read-write call per request, the token replay, the unknown-commit recovery) |
| G2 | A lost connection after commit, before the reply | The same |
| G3 | Key retention and expiry | The adapter's journal design |
| G4 | The model checks the in-memory fakes and the Truss adapter (a bounded run over a real Truss). It does not show that an adapter refines the model; the same machine is each adapter's acceptance suite (ADR-020), and the Ashlar adapter's run waits for that adapter | The Ashlar adapter |
| G5 | Liveness | Not planned |

A bounded randomized pass is not evidence that production behaves as modeled. Running-system verification of an adapter remains required.
