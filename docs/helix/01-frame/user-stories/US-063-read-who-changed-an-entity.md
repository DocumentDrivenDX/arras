---
ddx:
  id: US-063
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-11
  authoring:
    home: repo
  links:
    - id: FEAT-010
      kind: informed_by
    - id: prd
      kind: informed_by
---

# US-063: Read who changed an entity

**Feature**: FEAT-010 — Operator Console
**Feature Requirements**: OPR-05, OPR-06
**PRD Requirements**: FR-51
**Priority**: P1
**Status**: Draft

## Story

**As a** module builder
**I want** to open the change history of an entity and the changes of a module by person, action and time
**So that** I can answer who changed this and when

## Context

History is read from a provider's own journal with the viewer's token (`changes`, CONTRACT-001); Arras keeps no audit table. A module's actions may be applied by several providers, each keeping its own journal: a read names the provider (default, the module's record store), and the console offers a selector when a module has more than one provider that keeps a journal. Journals are not merged into one feed. The audit shows committed changes only and returns no input values. This is slice 2 of FEAT-010.

## Walkthrough

1. The builder opens a corrected Solution and its History.
2. She sees the change with the person, the time and the action.
3. She filters the module's changes by person and time.
4. She opens a receipt by its group id.
5. On a module whose actions are applied by two providers, she chooses the other provider and reads its journal.

## Acceptance Criteria

- [ ] **US-063-AC1** — Given an entity changed by `ana`, when its history is opened, then one change appears with `ana`, the time, the action and the entities touched, and no input values.
- [ ] **US-063-AC2** — Given a module, when its changes are filtered by person and time, then only matching changes appear, newest first, at most 100 per page.
- [ ] **US-063-AC3** — Given a receipt's group id, when it is looked up, then the same change appears.
- [ ] **US-063-AC4** — Given a viewer without the journal grant, when a history is opened, then the console shows the refusal and the reason.
- [ ] **US-063-AC5** — Given a module whose provider keeps no journal, when its history is opened, then the console says it has no change history and shows the feed position and lag.
- [ ] **US-063-AC6** — Given a module whose actions are applied by two providers, when `changes` or `loads` names one of them, then only that provider's journal is read; omitted, the record store's is.
- [ ] **US-063-AC7** — Given a provider that is neither the module's record store nor one of its providers, or a `provider` with no module, when `changes` or `loads` names it, then the read is `Invalid` (`unknown_type`, path `provider`; `scope` without a module) and does not say whether such a backend exists elsewhere; on the operator surface it is 400.
- [ ] **US-063-AC8** — Given a module with more than one journal-bearing provider, when its audit view is opened, then the console shows a provider selector defaulting to the record store, lists the chosen provider's journal, and sends the choice in the request body, never in a URL.

## Edge Cases

- A module with one journal-bearing provider shows no selector.
- A refused or validate-only attempt appears nowhere; the console says the trail shows committed changes only.
- An expired token shows a sign-in prompt, not a refusal.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| its history is opened | US-063-AC1 | an entity changed by `ana` | its history is opened | one change appears with `ana`, the time, the action and the entities touched, an |
| its changes are filtered by person and t | US-063-AC2 | a module | its changes are filtered by person and t | only matching changes appear, newest first, at most 100 per page |
| it is looked up | US-063-AC3 | a receipt's group id | it is looked up | the same change appears |
| a history is opened | US-063-AC4 | a viewer without the journal grant | a history is opened | the console shows the refusal and the reason |
| its history is opened | US-063-AC5 | a module whose provider keeps no journal | its history is opened | the console says it has no change history and shows the feed position and lag |
| a provider is named | US-063-AC6 | a module with two providers, each with changes | `changes` and `loads` with `provider`, and without | only the named provider's journal; the record store's by default |
| a provider outside the placement is named | US-063-AC7 | a backend that is not in the module's placement; no module | `changes` and `loads` with `provider` | `Invalid` (400 on the surface), nothing revealed about the backend |
| the audit view of a two-provider module is opened | US-063-AC8 | a module with two journal-bearing providers | choose the second provider | the selector shows both, the request body carries `provider`, the second journal is listed |

## Dependencies

- **Stories**: US-061
- **Feature Spec**: FEAT-010
- **Feature Requirements**: OPR-05, OPR-06
- **PRD Requirements**: FR-51
