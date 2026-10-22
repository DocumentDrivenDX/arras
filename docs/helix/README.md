# HELIX artifacts

Scope root for the `arras` instance of the `helix` flow declared in
[`.helix.yml`](../../.helix.yml). HELIX is the documentation-driven workflow that
organizes this repository's governed artifacts (PRDs, ADRs, designs, test plans) by
activity. Arras is an open-source interface to an ontology: UMF-defined types and
actions, reads that state their freshness, and a backend contract over named backends (a Truss adapter,
an Ashlar adapter and an in-memory adapter). Each activity has one directory:

| Directory | Activity | Owns |
| --- | --- | --- |
| `00-discover/` | Discover | product vision, business case, research |
| `01-frame/` | Frame | PRD, feature specs, user stories, concerns, principles |
| `02-design/` | Design | architecture, ADRs, contracts, spikes, solution designs |
| `03-test/` | Test | test plans |
| `04-build/` | Build | implementation plans |
| `05-deploy/` | Deploy | deployment checklists, runbooks |
| `06-iterate/` | Iterate | roadmap, iteration plans, backfill reports |

[`glossary.md`](glossary.md) defines the external systems and Arras terms the artifacts use.

The [Arras integration build plan](04-build/arras-integration-plan-20261022.md)
coordinates official UMF adoption, generated-client transport and the existing
Truss follow-up work. It records the current cohort, owners, first bounded change
and remaining native qualification; planned integration is not delivered support.

Raw incoming material goes in `docs/intake/`, outside HELIX. Author artifacts
through the HELIX skill (`/helix`).
