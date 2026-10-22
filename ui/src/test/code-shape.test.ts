// SPDX-License-Identifier: MIT OR Apache-2.0
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// A ceiling at the longest source module today (`SchemaImport.tsx`), never raised: lower it as
// modules are split. It is the module-length half of the code-shape concern; the complexity half is
// the lint (`biome.jsonc`).
const MAX_MODULE_LINES = 445;

const SRC = join(import.meta.dirname, "..");
const NOT_SOURCE = new Set(["test", "integration"]);

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name);
    if (e.isDirectory()) return NOT_SOURCE.has(e.name) ? [] : sources(path);
    return /\.tsx?$/.test(e.name) ? [path] : [];
  });
}

function tooLong(files: Record<string, string>, ceiling: number): Record<string, number> {
  const over: Record<string, number> = {};
  for (const [name, text] of Object.entries(files)) {
    const lines = text.split("\n").length - 1;
    if (lines > ceiling) over[name] = lines;
  }
  return over;
}

describe("code shape: module length", () => {
  it("no source module grows past the ceiling", () => {
    const files = Object.fromEntries(sources(SRC).map((p) => [p, readFileSync(p, "utf8")]));
    expect(Object.keys(files).length).toBeGreaterThan(20);
    expect(tooLong(files, MAX_MODULE_LINES)).toEqual({});
  });

  it("a module over the ceiling is found", () => {
    expect(
      tooLong({ "a.ts": "x\n".repeat(MAX_MODULE_LINES + 1), "b.ts": "x\n" }, MAX_MODULE_LINES),
    ).toEqual({ "a.ts": MAX_MODULE_LINES + 1 });
  });
});
