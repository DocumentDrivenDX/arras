// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { buildListQuery, columnsFor, listField, MAX_SELECTIONS, selectionCost } from "../api/gql";
import { buildInputs, encodeField, violationsByField } from "../lib/inputs";
import { defined } from "./defined";
import { catalog } from "./fake";

const spec = (
  type: string,
  cardinality: "one" | "optional" | "many" = "one",
  kind: "scalar" | "record" | "ref" = "scalar",
) => ({
  name: "x",
  type,
  kind,
  cardinality,
});

describe("input encoding (src/arras/inputs.py)", () => {
  it("encodes integers as numbers within 53 bits and as text beyond", () => {
    expect(encodeField(spec("integer"), "42").value).toBe(42);
    expect(encodeField(spec("integer"), "-9007199254740993").value).toBe("-9007199254740993");
    expect(encodeField(spec("integer"), "4.2").error).toBeTruthy();
  });
  it("keeps decimals, timestamps and binary as text and rejects malformed ones", () => {
    expect(encodeField(spec("decimal"), " 12.50 ").value).toBe("12.50");
    expect(encodeField(spec("decimal"), "1,5").error).toBeTruthy();
    expect(encodeField(spec("timestamp"), "2026-10-09T14:02:11Z").value).toBe(
      "2026-10-09T14:02:11Z",
    );
    expect(encodeField(spec("timestamp"), "2026-10-09T14:02:11").error).toBeTruthy(); // no offset
    expect(encodeField(spec("binary"), "aGk=").value).toBe("aGk=");
    expect(encodeField(spec("binary"), "not base64!").error).toBeTruthy();
  });
  it("omits an empty optional input and flags an empty required one", () => {
    expect(encodeField(spec("string", "optional"), "").value).toBeUndefined();
    expect(encodeField(spec("string", "one"), "  ").error).toBe("required");
  });
  it("reads a many input one value per line", () => {
    expect(encodeField(spec("integer", "many"), "1\n2\n\n3").value).toEqual([1, 2, 3]);
    expect(encodeField(spec("integer", "many"), "1\nx").error).toContain("line 2");
  });
  it("reads a record as a JSON object only", () => {
    expect(encodeField(spec("Terms", "one", "record"), '{"a":1}').value).toEqual({ a: 1 });
    expect(encodeField(spec("Terms", "one", "record"), "[1]").error).toBeTruthy();
  });
  it("builds the inputs and the per-field errors together", () => {
    const b = buildInputs(
      [
        { ...spec("integer"), name: "n" },
        { ...spec("string"), name: "s" },
      ],
      { n: "q", s: "ok" },
    );
    expect(b.inputs).toEqual({ s: "ok" });
    expect(Object.keys(b.errors)).toEqual(["n"]);
  });
  it("maps violation paths to input names", () => {
    const v = violationsByField([
      { path: "inputs.level", code: "type", message: "bad" },
      { path: "inputs.tags[2]", code: "type", message: "bad item" },
      { path: "inputs.terms.months", code: "type", message: "bad nested" },
      { path: "", code: "other", message: "general" },
    ]);
    expect(Object.keys(v.byField).sort()).toEqual(["level", "tags", "terms"]);
    expect(v.general).toHaveLength(1);
  });
});

describe("query building (CONTRACT-006 limits)", () => {
  it("builds compact list queries within the field-selection cap", () => {
    const m = catalog();
    const t = defined(m.entityTypes[1], "m.entityTypes[1]");
    const cols = columnsFor(m, t);
    expect(selectionCost(cols.filter((c) => c.kind !== "rel"))).toBeLessThanOrEqual(MAX_SELECTIONS);
    const q = buildListQuery(t.name, cols.slice(0, 3));
    expect(q).toContain(`${listField(t.name)}(filter: $filter`);
    expect(q).toContain("freshness { backend asOf at consistency }");
    expect(q).not.toMatch(/target \{/);
  });
});
