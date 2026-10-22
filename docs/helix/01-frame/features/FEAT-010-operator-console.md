---
ddx:
  id: FEAT-010
  type: feature-specification
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-001
      kind: informed_by
    - id: FEAT-003
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: FEAT-007
      kind: informed_by
    - id: concerns
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-021
      kind: informed_by
    - id: CONTRACT-009
      kind: informed_by
    - id: FEAT-002
      kind: informed_by
    - id: ADR-026
      kind: informed_by
    - id: CONTRACT-011
      kind: informed_by
---

# Feature Specification: FEAT-010 — Operator Console

**Feature ID**: FEAT-010
**Status**: Draft
**Priority**: P1
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Operator Console
**Covered PRD Requirements**: FR-48 to FR-63
**Cross-Subsystem Rationale**: None; single subsystem. It binds the reads of FEAT-001, the actions of FEAT-003 and the access of FEAT-005 into one interface, and, where a host mounts it, the registration of FEAT-002 as the person; it adds no operation to them and no role of its own.

## Overview

The Operator Console (**Operate**, in the shell) is the model and platform tool: a dense, designed interface for the people who build and run modules on the ontology, while the Graph Browser (**Explore**, FEAT-011) is where people work on the ontology's entities. Work on one entity (find, read, change, create, retire, its history) belongs in Explore and Operate links to it; work on the module as a system (its model, backends, bulk and import work, the changes of a whole module, the query language) belongs here (SD-013). It browses the registry (modules, types, relationships, actions, revisions), reads entities with their freshness, changes data only by validating and invoking the module's declared actions, and shows who changed what and what was run. It is a React application and component library in the `ui/` directory of this repository, published as `arras-ui`, that talks to Arras only over HTTP (ADR-021). The read surface is the console GraphQL surface (CONTRACT-006); the action and audit surface is CONTRACT-009, which binds the library's `validate`, `invoke`, `invoke_batch`, `changes` and `loads` (CONTRACT-003, CONTRACT-001).

## Delivery Slices

| Slice | Content | Depends on |
|-------|---------|------------|
| 1 | Model, Entities and Actions areas (OPR-01 to OPR-04, OPR-07, OPR-08, OPR-11) | CONTRACT-006 additions (attribution fields, typed action inputs); `expected_revision` and `group` in CONTRACT-003; the operate surface (CONTRACT-009) |
| 2 | Changes area (OPR-05, OPR-06) | `changes` and `loads` in CONTRACT-001 and CONTRACT-004; a documented journal read on the provider; the journal grant policy (PRD open questions) |
| 3 | Schema import and export, and the sandbox's roles and controls (OPR-12 to OPR-15), with the dev host serving the console | ADR-026; CONTRACT-011; `schema()` and `validate_register` (CONTRACT-002, CONTRACT-004); the dev host |
| 4 | Query area (OPR-16, OPR-17) | `POST /query` in CONTRACT-009 (a read of CONTRACT-001's `query`) |

Slice 1 ships without slice 2. The Changes area stays hidden until the backends serve it. Slices 3 and 4 do not wait on slice 2.

FEAT-007's console stays what it is: a read-only GraphiQL page with no write path. The Operator Console is a separate surface with a write path, and FR-37 binds FEAT-007 alone.

## Ideal Future State

A module builder opens the console in the embedding host or on its own host and sees the modules her principal may read. She opens a module, reads its types and the relationships between them as a diagram, and sees which backend serves each type and how current its reads are. She opens a type as a dense table, filters it, opens an entity beside the table and follows a relationship to the entity at its end. To correct an entry she does not edit a cell: she opens the action the module declares for the correction, which presents a form built from the action's inputs, sees the effects it would apply, confirms, and reads the receipt. She then opens the entity's history and sees the person who made the change and when, if the backend grants her that read. An administrator sees the same pages for every module he may read and a log of changes by person and by action. When the circle of operators widens to readers, each sees only the modules, actions and audit rows their own token permits, and nothing in the console grants more.

## Problem Statement

- **Current situation**: The interfaces are GraphiQL (read-only, no forms, no history) and this console. Changing a module's types needs a library call by the administrative principal at startup, so an operator needs a developer and a restart. Checking a module, correcting an entry or finding who changed it needs code, a database client, or a developer.
- **Pain points**: Module builders cannot see their own types and relationships as a whole, cannot try an action without writing a call, and cannot answer "who changed this" without access to the provider. Administrators cannot review activity across modules. The audience begins as administrators and module builders and may widen.
- **Desired outcome**: One interface for browsing the schema, reading data, running declared actions and reading the audit trail, scoped by each person's own token, with no write path other than actions (ADR-015) and no state of Arras's own (ADR-021).

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Model | What does this module declare, and what changed? | Modules, types, properties, relationships, actions, placement, capabilities and revisions, shown as tree and diagram; the registered UMF document in UMF's own schema explorer; import a UMF document with a preview and export a registered one |
| Entities | What is in it, and how current is that? | Dense paged tables by type (pages in key order, each after the last key of the one before), filters, entity detail, relationship traversal, consistency choice, freshness on every answer |
| Graph | What does the graph look like, and what is connected to what? | The module's entities as typed lanes with their relationships, filters, a selection panel and the changes just made |
| Actions | Make this change safely. | Forms generated from a declared action; validate; effects preview; confirm; invoke; receipt; batch with partial results |
| Changes | Who changed this, and what ran? | Change history of an entity, changes by person, action or time, a receipt by id, import loads, read from the backends |
| Query | What does this say, in my own words? | A read-only Weft SQL statement over a module, at the consistency the operator chooses, the result as a grid with its freshness, and a history of what was run in this session |
| Safety | Can this person do that? | The viewer's own token on every call; controls follow the backend's answer, never replace it; no raw row edit |
| Sandbox | Can I try every flow without Databricks? | In the development host only: pick a role and a name, and break and mend the sandbox's backends |

Model, Changes, Query and the sandbox are Operate's own work. **Entities**, **Graph** and **Actions** are power views over instances: each links to the same entity in Explore and is frozen, so no new per-entity feature is added here and each new per-entity need is built in Explore (SD-013 D5). The area names are the shell's vocabulary: Model, Entities, Graph, Actions, Changes (a module's journal), History (one entity's changes) and Query.

## Requirements

### Functional Requirements by Area

#### Model

OPR-01. An operator lists the modules their principal may read and, for each, browses its entity types with their properties, relationships and capabilities, its actions with their inputs, preconditions and effects, its placement and its registry revision, and sees the relationships between types as a diagram (FR-48).

OPR-11. An operator opens the module's registered UMF document, exactly as it was registered, in UMF's schema browser beside the live registry views, and sees only the modules their principal may read there too. The console reuses UMF's packaged schema browser (`@documentdrivendx/umf-schema-browser`, the public npm package at an exact version) rather than building a second one: the browser shows the declared document, and the console marks it with what this deployment serves (each backend's capabilities for each type, the record store, replicas and providers, a backend that is unavailable), refreshed in place when the live registry changes; the console's own views show the rest (full capabilities, the actions, the revision). The console reads the viewer's catalog with its own client and hands it to the package's `mountSchemaBrowser`, which is mounted only while the view is open and destroyed when it closes; choosing another module selects it in the same browser. A definition selected in the browser that is an entity type of the module can be opened in Entities or shown in Graph. The browser follows the console's colour scheme and runs under a strict Content-Security-Policy with no `'unsafe-eval'` (FR-48; CONTRACT-009 schema catalog; ADR-021, Reuse).

#### Schema administration

OPR-12. An operator chooses a UMF document (a file) and sees, before anything is applied, what it would add, change or retire in its module and every refusal the compatibility rules would raise, each with its rule and its count or offenders. The console calls validate-only registration (`validate`, CONTRACT-011) and shows the plan beside the module's current registered document. A document that does not parse, names an unplaced module or is incompatible shows its violations and offers no apply (FR-61).

OPR-13. An operator applies a plan as themselves. The console registers the document with the revision the plan was computed against as `expected_revision`, shows the new revision, refreshes the schema views, and, when the record store has moved on since the plan, shows the conflict and offers a fresh validate. Whether the operator may register is the record store's `schema` grant and the host's `authorize_schema`: the import control is shown only when the host has mounted the schema surface, is disabled with the reason after a refusal, and the console grants nothing (FR-61; ADR-026; CONTRACT-011).

OPR-14. An operator exports a module's registered UMF document as a file named `<module>.umf.json`, and every module they may read as one catalog file (`arras-schema-catalog.json`: the catalog's entries). A module whose document the catalog shows only as a "not shown" note (over its size limits) is not exportable, and the console says so. Export reads what the schema catalog already holds, as the viewer, and adds no operation (FR-52; CONTRACT-009).

#### Sandbox

OPR-15. In the development host only, a developer picks a role (viewer, editor, schema author, auditor, maintainer or none) and gives it any name, and the console runs as that person with the grants the role implies on the sandbox's backends, with no identity provider and no Databricks dependency. The same toolbar breaks and mends the sandbox's backends (an outage with a reason, token expiry, running the replica's feed). A made-up person is an operator (a configured example group `builders`, ADR-025), so the backends' grants for the role, not the host's operator hook, decide what they may do; the sandbox's `carol` and `dave` are not operators and see only the Graph Browser's Explore. The sandbox's administrator (`root`) stays among the fixed people to show that every surface refuses it, and it and the other fixed people cannot be chosen as a custom name. The toolbar is part of the standalone host and is not exported for embedding (FR-62; ADR-021).

#### Entities

OPR-02. An operator opens a type as a paged table, ordered by key, pages of up to the chosen limit (at most 100), Next reading the entities after the page's last key and Previous returning to a page read; filters it on the type's declared columns and relationships, chooses `LATEST` or `BULK` consistency, and sees the page's freshness. A page carries no cursor: the last key is the next page's `afterKey`. They open an entity beside the table, read its properties and attribution, and follow a relationship to the entity at its end; a relationship's targets show their name (the type's `title` template, read in bounded by-key requests of `floor(50 / (1 + placeholders))` targets) with the key beside it, and the key alone where no name is available. The entity panel opens with an action bar at its top: the declared updates of the entity's type as buttons, ranked among updates that qualify with the one that changes a property alone before one that changes it together with others, then the fewest properties, then by name, the other actions that take the entity in an Actions menu, and History and Graph; each action opens its form prefilled with the entity's key. Beside a property that a declared action updates, a Change control opens that action's form with the matching input focused (a pointer to the declared action, never an edit in place). Escape closes the panel and returns the focus to the row that opened it. Every declared filter is reachable: a filter cell under each shown filterable column, and the filters of declared columns that are not shown above the table. A column header sorts the page already read and says so (`aria-sort`, and a note that other pages stay in key order when the page is partial): the list read orders by key only, so the console asks for no other order. The first column stays in view and a shadow shows while columns are clipped. A *Query this type* button opens Query with the type's starter statement (OPR-16a). Below 768px the table and the entity panel take turns: opening an entity replaces the table with the panel under a *Back to list* bar, and Back returns to the list with the row focused; wider, they sit side by side. Every read is a read of CONTRACT-006 or CONTRACT-001; none reads a store directly (FR-49).

OPR-09. An operator sees the graph itself: the module's entities in typed lanes with their relationships as edges, bounded to about 150 nodes with a notice when a type has more. Hovering or selecting an entity lights its edges and opens the entity panel beside the graph; a text filter dims non-matching entities; the same freshness and consistency choices as the table apply (FR-49).

#### Actions

OPR-03. An operator changes data only by invoking an action the module declares. The Actions area lists the module's actions in sections by the type their effects act on (a section for the rest), with a filter on name and description and a count of what matches; opened for an entity, it lists the actions that take that entity first and opens on the action asked for, else the first of those, else the first declared. The console builds a form from the action's typed inputs (`inputSpecs`, CONTRACT-006), checks types in the browser while the operator edits, calls validate when a field loses focus and before confirmation (not on every keystroke), shows every violation and the effects that invoke would apply, requires an explicit confirmation, invokes with an idempotency key it generates, and shows the receipt. A refused invocation shows the refusal and its reason, and nothing changes (FR-50).

OPR-10. When an action validates, the console draws its effects on the affected neighbourhood of the graph before confirmation: created entities and added links, updated entities with the changed properties, deleted entities and removed links. After the invoke the same view stays in an applied state, and the operator can jump to the graph with the changed entities highlighted (FR-50).

OPR-04. An operator applies one action to many items as a batch of up to 100, atomic or independent, and sees each item's receipt or refusal with its index (FR-50).

#### Changes

OPR-05. An operator opens the change history of an entity, and the changes of a module filtered by person, action and time, each naming the person, the time, the action, the entities touched and the group it was applied in. An entity's History is a removable filter over the module's Changes, shown as a chip naming the entity. Each entity in a change links to its Entities view and its History, and each group id to its receipt, so no key or group id is retyped. An operator opens a receipt by its id. An administrator opens the loads that imported records into a module (FR-51). Each read is of one provider's journal: where a module's actions are applied by more than one provider, the Changes view shows a provider selector (default the record store) and reads the chosen provider's journal, the choice travelling in the request body (CONTRACT-009).

OPR-06. An operator sees what was committed: each change made through the console or any other client appears with the person who made it and the action. The audit shows committed changes only. A refused attempt and a validate-only run are not recorded by the provider, so no list shows them; a host that wants them logs them on its own side (FR-51).

#### Query

OPR-16. An operator chooses a module, writes one read-only Weft SQL statement over it (CONTRACT-001), chooses `LATEST` or `BULK` consistency, runs it, and reads the answer as a grid: one column per selected column, a row count, whether the answer was truncated, and the freshness and revision it was computed at. An answer holds at most 100 rows and says when that limit cut it; a next page is the statement's own keyset predicate (`WHERE x.<key> > :last`), which the operator writes, and the grid has no page control. The query runs as the viewer with the viewer's own token, so each backend's grants decide what comes back; a construct the backend does not serve, a refusal, an outage and a statement the backend cannot read are each shown as the library states them, never as an empty grid. The query text travels in a `POST` body only. Arras does not parse the statement; a statement that writes is refused by the backend, and the grid has no editing (FR-63).

OPR-16a. An operator reaches Query from a type. Each type in Model has direct links to its Entities, its Graph, its actions (when an action takes or writes the type) and Query; Query opens with a starter statement for the type in the editor (the key and the first four declared properties, ordered by the key, `LIMIT 50`, every name a Weft quoted identifier), not run. A starter replaces an empty draft; over a draft with text it is offered, never applied silently. In a result whose statement reads exactly one known type of the module, a cell of the type's key column is a link that opens that entity; for any other statement the cells are plain text. Model shows each type's capabilities as one line (the record store, the bulk-read backends, text search, counts) with each backend's detail collapsed.

OPR-17. An operator sees a history of the queries run in this console session, newest first, each with its module, consistency, when it ran, how many rows it returned or why it failed, and chooses one to put back in the editor or runs it again; a history can be cleared. The history, and the editor's draft and consistency, are held in memory only and survive moving between the console's areas and switching between Operate and Explore, because the shell holds them (SD-013 D6): they are gone when the page is reloaded and when another person is chosen, and nothing is written to browser storage, a URL or a log (OPR-07; FR-63).

#### Navigation

OPR-18. An operator's place in the console is its address (CONTRACT-010 D): the module, the area, the type selected in Model or shown in Entities, the entity open in Entities, selected in the graph or whose History Changes shows, the change group whose receipt Changes shows, the action chosen with entity keys prefilled into its ref inputs, and the table's and Changes' own state: the key-column filter, the key a page starts after, the sort column and direction, the action name and the ISO instants that bound Changes, and the view words `umf` (Model's UMF source) and `loads` (Changes' import loads). A refresh or a pasted link restores that place; every navigation (area, module, type, opening an entity) adds a history entry, so Back and Forward move through them; the arrow keys, Home and End move between the area tabs, the Actions mode tabs and the type tabs; `?` (or the header's Keyboard shortcuts button) opens one dialog, headed with the brand, listing every shortcut of both modes, grouped by mode and area, with a Single-key shortcuts switch that turns the plain-key shortcuts (`1`-`6`, `?`, `/`) off for the life of the page (held in memory; the console stores nothing), and those keys never act while the operator types in a field or a dialog is open; an expired sign-in (401) offers Sign in again where the host supplied `onUnauthorized`, and says that what was typed in a form or query is kept; the page title reads `<key, action or type> · <Area label> · <module> · <brand>`, the place first; an address that names nothing the viewer can open (a type or action the module does not declare, an unreadable entity, a group with no changes) shows one not-found page, the same for every cause, linking to the module's Model; and Explore and Operate carry the open entity across (US-072). Only keys, column ids, sort directions, action names, ISO instants, change group ids and the words `umf` and `loads` are in the address: never a person, typed text or a statement. Whenever an entity is in the address the module header names it (type, key and name where known) and links to its Entities, Graph, History and Actions views, marking the current one, with a control back to the area's list. The words are fixed: Actions are what can be invoked, History is one entity's changes, Changes is a module's whole journal. The receipt of an apply links each changed entity to Entities and History and its group to Changes, and offers editing the same inputs to apply again without a new request.

OPR-19. An operator finds an entity, an area, a type or an action from anywhere in the console with a command palette: `/` (when focus is not in a text field) or Ctrl/Cmd+K (anywhere) opens a modal over the module in view, labelled with its scope, and Escape closes it and returns focus to where it was. It is one search field over two groups. *Entities*: the module's `_search` read (CONTRACT-010 C), asked after a 250 ms pause once the text is 2 to 200 characters and at most 6 words, each hit shown as `<Type> · <title> (<key>)` with its excerpt, and an answer to earlier text is never shown as the answer to later text (the previous answer stays, marked busy, while the next loads). *Commands*: the module's types (open the type's Entities list), the areas (Changes only where it is shown) and the declared actions matched by name and description (open the action's form), matched case-insensitively by words, a word prefix ahead of a substring. With no text only the commands are listed (the areas and the first types) and no entity is read. The field is an ARIA combobox over a listbox with group headings: Up and Down move (wrapping), Home and End go to the ends, Enter opens the entity in Entities, Shift+Enter in Graph, Alt+Enter its History. A type that was not searched, a truncated answer and a failed or unsupported search are said in one polite status line, never as an error panel, and the commands keep working; a module with no searchable type shows no entity group and says so. The text is a `POST` body only: it is in no address, history entry, log, error message or storage, and is gone when the palette closes (OPR-07; CONTRACT-010 C).

#### Safety

OPR-07. The console holds no credential. Every call is made as the viewer's principal with the viewer's own token. A module or action the viewer cannot read is absent. Whether the viewer may write is known only from the provider's answer, so a control is disabled after a refusal, with the reason, and a host's `authorize_action` can hide an action for everyone (FR-52).

OPR-08. The console writes data only by invoking a declared action: no cell edit, no SQL that writes, no direct insert or delete. Its one other write is registering a UMF document as the viewer through the schema surface (OPR-13), which a host mounts separately and which carries no data (FR-52, FR-61).

### Non-Functional Requirements

- **Security**: no write without an action; confirmation before every invoke; no secret, token or input value in a URL, a log or browser storage (audit filters travel in a `POST` body); the console's address carries only the module, area, type, keys (an entity key, the key-column filter, a page start and prefilled ref inputs), column ids, sort directions, an action name, ISO instants, change group ids and the words `umf` and `loads`, all in the fragment, and never a person, typed text or a statement; error text from a backend is not shown unscrubbed; the host's content-security policy and origin allowlist apply (CONTRACT-009).
- **Performance** (proposed): a table page and an entity open within 1 second at p95 on the catalog's six types; an action's validate within 500 ms at p95 as the operator pauses typing.
- **Density and clarity**: a table shows at least 30 rows of at least 6 columns on a 1080p screen without scrolling the page; on a phone (below 768px) the header, module choice and area tabs take a few compact rows, the tabs never clip a label (they scroll), keyboard hints are hidden on narrow and touch screens, and the table and the panel never overlap; keyboard operation for navigation, filtering and the action form; WCAG 2.1 AA contrast and focus order.
- **Embeddability**: the same components run inside the embedding host and on a standalone host (ADR-021).
- **Cost**: the console issues only the reads and actions the contracts bound; a table page and the entities it opens never exceed CONTRACT-006's cost limits.

## User Stories

- [US-060: Browse a module's schema](../user-stories/US-060-browse-a-modules-schema.md)
- [US-061: Read a type as a table and follow a relationship](../user-stories/US-061-read-a-type-as-a-table-and-follow-a-relationship.md)
- [US-062: Change data by invoking a declared action](../user-stories/US-062-change-data-by-invoking-a-declared-action.md)
- [US-063: Read who changed an entity](../user-stories/US-063-read-who-changed-an-entity.md)
- [US-064: Keep the operator surface to declared actions as the viewer](../user-stories/US-064-keep-the-operator-surface-to-declared-actions-as-the-viewer.md)
- [US-073: Preview a schema change before applying it](../user-stories/US-073-preview-a-schema-change-before-applying-it.md)
- [US-074: Register a schema as myself](../user-stories/US-074-register-a-schema-as-myself.md)
- [US-075: Export registered UMF documents](../user-stories/US-075-export-registered-umf-documents.md)
- [US-076: Try every role in the development host](../user-stories/US-076-try-every-role-in-the-development-host.md)
- [US-077: Run a read-only query and read it as a grid](../user-stories/US-077-run-a-read-only-query-and-read-it-as-a-grid.md)
- [US-078: Reuse a query from this session's history](../user-stories/US-078-reuse-a-query-from-this-sessions-history.md)

The primary operator workflow (find a type, run a declared correction, read the attributed change) runs through the UI in a whole-stack test, as the `admin-console` concern requires.

## Edge Cases and Error Handling

- A module the viewer cannot read is absent from the list, and a direct link to it shows "not found", the same answer as an unknown module.
- The registry changes while a form is open: the form sends the revision it was built from, an object keyed by backend name, as `expected_revision`; an invoke under another revision for a backend it names is refused with a conflict, a backend it does not name is not checked, and the form rebuilds.
- An action requires a write the viewer lacks: validate returns `Refused`; the form shows the refusal and offers no invoke.
- The same invoke is sent twice (a double click or a retry): the idempotency key makes it one change, and the second answer is marked as a replay.
- A batch partly fails: the result lists each item's receipt or refusal by index, and the console states how many applied.
- The record store is down: reads of a replica still show, marked not current; invoke and validate show `Unavailable` and the backend.
- An entity's history is requested for a module whose provider keeps no journal: the console states that the module has no change history and shows the feed position and lag from `status`.
- A document is imported for a module the viewer cannot read: the plan is still the backend's answer (a new module needs the right to create one); the console never reveals another module's contents.
- Two operators import the same module: the second's register names the revision its plan saw and is refused with a conflict; its plan is recomputed on validate.
- The record store offers no dry run: validate answers `Unsupported` and the console offers no import for that module.
- A very large entity list: the table pages on the key (`afterKey`), a page at most the chosen limit, and never loads more than the contracts bound.

## Success Metrics

- A module builder finds a type, reads its relationships, runs a declared correction on the catalog and finds the resulting change attributed to them, using only the console.
- In tests with two principals, the second sees no module, action or audit row the first's grants alone permit.
- An introspection of CONTRACT-006's schemas still finds no Mutation or Subscription, CONTRACT-009 offers no operation other than validate, invoke, batch and reads, and the only write other than an action is CONTRACT-011's `register`, present only when a host mounts it.
- An operator with the `schema` grant imports a compatible change from a file in the console with a preview; an operator with only `write` is refused by the backend, and the console shows why.

## Constraints and Assumptions

- Writes are UMF actions applied by providers (ADR-015). The console never writes to a backend directly.
- The provider owns the audit trail (its journal, in production Truss's); Arras keeps no audit or data table of its own and no migration history; a replica's feed is reported by `status` position and lag, and a module whose provider keeps no journal has no change history (ADR-013, ADR-021). The two audit reads, `changes` and `loads`, are defined in CONTRACT-001 and CONTRACT-004 and depend on a documented journal read on the provider (on Truss, its audit pages under an audit grant that is separate from reading and writing). Truss, Ashlar and UMF documents never name Arras, and Arras's core names neither.
- The audit trail shows committed changes only. A refused attempt and a validate-only run leave no journal row (FR-42, CONTRACT-003), and Arras records none.
- Who may read whose audit rows is the backend's journal grant. Whether it belongs to module readers, module writers or administrators is open (PRD open questions); until it is decided, slice 2 does not ship.
- The audience begins as administrators and module builders. Widening it to readers is not decided here: a generic write surface for a wider audience is the situation ADR-005's governed-writes risk (P3) names, and the console claims no approval, review or reversal. A `delete` effect cannot be undone from the console. Structure derived from sensitive source records stays gated by ADR-005.
- Standalone means the host that serves `arras-ui` also supplies `principal_for_request`. This repository ships a development host over the sandbox's fakes only (`python -m arras.devhost`), in which a role and a name are chosen from the toolbar; a deployed standalone host with its own sign-in is that host's work, and Arras authenticates nobody (CONTRACT-009).
- Registering a module's types is the person's own act under the record store's `schema` grant (ADR-026), on a separate surface (CONTRACT-011) that a host mounts or not. `attach`, handlers and imports stay the administrative principal's, and install and upgrade the installing connection's, none on an HTTP surface. Placement is the host's: an imported module the host did not place is refused `invalid_placement`.
- A host maps its identity to a principal and proxies the viewer's token (ADR-017); `arras-ui` holds no identity logic.

## Dependencies

- **Other features**: FEAT-001 (reads and the audit reads), FEAT-002 (the registry, `validate` and `register` as the person), FEAT-003 (actions), FEAT-005 (the principal), FEAT-007 (the read surface it reuses).
- **External services**: a provider (a journal read), a replica (an import-load read), the host-provided design-system seam (ADR-029).
- **PRD requirements**: FR-48 to FR-52 (PRD, Operator Console).
- **Contracts and decisions**: ADR-026, CONTRACT-011, CONTRACT-002 (`schema()`), CONTRACT-006 (additions: attribution fields, typed action inputs), CONTRACT-009, CONTRACT-001 (`changes`, `loads`, `Refused.reason`), CONTRACT-003 (`group`, `expected_revision`), CONTRACT-004, ADR-005, ADR-015, ADR-017, ADR-021.
- **Read limits**: tables filter by equality on declared columns and relationships and order by key only (CONTRACT-001, until a backend declares a richer Weft profile); a richer table (ranges, `OR`, ordering, a total count) waits on a Weft profile the backend declares (Weft owns the SQL language). CONTRACT-006 caps a request at 50 field selections, which bounds table width.

## Out of Scope

- Raw row or cell editing, SQL that writes, and any write that is not an action. A read-only query is OPR-16.
- Editing a module's types by form: the console imports and exports UMF documents and builds none.
- Import of records (`import_records`), which stays administrative and off every client surface (CONTRACT-003); not to be confused with schema import (OPR-12).
- End-user screens and structure derived from sensitive source records.
- Arras's own audit table, and any history that the backends do not hold.
