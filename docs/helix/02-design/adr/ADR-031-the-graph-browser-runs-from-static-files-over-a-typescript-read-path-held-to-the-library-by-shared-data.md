---
ddx:
  id: ADR-031
  type: adr
  activity: design
  status: proposed
  owner: Erik LaBianca
  updated: 2026-11-06
  authoring:
    home: repo
  links:
    - id: ADR-011
      kind: informed_by
    - id: ADR-021
      kind: informed_by
    - id: ADR-022
      kind: informed_by
    - id: ADR-023
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: ADR-028
      kind: informed_by
    - id: SPIKE-006
      kind: informed_by
    - id: CONTRACT-012
      kind: informs
    - id: CONTRACT-010
      kind: informs
    - id: CONTRACT-006
      kind: informs
    - id: FEAT-011
      kind: informs
---

# ADR-031: The Graph Browser runs from static files over a TypeScript read path, held to the library by shared data

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-11-06 | Proposed | Erik LaBianca (architecture lead) | [ADR-011](ADR-011-read-only-graphql-generated-from-the-type-registry.md), [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [ADR-023](ADR-023-search-is-a-bounded-read-built-on-the-backends-capability.md), [ADR-025](ADR-025-one-shell-two-modes-and-operate-is-offered-by-the-host.md), [ADR-028](ADR-028-the-graph-is-exported-as-the-records-the-import-takes-in-a-file-git-can-keep.md), [SPIKE-006](../spikes/SPIKE-006-python-under-pyodide-as-a-static-backend.md), [CONTRACT-012](../contracts/CONTRACT-012-static-read-only-profile.md) | Medium |

Proposed records the direction under review. The implementation named here exists and passes the evidence below; it is not yet released, and the support claims in CONTRACT-012 are scoped to that evidence.

## Context

| Aspect | Description |
|--------|-------------|
| Problem | A public document graph (the first one is a technology atlas: under 1,000 nodes of under 8 KB, hubs of up to 1,000 edges, republished weekly) should be browsed with the Graph Browser, with search, a node page, the neighbourhood picture and relationship paging, from a static file host. Today the Browser reaches Arras only over HTTP, so it needs a running Python host and a database or the in-memory adapter. Operating a hosted service for read-only public content is a cost and an attack surface the owner does not want. |
| Current State | The UI reaches the server only through the `ArrasClient` interface (`ui/src/api/client.ts`). The Graph Browser calls five of its members: `meta` (two GraphQL reads), `status`, `moduleQuery` (generated per-module GraphQL, including `_search`), `viewer`, and, from the Export control only, `export`. A graph already has a file form, the `arras.graph` file (ADR-028, CONTRACT-003), and a module is a UMF document. The Python read path is `gqlschema`, `view`, `search`, `searchplan`, `entityread` and the in-memory adapter's evaluator: about 3,000 lines. |
| Requirements | Static files only; read-only; the existing React Browser unchanged; exact integers; the 100-key relationship cap and paging beyond it; ranked search with marked excerpts; weekly republish by replacing two files; no way for the two implementations to drift unnoticed. |
| Decision Drivers | No server to run or secure; the UI and the Python library keep one meaning for every read; the cost of keeping a second implementation honest; size and start-up time on a phone; the toolchain the repository already has (Node, Vite, vitest, Playwright, axe). |

## Decision

1. **Add a static read-only profile (CONTRACT-012): an `ArrasClient` that answers from memory.** The UI takes it through a new `client` prop of `ArrasProvider`, `GraphBrowser` and the shell (`ui/src/api/context.tsx`); nothing else in the UI changes. The backend loads a UMF module document and an `arras.graph` file once, builds the module's GraphQL schema with graphql-js (pinned `16.11.0`) from the same type, field, argument and error-code definitions as `gqlschema.py`, and answers the Browser's reads with the same limits (depth 6, 50 field selections, 1,000 entities, 100 relationship targets, page limits 100 and 50), the same budgets, ordering and `truncated` rules, and the same error codes. It is a profile of the interface with one backend, `static`, which is the system of record, serves `latest` and `bulk` alike, and has no replica.
2. **It is a TypeScript port of the read path, not a transport to Python.** The module reader, the `arras.view` reader and resolver, the template grammar, the search fold, ranking and excerpts, the numeric domains and the graph-file reader are TypeScript (`ui/src/static/`). Python remains the reference. This is the dual-implementation shape Truss ADR-003 chose for its Python bridge, applied here: two implementations, one body of shared data.
3. **The two implementations are held to each other by data, and the data is generated from the reference.**
   - `view_cases.json` (the existing `arras.view` cases: 28, of which the refusals state exact `(code, path)` faults) now runs against the TypeScript reader (`static-view-cases.test.ts`) as it runs against Python (`tests/test_view_conformance.py`).
   - `tests/vectors/template.json` (58 vectors) already ran in both languages for the Browser's title template; the static profile's own template evaluator now runs it too.
   - A new corpus, `src/arras/conformance/read_cases.json` (253 GraphQL requests over three fixtures: a purpose-built module with every scalar, a 150-edge hub and text that needs the fold, `examples/catalog` and `examples/pizza`), records the answer the Python console surface gives over the in-memory adapter. `tools/gen_static_reads.py` regenerates it; `tests/test_static_reads.py` fails when the file is not what the reference answers now; `static-read-corpus.test.ts` fails when the TypeScript answer differs. A change to a read in either language fails one of the two suites until the other follows.
   - `tests/vectors/domain.json` (41 vectors) holds how a decimal is held at its scale and what an out-of-range number refuses, again from the Python reference.
   - The Backend corpus of CONTRACT-004 (`corpus.json`) is written in Weft SQL for writes, principals and journals, and is not run here: the static profile has no SQL surface and no writer. The Backend contract's reads are covered by the read corpus above, which is its GraphQL-level equivalent for the Browser's reads. This is a deliberate narrowing, stated in CONTRACT-012.
4. **A graph that the Python import would reject does not load.** A record with an unknown type, a bad key, a missing required property, an undeclared property, an endpoint that does not exist, or a value outside its type or numeric domain fails the load and names every such record (`GraphLoadError`). A published graph is built; a bad record is a build fault, never a silent omission. `npm run check:static` runs the same load on a module and graph pair before they are staged.
5. **Writes, the journal and SQL answer a clear read-only error.** `validate`, `invoke`, `batch`, `changes`, `loads` and `query` answer `501 Unsupported` whose message is "this graph is published read-only…"; the viewer is a public viewer with Explore only (no Operate, no edit controls: `canEdit` stays false); the schema surface is never offered.
6. **The page is a built host plus two files.** `ui/static.html` builds to `dist-static` (relative URLs, no inline script, a page-level content security policy that allows no request but to the page's own origin); `arras-static.json` names the module document and the graph file as paths relative to the page, refusing anything else. `npm run stage:static` assembles a site; any static file host serves it. Weekly republish replaces the graph file (and the module if it changed); the graph's content digest is the freshness position, so a changed graph is a changed `asOf`.
7. **Pyodide stays a measured alternative, not a build target.** SPIKE-006 ran the unmodified Python library under Pyodide 0.29.0. It works, but needs the console surface bypassed (its `asyncio.run` failed in Pyodide's event loop, and its thread pool is not expected to run there), an 12 MB runtime download (5.4 MB gzip) before any data, and a second runtime in the page. It is revisited only if the TypeScript port cannot be kept in step (below).
8. **The `arras.view` `prose` format forbids markup, and Atlas content is Markdown.** This is a known gap, recorded and not solved here: Atlas will need a sanitized `markdown` format in the closed view vocabulary (a new vocabulary version, an upstream proposal to be written as its own ADR with a sanitizer and a golden corpus). Until then the profile renders `prose` as text, exactly as the server profile does, and no `dangerouslySetInnerHTML` is added (the boundary test still forbids it).

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| **(a) TypeScript port of the read path behind `ArrasClient`, held to Python by shared data** | One runtime in the page; 173 KB raw (48 KB gzip) added to the Browser bundle; load of a 7.9 MB, 1,024-node graph in 112 to 175 ms in Chromium; no download beyond the Browser; reuses the repository's own toolchain; answers synchronously in-process | A second implementation to keep in step; a TypeScript parser for the UMF subset; some Python behaviours are re-derived (Python's whitespace set, code point ordering, `Decimal` text) | **Chosen.** The drift risk is the cost, and it is paid for in data: the generated corpus fails in both suites on any difference; the corpus caught two of the three deliberate mutations tried (a ranking tier and the 100-key cap; a one-character change to the excerpt window went unseen), so it bites but is not exhaustive |
| (b) Python under Pyodide behind a fetch or Service Worker shim | No second implementation; every Python behaviour for free | 12.1 MB runtime (8.6 MB wasm, 2.4 MB stdlib, 1.1 MB glue; 5.4 MB gzip) and 0.7 MB of Python before any data; 0.9 s boot and import in Node (V8), more on a phone; Python 3.13, not the 3.11 the library qualifies; the console surface cannot run as is (thread pool, `asyncio.run`) so a shim must call `Console.execute` and keep its own request framing; a Service Worker adds a scope and an install step; wasm and a second runtime in a public page | Rejected for the durable form; measured in SPIKE-006 and kept as the fallback if a port cannot follow the Python behaviour |
| (c) Pre-render every possible read as static JSON | No query engine in the page | Search and arbitrary filters are not static; a hub has no fixed set of pages; a second query surface of its own | Rejected |
| (d) A binary flat snapshot (Truss ADR-009 as first proposed) | Smaller and faster to load | The `arras.graph` file already exists, is canonical, and loads in 25 ms (parse) plus 74 ms (index) for 7.9 MB; a second file format would be a second contract | Not needed |
| (e) A hosted Arras service for the public graph | Nothing to port | The owner decided against operating one | Rejected by the owner |
| (f) Reduce the Browser to a custom static reader | Small | Loses the Browser's reader, search, picture and the accessibility work, and forks the UI | Rejected |

## Consequences

| Type | Impact |
|------|--------|
| Positive | The Browser can be published as files; the UI and the Python library keep one meaning for a read, checked by data in both languages; the profile also gives UI tests a real, conformant client (the hand-made `browserFake.ts` is not conformant and stays a test double); a graph file is validated before it is published |
| Negative | A second implementation of about 3,500 lines under `ui/src/static/`, with a module-length ceiling and a complexity ceiling it must stay under; a 584 KB corpus file in the wheel (the three fixtures' meta answers dominate); graphql-js is a new runtime dependency of the UI (`16.11.0`, against graphql-core 3.3.0 in Python, whose validation message texts differ, so the corpus compares a `BAD_QUERY`'s code and path, not its text) |
| Neutral | The Browser's `arras.graph` reader moved from `browser/` to `api/` (the browser path re-exports it) because the static backend reads it too and the boundary tests keep `browser/` an importer, not an exporter, of shared code |

## Risks and unknowns

- **Drift in behaviours the corpus does not reach.** Known not carried: the vocabulary-alias and graph-format-alias policies (ADR for aliases), the duplicate-JSON-key refusal of the Python reader, `check_action` (actions are read for name, description and inputs only; declared guards and effects are not served), a `Ref.target` into another module (null; one module per host), introspection (graphql-js serves it; not in the corpus). CONTRACT-012 lists each. A new Python read behaviour that no case reaches is not caught; the generated cases are broad, not exhaustive.
- **Unicode tables.** Python 3.11's `str.lower`, `isalnum` and `isspace` and V8's Unicode data can differ for characters added after either's tables. The corpus covers `ß`, `İ`, `Ω`/`Σ` final sigma, a surrogate pair and the fold; a character outside what it covers is unverified.
- **Browser engines.** Chromium 153.0.8010.12 (Playwright 1.63.0, headless, macOS arm64) is the only engine run. Firefox and WebKit are not run; the page uses no engine-specific API except `crypto.subtle` (with a fallback) and `JSON.parse` source text access in `losslessJson`, which is required for integers past 2^53 and refuses, rather than rounds, where a browser lacks it (Safari and Firefox support to be verified before a claim).
- **Scale beyond the measurement.** The synthetic graph is 1,024 nodes and 6,021 records (7.9 MB, 1.3 MB gzip). The full document is held in memory as parsed JSON; a graph several times larger would load proportionally slower and use proportionally more memory. No bound is claimed beyond what was measured.
- **Search cost.** The first 50 matches per type are ranked in key order, as the server does; a very common word on a large type is `truncated`, as on the server.

## Validation

Section "Verification" of the build report records every run, its environment and result: the corpora, the unit suite (1,830 existing and new tests), the lint and type checks, the Playwright and axe runs on `examples/catalog`, `examples/pizza` and the synthetic graph, and the measurements. Re-validation triggers: a change to `gqlschema.py`, `view.py`, `search*.py`, `entityread.py` or the in-memory evaluator (regenerate the corpus), a new graphql-js or Pyodide major, a new `arras.view` vocabulary version, a graph past 5,000 nodes.

## Open questions

1. Is the corpus file's size acceptable in the wheel, or should the shipped copy carry fewer fixtures (the repository copy keeps all three)?
2. Should the static host be offered by `arras.ui` (the wheel) as a mount, or stay a built page in the npm tarball? Not decided here: nothing in this ADR changes the wheel's contents.
3. The Markdown format (decision 8) needs its own ADR and an owner for the sanitizer.
