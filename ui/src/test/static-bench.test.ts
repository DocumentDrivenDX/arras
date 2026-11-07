// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
// Measure the static profile on a synthetic graph (`npm run bench:static`, ADR-031): load time by stage and the
// time of the reads the Graph Browser makes. Set STATIC_BENCH_DIR to a directory holding `synthetic.umf.json`
// and `synthetic.graph.json` (`tools/gen_synthetic_graph.py`); with it unset the test is skipped.
import { readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseGraphFile } from "../browser/graphFile";
import { digestOf } from "../static/backend";
import { run } from "../static/execute";
import { Store } from "../static/store";
import { parseModule } from "../static/umf";
import { resolve } from "../static/view";

const dir = process.env.STATIC_BENCH_DIR;
const ms = (t0: number) => Math.round((performance.now() - t0) * 10) / 10;
const heapMb = () => Math.round(process.memoryUsage().heapUsed / 1048576);

describe.skipIf(!dir)("the static profile over the synthetic graph", () => {
  it("loads and answers within the measured bounds", async () => {
    const moduleText = readFileSync(`${dir}/synthetic.umf.json`, "utf8");
    const graphText = readFileSync(`${dir}/synthetic.graph.json`, "utf8");
    const out: Record<string, unknown> = { graphBytes: graphText.length };
    (globalThis as { gc?: () => void }).gc?.();
    const base = heapMb();
    let t = performance.now();
    const { module, declared } = parseModule(moduleText);
    out.parseModuleMs = ms(t);
    t = performance.now();
    const graph = parseGraphFile(graphText);
    out.parseGraphMs = ms(t);
    t = performance.now();
    const digest = await digestOf(graphText);
    out.digestMs = ms(t);
    t = performance.now();
    const store = new Store(module, resolve(module, declared), graph, digest);
    out.buildStoreMs = ms(t);
    (globalThis as { gc?: () => void }).gc?.();
    out.heapDeltaMb = heapMb() - base;
    const reads: Record<string, number> = {};
    const time = (name: string, query: string, variables?: Record<string, unknown>) => {
      const t0 = performance.now();
      const r = run(store, "synthetic", { query, variables });
      reads[name] = ms(t0);
      return r;
    };
    time(
      "listDocs",
      "query($l:Int){ docList(limit:$l){ items{ key name summary kind about{key} links{key} } truncated } }",
      { l: 50 },
    );
    time(
      "docByKey",
      '{ doc(key:"doc-0500"){ key name body about{ key target{ key } } links{ key target{ key } } linkedFrom{ key } } }',
    );
    time("hubKeys", '{ topic(key:"hub"){ key coveredBy{ key } } }');
    const hub = time(
      "hubPage",
      'query($a:String){ docList(filter:{about:"hub"}, limit:100, afterKey:$a){ items{ key name } truncated } }',
      { a: "doc-0899" },
    );
    time(
      "search",
      "query($t:String!){ _search(text:$t, limit:50){ hits{ key label excerpt{ text mark } } counts{ type count atLeast } truncated } }",
      { t: "needle07 pipeline" },
    );
    time(
      "meta",
      "{ modules { name entityTypes { name key properties { name type } view { title } } } }",
    );
    out.reads = reads;
    writeFileSync(`${dir}/bench-node.json`, JSON.stringify(out, null, 2));
    process.stdout.write(`${JSON.stringify(out)}\n`);
    expect(store.entities.get("Doc")?.length).toBe(1000);
    expect((hub.data as { docList: { items: unknown[] } }).docList.items.length).toBe(100);
  });
});
