// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { evaluate, parseTemplate, valueText } from "../lib/template";

// The vectors tests/test_template_vectors.py checks against the server's evaluator (tests/vectors/template.json):
// the browser must compose the same text from the same row, and read a refused template as null.
interface Vector {
  note: string;
  template: string;
  expected?: string;
  malformed?: boolean;
}
const file = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../tests/vectors/template.json",
);
const { row, vectors } = JSON.parse(readFileSync(file, "utf8")) as {
  row: Record<string, unknown>;
  vectors: Vector[];
};

describe("templates agree with the server (tests/vectors/template.json)", () => {
  it("has vectors for text, groups, escapes, malformed templates and value types", () => {
    expect(vectors.length).toBeGreaterThan(40);
    expect(vectors.some((v) => v.malformed)).toBe(true);
  });

  it.each(vectors.map((v) => [v.note, v] as const))("US-070-AC2: %s", (_note, v) => {
    if (v.malformed) {
      expect(parseTemplate(v.template)).toBeNull();
      return;
    }
    expect(evaluate(v.template, (n) => valueText(row[n]))).toBe(v.expected);
  });
});
