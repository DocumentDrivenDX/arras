---
ddx:
  id: PLAN-STATIC-BACKEND-20261106
  type: implementation-plan
  activity: build
  status: draft
  owner: Erik LaBianca
  updated: 2026-11-06
  authoring:
    home: repo
  links:
    - id: ADR-031
      kind: implements
    - id: CONTRACT-012
      kind: implements
    - id: SPIKE-006
      kind: informed_by
    - id: FEAT-011
      kind: informed_by
---

# Static read-only profile: what was built, how it was verified, and what it measured

Date: 2026-11-06. Scope: ADR-031 and CONTRACT-012. Nothing here is released; no tag, package or site was published.

## What exists

| Part | Where | Size |
|---|---|---|
| The backend: module reader, `arras.view` reader and resolver, template grammar, numeric domains, store, GraphQL schema and budgets, search, export, the `ArrasClient` | `ui/src/static/` (23 files) | about 3,800 lines |
| The `client` and `schemaApi` props, threaded through the provider, the Browser, the console and the shell; `useViewer` takes the client | `ui/src/api/context.tsx`, `ArrasConsole.tsx`, `browser/GraphBrowser.tsx`, `shell/` | 30 lines |
| The host page, its configuration reader, the staging and test-server scripts, the Vite and Playwright configs | `ui/static.html`, `src/static/host.tsx`, `config.ts`, `scripts/stage-static.mjs`, `serve-static-sites.mjs`, `vite.static.config.ts`, `playwright.static.config.ts` | |
| The shared data: `read_cases.json` (253 requests), `domain.json` (41 vectors); the reference generator and drift gate | `src/arras/conformance/`, `tests/vectors/`, `tools/gen_static_reads.py`, `tests/test_static_reads.py` | corpus 584 KB |
| Tests | `ui/src/test/static-*.test.ts` (view cases, read corpus, backend, site check, bench); `ui/e2e-static/` (Playwright and axe) | |
| Fixtures and tools | `examples/pizza/pizza.graph.json` (the Export of the pizza module); `tools/gen_synthetic_graph.py` | |
| Governance | ADR-031, CONTRACT-012, SPIKE-006; pointers in CONTRACT-006, CONTRACT-010, FEAT-011, the feature registry, `ui/README.md`, `CHANGELOG.md`; `tools/public-content-policy.json` (the new runtime dependency and three fixtures) | |

## Verification

All on macOS arm64. TypeScript: Node 26.12.1, vitest 5.0.3, graphql-js 16.11.0, TypeScript 6.0.3, Biome 2.5.15. Python: CPython 3.11.17, graphql-core 3.3.0. Browser: Chromium 153.0.8010.12 (Playwright 1.63.0, headless).

| Check | Result |
|---|---|
| `arras.view` cases (28) against the TypeScript reader, including every `(code, path)` refusal | 28 passed (29 tests with the count check) |
| Template vectors (58) against the static evaluator; numeric-domain vectors (41) against `domain.ts` and, in Python, against `fakes_domain.stored` | all passed |
| Read corpus (253 requests: 111 catalog, 68 pizza, 74 reads) against the TypeScript backend | 253 passed |
| The same corpus against the Python reference (`tests/test_static_reads.py`: regenerate and compare, coverage of error codes and statuses, the example graph files are exports) | passed |
| Mutation check of the corpus: a ranking tier, the 100-key relationship cap, the excerpt window | the first two failed 15 and 5 requests; the third (a one-character change of the excerpt's context) was not caught |
| The UI unit suite, after the `client` props, the module move and the new modules | 1,879 passed, 2 skipped (the site check and the bench, which run only when their environment variables are set); no existing test changed except the three guards below |
| `npm run test:integration` (the real dev host), `npm audit --omit=dev`, `check:css` | 206 passed; 0 vulnerabilities; clean |
| Guards updated for the change: `boundaries` (the static host's page mounts the shell, like `embed.tsx`), `brand-strings` (`arras.view` is an identifier, like `arras.graph`), `browser-readonly` (the Browser's export read now lives in `api/graphFile.ts`) | each still checks what it checked |
| `tsc --noEmit`, `biome check .` (complexity ceiling 15; no module over 445 lines), `check:public-manifest`, `check:externals` | clean |
| Python: ruff, ruff format, pyright strict on the new test, `tests/test_public_content.py`, `test_traceability.py` | clean |
| Playwright and axe (`npm run e2e:static`), Chromium: the catalog and pizza as files (open, type, node, relationship, picture, Back; search; no write controls and no Operate; a missing node is "Not available"; every request a `GET` of the page's own origin; no console error), WCAG 2.1 A and AA on four pages in light and dark, and the synthetic graph (search, the hub's 1,000 edges through the interface) | 15 passed; axe: no violations and no unreviewed results |

What was not run: Firefox and WebKit; any OS but macOS; the existing `e2e/` suite against the static host. That suite needs a person picker, the sandbox's four people, and fixtures made through the operate surface, and most of it exercises edits, history, Operate and schema administration, none of which this profile has; `e2e-static/` re-runs its read flows (`browser.spec.ts`, `a11y.spec.ts`) over the example modules instead. The Backend corpus (`corpus.json`) is Weft SQL over writes and journals and is not run against this profile (CONTRACT-012 G). The repository's Python suite: 3,697 passed, 100 skipped, 7 failed; all seven are Lakebase tests that import `truss`, which this environment does not install (`ModuleNotFoundError: No module named 'truss'`), and the first of them fails the same on the untouched base commit.

## Measurements

The synthetic graph (`tools/gen_synthetic_graph.py`): 1,000 documents of 6 to 8 KB, 24 topics (1,024 nodes), 6,021 records, one hub topic with 1,000 `about` edges, three `links` per document; the module has two types and two relationships.

| File | Bytes | Gzip |
|---|---|---|
| `synthetic.graph.json` | 7,864,678 | 1,312,078 |
| `synthetic.umf.json` | 17,976 | 1,687 |
| The page's script | 786,061 | 234,711 |
| The page's stylesheet | 72,446 | 12,803 |
| Total to open the page | 8.74 MB | 1.56 MB |

The page's script is 173 KB raw (48 KB gzip) larger than the existing Browser build (612,726 B to 786,061 B; 187,131 to 234,711 B gzip): graphql-js and `src/static/`.

| Stage, Node 26.12.1 (V8), `npm run bench:static` | Time |
|---|---|
| Read the module document | 1.6 ms |
| Parse the graph file (integers exact) | 27.7 ms |
| Digest (SHA-256) | 5.6 ms |
| Build the store (validate, index, canonical order) | 8.5 ms |
| **Load, total** | **about 44 ms**; JavaScript heap 10 MB above baseline after a collection |
| List 50 documents with two relationships each | 4.2 ms |
| One document with both relationships opened to their targets | 0.5 ms |
| The hub's first 100 keys; the hub's page of 100 after the cap | 0.2 ms; 0.7 ms |
| Search two words across 1,000 documents | 8.1 ms |

| Interaction, Chromium 153, static server on localhost | Time |
|---|---|
| Navigation to the first usable page (title and type cards visible), two runs | 112 and 175 ms |
| `DOMContentLoaded` | 29 ms |
| JavaScript heap after load; after reading the whole hub | 11 MB; 20 MB |
| Search "needle07", first hit on screen (includes the 250 ms pause before a search is asked) | 290 ms |
| Search "needle07 pipeline" | 4 to 5 ms |
| Open the hub node | 21 to 24 ms |
| All 1,000 hub edges through the interface (13 "Show more" clicks: 100 by the entity's keys, then pages of the other type) | 1.84 and 1.93 s |

The heap figures are the JavaScript heap (`Runtime.getHeapUsage` after a collection), not the process. The times are a desktop engine on a loopback connection, so they exclude transfer: the download is 1.56 MB gzip. No phone, throttled network or cold cache was measured.

The Pyodide alternative on the same graph, in Node (SPIKE-006): 0.6 s to start the runtime, 0.3 s to import the library, 97 ms to load the records, 18.6 ms to search, 42 MB of WebAssembly heap, and 12.8 MB (6.1 MB gzip) of runtime to download before any data.

## Findings worth keeping

- **The first full run of the corpus passed, with a defect found by reading, not by the corpus.** The decimal handling (`7` in a scale-2 field is `7.00`) was not in the first port; the corpus fixtures had been exported already at scale. It was found by reading `fakes_domain.py` and is now held by `domain.json` and a corpus note with `12.5` and `7`. The corpus bites where it has a case, and is only as broad as its cases.
- **The store build dropped from 74 ms to 8.5 ms** when relationship de-duplication changed from a scan per record to a set. A graph with tens of thousands of links would have made the first form quadratic.
- **Python's rules are narrower than they look.** Keys are ASCII (`[A-Za-z0-9._:-]`), so Unicode lives in values; the import rejects what the type or domain refuses; export order is by declaration, not by file order, so a fixture written in another order does not round-trip byte for byte (the catalog and pizza files do, because the library wrote them).
- **A static host's trust boundary is the file.** The load refuses a bad record and the page refuses a configuration that names another origin; nothing a visitor types is sent anywhere.

## What a real Atlas export showed (branch `arras-export` in the Atlas repository, not pushed)

11 documents, 5 external references, 25 links, 116 records: loads in Python (0 rejections, byte-identical re-export) and in the static host; search, node pages, backlinks, neighbourhood, hub paging (an Atlas-shaped 1,000-edge hub: 1,002 links in 14 clicks) and a 63-bit integer shown exactly all pass in Chromium 153.0.8010.12. No defect was found. Three limits, none worked around: Markdown bodies show as raw text; a `Link` record needs one relationship pair per node type (13 on `Link`) because a relationship allows one type per end; three documents are 18 to 30 KB against an assumed 8 KB and load and render without trouble (CONTRACT-012, Known gaps 1 to 3).

## Follow-ups (not done)

1. A sanitized `markdown` view format for Atlas (ADR-031 decision 8): an upstream proposal with a sanitizer and a golden corpus.
2. Firefox and WebKit runs, and a throttled-network, mid-range-phone measurement, before a claim beyond Chromium.
3. A second corpus pass on what the first does not reach: vocabulary aliases, `check_action`, introspection, a many-valued decimal, a self-relationship, a type with no search property.
4. Decide whether the corpus ships whole in the wheel (584 KB), and whether `arras.ui` offers the static page as a mount.
5. Multi-type relationship ends (or a supertype), so `Link` needs one pair of relationships, not thirteen.
6. Atlas's own module: its `Link` record per edge (so the pinned `rev` is kept) is the Atlas design's own and needs the module reader to be run on it before publication (`npm run check:static`).
