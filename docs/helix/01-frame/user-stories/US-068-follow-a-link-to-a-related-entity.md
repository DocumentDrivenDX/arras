---
ddx:
  id: US-068
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
    - id: US-067
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: CONTRACT-006
      kind: informed_by
---

# US-068: Follow a link to a related entity

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-09, BRW-10, BRW-11 (slice 1b)
**PRD Requirements**: FR-56
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader
**I want** every relationship of an entity listed by name with a link to each related entity
**So that** I can walk the graph by clicking, knowing what each link means

## Context

CONTRACT-006 returns, for each relationship field, at most 100 `Ref`s with the module, type and key of the entity at the other end, and a `target` that opens it as the viewer. The browser groups the refs by relationship, labels each group, and shows each related entity with its own label and type styling. A related entity the viewer may not read, or that is absent, comes back as a null `target`, and the interface does not say which.

## Walkthrough

1. The reader is on a `Solution` page and sees groups "Addresses use cases (4)" and "Provided by (1)".
2. Each group lists its related entities with icon, label and type.
3. She activates "Product: Lumen Search" under "Provided by"; the `Product` page opens.
4. On that page, the "Provides" group lists `Solution`s through the relationship's inverse, so she can go back by link.
5. A related `UseCase` that she may not read shows as "Not available".

## Acceptance Criteria

- [ ] **US-068-AC1** — Given an entity with relationships, when its page renders, then every relationship the entity takes part in is listed as a group titled by its declared label (or, with none, its name), with the count of related entities and the direction readable in words
- [ ] **US-068-AC2** — Given a group, when it is shown, then each related entity is a link with its own label, type and type styling, and activating it opens that entity's node page
- [ ] **US-068-AC3** — Given a relationship for which the interface returned its limit of 100 keys, when the group is shown, then the count states "100 or more", the first 20 are labelled, a "show more" control labels the next 20 of the keys read, and beyond the 100 a further control reads more through the other type's list read, filtered by the inverse relationship, a page at a time after the last key read (`afterKey`), when the relationship has an inverse; otherwise the group says it shows the first 100
- [ ] **US-068-AC4** — Given a related entity of another module that the viewer may read, when its link is activated, then it opens in that module's page
- [ ] **US-068-AC5** — Given a related entity the viewer may not read or that is absent, when the group is shown, then it appears as "Not available", is not a link and carries no key, type or reason
- [ ] **US-068-AC6** — Given a relationship that has an inverse, when the target's page opens, then the inverse relationship is listed there and links back
- [ ] **US-068-AC7** — Given a neighbour whose label read is refused for cost or fails, when the group is shown, then that neighbour shows its key and a retry control and is never shown as "Not available"

## Edge Cases

- **A relationship with no related entities**: the group is shown with a zero count and "none" (it is not hidden, because the absence is information), unless the declared view hides empty relationships.
- **A relationship to a type of another module whose endpoint the viewer cannot reach**: shown as "Not available".
- **An entity related to itself**: listed once with a "this entity" marker.
- **The same entity related by two relationships**: shown in each group.
- **Many relationships**: groups are ordered by the declared order, then by name; all remain reachable by keyboard.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Groups | US-068-AC1 | `Solution` with 4 use cases, 1 product | open | Two groups with counts 4 and 1 and readable direction |
| Follow | US-068-AC2 | the product link | activate | The `Product` page opens |
| Over a page | US-068-AC3 | 130 related, an inverse | open; show more until 100 are labelled; show more again | 20, then 40 labelled; "100 or more"; the next control reads the rest through the inverse's list read, after the last key |
| No inverse | US-068-AC3 | 130 related, no inverse | open; show more until 100 are labelled | "Showing the first 100", with no further control |
| Cost refusal | US-068-AC7 | a label read answered `COST_EXCEEDED` | open | Key and retry for that neighbour; others labelled |
| Cross module | US-068-AC4 | a ref to module `inventory` | activate | Opens in `inventory` if readable |
| Hidden entity | US-068-AC5 | carol has no grant on a related type | open | "Not available", not a link, identical to an absent key |
| Inverse | US-068-AC6 | `Product` page | open | "Provides" group lists the `Solution` and links back |
| Empty | US-068-AC1 | `Solution` with no findings | open | Group "Findings (0)" with "none" |

## Dependencies

- **Stories**: US-067 (the page).
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-09 to BRW-11
- **PRD Requirements**: FR-56
- **External**: CONTRACT-006 (`Ref`, `Ref.target`, cost limits).

## Out of Scope

- Filtering or sorting the related entities of a relationship.
- Creating, removing or changing a relationship (an action, in the Operator Console).
- Telling the viewer why an entity is unavailable.
