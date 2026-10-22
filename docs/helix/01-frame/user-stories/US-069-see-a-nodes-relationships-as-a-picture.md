---
ddx:
  id: US-069
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: US-068
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
---

# US-069: See a node's relationships as a picture

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-12, BRW-13, BRW-14 (slice 1b)
**PRD Requirements**: FR-57
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader
**I want** a picture of an entity and its neighbours that I can click through
**So that** I can see how it fits in the graph at a glance and move along it

## Context

The picture is a neighbourhood (also called an ego graph): the entity in the centre and the entities it is related to in groups, one hop (two hops are a later addition). It is not a map of the module (the Operator Console's graph does that). It is bounded at 40 nodes, so a hub entity does not produce a hairball, and it is a convenience over the relationship list, which stays complete and is the accessible equivalent.

## Walkthrough

1. The reader opens a `Solution`; beside its links she sees the picture with the `Solution` in the middle and its neighbours around it, each with its type's icon and tone.
2. Edges carry the relationship's label.
3. She hovers a `Product` node; a card shows its label, type and the relationship that joins it.
4. She selects the `Product`; its page opens and the picture re-centres on it.

## Acceptance Criteria

- [ ] **US-069-AC1** — Given an entity with neighbours, when its page renders, then the picture shows the entity in the centre and each related entity as a node styled with its own type's icon and tone, joined by edges labelled with the relationship
- [ ] **US-069-AC2** — Given an entity whose neighbours fit, when the picture renders, then every neighbour is drawn once, in groups ordered by the declared order and then the label, and members in each group ordered by title and then key
- [ ] **US-069-AC3** — Given more neighbours than the bound, when the picture renders, then it says how many are left out and from which relationships, and the relationship list still lists every one
- [ ] **US-069-AC4** — Given a node in the picture, when the reader selects it by pointer or by keyboard, then its node page opens and the picture re-centres on it
- [ ] **US-069-AC5** — Given a node, when the reader hovers or focuses it, then its label, type and joining relationship are shown, and the same information is available without hover
- [ ] **US-069-AC6** — Given the picture, when it is read by a screen reader or without colour, then the relationship list conveys all that the picture does, the picture is one Tab stop with the arrow keys moving between its nodes group by group, the container is a labelled group (not an image), and no meaning relies on colour alone
- [ ] **US-069-AC7** — Given a user with `prefers-reduced-motion`, when the picture re-centres, then no animation plays and the new picture appears at once

## Edge Cases

- **An entity with no relationships**: the picture shows the entity alone with "No relationships" and takes no space beyond a compact card.
- **A hidden or absent neighbour**: not drawn, counted in "left out" only as an unnamed number, never identified.
- **A self-link**: drawn once as a loop on the node.
- **Two entities with the same label**: drawn with the type beside the label.
- **A narrow window**: the picture scales to the available width; below 420 px it becomes the relationship list only, with a control to show the picture.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| One hop | US-069-AC1 | `Solution` with 4 use cases and a product | open | Centre plus 5 nodes, edges labelled |
| Order | US-069-AC2 | an entity with three groups | open | Groups and members in the stated order; coordinates equal the golden vectors |
| Hub | US-069-AC3 | an entity with 120 neighbours | open | 40 nodes; "80 left out"; list complete |
| Select | US-069-AC4 | the product node | click, then Enter on another node | Page opens; picture re-centres |
| Detail | US-069-AC5 | a node | hover; focus | Card shows label, type, relationship |
| Accessibility | US-069-AC6 | axe run on the page | run | No violation; list conveys the relationships |
| Reduced motion | US-069-AC7 | `prefers-reduced-motion` | re-centre | No transition |

## Dependencies

- **Stories**: US-067, US-068.
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-12 to BRW-14
- **PRD Requirements**: FR-57
- **External**: CONTRACT-006 (`Ref.target`, depth and cost limits), the module's declared styling (US-070) where present.

## Out of Scope

- Dragging, pinning or hand-arranging nodes, and saving a layout.
- Search inside the picture, and paths between two entities.
- A picture of the whole module.
