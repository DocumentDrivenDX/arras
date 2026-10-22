---
ddx:
  id: feature-registry
  type: feature-registry
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
---

# Feature Registry

**Status**: Active
**Last Updated**: 12 October 2026

## Active Features

| ID | Name | Description | Status | Priority | Owner | Source | Updated |
|----|------|-------------|--------|----------|-------|--------|---------|
| FEAT-001 | Ontology Reads | A client reads the ontology with one operation, `query`: an entity by key, a type's entities in bounded pages, an entity with the keys it relates to, and counts by a property where a backend serves them. An opened entity states who created and last changed it and when. Each answer states its consistency level and freshness | Draft | P0 | Erik LaBianca | PRD: Ontology Reads (FR-1, FR-2, FR-4, FR-6 to FR-8, FR-47) | 2026-10-05 |
| FEAT-002 | Type Registry | A module defines its entity types, relationships and actions in a UMF document (UMF is the metamodel, owned by DocumentDrivenDX, that defines Arras's types and actions) and is placed by the host (record store, replicas, providers). A client enumerates what the ontology holds, and what each backend can do with it, through `describe` | Draft | P0 | Erik LaBianca | PRD: Type Registry (FR-3, FR-9 to FR-13) | 2026-10-05 |
| FEAT-003 | Actions | Actions are the only way a client changes the ontology: declared in UMF, validated, applied atomically by a provider, attributed to a person, idempotent, singly or in bulk | Draft | P0 | Erik LaBianca | PRD: Actions (FR-14 to FR-21, FR-42, FR-43) | 2026-10-05 |
| FEAT-004 | Backends | One backend contract for named backends, with the roles reader and provider, any number of backends, and three adapters: Truss (the open-source property-graph engine on Lakebase, Databricks managed Postgres), a reader and provider, Ashlar (the open-source property-graph toolkit on Unity Catalog, Databricks' governance layer for data), a reader that serves bounded reads as a replica, and an in-memory adapter | Draft | P0 | Erik LaBianca | PRD: Backends (FR-22 to FR-27) | 2026-10-05 |
| FEAT-005 | Access | Every backend call carries the caller's own token; Arras keeps no access decision and no cache, and tells empty, not permitted and unavailable apart | Draft | P0 | Erik LaBianca | PRD: Access (FR-28 to FR-30) | 2026-10-05 |
| FEAT-006 | Embedding and Lifecycle | A host Python application starts Arras with its named backends, the placement of each module and an administrative principal for registration, attachment and imports and supplies an installing connection, installs or verifies the adapters' stores through their own installers, and learns whether each backend is available | Draft | P0 | Erik LaBianca | PRD: Embedding and Lifecycle (FR-31 to FR-35) | 2026-10-05 |
| FEAT-007 | Admin Console | A minimal read-only interface for administrators and module developers to see the modules, types, placement, capabilities and entities the ontology holds | Draft | P1 | Erik LaBianca | PRD: Admin Console (FR-36, FR-37) | 2026-10-05 |
| FEAT-008 | Reference Clients | The first real users of the interface and the source of its requirements: the product catalog, the use case inventory and an embedding workflow host | Draft | P0 | Erik LaBianca | PRD: Reference Clients (FR-38 to FR-41) | 2026-10-05 |
| FEAT-009 | MCP Binding | A stdio MCP server, `python -m arras.mcp`, built on the library (MCP, the Model Context Protocol, is Anthropic's open protocol for agent tools): `describe`, `query`, `validate_action` and one tool per declared action, serving one person per process | Draft | P0 | Erik LaBianca | PRD: MCP Binding (FR-44 to FR-46) | 2026-10-05 |
| FEAT-010 | Operator Console | Operate, the model and platform mode of the interface: a dense React interface (`arras-ui`, in `ui/`) for administrators and module builders: browse the model, read data, change it only by invoking declared actions, and read the changes the backends keep; its Entities, Graph and Actions are power views that link to Explore and are frozen (SD-013) | Draft | P1 | Erik LaBianca | PRD: Operator Console (FR-48 to FR-52); FR-71 to FR-74 shared with FEAT-011 (SD-013) | 2026-10-12 |
| FEAT-011 | Graph Browser | An interface for people who use the ontology: search with type filters, a node page that the module's own UMF view declaration styles, links to follow to related entities, a picture of the node's neighbourhood, and, for operators, instance work by declared actions: an in-place edit, links, New, Retire, an Actions menu and History (`arras-ui`, `browser` entry; SD-013) | Draft | P1 | Erik LaBianca | PRD: Graph Browser (FR-53 to FR-60, FR-64 to FR-74: FR-67 to FR-71 New, Retire, History, Actions and cross-mode links (US-079 to US-083); FR-72 to FR-74 shared quality, brand and bookmarkable pages with FEAT-010; SD-013) | 2026-10-12 |

## Status Definitions

- **Draft**: Requirements being gathered
- **Specified**: Feature spec complete (Frame done)
- **Designed**: Technical design complete (Design done)
- **In Test**: Tests being written
- **In Build**: Implementation in progress
- **Built**: Implementation complete
- **Deployed**: Released to production
- **Deprecated**: Scheduled for removal
- **Cancelled**: Will not be pursued

## Dependencies

| Feature | Depends On | Type | Notes |
|---------|------------|------|-------|
| FEAT-001 | FEAT-002 | Required | Reads use the enumerated types and capabilities |
| FEAT-001 | FEAT-004 | Required | Backends answer reads |
| FEAT-001 | FEAT-005 | Required | The backends enforce access on every read |
| FEAT-003 | FEAT-002 | Required | Actions are declared in the registry |
| FEAT-003 | FEAT-004 | Required | The provider applies actions |
| FEAT-003 | FEAT-005 | Required | The backends enforce access on every action |
| FEAT-004 | FEAT-006 | Required | The host lifecycle connects and migrates the backends |
| FEAT-005 | FEAT-004, FEAT-006 | Required | The person's own token reaches each backend through the connection sources |
| FEAT-007 | FEAT-001, FEAT-002 | Required | The console reads through the interface |
| FEAT-009 | FEAT-001, FEAT-003 | Required | The MCP tools bind `query`, `describe`, `validate_action` and the actions |
| FEAT-009 | FEAT-005, FEAT-006 | Required | One person's token per process; the only reader of the environment |
| FEAT-010 | FEAT-001, FEAT-003, FEAT-005, FEAT-007 | Required | The console reads through CONTRACT-006, changes data only through actions, and runs as the viewer's principal |
| FEAT-011 | FEAT-001, FEAT-002, FEAT-003, FEAT-005, FEAT-010 | Required | The browser reads through CONTRACT-006 and CONTRACT-010, changes data only by invoking declared actions as the viewer, and shares the package, shell and action kit with the console (SD-013) |
| FEAT-008 | FEAT-001 to FEAT-006 | Required | Clients use the whole interface |

## Trace Links

| Feature | Spec | Stories | Designs | Tests | Release |
|---------|------|---------|---------|-------|---------|
| FEAT-001 | [FEAT-001](features/FEAT-001-ontology-reads.md) | US-001 to US-007, US-055 | ADR-014, CONTRACT-001 | - | - |
| FEAT-002 | [FEAT-002](features/FEAT-002-type-registry.md) | US-008 to US-012 | ADR-013, CONTRACT-002 | - | - |
| FEAT-003 | [FEAT-003](features/FEAT-003-actions.md) | US-013 to US-020, US-045 to US-048 | ADR-015, CONTRACT-003 | - | - |
| FEAT-004 | [FEAT-004](features/FEAT-004-backends.md) | US-021 to US-026, US-059 | ADR-013, ADR-020, CONTRACT-004 | - | - |
| FEAT-005 | [FEAT-005](features/FEAT-005-access.md) | US-027 to US-029, US-049 | ADR-017 | - | - |
| FEAT-006 | [FEAT-006](features/FEAT-006-embedding-and-lifecycle.md) | US-030 to US-034, US-056 to US-058 | ADR-006, ADR-012, ADR-018, ADR-019, CONTRACT-005, CONTRACT-008 | - | - |
| FEAT-007 | [FEAT-007](features/FEAT-007-admin-console.md) | US-035 to US-037 | ADR-011, CONTRACT-006 | - | - |
| FEAT-008 | [FEAT-008](features/FEAT-008-reference-clients.md) | US-038 to US-044 | CONTRACT-001, CONTRACT-003 | - | - |
| FEAT-009 | [FEAT-009](features/FEAT-009-mcp-binding.md) | US-050 to US-054 | ADR-016, CONTRACT-007 | - | - |
| FEAT-010 | [FEAT-010](features/FEAT-010-operator-console.md) | US-060 to US-064 | ADR-021, CONTRACT-009 | - | - |
| FEAT-011 | [FEAT-011](features/FEAT-011-graph-browser.md) | US-065 to US-072, US-079 to US-083 | ADR-022 to ADR-025, ADR-029, ADR-030, SD-011 to SD-013, CONTRACT-010 | - | - |

## Feature Categories

### Interface
- FEAT-001: Ontology Reads
- FEAT-002: Type Registry
- FEAT-003: Actions
- FEAT-009: MCP Binding

### Platform
- FEAT-004: Backends
- FEAT-005: Access
- FEAT-006: Embedding and Lifecycle

### Clients and tools
- FEAT-007: Admin Console
- FEAT-008: Reference Clients
- FEAT-010: Operator Console
- FEAT-011: Graph Browser

## ID Rules

1. Sequential numbering: FEAT-XXX (zero-padded 3 digits)
2. Never reuse IDs, even for cancelled features
3. Do not encode category or priority into the ID
4. Keep full behavior in Feature Specifications, not in this registry

## Deprecated/Cancelled

| ID | Name | Status | Reason | Date |
|----|------|--------|--------|------|
| None | | | | |
