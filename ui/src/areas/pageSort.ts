// SPDX-License-Identifier: MIT OR Apache-2.0
import type { Column } from "../api/gql";
import type { Ref } from "../api/types";
import { isNumeric } from "../lib/format";

/**
 * Sorting a table page on the client. The list read orders by key and has no other order (CONTRACT-006), so this
 * only reorders the rows of the page already read; it is labelled that way wherever it shows.
 */
export type SortDir = "asc" | "desc";
export interface Sort {
  colId: string;
  dir: SortDir;
}

/** The next state for a click on a column's header: ascending, then descending, then the key order again. */
export function nextSort(current: Sort | null, colId: string): Sort | null {
  if (current?.colId !== colId) return { colId, dir: "asc" };
  return current.dir === "asc" ? { colId, dir: "desc" } : null;
}

export const ariaSort = (sort: Sort | null, colId: string): "ascending" | "descending" | "none" => {
  if (sort?.colId !== colId) return "none";
  return sort.dir === "asc" ? "ascending" : "descending";
};

function sortKey(col: Column, raw: unknown): number | string | null {
  if (raw === null || raw === undefined || raw === "") return null;
  if (col.kind === "rel") return ((raw as Ref[]) ?? []).map((r) => r.key).join(", ") || null;
  if (isNumeric(col.type)) return Number(raw);
  if (typeof raw === "boolean") return raw ? 1 : 0;
  return String(raw);
}

function compareKeys(a: number | string, b: number | string): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

/** The rows ordered by a column, empty values last in either direction; a stable copy, the page itself untouched. */
export function sortRows<T extends Record<string, unknown>>(
  rows: T[],
  cols: Column[],
  sort: Sort | null,
): T[] {
  const col = sort ? cols.find((c) => c.id === sort.colId) : undefined;
  if (!(sort && col)) return rows;
  const sign = sort.dir === "asc" ? 1 : -1;
  const keyed = rows.map((row, i) => ({ row, i, k: sortKey(col, row[col.field]) }));
  keyed.sort((x, y) => {
    if (x.k === null || y.k === null) {
      if (x.k === y.k) return x.i - y.i;
      return x.k === null ? 1 : -1;
    }
    return compareKeys(x.k, y.k) * sign || x.i - y.i;
  });
  return keyed.map((e) => e.row);
}
