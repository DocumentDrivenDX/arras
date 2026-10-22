---
ddx:
  id: truss-statement-overhead-spec
  type: design-note
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-21
  authoring:
    home: repo
  links:
    - id: truss-requirements
      kind: informed_by
---

# Truss's SQL statements per public operation

Written to be handed to the Truss project as-is. It records the statements `truss-toolkit` 0.0.45 (native runtime 0.72, layout 1.0, manifest SHA-256 `71c4c3d4...2a2e`) issues per public operation as an embedding Python host sees them over a caller-owned psycopg connection, which asks are met and which remain. It names no host-specific concept.

## Summary

A public call that runs one SQL function is **3 statements** (a savepoint, the call with its guard facts in the same statement, a release); `adopt_transaction` is 3. Measured through the host's adapter on a warm local PostgreSQL 18.6 (a throwaway `pgserver`, a machine at a one-minute load of 7 to 10 on 18 cores, so every figure is not quiet), complete workflows are:

| Workflow | Statements (execute + rollback or commit) | Round trips | p50 / p95 (ms) |
|----------|---------------------------------:|------------:|---------------:|
| singleton read by key with facts | 26 + 2 = 28 | 28 | 36.7 to 38.0 / 40.5 to 42.6 |
| three-effect action (a create and two links) | 31 + 2 = 33 | 33 | 71.8 to 74.1 / 89.4 to 127.8 |
| `describe` (every module and its types) | 18 + 2 = 20 | 20 | 16.0 to 17.0 / 17.4 to 19.7 |
| 30-record list | 26 + 2 = 28 | 28 | 29.4 to 29.7 / 31.7 to 32.7 |
| one-effect update | 28 + 2 = 30 | 30 | 39.9 / 46.0 |
| import of 128 records | 34 + 2 = 36 | 36 | 1.83 to 1.99 s |
| import of 1,024 records, in eight calls of 128 | 209 + 9 = 218 | 218 | 14.8 to 15.9 s |

A complete compiled entity read is not a 3-statement operation: it is two transactions, each with its adoption, one conditional catalog call and the data statement. The same workflows over the adapter before the 0.0.44 APIs were adopted (0.0.41, one catalog read per call): 28, 42, 20, 28 and 30 statements, p50 63 to 65, 107 to 114, 44 to 47, 54 to 60 and 74 ms, and imports of 128 and 1,024 records of 1,704 and 13,562 round trips in 2.7 to 2.8 s and 21 to 22 s. Truss's own trace of the unchanged consumer (a read 29 execute + 2 rollback = 31, an update 31 + 1 + 1 = 33, describe 27 + 3 = 30) counts the adapter as it stood before the call-scope change (29, 43 and 27 execute statements), which is why its numbers are higher.

The acceptance targets: (A) a lighter guard (met), (B) a receipt token with the pending answer (met), (C) a cheap revision probe and bundled metadata (met, below), (D) a commit-time cost that is not super-linear (met), and (E) per-call work inside Truss (E1 met, the rest open).

## 0.0.45

Through the host's adapter on a warm local PostgreSQL 18.6 (a throwaway `pgserver`, a one-minute load of 9 to 16 on 18 cores, so not quiet; three runs of each, 100 calls after 10 warm-up calls, nearest-rank percentiles, truss-toolkit 0.0.45 and weft-sql 0.4.49 against 0.0.44 and 0.4.48, the same adapter before and after it adopted the combined read), one run's load and one's spread given; transactions are rollbacks and commits counted on the connection:

| Workflow | Transactions | Round trips | Statements (execute + settle) | p50 / p95 ms, 0.0.44 | p50 / p95 ms, 0.0.45 |
|----------|-------------:|------------:|------------------------------:|---------------------:|---------------------:|
| singleton read by key with facts | 2 to 1 | 28 to 18 | 26 + 2 to 17 + 1 | 37.6 to 51.4 / 42.1 to 67.8 | 24.7 to 25.9 / 30.0 to 38.8 |
| three-effect action | 2 | 33 | 31 + 2 | 80.2 to 81.7 / 99.3 to 209.6 | 62.1 to 64.2 / 163.8 to 229.5 |
| `describe` | 2 | 20 | 18 + 2 | 17.0 to 18.7 / 19.7 to 23.8 | 12.0 to 12.7 / 12.6 to 14.0 |
| 30-record list | 2 to 1 | 28 to 18 | 26 + 2 to 17 + 1 | 30.1 to 31.8 / 34.0 to 36.4 | 15.4 to 16.6 / 16.9 to 22.4 |

Against the original targets, p95: singleton read with facts 20 ms (30.0, 38.8 and 33.6: not met), three-effect action with its change record 100 ms (202.1, 163.8 and 229.5: not met; p50 62 to 64), type enumeration 20 ms (14.0, 12.6 and 13.2: met) and the 30-record list 1,000 ms (19.2, 16.9 and 22.4: met). Truss's own noisy-host figures for the unchanged adapter were 28.19, 208.51, 10.51 and 13.66 ms. With a connection opened for every call the same four read 45 to 50 / 63 to 68, 159 to 163 / 272 to 375, 19 to 21 / 23 to 26 and 33 to 35 / 35 to 59 ms.

The statements of a singleton read: the adapter's three (`SET TRANSACTION`, `SET LOCAL`, `current_setting('role')`), the adoption (3), the combined operation (11: the savepoint, the guard, the registry payload of 0.4 KB, the search path, the query scope, the snapshot, the data statement, the conditional catalog with its scope, the search path again, the guard, the release) and the rollback: 17 execute and 1 rollback, the combined operation being Truss's published budget of 11. The data statement is 15 to 19 ms of the 25 ms. A three-effect action's 31 statements: its two transactions' adoptions, the conditional catalog, the accepted document (246 KB, 3.2 ms), the group preparation (3), the lookups and the group's `apply_in_transaction` (3 statements, 46 to 52 ms). The process CPU per call, which the host's own Python and the driver and Truss's client side share, fell from 11.7 to 14.7 ms to 4.4 to 4.5 for the read, from 21.8 to 22.8 to 7.5 to 8.0 for the action, from 8.1 to 9.2 to 3.3 to 3.5 for `describe` and from 12.5 to 3.3 for the list.

Imports (the host's `import_records`; three runs): 128 records 2.16 to 2.30 s and 1.03 to 1.14 s with 36 round trips (34 + 2) both before and after; 1,024 records in eight calls of 128 16.2 to 17.1 s and 8.1 to 8.3 s with 218 round trips; one call of 1,024 records 47.9 to 49.4 s on 0.0.45 (49 s on 0.0.44) and, at a load of 24 to 54, 512-record calls 19.6 s, 256 11.4 s and 128 10.0 to 10.7 s for 1,024 records. Cold seed of the three samples from an empty database: 14.8 to 19.6 s before (4.7 to 6.6 for the PostgreSQL and the install, 6.3 to 8.7 the catalog, 2.0 to 2.6 northwind, 1.5 to 2.2 pizza) and 13.2 to 13.4 s after (4.3 to 4.7, 5.4 to 5.7, 1.7 to 2.2, 1.3 to 1.5).

Status of the open targets: E1 met (the conditional catalog), E2 met (no registry payload in a read), E3 and E4 met in effect (the per-call CPU above; the verification and the compile are not separated), E5 met for a read (one transaction, one adoption) and open for a write and `describe`, which each still open two transactions. The remaining cost of a read is Truss's data statement, which scans the type's population: a source bound before the predicate, 15 to 19 ms at 62 rows, so a keyed singleton read costs a scan.

## Measurements

### Truss's own example, no host involved

`packages/python/examples/adopter_workflow.py` at v0.0.41, counting statements per public call (a monkeypatch of `psycopg.Cursor.execute`, script below); the guarded-call counts are unchanged in 0.0.44 (the batched import is below):

| Public call | Statements | Calls | Per call |
|-------------|-----------:|------:|---------:|
| `group_context_in_transaction` | 6 | 2 | 3 |
| `lookup_key_in_transaction` | 6 | 2 | 3 |
| `reached_in_transaction` | 9 | 3 | 3 |
| `apply_in_transaction` | 10 | 3 | about 3 |
| `import_in_transaction` | 19 | 3 | about 6 |
| `adopt_transaction` | 54 | 18 | 3 |
| `install_in_transaction` | 2,152 | 1 | one-time |

### A read, a write and `describe`, end to end (host driving Truss)

By kind and by call, the read of a singleton by key: the transaction control of two transactions, the conditional catalog call (3 statements, about 3 to 6 ms and 0.2 KB when `unchanged`, against 33 to 61 ms and 42.1 KB for a full read of three modules) and the data call, each adopted (3 statements) and guarded. The conditional call is the person's access answer every time: Truss answers a refusal even with a validator in hand, and a validator names one person's view in one kind of transaction (a read-only call and a read-write call do not share one, so a host keeps one per kind).

The three-effect action's group is built with one `prepare_group_in_transaction` (3 statements: the revision, the group context and the references the plan names) in place of the separate context and reference calls: 40 + 2 statements before, 31 + 2 after, 42 round trips to 33.

### Import, one registrar's `import_records` through the host

Warm throwaway, records of one type, one person; 3 runs each, medians. The phases are classified by the first import call's statements (setup before the records are built, payload, settlement: the deferred checks and the commit); a later call's setup is counted in the payload.

| Records | Route | Time | Round trips | Statements | Setup / payload / settlement |
|--------:|-------|-----:|------------:|-----------:|------------------------------|
| 128 | legacy builder and `import_in_transaction`, one call | 2.72 to 2.84 s | 1,704 | 1,702 + 2 | 25 / 1,676 / 3 |
| 128 | `build_import_records_in_transaction` and `import_batched_in_transaction`, one call | 1.83 to 1.99 s | 36 | 34 + 2 | 25 / 8 / 3 |
| 1,024 | legacy, eight calls and commits of 128 | 21.1 to 22.1 s | 13,562 | 13,553 + 9 | 25 / 13,520 / 17 |
| 1,024 | batched, eight calls and commits of 128 | 14.8 to 15.9 s | 218 | 209 + 9 | 25 / 176 / 17 |

Truss's statement claims hold: the legacy 128-record import is 512 builder and 1,162 executor statements (1,674, measured 1,676 with the call's two others) and the batched one is 3 for the builder and 6 for the executor with its final report authorization (9, the savepoint pairs counted), each extra chunk adding 3. The statements fall by a factor of 47 and the time by about a third: Truss's native enforcement still contains each record on its own, so this is not set-based DML and no tenfold latency claim holds (the time of a 128-record call is 1.8 s of which 1.58 s is the one executor statement).

**A call's time grows faster than its records.** One batched call of 1,024 records is within Truss's 1,024-record profile and its 60 s operation bound but took 49 s (47.9 to 48.7 ms a record); two calls of 512 took 22.5 s, four of 256 15.9 s and eight of 128 14.0 to 15.9 s (14 to 15.5 ms a record), a local PostgreSQL at a load of 5 to 9 (not quiet). Each record has a subtransaction of its own, so the host sends calls of 128 records.

### Import chunk, one legacy call, entities only (0.0.41, load average near 9)

| Objects in the call | Whole call | `SET CONSTRAINTS ALL IMMEDIATE` |
|---------------------|-----------:|-------------------------------:|
| 32 | 0.74 s | 0.03 s |
| 64 | 1.33 s | 0.05 s |
| 128 | 2.64 s | 0.11 s |
| 256 and over | refused `ImportInvalid` | |

### Groups

A group of 128, 256, 512, 1,000 and 1,024 creates commits (0.15, 0.23, 0.44, 0.75, 0.84 s on 0.0.41); 1,025 is `GroupUnavailable(resource)`; preconditions are bounded at 3,072 (a group of one create and 300 `ObjectExists` conditions commits, and a failing one among them is named, measured on 0.0.44). An atomic batch of 32, 64 and 100 `AddUseCase` items (a create and a `KeyAbsent` each) takes 0.18, 0.22 and 0.27 s in one group (0.0.41).

### Condition preview

`preview_group_conditions_in_transaction` of five `ObjectExists` conditions in a read-only transaction is 3 statements and 13 ms; a dry run of one create under the same five conditions through the adapter is 24 statements and 92 ms (it also reads the catalog and the accepted document and applies and rolls back the group). The preview states an observation basis and reserves nothing, so a host's dry run, which must report what an apply would refuse for the effects too, does not replace the rolled-back group with it.

## Targets

### A. A lighter per-operation guard (met)

A call that does one SQL function issues 3 statements; `adopt_transaction` 3.

### B. A receipt token in the same transaction as the write (met, one part unverified)

`AppliedPending.receipt_token` carries the token and it equals the string the committed replay returns (verified for an update through the adapter); an apply followed by a commit yields a usable token without a second transaction. Unverified by the host: `reached` on the token before the commit answering `not_yet`, and a rolled-back group's token never `True` (Truss's guide states both).

### C. Fewer, bundled metadata calls and a cheap revision probe (met on 0.0.44)

C1. `prepare_group_in_transaction(tx, records=, relationships=)` returns the catalog revision, the group context and the type and relationship references for a named record set in one call (3 statements): the adapter uses it, and its planner asks for none of them again.

C2. `reader_catalog_if_changed_in_transaction(tx, validator=)` is the revision probe that carries the person's access: it re-answers the connected person's access on every call (a revoked role's very next call is `CatalogRefused` with the validator in hand, measured), and answers `ReaderCatalogUnchanged` without the catalog for an unchanged view. Each module entry states `sourceCatalogRevision`, so a parsed module stays valid across the registration of another document. The host keeps one snapshot and validator per person and per kind of transaction. In the host's workflows it takes a singleton read from p50 63 to 37 ms, `describe` from 44 to 16 ms and the 30-record list from 55 to 29 ms, each now two conditional calls and a data statement, the database wait per call from 52 to 26, about 40 to 10 and 44 to 17 ms.

### D. Commit-time cost (met)

The deferred check is 0.03 s at 32 objects, 0.05 s at 64 and 0.11 s at 128 (0.0.41); in a 128-record batched call the check and the commit are 0.114 s and the final report authorization 0.132 s.

### E. Per-call work inside Truss (E1 met, E2 to E5 open and not re-measured on 0.0.44)

E1. The catalog read itself: with C2 a host skips the 42 KB read when nothing moved (an unchanged call is 2.6 to 5.9 ms and 0.2 KB against 33 to 61 ms and 42.1 KB).
E2. `query_in_transaction` loads a 239 KB registry payload (`SELECT payload.*`) on every call, 3.8 to 5 ms a read (measured on 0.0.41). Serving it from the session's own state, or sending only a digest check, would remove it.
E3. `catalog_runtime._release()` reads and sha-256 verifies about 45 release files on every Truss call, about 3 ms of CPU each (0.0.41); a read makes two calls and a write about eight, so verifying once per process (the wheel's files are immutable) would remove about 6 ms of a read and 20 ms or more of a write.
E4. `weft.compile_truss_runtime_json` is 5.3 ms of CPU per query (0.0.41); a compiled-statement cache keyed by the statement text and the document digest would remove it for a repeated statement.
E5. The guard probe and savepoint pair around every call (6 statements a call) and a second transaction per host call: a call that took the catalog, the document and the query in one adopted transaction would drop one transaction's three `SET` statements and, for a host that opens a connection per call, one connection (50 to 70 ms). A host that opens a connection for every call measures a singleton read at p50 66 to 69 ms against 103 to 104 before.

## Reproduction

```python
import collections, pathlib, sys, tempfile, traceback
import psycopg
sys.path.insert(0, "truss-src/packages/python/examples")   # a checkout of the Truss tag
import adopter_workflow as aw

counts = collections.Counter()
orig = psycopg.Cursor.execute
def execute(self, query, *a, **k):
    names = [f.name for f in traceback.extract_stack()
             if "site-packages/truss/" in f.filename
             and not f.name.startswith("_") and f.name not in ("execute", "guarded", "wrapper")]
    counts[names[0] if names else "(outside a public Truss call)"] += 1
    return orig(self, query, *a, **k)
psycopg.Cursor.execute = execute

aw.run_workflow(pathlib.Path(tempfile.mkdtemp()) / "demo")
for name, n in counts.most_common():
    print(f"{n:5d}  {name}")
```

## Open questions for Truss

1. Does 0.0.45's set-based writer apply to the host's imports (independent rootless records with source provenance)? The statements are those of the batched route and the time halves, but one call of 1,024 records still takes 48 s against 8 s in eight calls of 128: what makes a call's time grow faster than its records, and is there a bound under which it is linear?
2. Can a keyed singleton read avoid the scan of the type's whole population (15 to 19 ms of a 25 ms read at 62 rows) by a key predicate in the compiled source, within the 10,000-row bound's intent?
3. A read and a `describe` still open the adoption and its three statements per transaction, and a three-effect group's `apply_in_transaction` takes 46 to 52 ms with a 246 KB source read before it: can a group be applied against the source digest of the person's catalog without reading it again, and can a write's catalog and source be read in its own read-write transaction (the combined read is read-only)?
4. The validator of a catalog binds the `maximum_bytes` it was read under (a combined read presenting the validator of a catalog read with another bound is answered a new snapshot): is that intended, and can the validator name the catalog alone?
