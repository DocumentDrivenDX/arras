// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
// The shared `arras.view` cases (CONTRACT-010 A, `arras/conformance/view_cases.json`) held against the static
// profile's TypeScript reader and resolver, as `arras.conformance.views` holds the Python ones (ADR-031).
import { readFileSync } from "node:fs";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { InvalidDocument } from "../static/model";
import { parseModule } from "../static/umf";
import { resolve } from "../static/view";

const dir = resolvePath(dirname(fileURLToPath(import.meta.url)), "../../../src/arras/conformance");
type Json = Record<string, unknown>;
interface Step {
  at: (string | number)[];
  value?: unknown;
  remove?: boolean;
}
interface Case {
  id: string;
  set: Step[];
  expect: {
    ok?: boolean;
    module?: Json;
    types?: Record<string, Json>;
    violations?: { code: string; path: string }[];
  };
}
const cases = JSON.parse(readFileSync(`${dir}/view_cases.json`, "utf8")) as {
  module: string;
  cases: Case[];
};
const document = JSON.parse(readFileSync(`${dir}/${cases.module}`, "utf8")) as Json;

function patched(steps: Step[]): string {
  const doc = JSON.parse(JSON.stringify(document)) as Json;
  for (const step of steps) {
    const parents = step.at.slice(0, -1);
    const last = step.at[step.at.length - 1] as string | number;
    let node = doc as Record<string | number, unknown>;
    for (const k of parents) {
      if (typeof node[k] !== "object" || node[k] === null) node[k] = {};
      node = node[k] as Record<string | number, unknown>;
    }
    if (step.remove) {
      if (Array.isArray(node)) node.splice(last as number, 1);
      else delete node[last];
    } else node[last] = step.value;
  }
  return JSON.stringify(doc);
}

function refusedWith(text: string): [string, string][] | null {
  try {
    parseModule(text);
    return null;
  } catch (e) {
    if (!(e instanceof InvalidDocument)) throw e;
    return e.violations.map((v) => [v.code, v.path]);
  }
}

function checkResolution(c: Case, text: string): void {
  const { module, declared } = parseModule(text);
  const resolved = resolve(module, declared);
  if (c.expect.module)
    expect({
      title: resolved.module.title,
      description: resolved.module.description,
    }).toMatchObject(c.expect.module);
  for (const [name, want] of Object.entries(c.expect.types ?? {})) {
    const v = resolved.types.get(name);
    expect(v, name).toBeDefined();
    expect(v).toMatchObject(want);
  }
}

describe("view_cases.json holds for the TypeScript reader", () => {
  it("has the cases", () => expect(cases.cases.length).toBeGreaterThan(20));
  it.each(cases.cases.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    const text = patched(c.set);
    if (c.expect.ok) return checkResolution(c, text);
    const faults = refusedWith(text);
    expect(faults, "registered, but a refusal was expected").not.toBeNull();
    const want = (c.expect.violations ?? []).map((v) => [v.code, v.path]).sort();
    expect([...(faults ?? [])].sort()).toEqual(want);
  });
});
