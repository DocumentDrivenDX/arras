---
ddx:
  id: ADR-024
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: prd
      kind: informed_by
    - id: FEAT-011
      kind: informed_by
    - id: FEAT-010
      kind: informed_by
    - id: ADR-005
      kind: constrained_by
    - id: ADR-017
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: CONTRACT-010
      kind: informs
---

# ADR-024: A node page's location lives in the URL fragment

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-12 | Accepted | Erik LaBianca (architecture lead) | [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md), [ADR-005](ADR-005-durable-knowledge-state.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | A browser of entities is only useful if a page can be linked to, sent to a colleague and returned to with Back. A URL reaches servers, proxies, logs and `Referer` headers, so an address must carry nothing that those should not see, while a page's address must say which page it is. The two needs conflict. |
| Current State | `arras-ui` holds its place in component state (FEAT-010) and stores nothing in the browser; the audit filters travel in a `POST` body. The browser is embedded in praxis, which owns its own routing, or runs on a standalone host. Keys in this ontology are identifiers of catalog entries, which the platform owner confirms may appear in URLs; ADR-005 keeps structure derived from sensitive source records out for now. |
| Requirements | Shareable, bookmarkable, working Back and Forward; no key or search text visible to any server, proxy or log on the request path; no state held by Arras; the embedding host can take over the location; one rule for the fragments of both modes. |
| Decision Drivers | The fragment (the part after `#`) is never sent in an HTTP request, in a `Referer` header or to a server log. A shared link that cannot be shared is a defect of a browser, and a link that leaks keys is a defect of a host's security posture. |

## Decision

We will carry a node page's location in the **URL fragment only**: `#/explore/<module>/<type>/<key>`, each segment percent-encoded, never in the path or the query string. `#/explore/<module>/<type>` (no key) is a type's list and `#/explore/<module>` the module's entry, so every place a breadcrumb names has a location of its own. The `explore` prefix names Explore (`browse` is an accepted alias); the Operator Console's routes take `#/operate/…` in the shared shell (ADR-025), so the two route grammars cannot collide. The browser reads and writes the fragment itself (a small router in `arras-ui`) and works with no URL at all.

- **Search text, type chips, picture hops and scroll position stay out of every part of the URL.** They live in the history entry's state (`history.state`), which restores them on Back; it is the browser's own session history, not storage that Arras writes.
- **An embedding host may own the location.** The browser takes a `location` prop and an `onLocation` callback carrying `{module, type, key}` as data, and whether the entry is replaced rather than added; when a host supplies them the browser does not touch the URL, and the host stores the location as it chooses (praxis, in its own router).
- **The decision applies to the fragments of both modes.** An entity key, a key-column filter value, an action or type name, a group id, an instant (`since`, `until`), a column id with its sort direction, and the view words `umf` and `loads` may appear in the fragment of either mode (Explore's `#/explore/…` and Operate's `#/operate/…`); none of them appears in a path, a query string, a `Referer`, a log or storage. Search text, a Query statement, a typed form value and a person never appear in any part of either address.
- A location that fails to parse, names a module or entity the viewer cannot read, or names an absent entity shows the same "not available" page.

**Key Points**: Fragment only, never path or query | search text, statements, typed values and people never in a URL | both modes' fragments may hold keys, key-column filter values, action and type names, group ids, instants, column ids with sort directions and the `umf` and `loads` view words | host can own the location

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| No URL state | Nothing leaks | No sharing, no bookmarks, no Back; the browser's purpose is lost | Rejected |
| Key in the path or query (`/node/Solution/abc`) | Conventional; server-renderable | Needs the host to route every node path (praxis owns its routes; the dev host serves one page); reaches servers, proxies and logs | Not needed: keys are allowed in URLs, so this is permitted, but the fragment works under any host with no routing and leaks nothing; a host that prefers paths can supply `location` itself |
| An opaque server-issued short link | Hides the key from the address | Needs Arras to keep state (a link table), which ADR-013 refuses, and an access rule for links | Rejected |
| The embedding host alone owns location | Host in control | The standalone host and tests have none; each host re-implements | Adopted only as the second mode, alongside the fragment |
| **The fragment, with `history.state` for the rest and a host override** | Shareable with no server seeing the key; Back works; no state in Arras | The fragment is visible to scripts on the page and to anything that logs full URLs from the client side (some chat and helpdesk tools do); browser history and sync keep it | **Selected: removes the server-side leak, states the residual** |

## Consequences

| Type | Impact |
|------|--------|
| Positive | Pages can be linked and shared and Back works, while no server, proxy or log on the request path sees a key. |
| Negative | A shared link pasted into a system that records full URLs, and browser history and its sync, hold the key. A strict content-security policy (no third-party script) is a precondition; the host must not run analytics that read `location.hash`. |
| Neutral | The browser carries a small router. Another host-visible contract: the `location` and `onLocation` shape (CONTRACT-010). |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A host's analytics or error reporter sends `location.href` including the fragment | M | M | The browser documents the precondition; the standalone host ships none; an end-to-end test asserts no request carries the fragment |
| A key is itself sensitive (a person's name as a key) | L | L | Keys may appear in URLs (decided 2026-10-11); ADR-005 governs what content may enter; the fragment still keeps keys out of server logs |
| Fragment and `history.state` disagree after a host navigation | L | L | The fragment is the source of truth for the node; `history.state` only restores view state |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| A whole-stack test records every request in a session and finds no key or search text in any path, query string, header or `Referer` | Any occurrence |
| A copied location opens the same page for a viewer who may read it, and the same "not available" page for one who may not and for an absent entity | A difference between the two failures |
| praxis embeds the browser and owns the location without touching the URL | The praxis owners decline the `location` contract |

## Concern Impact

- **No concern impact.** It states which values the fragments of both modes may carry.

## References

- [FEAT-011](../../01-frame/features/FEAT-011-graph-browser.md), [US-071](../../01-frame/user-stories/US-071-share-a-nodes-location-the-browser-acts-as-the-viewer.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md)
- [FEAT-010](../../01-frame/features/FEAT-010-operator-console.md) (the Operator Console, whose fragment this decision also governs), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md)
