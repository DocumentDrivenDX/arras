---
ddx:
  id: US-066
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
    - id: US-065
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-066: Narrow a search by entity type

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-03, BRW-04, BRW-20 (AC1, AC2: slice 1b; AC3 to AC6: slice 3)
**PRD Requirements**: FR-54, FR-53
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader
**I want** a single choice of "All" or one entity type, with counts, and a list of each type
**So that** I can keep to one kind of thing and browse a type when I have no words to search

## Context

The chips are one single choice: "All" first and selected, then one chip per type, exactly one selected at a time. They show how many hits each type has for the current text (and "All" the total), so the reader learns the shape of the answer before choosing. With no text the browser opens on the module's types, without counts (the console's reads have no count), and a type opens as a paged list in key order (the same read as the operator console's table, presented as hits), each page after the last key of the one before.

## Walkthrough

1. The reader opens `catalog` and sees `All`, selected, and a chip for each of its six types.
2. She opens `Solution` and sees its entities in key order, 50 to a page, as hit rows, and reads the next page.
3. She types `lumen`; the chips change to the hit count of each type for that text.
4. She selects the `Solution` chip; `All` is deselected, the list keeps only `Solution` hits and the other chips stay visible with their counts.
5. She selects `All`; all hits return.

## Acceptance Criteria

- [ ] **US-066-AC1** — Given a module opened with no text, when the page loads, then an `All` chip, selected, and a chip for every entity type the viewer may read are shown, without a count until a search has been made, and exactly one chip is selected
- [ ] **US-066-AC2** — Given a type chip selected with no text, when the page updates, then the type's entities are listed in key order in pages of at most 50, with a control that reads the next page, the entities after the last key shown
- [ ] **US-066-AC3** — Given text entered, when the answer arrives, then each chip shows the number of hits of its type for that text, and a type with none shows zero
- [ ] **US-066-AC4** — Given a type chip selected, when the search runs, then only hits of that type are shown, the other chips remain visible with their counts, and selecting the selected chip changes nothing
- [ ] **US-066-AC5** — Given a type chip selected, when the reader selects `All`, then all hits return and the text is unchanged; with no text `All` shows one card per type
- [ ] **US-066-AC6** — Given a chip's state, when the page is read without colour, then the chips are one radio group (`role="radiogroup"`, each `role="radio"`) whose selection is conveyed by `aria-checked` and a visible check mark, not colour alone, only the selected chip is in the Tab order and the arrow keys move the selection

## Edge Cases

- **A type the viewer cannot read**: no chip is shown for it, with no hint it exists.
- **A type with no searchable property**: its chip is shown, marked "not searched", and counts are omitted for text searches; it can still be listed.
- **A type with no hits in a search**: its chip shows zero; before a search no chip shows a number, so zero is never shown for an unknown count.
- **The module has more types than fit a row**: the chips wrap; none is hidden behind a control that has no label.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Module entry | US-066-AC1 | catalog | open the module | `All` selected and six chips, no counts |
| List a type | US-066-AC2 | 51 `Solution`s | select `Solution`; show the next | 50 rows in key order; the next control reads the 51st |
| Counts per text | US-066-AC3 | text `lumen` | search | Chip counts equal hits by type, `All` their total; types with none show 0 |
| Choose one | US-066-AC4 | `Solution` selected | search | Only `Solution` hits; `All` deselected; others' chips still visible |
| Back to All | US-066-AC5 | `Solution` selected | select `All` | All hits return; text kept |
| Non-colour state | US-066-AC6 | a chip selected | read the accessibility tree | `aria-checked="true"` on one radio and a visible check |

## Dependencies

- **Stories**: US-065 (search) for text narrowing; the type list works without it.
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-03, BRW-04, BRW-20
- **PRD Requirements**: FR-53, FR-54
- **External**: CONTRACT-006 (list reads, counts where served), CONTRACT-010 (per-type hit counts).

## Out of Scope

- Filtering by property values or relationships in the browser (the Operator Console's table does that).
- Sorting by anything but key (hits by rank).
