// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
// The shared read corpus (`arras/conformance/read_cases.json`, CONTRACT-012) held against the static
// profile: every request is answered as the Python reference answered it (ADR-031).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { loadStore } from "../static/backend";
import { normaliseResult } from "../static/corpus";
import { Refusal, type Request, run } from "../static/execute";
import type { Store } from "../static/store";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
interface Case {
  id: string;
  fixture: string;
  path: string;
  query: string;
  variables?: Record<string, unknown>;
  expect: unknown;
}
const corpus = JSON.parse(
  readFileSync(`${root}/src/arras/conformance/read_cases.json`, "utf8"),
) as { fixtures: Record<string, { module: string; graph: string }>; cases: Case[] };

const text = (v: string) => (v.startsWith("{") ? v : readFileSync(`${root}/${v}`, "utf8"));
const stores = new Map<string, Promise<Store>>();
const storeOf = (name: string) => {
  let s = stores.get(name);
  if (!s) {
    const f = corpus.fixtures[name] as { module: string; graph: string };
    s = loadStore(text(f.module), text(f.graph), new Date("2026-01-01T00:00:00Z"));
    stores.set(name, s);
  }
  return s;
};

function answer(store: Store, c: Case) {
  const module =
    c.path === "/graphql" ? null : decodeURIComponent(c.path.slice("/graphql/".length));
  const req: Request = { query: c.query, variables: c.variables ?? null };
  try {
    return normaliseResult(run(store, module, req));
  } catch (e) {
    if (e instanceof Refusal) return normaliseResult(e);
    throw e;
  }
}

describe("read_cases.json holds for the TypeScript backend", () => {
  it("has the cases", () => expect(corpus.cases.length).toBeGreaterThan(200));
  for (const name of Object.keys(corpus.fixtures)) {
    describe(name, () => {
      for (const c of corpus.cases.filter((x) => x.fixture === name))
        it(c.id, async () => expect(answer(await storeOf(name), c)).toEqual(c.expect));
    });
  }
});
