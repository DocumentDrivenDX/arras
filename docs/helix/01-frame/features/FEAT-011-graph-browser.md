---
ddx:
  id: FEAT-011
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
    - id: FEAT-002
      kind: informed_by
    - id: FEAT-005
      kind: informed_by
    - id: FEAT-010
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: ADR-023
      kind: informed_by
    - id: ADR-024
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
---

# Feature Specification: FEAT-011 — Graph Browser

**Feature ID**: FEAT-011
**Status**: Draft
**Priority**: P1
**Owner**: Erik LaBianca
**Covered PRD Subsystem(s)**: Graph Browser
**Covered PRD Requirements**: FR-53 to FR-60, FR-64 to FR-71
**Cross-Subsystem Rationale**: None; single subsystem. It reads through CONTRACT-006 and the search read of CONTRACT-010 and writes only by validating and invoking a declared action as the viewer (CONTRACT-010 F, SD-013); it shares the `arras-ui` package and host with the Operator Console (FEAT-010) but not its areas.

## Overview

The Graph Browser (**Explore**, the instance tool) is the interface for people who use the ontology rather than build it. A viewer searches by text, narrows by entity type, opens an entity as a readable page, follows its links to related entities and sees the entity's neighbourhood as a picture. How a type's page looks is declared by its module in the module's UMF document, so a Solution reads differently from a Finding without any code in Arras or the host. It lives in the `arras-ui` package beside the Operator Console (ADR-021), reads through the console's read surface (CONTRACT-006) and the search read (CONTRACT-010), writes only by validating and invoking declared actions as the viewer, and holds no state of its own. One shell offers it as **Explore** (Explore) and the Operator Console as **Operate** (Operate), with a switch that only module builders and administrators see (ADR-025). Explore works on instances: find, read, change, create, retire and see what happened; Operate works on the model and the platform (SD-013).

## Delivery Slices

| Slice | Content | Depends on |
|-------|---------|------------|
| 1a | Server, small: the resolved view with defaults only (`Module.view`, `EntityTypeInfo.view`); the viewer's modes (`GET /viewer`, `authorize_operator`, the `not_operator` refusal) (BRW-18, BRW-24 to BRW-26) | CONTRACT-010 sections B (defaults), E; CONTRACT-009 |
| 1b | UI: the shell and mode switch, the module entry with the type list (no counts), the node page, the relationship groups with links, a one-hop picture, locations (BRW-04 to BRW-14, BRW-20 to BRW-23, BRW-24 to BRW-26) | Slice 1a; the existing console reads (CONTRACT-006); ADR-024, ADR-025 |
| 2 | Declared view: a module styles its node pages in UMF, checked at registration (BRW-15 to BRW-17, BRW-19) | ADR-022; CONTRACT-010 section A; UMF's acceptance of the vocabulary |
| 3 | Search: text search, a single choice of type (All or one) with counts, the search box (BRW-01 to BRW-03) | ADR-023; CONTRACT-010 section C; the backend `search` capability (CONTRACT-004) |

Slice 1 ships without slices 2 and 3: with no search the entry point is the type list, and with no declared view every page uses the defaults the server resolves. Slices 2 and 3 are independent of each other. A two-hop picture, paging of a multi-type search, per-row badges, a numeric search weight and a consistency choice in the browser are later additions, not part of these slices.

## Ideal Future State

A product-team member opens the browser in praxis and sees the modules her principal may read, each with the types that have something to look at. She types "lumen" and, before she has finished, sees ranked hits across Solutions, Products and Findings, each with the words that matched; a row of type chips tells her how many of each there are and lets her keep only Solutions. She opens one. The page opens as a Solution should look, because the catalog module said so: a title, a one-line summary, a status badge in the module's own tone, the properties grouped into the sections the catalog chose, long text set as prose and a launch URL as a link. Beside the page she sees what the Solution is connected to: the use cases it addresses and the Product that provides it, each grouped by the relationship, each a link. Beneath them a small picture draws the Solution with those neighbours, coloured and iconed as their own pages are. She clicks the Product in the picture and its page opens with the picture re-centred. She copies the address and sends it to a colleague, who sees the same page if her own principal may read it, and a plain "not available" if not. She is an operator too, so she turns on edit mode, corrects the Solution's status, retires a duplicate Finding after reading which links go with it, creates a new Solution from the type's list and opens its History to see who changed what and when, each by a declared action as herself and never by any route of its own. A colleague who is not an operator sees the same pages with no control that changes anything. Every page says how current it is.

## Problem Statement

- **Current situation**: The operator console shows every type as a generic property table and a whole-module graph meant for checking the schema. GraphiQL needs a query. The graph in the console is cut at 150 nodes of the first 100 entities per type, so a search box there finds only what happens to be loaded.
- **Pain points**: A reader who does not know the schema has no way in: no search, no type-aware page, and relationships are read from keys rather than followed. Modules cannot say how their own entities should be shown, so any good presentation would have to be hard-coded per module in a client.
- **Desired outcome**: A reader goes from a few words to a styled page and along its links to the rest of the graph in a few clicks, with the page's look declared by the module that owns the type, scoped by the viewer's own token, and without any new write path or state.

## Functional Areas

| Area | User question or job | Feature responsibility |
|------|----------------------|------------------------|
| Find | Where is the thing I am thinking of? | A search box, ranked hits across types, matched text, a single choice of type (All or one) with counts, a type list without a search |
| Node page | What is this, in the module's own terms? | Title, summary, grouped and formatted properties, icon and tone, attribution and freshness, derived default |
| Follow | What is it connected to, and how do I get there? | Relationships grouped by name with a link to each related entity, across modules where readable, an honest "unavailable" |
| Picture | How does it sit among its neighbours? | A bounded neighbourhood drawing with the declared styling, selection to navigate, a text equivalent |
| Declared view | How does my module's type present itself? | A UMF extension, checked at registration, with a closed vocabulary and a derived default |
| Instance work | Can I change, create or retire this, and see what happened? | For operators: New, Retire, an Actions menu and History, each a declared action validated and invoked as the viewer (US-079 to US-083) |
| Shell and safety | Can I share this, and is it safe? | Locations for pages, history and back, principal-scoped reads, writes only by declared action, no credential |
| Modes | Can I also run the operator tools, and only if I am meant to? | One shell with Explore and Operate, a switch for operators only, absent for others, refused on the server |

## Requirements

### Functional Requirements by Area

#### Find

BRW-01. A viewer types text into a search box and receives hits across the entity types of the open module that declare at least one searchable property, ranked, within a bounded page (FR-53).

BRW-02. Each hit shows its type, its label, a one-line excerpt with the matched text marked, and the page of results states the freshness of the answer (FR-53).

BRW-03. A viewer narrows search to one type, or keeps all, with type chips that are a single choice: `All` first and selected by default, then one chip per readable type, exactly one selected. Each type chip shows the number of hits of that type for the current text (`All` the total), and selecting `All` brings every type back. Before any text, the chips are `All` and the module's readable types without counts (FR-54).

BRW-04. With no text, the viewer can open a type and list its entities, paged in key order through the type's list read (each page after the last key shown), with the same hit presentation (FR-54).

#### Node page

BRW-05. Opening an entity shows a node page: a title, a summary line, the type's icon and tone, the properties grouped into sections, and the entity's attribution (created by and when, last changed by and when) where the backend supplies it (FR-55).

BRW-06. Each property value is formatted by its declared format or, where none is declared, by its type: text, long text as prose, a timestamp as a date and time with the exact value on demand, a decimal or integer with grouping, a boolean as yes or no, a structured value as collapsible formatted data; the format is the declared one, else the default of CONTRACT-010 for the property's name and type (FR-55).

BRW-07. The page states the freshness of what it shows (the backend and how current); an answer older than the backend's current position is marked as such. The browser reads at `LATEST`; a choice of consistency in the browser is later (FR-55, FR-59).

BRW-08. A property that is absent is shown as absent in a consistent way, not hidden, unless the declared view hides it when empty (FR-55).

#### Follow

BRW-09. The page lists every relationship of the entity, grouped by the relationship's declared label, each with its direction and the number of entities at the other end, or "100 or more" when the interface returned its limit of keys (FR-56).

BRW-10. Each related entity is a link showing that entity's own label and type styling; activating it opens its node page. A group lists the first 20 related entities with their labels and a "show more" control that labels the next 20 of the keys already read; beyond the 100 keys a read returns, "show more" reads the further entities through the other type's list read when the relationship has an inverse, and otherwise the group says it shows the first 100 (FR-56).

BRW-11. A related entity of another module opens in that module's page when the viewer may read it. One the viewer may not read, or that is absent, shows as "not available" with no reason, because the interface does not say which (FR-56; CONTRACT-006 `Ref.target`).

#### Picture

BRW-12. The page shows a picture of the entity and its neighbours: the entity in the centre and its related entities in groups by relationship, one hop (FR-57).

BRW-13. The picture is bounded at 40 nodes in all; when neighbours are left out the picture says how many and from which relationships, and the page's relationship list remains complete (FR-57).

BRW-14. Selecting a node in the picture opens its node page and re-centres the picture; hovering or focusing a node shows its label, type and the relationship that joins it; the picture is one keyboard stop with arrow keys moving between its nodes, and its text equivalent is the relationship list (FR-57).

#### Declared view

BRW-15. A module declares, for any entity type, in a UMF extension, the title, the summary, the icon, the tone, the sections of properties with an optional format for each, the properties to search and how heavily, the properties to show in a hit, and a label for each relationship (FR-58).

BRW-16. The declaration must be data from a closed vocabulary (CONTRACT-010): a label is a template of property names and literal text, an icon is a name from a fixed set, a tone is one of a fixed set of palette slots, a format is one of a fixed set. It contains no script, no markup, no URL to load and no colour value, so a declaration cannot run code, restyle the host or break the contrast of a page (FR-58).

BRW-17. Arras checks the declaration when the module is registered: an unknown vocabulary term, a reference to a property or relationship the type does not have, a format that does not suit the property's type, and a template with an unclosed placeholder are each refused with the path of the fault, and the stored registry is unchanged (FR-58).

BRW-18. A module that declares nothing for a type gets the defaults of CONTRACT-010, resolved by the server: the first conventional name property or the first string property as title, the first of `summary`, `description`, `statement`, `problem` or `notes` the type has (and the title does not use) as summary, one section of the other properties in declared order, the type's palette slot by its position in the module, a generic icon, and a default format by property name and type (FR-55, FR-58).

BRW-19. The declaration travels with the registry revision, so a page and the revision it was read under always agree; a registration that changes a view takes effect on the next request, and a page open under the old revision refreshes without losing its place (FR-58; CONTRACT-006 Snapshot).

#### Shell and safety

BRW-20. The browser opens on a module chosen from those the viewer may read; with one readable module it opens on that one. Its entry shows the module's title and description and its readable types as chips and cards (with search, from slice 3, the search box and counts) (FR-54).

BRW-21. Each node page has a location the viewer can copy and open later or send to a colleague. The location carries the module, the type and the key in the URL fragment only, never in the path or the query string; search text is not placed in any part of the URL. A host that embeds the browser receives the location as data and chooses how to store it (FR-59; ADR-024).

BRW-22. Browser history works: back returns to the previous page or the previous search with its text, type chips and scroll position; a location that no longer resolves shows "not available", the same answer as an entity the viewer cannot read (FR-59).

BRW-23. Every call is made as the viewer's principal with the viewer's own token; the browser writes only by validating and invoking a declared action, and holds no credential. Links into Operate are offered to operators only. An embedding host may add a link from a node page to its own place, supplied by the host (FR-59, FR-71; FR-52 by the same boundary).

#### Modes

BRW-24. The shell offers Explore (the Graph Browser) and Operate (the Operator Console) and opens in Explore; an operator sees a two-option switch in the top bar, `Explore` and `Operate`, and a node's module and type carry over when the operator switches (FR-60).

BRW-25. A viewer who is not an operator sees no switch, link or text that refers to Operate, and an Operate address opened by such a viewer shows Explore's entry; the shell learns the viewer's modes from one read of the operate surface and treats a failed read as Explore only (FR-60).

BRW-26. The operate surface refuses every non-operator, on the server, with a refusal that names `not_operator`; which principals are operators is the host's decision, and Arras infers it from no group or flag (FR-60; ADR-025).

#### Instance work

These apply where the host offers the viewer Operate; a non-operator is refused `not_operator` whatever the interface shows (ADR-025). Each is a declared action, validated and then invoked as the viewer (ADR-015; SD-013).

BRW-27. A type's list offers **New <type>** in edit mode where a declared action creates that type; the form asks for the action's inputs, a reference through the picker, is validated and then applied, and on success the created entity's page opens from the validated create key (FR-67).

BRW-28. A node page in edit mode offers **Retire** where a declared action deletes that type; the confirmation names the entity's links from the page's own read, says that the key cannot be used again and that there is no undo, and on success the type's list opens (FR-68).

BRW-29. A node page in edit mode offers an **Actions** menu of the other declared actions that take the entity; one opens a form with the entity prefilled, a text summary of the effects, and a receipt that links the entities it touched (FR-70).

BRW-30. An operator opens an entity's **History**: the changes that touched it, newest first, 20 a page, each naming who, when, the action and what it touched; an entity the viewer cannot read shows as "not available" (FR-69).

BRW-31. An operator moves between the modes at the entity, the type and the module: **Open in Operate** from Explore and **View in Explore** from Operate, with area-specific targets (History, Actions, a change group) (FR-71).

### Non-Functional Requirements

- **Performance** (proposed): a search answer and a node page within 1 second at p95 on the catalog's six types; typing is debounced so one search is issued per pause of 250 ms, and an answer to a text that has since changed is discarded, never shown.
- **Cost**: a node page is planned inside CONTRACT-006's limits (50 field selections, depth 6, 1,000 entities, 100 targets): one request reads the entity's properties, attribution, freshness and the relationship keys; the labels of the 20 first neighbours per group and of the 40 picture nodes come in further requests of at most 20 targets and 50 selections each; a cost refusal of a target is shown as a retry, never as "Not available"; a search is bounded by CONTRACT-010.
- **Security**: no key or search text in a path or query string, in a log line, or in storage that Arras writes (cookies, `localStorage`, `sessionStorage`, IndexedDB); the history entry's own state holds view state for Back and nothing else; view declarations are data and are never interpreted as markup; unreadable and absent entities are indistinguishable; Operate is absent for non-operators and refused for them on the server.
- **Accessibility**: WCAG 2.1 AA; every interaction reachable by keyboard; the picture is never the only way to learn a relationship; no meaning by colour alone (a tone always accompanies an icon or a label); respects `prefers-reduced-motion` and `prefers-color-scheme`.
- **Embeddability**: the same components run inside praxis and on a standalone host, and take their theme from the host's tokens (ADR-021).
- **Bundle**: the browser is a separately importable entry of `arras-ui` (`arras-ui/browser`); a host that mounts only the Operator Console does not load it, and the reverse; the shell (`ArrasApp`) is the entry that loads both.

## User Stories

- [US-065: Search for an entity by text](../user-stories/US-065-search-for-an-entity-by-text.md)
- [US-066: Narrow a search by entity type](../user-stories/US-066-narrow-a-search-by-entity-type.md)
- [US-067: Open an entity as a node page](../user-stories/US-067-open-an-entity-as-a-node-page.md)
- [US-068: Follow a link to a related entity](../user-stories/US-068-follow-a-link-to-a-related-entity.md)
- [US-069: See a node's relationships as a picture](../user-stories/US-069-see-a-nodes-relationships-as-a-picture.md)
- [US-070: Declare how a type's pages look in UMF](../user-stories/US-070-declare-how-a-types-pages-look-in-umf.md)
- [US-071: Share a node's location; the browser acts as the viewer with the viewer's own access](../user-stories/US-071-share-a-nodes-location-the-browser-acts-as-the-viewer.md)
- [US-072: Switch between Explore and Operate](../user-stories/US-072-switch-between-explore-and-operate.md)
- [US-079: Create an entity from a type's list](../user-stories/US-079-create-an-entity-from-a-types-list.md)
- [US-080: Retire an entity from its page](../user-stories/US-080-retire-an-entity-from-its-page.md)
- [US-081: Run a declared action on an entity](../user-stories/US-081-run-a-declared-action-on-an-entity.md)
- [US-082: See an entity's history](../user-stories/US-082-see-an-entitys-history.md)
- [US-083: Move between Explore and Operate at an entity](../user-stories/US-083-move-between-explore-and-operate-at-an-entity.md)

The primary reader workflow (type a few words, open a hit, follow a link, read the picture) runs through the UI in a whole-stack test, the same practice FEAT-010 applies to its primary workflow.

## Edge Cases and Error Handling

- A search with no hits shows what was searched, the types that were searched and which declare no searchable property, and, when a type is selected, says that `All` searches every type; it never shows an empty page without a reason.
- A search text shorter than two characters is not sent; the browser says so.
- A backend that does not serve text search for a type (CONTRACT-004 capability) is named in the page as not searched, and the hits of the other types still show; the search never silently omits a type.
- A backend is unavailable or behind: the page shows what came from the reachable backends marked with each answer's freshness, and names the one that is not; the page does not claim an empty result.
- An entity references an entity the viewer cannot read, or one that no longer exists: it shows as "not available", with no key, no type and no reason (BRW-11).
- A cycle or a hub: an entity related to itself, or related to hundreds of others. The picture draws a self-link once, caps at 40 nodes with a count, and the list pages at 100, reading beyond the 100 keys through the inverse relationship's list read when there is one.
- A declared view names a property that a later revision removes: the new registration is refused if it breaks the declaration; the view and the types are always registered together.
- A very long title, an unbroken string or a long text value wraps or truncates inside its container with the full value reachable; no value can widen the page.
- The viewer's token expires: the browser shows the session-expired state the host supplies (as the Operator Console does) and keeps its place.
- Two types share a label: hits and links always show the type beside the label.
- A neighbour's label read is refused for cost: the page shows the key and a retry for that neighbour, never "Not available", which is reserved for an entity the interface answered as absent or unreadable.
- The operator read fails or is slow: the shell shows Explore and no switch until it answers.

## Success Metrics

- A graph reader finds a Solution by two words and reaches the Product that provides it in no more than three actions (type, open, follow), using only the browser.
- In a test with two principals, the second sees no entity, hit, count, link or picture node the first's grants alone permit, and cannot tell a hidden entity from an absent one.
- A module that declares a view for each of the catalog's six types presents each page differently from the derived default without any change to the browser's code.
- An introspection of the request log finds no key or search text in a path or query string, and no request that writes other than the validate and invoke of a declared action the viewer asked for.

## Constraints and Assumptions

- Reads, and the writes of SD-013. The browser performs the reads of CONTRACT-006 and CONTRACT-010. Its writes are an in-place edit, a link, a new entity, a retirement and an entity action, each offered only where the host offers the viewer Operate and the module declares the action, and each made by validating and invoking that action as the viewer (ADR-015, CONTRACT-010 F). It has no write of its own.
- The browser keeps no state of its own and nothing in browser storage but the viewer's own convenience choices (theme override, last module); entities, hits and views are never stored there (ADR-021).
- Structure derived from sensitive source records stays gated by ADR-005; the browser is generic over modules and adds no access rule. What the viewer sees is what the backends' own grants allow.
- Search strength is a backend capability, not a promise of the interface (ADR-023). Until a backend serves it, a module's search is limited to the types whose backend does.
- A view declaration is presentation only. It does not change what is read, what is permitted or what an action does, and the registry's types and relationships are identical with or without it (ADR-022).
- The picture is a convenience over the relationship list, not a graph database client: it is not a layout of the whole module, and the module-wide graph stays in the Operator Console (FEAT-010, OPR-09).
- UMF's validator is assumed to accept an additional vocabulary in `vocabularies` and `extensions`; this is unconfirmed (PRD open questions) and Slice 2 does not ship until it is.

## Dependencies

- **Other features**: FEAT-001 (reads), FEAT-002 (the registry that holds the declared view), FEAT-005 (the principal), FEAT-010 (the package, host, shell tokens and the reads it already uses; its whole-module graph stays there).
- **External services**: the backends' text search (CONTRACT-004, a new capability); UMF's acceptance of an additional vocabulary; `@databricks/appkit-ui` and the praxis frontend stack (ADR-021).
- **PRD requirements**: FR-53 to FR-60 and FR-64 to FR-71 (PRD, Graph Browser).
- **Contracts and decisions**: CONTRACT-010 (new), CONTRACT-006 (extended additively by CONTRACT-010), CONTRACT-002 (the registry holds the view), CONTRACT-004 (the `search` capability), ADR-005, ADR-021, ADR-022, ADR-023, ADR-024.
- **Visual and technical design**: SD-011 (technical approach), SD-012 (editing relationships and exporting the graph), SD-013 (instance work and the shared action kit), DESIGN-GB (visual design, `graph-browser-visual-design.md`).

## Out of Scope

- A write that is not a declared action invoked as the viewer: annotation, bookmarks or comments stored by Arras, batch invoke, schema registration and import (these stay Operate).
- A module-wide graph canvas, free-form graph queries, path finding between two entities and any graph analytics; the whole-module graph remains in the Operator Console.
- A two-hop picture, paging a multi-type search, a numeric search weight, per-row badges and a consistency choice in the browser (later, additive).
- Deciding who is an operator: the host's hook and directory do (ADR-025).
- Saved searches, search history stored by Arras, ranking tuned per viewer and any recommendation.
- Full-text search over documents and the corpus (retrieval over the corpus stays where it is); search here is over entity properties.
- Custom components, scripts, markup or stylesheets in a view declaration; a module that needs more builds its own screen (PRD non-goals).
- A multi-module federated search in one request; the viewer searches one module at a time, and follows links across modules.
- Print and export of pages.
