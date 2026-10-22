// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { buildListQuery, nextAfterKey, weftName, weftType } from "../api/gql";
import type { EntityTypeInfo } from "../api/types";
import { templateOf } from "../areas/QueryPanels";

// Legal UMF names that are Weft reserved words read through every statement the console writes: each name is a
// Weft quoted identifier (as `arras.names.quoted` writes it; tests/test_reserved_names.py runs the same
// statements on the memory adapter and through Weft's parser).

const ticket: EntityTypeInfo = {
  name: "desk.Ticket",
  key: "order",
  properties: [
    { name: "order", type: "string", required: true, cardinality: "one" },
    { name: "group", type: "string", required: true, cardinality: "one" },
  ] as EntityTypeInfo["properties"],
  capabilities: {},
};

describe("Weft names in the console's statements", () => {
  it("writes an admitted name as a quoted identifier and refuses anything else", () => {
    expect(weftName("order")).toBe('"order"');
    expect(weftType("desk.Ticket")).toBe('"desk"."Ticket"');
    for (const bad of ['a"b', "a b", "", "1a", "x; DROP"]) expect(() => weftName(bad)).toThrow();
  });

  it("a template over a type whose key and properties are reserved words", () => {
    expect(templateOf(ticket, `x.${weftName("order")}, x.${weftName("group")}`, 50)).toBe(
      'SELECT x."order", x."group" FROM "desk"."Ticket" x ORDER BY x."order" LIMIT 51',
    );
    expect(templateOf(ticket, "x.*", 100)).toBe(
      'SELECT x.* FROM "desk"."Ticket" x ORDER BY x."order" LIMIT 101',
    );
  });

  it("a list always reads the key, whose last value is the next page's afterKey", () => {
    expect(buildListQuery("desk.Ticket", [])).toContain("afterKey: $afterKey");
    expect(buildListQuery("desk.Ticket", [])).toContain("items { key }");
    expect(nextAfterKey({ items: [{ key: "a" }, { key: "b" }], truncated: true })).toBe("b");
    expect(nextAfterKey({ items: [{ key: "a" }], truncated: false })).toBeUndefined();
    expect(nextAfterKey(null)).toBeUndefined();
  });
});
