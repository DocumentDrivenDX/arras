// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type ArrasClient, createClient } from "../api/client";
import { parseLossless } from "../api/losslessJson";
import {
  canonical,
  graphFileName,
  graphText,
  parseGraphFile,
  readGraph,
} from "../browser/graphFile";

// The vectors tests/test_graphfile.py checks against arras.graphfile.dumps: a file saved by the
// Export control and one the library writes are the same text, so a file kept in git changes only
// when the graph does.
const file = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/vectors/graphfile.json",
);
const { vectors, rejected, unwritable } = parseLossless(readFileSync(file, "utf8")) as {
  rejected: { name: string; text: string; path: string; token: string }[];
  unwritable: { name: string; graph: unknown; path: string; token: string }[];
  vectors: {
    name: string;
    graph: {
      module: string;
      records: Record<string, unknown>[];
      complete: boolean;
      omitted: string[];
    };
    text: string;
  }[];
};

describe("the graph file agrees with the library (tests/vectors/graphfile.json)", () => {
  for (const v of vectors)
    it(v.name, () => {
      expect(graphText(v.graph)).toBe(v.text);
    });
});

/** The vector's `{"$number": token}` as the number it stands for. */
function withNumbers(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(withNumbers);
  if (v === null || typeof v !== "object") return v;
  const o = v as Record<string, unknown>;
  if (Object.keys(o).length === 1 && typeof o.$number === "string") return Number(o.$number);
  return Object.fromEntries(Object.entries(o).map(([k, x]) => [k, withNumbers(x)]));
}

describe("a number that is not an integer is not written (tests/vectors/graphfile.json)", () => {
  for (const v of unwritable)
    it(`refuses ${v.name}, naming where, as the reader does`, () => {
      expect(() => graphText(withNumbers(v.graph) as Parameters<typeof graphText>[0])).toThrow(
        new Error(`${v.path}: ${v.token} is not an integer (a decimal is written as a string)`),
      );
    });

  it("refuses an exponent a double writes for a large integer, which the reader refuses too", () => {
    const g = { module: "m", records: [{ n: 1e21 }], complete: true, omitted: [] };
    expect(() => graphText(g)).toThrow("records[0].n: 1e+21 is not an integer");
  });
});

describe("reading a graph file (tests/vectors/graphfile.json)", () => {
  for (const v of vectors)
    it(`reads ${v.name} back as the graph`, () => {
      expect(parseGraphFile(v.text)).toEqual(v.graph);
    });

  for (const v of rejected)
    it(`refuses ${v.name}, naming where`, () => {
      expect(() => parseGraphFile(v.text)).toThrow(
        new Error(`${v.path}: ${v.token} is not an integer (a decimal is written as a string)`),
      );
    });

  it("keeps an integer past 2^53 digit for digit", () => {
    const text =
      '{"complete": true, "format": "arras.graph", "module": "m", "records": [{"n": 123456789012345678901234567890}], "version": 1}';
    expect(parseGraphFile(text).records[0]).toEqual({ n: 123456789012345678901234567890n });
  });

  it("says what is wrong with its shape", () => {
    expect(() => parseGraphFile("{")).toThrow(/^not JSON/);
    expect(() => parseGraphFile("[]")).toThrow("a graph file is a JSON object");
    expect(() => parseGraphFile('{"format": "x"}')).toThrow(/not a graph file/);
    expect(() => parseGraphFile('{"format": "arras.graph", "version": 2}')).toThrow(/version 1/);
    expect(() => parseGraphFile('{"format": "arras.graph", "version": 1, "records": []}')).toThrow(
      /"module"/,
    );
    expect(() =>
      parseGraphFile('{"format": "arras.graph", "version": 1, "module": "m", "records": [1]}'),
    ).toThrow(/"records"/);
  });

  it("does not take a file for whole unless it says so", () => {
    const text = '{"format": "arras.graph", "version": 1, "module": "m", "records": []}';
    expect(parseGraphFile(text).complete).toBe(false);
  });
});

describe("the export a client reads", () => {
  const read = (body: string) => {
    vi.stubGlobal("fetch", async () => new Response(body, { status: 200 }));
    return createClient({ operateBase: "/api/operate", consoleBase: "/api/console" }).export({
      module: "m",
    });
  };

  it("refuses a record's number that is not an integer, but not a freshness's lag", async () => {
    await expect(
      read('{"items": [{"properties": {"n": 1.5}}], "nextCursor": null, "omitted": []}'),
    ).rejects.toThrow("items[0].properties.n: 1.5 is not an integer");
    const page = await read(
      '{"items": [], "nextCursor": null, "omitted": [], "freshness": {"lag": 0.25}}',
    );
    expect(page.items).toEqual([]);
  });
});

describe("canonical JSON", () => {
  it("is JSON.parse-able to the same value, with sorted keys at every depth", () => {
    const value = { b: [1, { z: 1, a: 2 }], a: null, c: "x" };
    expect(JSON.parse(canonical(value))).toEqual(value);
    expect(canonical(value).indexOf('"a"')).toBeLessThan(canonical(value).indexOf('"b"'));
  });
  it("writes empty containers compactly, as Python does", () => {
    expect(canonical({ a: [], b: {} })).toBe('{\n  "a": [],\n  "b": {}\n}');
  });
});

describe("reading the whole graph", () => {
  const page = (
    items: Record<string, unknown>[],
    nextCursor: string | null,
    omitted: string[] = [],
  ) => ({
    items,
    nextCursor,
    omitted,
    freshness: null,
  });

  it("follows the cursor to the end and keeps the records in order", async () => {
    const asked: unknown[] = [];
    const pages = [page([{ key: "a" }, { key: "b" }], "2"), page([{ key: "c" }], null)];
    const client = {
      export: async (req: unknown) => {
        asked.push(req);
        return pages.shift();
      },
    } as unknown as ArrasClient;
    const seen: number[] = [];
    const g = await readGraph(client, "catalog", (n) => seen.push(n));
    expect(g.records.map((r) => r.key)).toEqual(["a", "b", "c"]);
    expect(g.complete).toBe(true);
    expect(seen).toEqual([2, 3]);
    expect(asked).toEqual([
      { module: "catalog", limit: 500 },
      { module: "catalog", limit: 500, after: "2" },
    ]);
  });

  it("says the graph is incomplete, once per type, when pages left types out", async () => {
    const pages = [page([], "1", ["Secret"]), page([], null, ["Secret", "Other"])];
    const client = { export: async () => pages.shift() } as unknown as ArrasClient;
    const g = await readGraph(client, "catalog");
    expect(g).toMatchObject({ complete: false, omitted: ["Other", "Secret"] });
  });

  it("names the file after the module", () => {
    expect(graphFileName("catalog")).toBe("catalog.graph.json");
  });
});

describe("integers beyond 2^53", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const BIG = "9007199254740993";
  const wire = `{"items":[{"type":"T","key":"k","properties":{"n":${BIG},"m":-${BIG},"ok":12}}],"nextCursor":null,"omitted":[],"freshness":null}`;

  it("are read exactly and written digit for digit, from the response body to the file", async () => {
    vi.stubGlobal("fetch", async () => new Response(wire, { status: 200 }));
    const client = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    const text = graphText(await readGraph(client, "m"));
    expect(text).toContain(`"m": -${BIG},`);
    expect(text).toContain(`"n": ${BIG}`);
    expect(text).toContain('"ok": 12');
  });

  it("a plain JSON.parse would have rounded them (the control)", () => {
    const n = (JSON.parse(wire) as { items: { properties: { n: number } }[] }).items[0]?.properties
      .n;
    expect(String(n)).not.toBe(BIG);
  });

  it("parseLossless keeps safe integers, floats and strings, and reads big integers as bigint", () => {
    const text = `[1, -2, 1.5, 1e30, "${BIG}", ${BIG}, 9007199254740992]`;
    expect(parseLossless(text)).toEqual([
      1,
      -2,
      1.5,
      1e30,
      BIG,
      BigInt(BIG),
      BigInt("9007199254740992"),
    ]);
  });

  it("a runtime that cannot tell the source of a number refuses a big integer instead of rounding it", () => {
    const real = JSON.parse;
    // JSON.parse calling the reviver without a context, as a runtime without source text does
    vi.spyOn(JSON, "parse").mockImplementation((text, reviver) =>
      real(
        text,
        reviver &&
          ((k: string, v: unknown) => (reviver as (k: string, v: unknown) => unknown)(k, v)),
      ),
    );
    expect(() => parseLossless(`[${BIG}]`)).toThrow(/beyond 2\^53/);
    expect(parseLossless("[1, 1.5]")).toEqual([1, 1.5]);
  });
});
