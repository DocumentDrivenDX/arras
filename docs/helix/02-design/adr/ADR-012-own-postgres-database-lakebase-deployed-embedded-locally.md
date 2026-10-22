---
ddx:
  id: ADR-012
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-13
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: SPIKE-005
      kind: informed_by
    - id: ADR-006
      kind: informed_by
    - id: CONTRACT-004
      kind: informs
---

# ADR-012: The Truss adapter's store persists in its own Postgres database: Lakebase when deployed, a local PostgreSQL 18.6 for development and tests

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-04 | Accepted | Erik LaBianca (architecture lead) | [ADR-006](ADR-006-embedded-library-on-psycopg-and-the-truss-toolkit.md), [SPIKE-005](../spikes/SPIKE-005-lakebase-cost-and-instance-topology.md), [PRD](../../01-frame/prd.md), [CONTRACT-004](../contracts/CONTRACT-004-backend-contract.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | Arras is the interface to an ontology, a Python library embedded in a host application. Its mutable modules run on Truss (an open-source, UMF-driven property-graph engine on SQL databases; owner: DocumentDrivenDX), and Truss runs on Postgres. Where that Postgres lives, locally and on Databricks, and whether it shares a database instance with the embedding host, need a decision. One option is a separate catalog database inside the host's own Lakebase project. Lakebase is Databricks' managed Postgres. |
| Current State | The original deployment input described a dedicated Arras Lakebase project beside a host-state project. Its 0.5-to-2-CU sizing and 300-second suspend were decision-time settings, not a current account qualification. Arras pins Truss 0.0.45; the exact server/driver/platform cohort and local engine requirements remain CONTRACT-005 concerns. |
| Requirements | Local development and tests need no external database. A deployed Arras uses Lakebase. The Truss adapter's data stays separate from the host's operating state. |
| Decision Drivers | Cost: SPIKE-005 finds that sharing the host's instance saves at most one endpoint, about $40 per month if never suspended and $0 when idle. Isolation: a separate database means a separate failure domain, permission model and install lifecycle. The library must run on Python 3.11 (ADR-010), and `pgserver-pg18` through Truss's `local` extra is the local PostgreSQL Truss qualifies. |

## Decision

We will run the Truss adapter's store on **its own Postgres database, separate from the host's**, even when Arras runs inside the same Databricks app. **Deployed on Databricks it uses Lakebase; locally it uses the local PostgreSQL 18.6 that Truss's `local` extra provides, as a dev-only dependency.** It shares a database instance with the embedding host only for a recorded cost reason, and SPIKE-005 found none.

**Key Points**: Arras uses its own Lakebase project, `arras`, separate from the host's | The workspace module's defaults and comments name that project `arras` | Arras's application bundle creates its database, and cost does not decide the choice | The deployed app attaches Arras's database as a resource separate from the host's, and Arras reads only the connection settings the host gives it (ADR-006) | Locally, `pgserver-pg18` through `truss-toolkit[local]` provides the database for development and tests; it is a dev-group dependency and is absent from the deployed install | Local and CI use PostgreSQL 18.6, the version Lakebase runs; Arras composes no SQL of its own (ADR-006), so there is no portability rule | Lakebase is the required deployment target and is PostgreSQL 18.6 | Sizes start at 0.5 to 2 CU with a 300-second suspend until measurement says otherwise

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| A separate database inside the host's Lakebase project | Shares one endpoint (saves up to about $40 per month at the 0.5 CU floor) | One compute, one failure and performance domain, and one permission model; the original topology assumed the host app principal was the only reader and writer of its own operating-state project; cross-database grant behavior is undocumented | Rejected: the saving is small and separation is the stated default |
| Arras tables in the host's own database | One resource | Mixes the ontology's data with sessions and transcripts, against the separation of host session state and ontology data | Rejected |
| `pgembed` for local development | Newer; bundles Postgres 17 and vector extensions | Its wheels cover Python 3.12 to 3.14 only, so it cannot install with the library's 3.11; Truss does not qualify Postgres 17 | Rejected: incompatible with ADR-010 and with Truss's qualified engine |
| A local Postgres from Docker or a system install | Familiar | An external dependency to install; its version must match Truss's qualified 18.6 exactly | Rejected: embedded needs no setup |
| A second Lakebase project for Arras beside `arras` | Nothing | Two projects to own, size and pay for, one of them unused | Rejected: the declared `arras` project is the one |
| **Own database in the `arras` project; Lakebase deployed; local PostgreSQL 18.6 locally** | Runs on 3.11; one engine version locally and in CI; no extra cost at idle; separate failure domains | A second database resource to provision and attach| **Selected** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Arras can be sized, migrated, branched and suspended independently of the embedding host. A fault or a heavy query in one cannot stall the other. Local work needs nothing installed. |
| Negative | A second connection in the deployed app, and a database and roles to create in the `arras` project through Arras's bundle. No new project: the cost is what `arras` already incurs, up to about $40 per month at its 0.5 CU floor if it never suspends, double if the reported rate is the promotional half. Whether a project named `ontology` was ever applied in the workspace is unchecked (concerns.md, open question 2). |
| Neutral | The catalog is served from Arras's database, not from a separate one inside the host's own project. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The deployed app cannot attach a database from a second Lakebase project beside the host's | L | M | Verify on the first deploy of Arras's resource; if it cannot, the host's project would have to host a database for Arras, and this ADR must be revisited |
| Costs differ from the reported rates | M | M | Verify the Azure rates and the post-January 2027 standard rate (SPIKE-005 recommendation 2) |
| `pgserver-pg18` is abandoned or lacks a wheel for a CI platform or a Python version above 3.11 (unchecked) | M | L | Dev-only; the connection source is the host's (CONTRACT-005), so a PostgreSQL 18.6 can stand in |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| The full suite passes locally on the local PostgreSQL 18.6 and in CI on the same engine | A test passes on one and fails on the other |
| The deployed app serves the catalog from Arras's database while host sessions stay in the host's own database | Any Arras table appears in the host's database, or the reverse |
| Arras's monthly Lakebase compute cost stays within the SPIKE-005 range | A month exceeds the always-on figure at the sized maximum |

## Concern Impact

- **Concern selection**: `lakebase-postgres` in [`../../01-frame/concerns.md`](../../01-frame/concerns.md) gains the local embedded engine, the qualified-version rule and the own-database rule.
- **Practice override**: none.

## References

- [SPIKE-005](../spikes/SPIKE-005-lakebase-cost-and-instance-topology.md): cost, hierarchy and limits, and the embedded-Postgres test
- Original downstream connection-lifecycle input; the reusable separation decision and validation are owned by this ADR and CONTRACT-005.
