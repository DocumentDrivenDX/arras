---
ddx:
  id: stakeholder-map
  type: stakeholder-map
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: product-vision
      kind: informed_by
---

# Stakeholder Map

**Status**: Draft

Stakeholders are roles, drawn from the artifacts this repository holds. Where a role is inferred rather than stated, the entry says so.

Arras is the interface to an ontology over named backends, with the roles reader and provider; in production two stores: Truss, the hot mutable store on Lakebase (Databricks managed Postgres), and Ashlar, the warehouse store on Unity Catalog (Databricks' governance layer for data). Types and actions are defined in UMF (the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions).

## Primary Stakeholders (High Influence, High Interest)

### Arras maintainers
- **Role**: Decide the direction, scope and stack of Arras and own its artifacts.
- **Interest**: Arras becoming the one interface to the ontology over its backends (Truss and Ashlar today), starting with the catalog, with a stack a host app can embed.
- **Influence**: Decide scope and stack.
- **Concerns**: A host and Arras diverging into two stores; startup risk in a shared app; latency on Lakebase; the interface fitting only one backend.
- **Success Criteria**: The catalog runs on Arras's interface inside a host within the latency targets.
- **Communication**: Direct working sessions; pull-request review.
- **Contact Channel**: Pull requests and issues in this repository.

### Host-app developers
- **Role**: Embed Arras in a host application (praxis is the first host), own the host's startup path and map its identity to a principal. Inferred as the host's integration owner.
- **Interest**: A catalog that deploys with the host through Arras's interface, imports nothing from the host's internals, cannot break shared-app startup, and gives the host context reads on behalf of the user.
- **Influence**: Can accept or reject Arras as a module's store; own the host's startup path.
- **Concerns**: Startup budget, migration safety across instances, an independence check in the build.
- **Success Criteria**: The host starts and serves with the catalog available, and still serves when the catalog database is down.
- **Communication**: Pull-request review on the embedding and the catalog's store.
- **Contact Channel**: Pull requests in the host's repository.

### Data governance owner
- **Role**: Decides whether structure derived from sensitive source records may be built (ADR-005). Inferred.
- **Interest**: Knowledge made traceable and actionable, without speculative builds; no structure derived from sensitive source records without a workload, an entitlement rule and a governed write path.
- **Influence**: Approves what is built and when.
- **Concerns**: Building structure that no workload needs; unowned governed writes.
- **Success Criteria**: A named workload (the catalog) justified in writing, and a working demonstration.
- **Communication**: Review of ADR-005 and the demonstration.
- **Contact Channel**: Pull requests and issues.

## Secondary Stakeholders (Variable Influence/Interest)

### Module builders
- **Role**: Build modules in UMF and maintain catalog knowledge through the catalog screens and the console.
- **Interest**: Correct a record once, attributed to them; see a module's registry and audit trail.
- **Influence**: Medium; their acceptance decides whether the catalog is used.
- **Engagement Level**: Consult
- **Contact Channel**: Catalog demonstration and issues.

### Administrators (platform owners)
- **Role**: Provision the Lakebase database resource, its roles and grants, and the Unity Catalog access Ashlar reads need. Inferred from the dependency on a second database and its grants.
- **Interest**: Few resources, grants that can be stated and audited.
- **Influence**: High on delivery: nothing deploys without the resource and grants.
- **Engagement Level**: Collaborate
- **Contact Channel**: The host's infrastructure change process.

### Truss, Ashlar and UMF maintainers
- **Role**: Own the generic engine, the warehouse toolkit and the metamodel that Arras's backends and types depend on. Arras's requirements reach them as requests to each project.
- **Interest**: Clear, generic requirements derived from real client interactions, with no Arras-specific content in their repositories.
- **Influence**: High on delivery of the backends and of UMF's action contract; none on Arras's scope.
- **Engagement Level**: Collaborate
- **Contact Channel**: Pull requests in each repository.

### End users (readers)
- **Role**: Read what the ontology holds through the Graph Browser or a host's screens. They are not operators.
- **Interest**: Find a thing, read it as a page, follow its links.
- **Influence**: Low on scope; their use decides whether the browser is worth keeping.
- **Engagement Level**: Inform
- **Contact Channel**: Issues.

## RACI Matrix

| Activity/Decision | Arras maintainers | Host-app developers | Data governance owner | Administrators |
|-------------------|-------------------|---------------------|-----------------------|----------------|
| Product vision and PRD | A/R | C | C | I |
| Does the catalog use Arras's interface? | A/R | R | C | I |
| Catalog types and demonstration records | C | A/R | I | I |
| Role names and grants per module; Unity Catalog access | C | C | I | A/R |
| Embedding and startup behavior | C | A/R | I | C |
| Technical decisions (ADRs) | A/R | C | I | C |
| Sensitive-source-record-free assumption | R | I | A | I |
| Governed write path for derived structure | C | I | A/R | I |
| Release decision | A/R | C | C | C |

**R** = Responsible | **A** = Accountable | **C** = Consulted | **I** = Informed

## Power/Interest Grid

```
High Power  | Keep Satisfied      | Manage Closely
            | - Administrators    | - Arras maintainers
            |                     | - Host-app developers
            |                     | - Data governance owner
            |---------------------|-------------------
Low Power   | Monitor             | Keep Informed
            | - Truss, Ashlar and | - Module builders
            |   UMF maintainers   | - End users
            Low Interest          High Interest
```

## Communication Plan

| Stakeholder Group | Channel | Frequency | Content | Owner |
|-------------------|---------|-----------|---------|-------|
| Host-app developers | Pull requests in the host's repository | Per change | Embedding, startup, catalog types | Arras maintainers |
| Administrators | The host's infrastructure change process | Per resource change | Database resource, roles, grants | Arras maintainers |
| Data governance owner | ADR-005 review | As needed | Status, the catalog demonstration, open questions; no structure built outside this scope | Arras maintainers |
| Module builders | Catalog demonstration | Per demonstration | Catalog behavior and corrections | Host-app developers |

### Escalation Path
1. A host-startup or integration dispute goes to the Arras maintainers and the host-app developers first, then to the data governance owner.
