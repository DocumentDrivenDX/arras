---
ddx:
  id: SPIKE-005
  type: tech-spike
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-04
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: ADR-012
      kind: informs
---

# Technical Spike: What Lakebase costs, and whether the Truss backend needs to share an instance with the embedding host

**Spike ID**: SPIKE-005 | **Lead**: Erik LaBianca | **Time Budget**: one research session | **Status**: Completed

Terms used in this spike:

- Arras is the interface to an ontology: UMF-defined types and actions, reads that state their freshness, and a backend contract with two adapters.
- Truss (DocumentDrivenDX) is the UMF-driven property-graph engine that Arras runs as its hot, authoritative, mutable store. The Truss backend is that store and its database.
- Lakebase is Databricks' managed Postgres. A Lakebase project holds branches, and each branch holds databases and one primary read-write compute.
- the host is the application that embeds Arras as a library.
- ADR is an architecture decision record. ADR-012 decides that Truss has its own Postgres database, on Lakebase when deployed and embedded Postgres locally.
- CU (capacity unit) is Lakebase's compute size, billed per hour. DBU is the Databricks billing unit for compute. DSU is the billing unit for storage.
- `pgserver` and `pgembed` are Python packages that run an embedded Postgres for local development.

## Objective

**Historical scope.** Deployment topology, costs and local engines below describe the dated reference configuration and measurements. They do not impose a service identity on every host or qualify the current installed server cohort.

**Technical Question**: What does a Lakebase Postgres project cost at the sizes Arras runs, and is there a cost reason for the Truss backend to share a database instance with the embedding host instead of living in its own database?

**Why now**: The Truss backend holds the catalog's mutable data. It runs on Lakebase when deployed on Databricks and on an embedded Postgres locally. The default is a separate database from the embedding host, even inside one Databricks app, unless cost argues otherwise.

**Goals**:
- [x] Estimate the monthly cost of the configurations in use.
- [x] Identify the billing unit and what scales it.
- [x] Identify the project and database hierarchy and the limits that bear on topology.
- [x] Compare the cost of the alternatives.

**Success Criteria**: A monthly cost range for the configurations in use, the billing unit and what scales it, the project and database hierarchy and limits that bear on topology, and a recommendation with the cost delta of the alternatives.

**Out of Scope**: Query performance on Lakebase, high-availability replicas, read replicas, cross-region options.

## Hypothesis

**Primary**: A second Lakebase project adds little cost at the sizes in use, because compute scales to zero when idle and storage is small.

**Assumptions**: A separate database inside the host's project saves one compute endpoint at most, which is too little to justify losing the failure and permission separation.

## Approach

**Method**: Literature review and comparative analysis of Lakebase documentation, public price points and the Lakebase project and endpoint settings, plus a local test of the embedded Postgres packages.

**Activities**:

1. Read the Lakebase documentation for the hierarchy, limits and scale-to-zero (docs.databricks.com, manage-projects and manage-databases).
2. Collect price points from public sources. The official pricing table is rendered client-side and did not load, so figures come from a third-party summary dated 23 Jul 2026 (updated 1 Oct 2026) and Databricks' Always-On announcement.
3. Read the Lakebase project settings (cloud, version, sizes and suspend windows) that bear on a small deployment.
4. Compute monthly costs for the configurations in use.
5. Run the embedded-Postgres candidates locally to confirm they support what the Truss backend's role model needs (`SET LOCAL ROLE` with a settable, non-inherited grant).

**Stop rule**: Stop when the five questions in the Objective have an answer, or when a figure cannot be found on a primary source (then mark it unverified).

## Findings

**FINDING 1**: Lakebase compute is billed in CU per hour, and storage per GB-month.
- **Evidence**: One CU is "roughly 2 GB of RAM, along with associated CPU and local SSD" (third-party summary, 23 Jul 2026, updated 1 Oct 2026). Compute is billed in DBUs through Lakebase SKUs and storage in DSUs per GB-month (Databricks community post, 12 Aug 2025). The CU range is 0.5 to 112, with autoscaling up to 64 CU, and the difference between minimum and maximum may not exceed 16 CU (manage-projects limits).
- **Implications**: Cost scales with active compute hours and CU size, so suspend settings and the maximum CU govern the bill.

**FINDING 2**: On Azure, the reported list rates are $0.111 per CU-hour and $0.390 per GB-month. These are unverified.
- **Evidence**: The third-party summary lists Azure at $0.111 per CU-hour and $0.390 per GB-month of storage (AWS $0.092 and $0.345). The same source says the CU rates "reflect 50% off until Jan 31, 2027" promotional pricing, and Databricks' Always-On announcement describes a promotional 50% discount through 31 Jan 2027. It is therefore unclear whether $0.111 is the promotional or the standard rate. If it is the promotional rate, the standard Azure rate would be about $0.222 (inference). The official table was not readable.
- **Implications**: Budget with both rates until the price table is read.

**FINDING 3**: Idle compute can cost nothing, and always-on compute has a discounted baseline.
- **Evidence**: Scale-to-zero is on by default with a 24-hour suspend timeout; the minimum is 60 seconds and the maximum 7 days (manage-projects limits). Always-On pricing gives 25% off baseline capacity after 24 hours of continuous use, if scale-to-zero is disabled; the third-party summary lists Azure Always-On at $0.083 per CU-hour. Snapshot storage became chargeable on 1 Jun 2026; the rate was not found.
- **Implications**: A short suspend timeout makes idle time free. Snapshot storage cost is unknown.

**FINDING 4**: A small project is a sizing choice, not the default.
- **Evidence**: A new project defaults to 8 to 16 CU with a 24-hour suspend. A configuration of 0.5 CU minimum, 2 CU maximum and a 300-second suspend, on Postgres 18, is set explicitly.
- **Implications**: A project created at the defaults would cost far more than one sized explicitly.

**FINDING 5**: Several databases can live in one branch of one project, sharing that branch's compute.
- **Evidence**: "a database exists within a branch of a project, with a limit of 500 databases per branch" (manage-databases). Each branch has one primary read-write compute (search result summarizing manage-projects). Limits: 500 branches per project, 500 roles per branch, 20 concurrently active computes, 1,000 projects per workspace. The documents read do not say how databases share compute or storage cost, nor how roles and grants work across databases (absent from the page).
- **Implications**: Sharing a branch would save one endpoint. Cross-database grant behavior is undetermined.

**FINDING 6**: A Lakebase project of Arras's own, separate from the host's, needs no new mechanism.
- **Evidence**: A workspace holds up to 1,000 projects (Finding 5), and a project is declared with an identifier, a display name and a Postgres version (here `arras`, "Arras", 18). Roles, databases and dev branches belong to the application's own bundle.
- **Implications**: A separate project is one more declaration.

**FINDING 7**: Of the two embedded Postgres packages, only `pgserver` runs on the Python 3.11 that the library requires.
- **Evidence**: Tested 4 Oct 2026. `pgserver` 0.1.4 on Python 3.11.17 starts PostgreSQL 16.2. `pgembed` 0.2.0 starts PostgreSQL 17.9 on Python 3.12, but has wheels only for CPython 3.12, 3.13 and 3.14, so installing it under 3.11 fails. Both accepted a role grant with `INHERIT FALSE, SET TRUE` (the form CONTRACT-004 requires). Neither provides `uuidv7`. The original reference host also used a local PostgreSQL development dependency. This dated observation does not qualify the current Truss engine cohort.
- **Implications**: Local development uses `pgserver`.

### Measurements

Monthly compute cost at the reported Azure list rate of $0.111 per CU-hour, 730 hours in a month. The last column applies if the reported rate is the promotional half.

| Configuration | At $0.111 | If $0.222 |
|---|---|---|
| Suspended all month (idle) | $0 | $0 |
| 0.5 CU, about 176 active hours (weekday working hours) | $9.8 | $19.5 |
| 0.5 CU always on | $40.5 | $81.0 |
| 0.5 CU always on, Always-On baseline ($0.083) | $30.3 | not computed |
| 2 CU always on (the project maximum) | $162.1 | $324.1 |
| 8 CU always on (a new project's default minimum) | $648.2 | $1,296.5 |

Storage at $0.390 per GB-month: a 6.51 GB database costs about $2.54 per month. Branches are copy-on-write, and snapshot storage is chargeable at an unknown rate. Local development costs nothing.

## Analysis

**Hypothesis**: CONFIRMED
**Rationale**: A second endpoint adds at most about $40 per month at the 0.5 CU floor and nothing when idle (Findings 3 and 4, Measurements). The saving is small next to the loss of separation. This confirms the cost claim only; the resume-latency risk is not confirmed or ruled out, because resume time was not measured.

Cost of sharing. Putting the Truss backend in the host's project would save one endpoint. At the configured 0.5 CU floor that is at most about $40 per month if the second endpoint never suspended, about $10 per month on business hours, and $0 when idle. If the reported rate is the promotional half, double each.

Isolation. The host's project is set up so the app's service principal is the only reader and writer by design. A second database in that branch would share one compute (one performance and failure domain, and one suspend and resume cycle) and the same project-level permission model. Cross-database grant behavior is not documented on the pages read.

Cold start. With a 300-second suspend, the first request after idle pays a resume delay. The documents read give no resume time. The singleton read target in the PRD (p95 of 20 ms) assumes a warm connection, so the first request after suspension needs its own measurement (US-044 covers the latency targets on the catalog).

Version gap. Lakebase here runs Postgres 18 and the local `pgserver` runs 16.2. Any SQL in the Truss backend that needs 17 or 18 features (for example `uuidv7`) would not run locally.

### Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| The reported rate is the promotional half and the standard rate applies after 31 Jan 2027 | M | M | Re-check against the Azure price table or the workspace's `system.billing.list_prices` before budgeting past January 2027 |
| A project left at the default 8 to 16 CU is created by mistake | L | H | Arras's project is declared with explicit sizes; the default would cost about $648 per month |
| Resume latency breaks the latency targets | M | M | Measure first request after suspend separately (US-044); set the suspend timeout from that measurement |
| Snapshot and branch storage charges grow unnoticed | L | L | Track `system.billing.usage` by SKU; keep dev branches expiring |
| An app cannot attach two Lakebase databases from different projects | L | M | Verify on the first deploy of an Arras resource (unverified) |

## Conclusions

**Primary Conclusion**: No cost reason exists to share the host's database instance with the Truss backend. The most a second endpoint can add at the sizes in use is about $40 per month, and it adds nothing when idle.

- The Truss backend should have its own database, and its own instance (project), separate from the host's.
- The Lakebase project `arras` is separate from the host's and sized small. It is the home for the Truss backend's database.
- Locally, `pgserver` is the embedded Postgres: it runs on Python 3.11 and is the original host convention.

**Confidence**: Medium. The rates are unverified and cold-start latency is unmeasured.

**Limitations**: The standard Azure rate, the snapshot storage rate, resume time, cross-database grant behavior and attaching two projects to one app were not determined.

## Recommendations

**RECOMMENDATION**: Use a Lakebase project of its own, `arras`, for the Truss backend, never the host's, sized at 0.5 to 2 CU with a 300-second suspend until measurement says otherwise. Run locally on `pgserver`, as a dev-only dependency.
- **Rationale**: Findings 3, 4 and 6 and the Measurements show the cost of a separate project is small, and the isolation argument favors separation.
- **Next Steps**:
  1. Have the application bundle create the Truss backend's database and roles in the `arras` project (ADR-012).
  2. Verify the Azure CU-hour and storage rates, and the standard rate after 31 Jan 2027, from the price table or `system.billing.list_prices`.
  3. Measure resume time and first-request latency on the chosen project, and confirm the app can attach it beside the host's.
  4. Keep the SQL portable across Postgres 16 and 18, with CI (continuous integration) on both.
- **Concern Impact**: Consistent with ADR-012 and the `lakebase-postgres` concern's project-local setting, pending the resume-time measurement. No change.

## Artifacts

- Local test of embedded Postgres: scratch script run 4 Oct 2026 (not kept); results in Finding 7.
- Sources: Databricks docs [manage projects](https://docs.databricks.com/aws/en/oltp/projects/manage-projects) and [manage databases](https://docs.databricks.com/aws/en/oltp/projects/manage-databases); Databricks blog [Always-On pricing for Lakebase](https://www.databricks.com/blog/introducing-always-pricing-automatic-savings-databricks-lakebase); [Lakebase Autoscaling cost summary, LakeSentry](https://lakesentry.io/blog/databricks-lakebase/) (23 Jul 2026, updated 1 Oct 2026); [Lakebase costing, Databricks community](https://community.databricks.com/t5/lakebase-blogs/partner-databricks-lakebase-costing-compute-storage-amp-reusable/ba-p/127945) (12 Aug 2025).
- The official Lakebase pricing page was not readable (client-rendered), so Finding 2's rates remain unverified.
