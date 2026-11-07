---
ddx:
  id: ADR-032
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-11-06
  authoring:
    home: repo
  links:
    - id: ADR-022
      kind: informed_by
    - id: ADR-031
      kind: informed_by
    - id: CONTRACT-010
      kind: informs
    - id: CONTRACT-012
      kind: informs
---

# ADR-032: Markdown is a closed, sanitized format of the view vocabulary

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-11-06 | Proposed | Erik LaBianca (architecture lead) | [ADR-022](ADR-022-a-modules-presentation-is-declared-in-a-closed-umf-view-vocabulary.md), [ADR-031](ADR-031-the-graph-browser-runs-from-static-files-over-a-typescript-read-path-held-to-the-library-by-shared-data.md), [CONTRACT-010](../contracts/CONTRACT-010-graph-browser-view-and-search.md) | Medium |

## Context

A real Atlas export (11 documents, Markdown bodies of 7 to 30 KB with tables, lists and bold run-ins) showed as raw Markdown, because `prose` keeps line breaks and never interprets markup (US-070-AC5, and Biome forbids `dangerouslySetInnerHTML`). Public content makes the reader's safety the constraint: a value is data from a graph file, and nothing in it may become markup the page did not choose.

## Decision

1. **Vocabulary 0.2.0 adds one format, `markdown`, and changes nothing else.** The vocabulary stays closed; 0.1.0 documents read as before; a 0.2.0 document that does not use it is a 0.1.0 document; `markdown` at 0.1.0 is refused (`view_format_mismatch`); any other version is `view_unsupported_version`. The Python reader, the static profile's TypeScript reader and the shared `view_cases.json` implement and hold this.
2. **The format is a closed subset** (CONTRACT-010 A): headings, paragraphs, lists, pipe tables, fenced code, block quotes, rules, code spans, strong, emphasis, links and escapes. Nothing else is interpreted: raw HTML is text, an image is its alt text, a link is `http`, `https` or `mailto` without credentials. Images from content-addressed assets, in-text references to nodes and print styling are later versions, each its own decision.
3. **The reader is ours, not a library.** `ui/src/browser/markdown.ts` reads the subset into a tree and `MarkdownText.tsx` draws React elements; no HTML string is built, so there is no sanitizer to bypass and no new dependency to audit. It bounds its input (200,000 characters) and its nesting (twelve levels) and shows what exceeds either as text.
4. **The server needs no renderer.** Markdown is only a declared `format` the view carries to the client; resolution, search and the corpus are unchanged. Search matches the raw text, so a query can match Markdown syntax (a known, minor effect).

## Alternatives

| Option | Evaluation |
|---|---|
| A Markdown library (marked, markdown-it, micromark) with a sanitizer | Rejected: a larger dependency and a second thing to keep correct (library plus sanitizer plus allow-list); the subset we need is small |
| Render to an HTML string and sanitize (DOMPurify) | Rejected: needs `dangerouslySetInnerHTML`, which the repository's boundary tests and lint forbid |
| Extend `prose` | Rejected: changes what 0.1.0 documents mean |
| Render at publish time | Rejected: moves the sanitizer into every host's build and gives the Browser nothing to draw |

## Consequences

Positive: Atlas bodies read as documents; the safety property is local and tested (a hostile corpus of 17 inputs, a 200 KB nesting stress). Negative: a second small parser to maintain; CommonMark edge cases (setext headings, indented code, reference links, raw HTML blocks, hard breaks, autolinks, strikethrough, task lists) are not read and show as text; no client other than the Browser draws it yet. The hostile nesting test found a stack overflow in the first draft (now a depth bound), which is the kind of defect this format will keep producing; the corpus of hostile inputs is the guard.

## Validation

`ui/src/test/browser-markdown.test.tsx` (28 tests), `view.markdown-*` cases in both readers, `e2e-static/synthetic.spec.ts` (a Markdown page, axe WCAG 2.1 A and AA, Chromium 153.0.8010.12), the read corpus with a `markdown` field in the Python reference and the TypeScript backend.

## Open questions

1. Assets and typed in-text links (Atlas design, section 6) need vocabulary 0.3.0.
2. Whether search should match rendered text rather than raw.
