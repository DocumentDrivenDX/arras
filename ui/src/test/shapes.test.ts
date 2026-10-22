// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { schemaErrors, shapeDiff } from "../integration/shapes";
import { defined } from "./defined";
import { wire } from "./fake";

// The drift guard's own checks (src/integration/shapes.ts): would they have caught the drift the
// review found?
describe("drift guard: shapeDiff", () => {
  it("catches a `_type` tag the server strips (the old batch-refusal fixture)", () => {
    const real = wire.batch();
    const old = wire.batch({
      items: [
        defined(real.items[0], "real.items[0]"),
        {
          index: 1,
          refusal: {
            ...wire.precondition(),
            failures: [{ _type: "Failure", id: "fresh", reason: "x" } as never],
          },
        },
      ],
    });
    expect(shapeDiff(real, old).join("\n")).toContain("_type: only in the fake");
  });
  it("catches a missing key, a type change and an unexpected null; allows declared nulls and open maps", () => {
    expect(shapeDiff({ a: 1, b: "x" }, { a: 1 })).toEqual(["$.b: only in the real answer"]);
    expect(shapeDiff({ a: 1 }, { a: "1" })).toEqual(["$.a: real is number, fake is string"]);
    expect(shapeDiff({ a: null }, { a: "x" })).toEqual(["$.a: real is null, fake is string"]);
    expect(shapeDiff({ a: null }, { a: "x" }, { nullable: [".a"] })).toEqual([]);
    expect(shapeDiff({ m: { x: 1 } }, { m: { y: "z" } }, { open: [".m"] })).toEqual([]);
    expect(shapeDiff([{ a: 1 }], [])).toEqual([]);
    expect(shapeDiff([{ a: 1 }, { b: 1 }], [{ a: 2 }])).toHaveLength(1); // the real `b` element has no fake
  });
});

describe("drift guard: schemaErrors", () => {
  const doc = {
    components: {
      schemas: {
        R: {
          type: "object",
          required: ["t"],
          properties: { t: { type: ["string", "null"] }, n: { type: "integer", minimum: 0 } },
          additionalProperties: false,
        },
      },
    },
  };
  const ref = { $ref: "#/components/schemas/R" };
  it("checks types, required, additional properties, bounds, enums and alternatives", () => {
    expect(schemaErrors({ t: null, n: 1 }, ref, doc)).toEqual([]);
    expect(schemaErrors({ n: 1.5 }, ref, doc)).toEqual([
      "$.t: required",
      "$.n: 1.5 is not integer",
    ]);
    expect(schemaErrors({ t: "x", z: 1 }, ref, doc)).toEqual(["$.z: not allowed"]);
    expect(schemaErrors({ t: "x", n: -1 }, ref, doc)).toEqual(["$.n: below 0"]);
    expect(schemaErrors("c", { enum: ["a", "b"] }, doc)).toHaveLength(1);
    expect(schemaErrors(null, { oneOf: [ref, { type: "null" }] }, doc)).toEqual([]);
    expect(schemaErrors(3, { oneOf: [ref, { type: "null" }] }, doc)).toHaveLength(1);
    expect(
      schemaErrors([1, 2, 3], { type: "array", maxItems: 2, items: { type: "string" } }, doc),
    ).toHaveLength(4);
    expect(schemaErrors({}, { $ref: "#/components/schemas/Nope" }, doc)).toEqual([
      "$: unresolved #/components/schemas/Nope",
    ]);
  });
});
