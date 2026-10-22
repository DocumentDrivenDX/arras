# CLAUDE.md

Arras: an open-source interface to an ontology. UMF-defined types and actions, reads that state their freshness, and a backend contract with a Truss adapter (authoritative, PostgreSQL or Lakebase) and an Ashlar adapter (replica, Unity Catalog). A Python library that host apps such as praxis embed. See `docs/helix/01-frame/prd.md`, `concerns.md`, ADR-013 to ADR-015 and the contracts in `docs/helix/02-design/contracts/`.

## HELIX

HELIX is initialized. `.helix.yml` declares one instance, `arras`, rooted at `docs/helix/` with the activity tree `00-discover` to `06-iterate`. Governed artifacts (PRDs, ADRs, designs, test plans) go in the matching activity directory via the HELIX skill. Raw incoming material lands in `docs/intake/` unedited and is outside HELIX.

- Durable structure over sensitive source records is deferred until a named workload, an entitlement rule and a governed write path exist (ADR-005). Spikes under `docs/helix/02-design/spikes/` are feasibility work, not the product.
- Python 3.11 with `uv` and a committed `uv.lock`; never a `requirements.txt` in an app directory (ADR-010). Writes are UMF actions applied on the authoritative backend; access is the backends' own (Postgres role grants on Truss, Unity Catalog on Ashlar). Truss, Ashlar and UMF docs never name Arras.
