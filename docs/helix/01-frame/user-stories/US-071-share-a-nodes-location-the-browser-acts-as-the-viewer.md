---
ddx:
  id: US-071
  type: user-story
  activity: frame
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: prd
      kind: informed_by
    - id: ADR-024
      kind: informed_by
    - id: ADR-017
      kind: informed_by
    - id: US-037
      kind: informed_by
---

# US-071: Share a node's location; the browser acts as the viewer with the viewer's own access

**Feature**: FEAT-011 — Graph Browser
**Feature Requirements**: BRW-20, BRW-21, BRW-22, BRW-23
**PRD Requirements**: FR-59
**Priority**: P1
**Status**: Draft

## Story

**As a** graph reader
**I want** a location for each node page that I can copy and open later, and the assurance that the browser acts only as me, with my own access
**So that** I can send a colleague to the thing I am looking at, and the organization can trust the browser with everyone because it can do nothing its viewer could not do through a declared action

## Context

The Operator Console carries an open entity's key in the fragment too, and no other input or person (FEAT-010). A browser that cannot be linked to is of little use, so ADR-024 puts the node's location in the URL fragment, the part of an address that a browser never sends to a server, a proxy or a referrer. Search text stays out of every part of the URL. As in the Operator Console, every call is the viewer's own, and the only writes are the validate and invoke of declared actions, offered to operators.

## Walkthrough

1. The reader opens a `Solution` page and copies its address.
2. Her colleague opens it; the browser reads the module, type and key from the fragment and shows the page if the colleague's principal may read it.
3. A third colleague without access opens the same address and sees "Not available".
4. The reader presses Back and returns to the search she came from, with her text and chips.
5. A reviewer inspects the requests and finds reads, and for an operator the validate and invoke of declared actions, each carrying the viewer's token, and no key or search text in a path or query string.

## Acceptance Criteria

- [ ] **US-071-AC1** — Given a node page, when it is shown, then its address is `#/explore/<module>/<type>/<key>` in the URL fragment with nothing of them in the path or the query string
- [ ] **US-071-AC2** — Given a copied address, when it is opened by a viewer who may read the entity, then the same node page opens
- [ ] **US-071-AC3** — Given a copied address, when it is opened by a viewer who may not read the entity, or for an entity that does not exist, then the same "Not available" page shows in both cases
- [ ] **US-071-AC4** — Given a search with text and chips, when the reader opens a hit and presses Back, then the search returns with its text, chips and scroll position, and the text appears in no part of the URL and is held only in the history entry's own state
- [ ] **US-071-AC5** — Given the browser in use, when its requests are inspected, then every one is a read, or the validate or invoke of a declared action the viewer asked for (FR-64, FR-65, FR-67, FR-68, FR-70), each carries the viewer's own token through the host, and none puts a key, a search text or a person in a path or query string
- [ ] **US-071-AC6** — Given the browser, when its operations are listed, then the only operations that write are the validate and invoke of declared actions, links into Operate are offered to operators only, and no credential is held
- [ ] **US-071-AC7** — Given a host that embeds the browser, when the viewer navigates, then the host receives the location as data and may store or ignore it, and the browser works with no URL at all

## Edge Cases

- **A key with reserved characters** (spaces, slashes, `#`): encoded in the fragment and decoded exactly.
- **A fragment that does not parse**: shows "Not available", not an error trace.
- **A key the platform treats as sensitive** (a person's name used as a key): the location is still a fragment only, but the module's owner decides whether such keys exist (ADR-005); the browser does not rewrite keys.
- **A shared address copied into a system that logs full URLs, including fragments** (some chat or helpdesk tools do): the key appears in that system's log; the story's assurance is limited to what a server on the path sees. Stated in ADR-024.
- **The token expires**: the host's session-expired state shows; the location is kept so signing in returns to the page.

## Test Scenarios

| Scenario | AC ID | Input / State | Action | Expected Result |
|----------|-------|---------------|--------|-----------------|
| Fragment only | US-071-AC1 | a `Solution` page | read `location` | Path and query unchanged; fragment `#/explore/<module>/<type>/<key>` |
| Open as reader | US-071-AC2 | the copied address, alice | open | Same page |
| Open without access | US-071-AC3 | the address, dave; and a deleted key | open both | Identical "Not available" pages |
| Back keeps search | US-071-AC4 | text `lumen`, chip `Solution`, a hit opened | Back | Text, chip and scroll restored; URL never held the text |
| Reads and declared actions | US-071-AC5 | record requests during a session | inspect | Reads, and validate and invoke for an operator's change; token present; no key or text in path or query |
| Writes only by a declared action | US-071-AC6 | the client's operations the browser calls; alice and carol | enumerate; open a page | Reads, validate and invoke only; no mutation; links into Operate for alice, none for carol |
| Host-owned location | US-071-AC7 | a host passing `onLocation` | navigate | Host receives `{module, type, key}` (and `{replace: true}` where the entry is rewritten); the URL is untouched |

## Dependencies

- **Stories**: US-067.
- **Feature Spec**: FEAT-011
- **Feature Requirements**: BRW-20 to BRW-23
- **PRD Requirements**: FR-59
- **External**: ADR-024 (the location), ADR-017 (the viewer's own token), US-037 (the read-only, principal-scoped rule the Operator Console already keeps).

## Out of Scope

- Short links, link expiry and link access control (the backends decide access).
- Bookmarks or "recent" lists stored by Arras.
- Putting search text in a URL.
