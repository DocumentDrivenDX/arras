# Single-SET action binding fixture

This is a neutral, synthetic UMF 0.10.0 fixture for the bounded
`umf.actions` 0.1.0 single-SET binding. It was authored for this qualification
and contains no customer, production, or private Arras data. The exact source
bytes are retained in `source.json`; vectors record their SHA-256 rather than
reformatting them during a test.

The fixture has one module (`catalog`), one Record (`item`), one STRING Key
Field (`item_id`), one constrained STRING Field (`label`), and the declared
`catalog.set_label` action with `item`, `label_value`, and `write_item` IDs.
The opaque `arras.module-write/1` policy is test data only. It is not an Arras
authorization grant or evidence of execution. The host supplies a separate
compatibility declaration; all tests must retain the unchecked source
obligation and `executionVerified: false`.

`vectors.json` freezes the tuple encoding and the Apply/Validate envelopes
captured by the existing generated Python `SyncActions` client. The Validate
request omits `idempotency_key`; it must not be rewritten into Apply. Vector
inputs use the fixture's exact source SHA-256 and source-publisher revision.

License: MIT OR Apache-2.0, consistent with this repository. Source provenance:
neutral fixture authored in this repository for the action-binding work dated
2026-10-23.
