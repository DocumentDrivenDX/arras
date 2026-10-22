// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import type { Column } from "../api/gql";
import { hiddenFilters } from "../areas/EntityFilters";
import { ariaSort, nextSort, sortRows } from "../areas/pageSort";
import { scrollCue } from "../lib/scrollCue";

describe("scrollCue: the edges with more to scroll to", () => {
  it("shows nothing when the content fits", () => {
    expect(scrollCue({ scrollLeft: 0, clientWidth: 400, scrollWidth: 400 })).toEqual({
      start: false,
      end: false,
    });
  });

  it("shows only the end at the start of a wider box", () => {
    expect(scrollCue({ scrollLeft: 0, clientWidth: 400, scrollWidth: 900 })).toEqual({
      start: false,
      end: true,
    });
  });

  it("shows both edges in the middle and only the start at the end", () => {
    expect(scrollCue({ scrollLeft: 200, clientWidth: 400, scrollWidth: 900 })).toEqual({
      start: true,
      end: true,
    });
    expect(scrollCue({ scrollLeft: 500, clientWidth: 400, scrollWidth: 900 })).toEqual({
      start: true,
      end: false,
    });
  });

  it("treats a sub-pixel remainder as at the edge, and a right-to-left offset by its size", () => {
    expect(scrollCue({ scrollLeft: 499.4, clientWidth: 400, scrollWidth: 900 }).end).toBe(false);
    expect(scrollCue({ scrollLeft: -200, clientWidth: 400, scrollWidth: 900 })).toEqual({
      start: true,
      end: true,
    });
  });
});

const col = (id: string, over: Partial<Column> = {}): Column => ({
  id,
  label: id,
  field: id,
  kind: "prop",
  type: "string",
  cost: 1,
  ...over,
});

describe("page sort", () => {
  const cols = [
    col("name"),
    col("n", { type: "int" }),
    col("rel", { kind: "rel", type: undefined }),
  ];
  const rows = [
    { key: "a", name: "pear", n: 10 },
    { key: "b", name: null, n: 9 },
    { key: "c", name: "Apple", n: 100, rel: [{ key: "z" }] },
    { key: "d", name: "fig", n: null, rel: [{ key: "y" }] },
  ];
  const keys = (r: { key: string }[]) => r.map((x) => x.key).join("");

  it("cycles ascending, descending, then the key order", () => {
    const asc = nextSort(null, "name");
    expect(asc).toEqual({ colId: "name", dir: "asc" });
    const desc = nextSort(asc, "name");
    expect(desc).toEqual({ colId: "name", dir: "desc" });
    expect(nextSort(desc, "name")).toBeNull();
    expect(nextSort(desc, "n")).toEqual({ colId: "n", dir: "asc" });
  });

  it("names aria-sort for the sorted column only", () => {
    const s = { colId: "name", dir: "desc" as const };
    expect(ariaSort(s, "name")).toBe("descending");
    expect(ariaSort({ colId: "name", dir: "asc" }, "name")).toBe("ascending");
    expect(ariaSort(s, "n")).toBe("none");
    expect(ariaSort(null, "name")).toBe("none");
  });

  it("orders text without regard to case and puts empty values last in either direction", () => {
    expect(keys(sortRows(rows, cols, { colId: "name", dir: "asc" }))).toBe("cdab");
    expect(keys(sortRows(rows, cols, { colId: "name", dir: "desc" }))).toBe("adcb");
  });

  it("orders numbers by value, not by their text", () => {
    expect(keys(sortRows(rows, cols, { colId: "n", dir: "asc" }))).toBe("bacd");
    expect(keys(sortRows(rows, cols, { colId: "n", dir: "desc" }))).toBe("cabd");
  });

  it("orders a relationship by its keys, and leaves the page alone with no sort or an unknown column", () => {
    expect(keys(sortRows(rows, cols, { colId: "rel", dir: "asc" }))).toBe("dcab");
    expect(sortRows(rows, cols, null)).toBe(rows);
    expect(sortRows(rows, cols, { colId: "gone", dir: "asc" })).toBe(rows);
    expect(keys(rows)).toBe("abcd");
  });
});

describe("hiddenFilters: the declared filters with no header cell", () => {
  const all = [
    col("key", { kind: "key" }),
    col("name"),
    col("workArea"),
    col("addressedBy", { kind: "rel", type: undefined }),
  ];
  const declared = { columns: ["code", "name"], relationships: ["addressedBy"] };
  const filterName = (c: Column) => {
    if (c.kind === "key") return "code";
    if (c.id === "name") return "name";
    if (c.kind === "rel") return "addressedBy";
    return null;
  };

  it("lists the filters of hidden columns, not those with a header cell, and none that are undeclared", () => {
    expect(hiddenFilters(all, ["key", "name"], declared, filterName)).toEqual([
      { name: "addressedBy", label: "addressedBy", rel: true },
    ]);
    expect(hiddenFilters(all, ["key"], declared, filterName).map((e) => e.name)).toEqual([
      "name",
      "addressedBy",
    ]);
  });

  it("adds a declared name no column stands for, by its name", () => {
    expect(
      hiddenFilters(
        all,
        ["key", "name", "addressedBy"],
        { columns: ["code", "name", "region"], relationships: ["addressedBy", "owns"] },
        filterName,
      ),
    ).toEqual([
      { name: "region", label: "region", rel: false },
      { name: "owns", label: "owns", rel: true },
    ]);
  });
});
