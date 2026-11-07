---
ddx:
  id: SPIKE-006
  type: tech-spike
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-11-06
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: ADR-031
      kind: informs
    - id: CONTRACT-012
      kind: informs
---

# Technical Spike: Can the Python library run in the browser as the static backend, and at what cost?

**Spike ID**: SPIKE-006 | **Lead**: Erik LaBianca | **Time Budget**: one session | **Status**: Completed

Terms used in this spike:

- Pyodide is CPython compiled to WebAssembly with a JavaScript loader; it runs in a browser tab or in Node.
- The static read-only profile is an `ArrasClient` that answers from a module document and a graph file with no server (CONTRACT-012, ADR-031).
- The reference is the Python library: the console surface (`arras.console`) over the in-memory adapter.
- Approach (a) is a TypeScript port of the read path; approach (b) is the Python library under Pyodide behind a fetch or Service Worker shim.

## Question

ADR-031 chooses (a). Does (b), the unmodified Python library under Pyodide, give the same answers at a cost that would change that choice: download size, start-up time, memory, and the work to put it behind `ArrasClient`?

## Method

Pyodide 0.29.0 (CPython 3.13) from npm, run in Node 26.12.1 on macOS arm64, loading its files from local disk (no network in the numbers). `src/arras` and the pure-Python `graphql` package were copied into the Pyodide file system as a zip (258 files; 3.1 MB unpacked, 0.68 MB zipped), with `arras/ui/static`, `arras/mcp` and `arras/adapters` left out. The in-memory adapter was loaded with `examples/catalog` (87 entities, 170 records) and then with the synthetic graph (1,024 entities, 6,021 records, 7.9 MB; `tools/gen_synthetic_graph.py`), a reader granted, and queries were run through `Console.execute`. Two runs of each; the figures are the two runs' range. The script is not kept in the repository: it is the 40 lines described here.

## Results

| Measure | catalog | synthetic |
|---|---|---|
| `loadPyodide()` (runtime start) | 579 to 581 ms | 586 ms |
| `import arras` (testing, console, core) | 291 to 303 ms | 299 ms |
| Register the module and import the records | 9 to 10 ms | 97 ms |
| First list query | 3 ms | 6 ms |
| `_search` of one or two words, median of 20 | 4.8 to 5 ms | 18.6 ms |
| WebAssembly heap | 29 MB | 42 MB |
| Node process RSS | 164 MB | 208 MB |

| Runtime download | Raw | Gzip |
|---|---|---|
| `pyodide.asm.wasm` | 8.65 MB | 2.82 MB |
| `python_stdlib.zip` | 2.42 MB | 2.38 MB |
| `pyodide.asm.js` + loader | 1.09 MB | 0.23 MB |
| Arras and graphql-core (zip) | 0.68 MB | 0.68 MB |
| **Total before any data** | **12.8 MB** | **6.1 MB** |

For comparison, approach (a) adds 173 KB raw (48 KB gzip) to the Browser's script (613 KB to 786 KB; 187 KB to 235 KB gzip), loads the synthetic graph in 112 to 175 ms to the first usable page in Chromium, and holds it in about 11 MB of JavaScript heap (ADR-031 and the build report).

## Findings

1. **It works, and fast once started.** Reads, search and graph load are the same speed as the TypeScript port or within a few multiples, and give the same answers by construction.
2. **The console surface does not run as is.** `create_app` serves each request on a `ThreadPoolExecutor` and the spike's first harness drove it with `asyncio.run`, which failed inside Pyodide's `webloop.run_until_complete` (the request never reached the executor; Pyodide has no threads, so the executor is expected to fail too, and that was not run). The spike called the synchronous `Console.execute(principal, module, query, variables, op_name)` instead. A real shim would own the request framing (the body, the status, the `application/json` headers, the 400 and 404 forms) that `Console.handle` provides, and keep it in step with the console.
3. **The cost is the first 6 MB.** About 0.9 s to boot and import on a desktop V8 before any graph is loaded, and 6.1 MB gzip (12.8 MB raw) to download, against 48 KB for approach (a). The figures are for a desktop engine from local disk; a phone's compile and parse of 8.6 MB of WebAssembly was not measured and is expected to be several times slower.
4. **Python 3.13, not 3.11.** Pyodide 0.29.0 ships CPython 3.13; the library qualifies 3.11 only (CHANGELOG 0.6.5). The spike ran, but nothing here qualifies Arras on 3.13.
5. **A second runtime in a public page** means WebAssembly compilation (blocked by a content security policy that forbids `wasm-unsafe-eval`), a Service Worker or fetch shim scope, and a second copy of the module in memory; approach (a) has none of these.
6. **Not tried.** A real browser, a network, a phone, a Service Worker, Pyodide's `micropip`, the Truss adapter, and the library's optional telemetry.

## Decision

Approach (a) remains the durable form, as ADR-031 records. Approach (b) is kept as the fallback if the TypeScript port cannot be kept in step with Python: the shared corpus (CONTRACT-012 G) would then be run against (b) as well, and a difference between the three would be a bug in one of them.

## Follow-ups

None created. A browser measurement of (b) on a phone would be needed before it were chosen for any reason.
