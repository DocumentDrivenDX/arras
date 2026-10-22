// SPDX-License-Identifier: MIT OR Apache-2.0
// @vitest-environment node
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { checkScalar, encodeField } from "../lib/inputs";

// The vectors tests/test_inputs_vectors.py checks against the server's conversion: the same text must
// be accepted or refused by the form before any request (tests/vectors/inputs.json, its `note`).
interface Vector {
  type: string;
  value: string;
  ok: boolean;
}
const file = resolve(dirname(fileURLToPath(import.meta.url)), "../../../tests/vectors/inputs.json");
const { vectors } = JSON.parse(readFileSync(file, "utf8")) as { note: string; vectors: Vector[] };

describe("typed inputs agree with the server (tests/vectors/inputs.json)", () => {
  it("has vectors for every typed scalar", () => {
    expect(new Set(vectors.map((v) => v.type))).toEqual(
      new Set(["timestamp", "integer", "decimal", "binary", "boolean"]),
    );
  });

  it.each(vectors.map((v) => [v.type, JSON.stringify(v.value), v.ok, v] as const))(
    "%s %s ok=%s",
    (_t, _v, _ok, v) => {
      const r = checkScalar(v.type, v.value);
      expect(r.error === undefined).toBe(v.ok);
      if (!v.ok) expect(r.value).toBeUndefined();
    },
  );

  it.each(vectors.filter((v) => v.value.trim() !== "").map((v) => [v.type, v.value, v] as const))(
    "a form field of type %s agrees for %s, surrounding spaces trimmed",
    (_t, _v, v) => {
      const spec = {
        name: "x",
        type: v.type,
        kind: "scalar" as const,
        cardinality: "one" as const,
      };
      const r = encodeField(spec, `  ${v.value}  `);
      expect(r.error === undefined).toBe(v.ok);
      if (v.ok && (v.type === "timestamp" || v.type === "decimal" || v.type === "binary"))
        expect(r.value).toBe(v.value);
    },
  );
});
