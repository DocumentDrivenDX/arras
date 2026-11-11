# Roadmap

Open work, in rough order. Nothing here is a commitment.

- **Move to the unified UMF stack.** Depend on `umf-truss` (replacing `truss-toolkit`), `umf-weft` (replacing
  `weft-sql`) and the unified `umf-core` line once released, with ranges instead of exact pins; regenerate
  `tests/fixtures/umf-core-reference/current-conformance.json` from the new `umf-core`. Drop
  `tools/find-links/index.html` when `pgserver-pg18` is on PyPI.
- **Truss adapter drift.** Run `pytest -m truss` against the newer Truss and fix the adapter; PostgreSQL 18.6
  is the only supported server.
- **Ashlar adapter.** Experimental and not CI-tested; it needs a host factory and a CI path before it can be
  called supported. The feed from Truss to Ashlar is not built.
- **Visual regression tests.** Screenshot baselines are not committed. If wanted, generate Linux baselines in
  CI as artifacts, and remove the `visual` project from the public testkit otherwise.
- **Trim the design documents.** The PRD, user stories, spikes and test plan predate the current scope.
