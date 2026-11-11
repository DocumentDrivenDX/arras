# Arras

An open-source interface to an ontology: UMF-defined types and actions, reads that state their freshness,
and a backend contract with a Truss adapter (PostgreSQL) and an experimental Ashlar adapter. A Python 3.11
library that host apps embed, plus a React operator console and Graph Browser in `ui/`.

- Setup: `uv sync --extra truss --extra umf --extra devhost`. Tests: `uv run pytest -q`; lint and types:
  `uv run ruff check . && uv run ruff format --check . && uv run pyright`; UI: `cd ui && npm ci && npm test`.
- Real Truss needs `--group truss-test` and `pytest -m truss`; CI runs it nightly and on release.
- CI (`.github/workflows/ci.yml`) is the gate and is Linux only. Releases are tag-driven (`release.yml`).
- Design lives in `docs/helix/`: ADRs in `02-design/adr/`, contracts in `02-design/contracts/`. UMF defines
  metamodel semantics; Arras consumes it and never redefines it.
- Do not commit run output, receipts, evidence or qualification documents; put notes in the PR description.
  Never put a person's name or credentials in test data or docs.
