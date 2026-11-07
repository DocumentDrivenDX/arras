// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
// The static read-only backend itself (ADR-031, CONTRACT-012): what loads and what is refused, exact integers, the
// hub beyond the 100 keys an entity carries, the export as the bytes the library writes, and every write refused.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import { canonical, GRAPH_FORMAT, parseGraphFile } from "../browser/graphFile";
import { createStaticClient, loadStore, READ_ONLY, staticSchemaApi } from "../static/backend";
import { readConfig } from "../static/config";
import { type Domain, integerFault, storedDecimal } from "../static/domain";
import { GraphLoadError, isoTimestamp, type Store } from "../static/store";
import { evaluate } from "../static/view";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const read = (p: string) => readFileSync(`${root}/${p}`, "utf8");
const catalogModule = read("examples/catalog/catalog.umf.json");
const catalogGraph = read("examples/catalog/catalog.graph.json");

const corpus = JSON.parse(read("src/arras/conformance/read_cases.json")) as {
  fixtures: Record<string, { module: string; graph: string }>;
};
const readsModule = corpus.fixtures.reads?.module as string;
const readsGraph = corpus.fixtures.reads?.graph as string;

describe("loading", () => {
  it("holds the example graph and states the one backend it is", async () => {
    const store = await loadStore(catalogModule, catalogGraph);
    const meta = await createStaticClient(store).meta();
    expect(meta.modules.map((m) => [m.name, m.record, m.replicas])).toEqual([
      ["catalog", "static", []],
    ]);
    expect(meta.status).toEqual([
      expect.objectContaining({ backend: "static", available: true, reason: null }),
    ]);
    expect(meta.modules[0]?.entityTypes.every((t) => t.view !== undefined)).toBe(true);
    expect(meta.modules[0]?.entityTypes[0]?.capabilities.static?.mutable).toBe(false);
  });

  it("refuses a graph of another module", async () => {
    const other = catalogGraph.replace('"module": "catalog"', '"module": "other"');
    await expect(loadStore(catalogModule, other)).rejects.toThrow(/graph is of module other/);
  });

  it("refuses every record the Python import rejects, naming each, and loads none", async () => {
    const g = parseGraphFile(catalogGraph);
    const bad = {
      ...g,
      records: [
        ...g.records,
        { type: "Nope", key: "x", properties: {} },
        { type: "UseCase", key: "has space", properties: { name: "x" } },
        { type: "UseCase", key: "uc-missing", properties: {} },
        { type: "UseCase", key: "uc-extra", properties: { name: "n", surprise: 1 } },
        { relationship: "addresses", source: "no-source", target: "no-target" },
        { relationship: "nonesuch", source: "a", target: "b" },
      ],
    };
    const text = JSON.stringify({
      format: GRAPH_FORMAT,
      version: 1,
      module: g.module,
      complete: true,
      records: bad.records,
    });
    const err = await loadStore(catalogModule, text).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(GraphLoadError);
    const reasons = (err as GraphLoadError).rejections.map((r) => `${r.kind} ${r.reason}`);
    expect(reasons).toEqual([
      "entity unknown type or not a key",
      "entity unknown type or not a key",
      expect.stringMatching(/^entity missing \[name\]/),
      "entity missing [], undeclared [surprise]",
      "relationship an endpoint is missing or of the wrong type",
      "record neither an entity nor a relationship",
    ]);
  });

  it("refuses a decimal number the graph file cannot hold, as the library does", async () => {
    const text = catalogGraph.replace('"complete": true', '"complete": true, "x": 1.5');
    await expect(loadStore(catalogModule, text)).rejects.toThrow(/is not an integer/);
  });

  it("reads timestamps as Python's isoformat writes them", () => {
    expect(isoTimestamp("2026-01-01T00:00:00Z")).toBe("2026-01-01T00:00:00+00:00");
    expect(isoTimestamp("2026-03-04T05:06:07.5+02:00")).toBe("2026-03-04T05:06:07.500000+02:00");
    expect(isoTimestamp("2026-02-30T00:00:00Z")).toBeNull();
    expect(isoTimestamp("2026-01-01T00:00:00")).toBeNull();
  });
});

describe("reads over the synthetic corpus fixture", () => {
  let store: Store;
  let client: ReturnType<typeof createStaticClient>;
  beforeAll(async () => {
    store = await loadStore(
      readsModule.startsWith("{") ? readsModule : read(readsModule),
      readsGraph.startsWith("{") ? readsGraph : read(readsGraph),
    );
    client = createStaticClient(store);
  });

  it("keeps integers past 2^53 exact, as text through the BigInt scalar", async () => {
    const r = await client.moduleQuery<{ note: { big: string; count: string } }>(
      "reads",
      '{ note(key: "n-001") { big count } }',
    );
    expect(r.data?.note).toEqual({ big: "9007199254740993", count: "-7" });
    const rec = store.records.find((x) => x.key === "n-001") as { properties: { big: unknown } };
    expect(rec.properties.big).toBe(9007199254740993n);
  });

  it("carries 100 relationship keys on an entity and reaches the other 50 of the hub by paging", async () => {
    const carried = await client.moduleQuery<{ topic: { mentionedBy: { key: string }[] } }>(
      "reads",
      '{ topic(key: "hub") { mentionedBy { key } } }',
    );
    expect(carried.data?.topic.mentionedBy).toHaveLength(100);
    let after: string | null = null;
    const all: string[] = [];
    for (let i = 0; i < 5; i++) {
      const page: { data: { noteList: { items: { key: string }[]; truncated: boolean } } } =
        (await client.moduleQuery(
          "reads",
          'query($a: String) { noteList(filter: { mentions: "hub" }, limit: 100, afterKey: $a) { items { key } truncated } }',
          { a: after },
        )) as never;
      all.push(...page.data.noteList.items.map((n) => n.key));
      if (!page.data.noteList.truncated) break;
      after = all[all.length - 1] ?? null;
    }
    expect(all).toHaveLength(150);
    expect(new Set(all).size).toBe(150);
  });

  it("answers an entity budget as COST_EXCEEDED, naming the limit", async () => {
    const lists = Array.from(
      { length: 11 },
      (_, i) => `a${i}: noteList(limit: 100) { items { key } }`,
    ).join(" ");
    const r = await client.moduleQuery("reads", `{ ${lists} }`);
    expect(r.errors.map((e) => e.code)).toContain("COST_EXCEEDED");
  });

  it("exports every record of the example in the canonical order, as the bytes the library wrote", async () => {
    const example = createStaticClient(await loadStore(catalogModule, catalogGraph));
    const items = [];
    let after: string | undefined;
    for (;;) {
      const p = await example.export({ module: "catalog", limit: 40, ...(after ? { after } : {}) });
      items.push(...p.items);
      if (p.nextCursor === null) break;
      after = p.nextCursor;
    }
    const written = `${canonical({
      format: GRAPH_FORMAT,
      version: 1,
      module: "catalog",
      complete: true,
      records: items,
    })}\n`;
    expect(written).toBe(catalogGraph);
  });

  it("refuses an export cursor of another export, and a limit out of range", async () => {
    await expect(client.export({ module: "reads", after: "not-a-cursor" })).rejects.toMatchObject({
      status: 400,
    });
    await expect(client.export({ module: "reads", limit: 501 })).rejects.toMatchObject({
      status: 400,
    });
  });
});

describe("what the profile refuses", () => {
  it("answers every write, the journal and SQL with a 501 that says the graph is read-only", async () => {
    const client = createStaticClient(await loadStore(catalogModule, catalogGraph));
    const calls = [
      () => client.validate("catalog", "AddUseCase", { inputs: {} }),
      () => client.invoke("catalog", "AddUseCase", { inputs: {} }),
      () => client.batch("catalog", "AddUseCase", { items: [], atomic: true }),
      () => client.changes({ module: "catalog" }),
      () => client.loads({ module: "catalog" }),
      () =>
        client.query({
          module: "catalog",
          sql: "SELECT 1",
          consistency: "latest",
          limit: 1,
        } as never),
    ];
    for (const call of calls) {
      const e = (await call().catch((x: unknown) => x)) as ApiError;
      expect(e).toBeInstanceOf(ApiError);
      expect(e.status).toBe(501);
      expect(e.kind).toBe("unsupported");
      expect(e.message).toBe(READ_ONLY);
    }
    expect(await staticSchemaApi().offered()).toBe(false);
  });

  it("is a public viewer with Explore only, and an unknown module is a 404", async () => {
    const client = createStaticClient(await loadStore(catalogModule, catalogGraph));
    expect(await client.viewer()).toEqual({ user: "public", modes: ["user"] });
    await expect(client.moduleQuery("nope", "{ __typename }")).rejects.toMatchObject({
      status: 404,
    });
    await expect(client.moduleQuery("catalog", "{ not valid")).rejects.toMatchObject({
      status: 400,
    });
  });
});

describe("the page's configuration", () => {
  it("names two files relative to the page and no other place", () => {
    expect(readConfig('{"module":"a.umf.json","graph":"data/a.graph.json"}')).toEqual({
      module: "a.umf.json",
      graph: "data/a.graph.json",
    });
    for (const bad of [
      "https://x.test/a.json",
      "//x.test/a.json",
      "/abs.json",
      "../up.json",
      "a/../../b.json",
      "a b.json",
      "a.json?x=1",
      "C:/a.json",
      "",
    ])
      expect(() => readConfig(JSON.stringify({ module: bad, graph: "g.json" })), bad).toThrow(
        /relative/,
      );
    expect(() => readConfig("not json")).toThrow(/not JSON/);
  });
});

describe("templates agree with the Python reference (tests/vectors/template.json)", () => {
  const { row, vectors } = JSON.parse(read("tests/vectors/template.json")) as {
    row: Record<string, unknown>;
    vectors: { note: string; template: string; expected?: string; malformed?: boolean }[];
  };
  it.each(vectors.map((v) => [v.note, v] as const))("%s", (_n, v) => {
    if (v.malformed) expect(() => evaluate(v.template, row)).toThrow();
    else expect(evaluate(v.template, row)).toBe(v.expected);
  });
});

describe("numeric domains agree with the Python reference (tests/vectors/domain.json)", () => {
  const doc = JSON.parse(read("tests/vectors/domain.json")) as {
    domains: Record<
      string,
      {
        family: "integer" | "decimal";
        precision?: number;
        scale?: number;
        bits?: number;
        signed?: boolean;
      }
    >;
    vectors: { domain: string; value: string | number; held?: string; refused?: string }[];
  };
  const asDomain = (name: string): Domain => {
    const d = doc.domains[name] as (typeof doc.domains)[string];
    return {
      family: d.family,
      precision: d.precision ?? null,
      scale: d.scale ?? null,
      bits: d.bits ?? 64,
      signed: d.signed ?? true,
    };
  };
  const hold = (name: string, value: string | number): string => {
    const d = asDomain(name);
    if (d.family === "decimal") return storedDecimal(d.scale === null ? undefined : d, value);
    const why = integerFault(d, BigInt(value));
    if (why) throw new Error(why);
    return String(BigInt(value));
  };
  it("has vectors for every domain", () => expect(doc.vectors.length).toBeGreaterThanOrEqual(30));
  it.each(doc.vectors.map((v) => [`${v.domain} ${JSON.stringify(v.value)}`, v] as const))(
    "%s",
    (_n, v) => {
      if (v.refused !== undefined) expect(() => hold(v.domain, v.value)).toThrow(v.refused);
      else expect(hold(v.domain, v.value)).toBe(v.held);
    },
  );
});
