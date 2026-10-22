---
ddx:
  id: US-070
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
    - id: prd
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: CONTRACT-002
      kind: informed_by
---

# US-070: Declare how a type's pages look in UMF

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-15, BRW-16, BRW-17, BRW-19
**PRD Requirements**: FR-58
**Priority**: P1
**Status**: Draft

## Story

**As a** client developer (the person who builds a module)
**I want** to declare in my module's UMF document how each type's node page, hit and links should look
**So that** the browser presents my types well without any code from me or any change to Arras

## Context

A UMF document may carry extensions on a record, a field and a relationship. ADR-022 defines one more vocabulary, `arras.view`, whose terms are listed in CONTRACT-010. The vocabulary is data from closed sets, so it cannot run code or break the host's theme or contrast. Arras checks it when the module is registered, carries it in the registry revision, and serves it on the type's description so the browser reads it with the types.

## Walkthrough

1. The developer adds `arras.view` to the `vocabularies` of the catalog document and to `Solution`'s `extensions`: a title template, a summary property, an icon, a tone, sections of properties with formats, and the searchable properties.
2. She registers the module; Arras checks the declaration and accepts it.
3. She opens a `Solution` in the browser; the page shows her title, summary and sections, in her tone and icon.
4. She misspells a property in a section and registers again; the registration is refused, naming the path of the fault and leaving the registry as it was.

## Acceptance Criteria

- [ ] **US-070-AC1** — Given a UMF document with a valid `arras.view` declaration on a record, when the module is registered, then the registration succeeds and the type's description carries the declared view
- [ ] **US-070-AC2** — Given a declared view, when an entity of that type is opened, then its title, summary, icon, tone, sections and formats follow the declaration
- [ ] **US-070-AC3** — Given a declaration that names a property or relationship the type does not have, when the module is registered, then registration is refused with the path of the fault and the stored registry is unchanged
- [ ] **US-070-AC4** — Given a declaration with a term outside the vocabulary, a format that does not suit the property's type, an unknown icon or tone, or an unclosed template placeholder, when the module is registered, then registration is refused with the path of the fault
- [ ] **US-070-AC5** — Given a declaration containing markup, script, a URL to load or a colour value, when the module is registered, then it is refused as outside the vocabulary
- [ ] **US-070-AC6** — Given a module with no `arras.view`, when it is registered, then it registers as before and its pages use the derived default
- [ ] **US-070-AC7** — Given a module registered with and without the declaration, when the registry's types, relationships and actions are compared, then they are identical
- [ ] **US-070-AC8** — Given a registration that changes a view, when a page is open under the old revision, then it refreshes under the new one without losing its place

## Edge Cases

- **A declaration on one type only**: the other types use the derived default; the module is not refused for partial coverage.
- **A template using a property that is optional**: an empty value drops its placeholder and the separators that depend on it; a title that comes out empty falls back to the key.
- **A relationship label for a relationship that has an inverse**: each direction carries its own label; a missing one falls back to the relationship's name.
- **Two types claim the same tone**: allowed; tones are a palette of eight, not identities.
- **The document is registered through a validator that does not accept the vocabulary**: registration is refused naming the vocabulary (PRD open question on UMF).

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Valid view | US-070-AC1 | catalog with a view on `Solution` | register | Succeeds; `describe` returns the view |
| Page follows | US-070-AC2 | the same | open a `Solution` | Title, summary, sections, tone and icon as declared |
| Unknown property | US-070-AC3 | a section naming `sumary` | register | Refused: `modules[0].elements.Solution.extensions.arras.view.sections[0].properties[2]` names `sumary`; registry unchanged |
| Bad vocabulary | US-070-AC4 | a term `onClick`; format `date` on a string property | register | Each refused with its path |
| No code | US-070-AC5 | a `<script>` in a label; a `#ff0000` tone | register | Refused as outside the vocabulary |
| No view | US-070-AC6 | the current catalog | register | Succeeds; pages use the derived default |
| Registry equal | US-070-AC7 | catalog with and without a view | compare `describe` types, relationships, actions | Equal |
| Live change | US-070-AC8 | a page open; a new revision registered | wait for the next request | Page re-renders with the new view in place |

## Dependencies

- **Stories**: US-067 (the page that reads the view).
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-15 to BRW-17, BRW-19
- **PRD Requirements**: FR-58
- **External**: ADR-022, CONTRACT-010 (the vocabulary), CONTRACT-002 (registry), UMF's acceptance of an additional vocabulary (open).

## Out of Scope

- Custom components, stylesheets, scripts, markup or images in a declaration.
- Per-viewer or per-role presentation.
- Changing what is read or permitted through a view declaration.
- A visual editor for views.
