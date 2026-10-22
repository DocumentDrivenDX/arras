// SPDX-License-Identifier: MIT OR Apache-2.0
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d+Z$/, "Z")
    .replace(/Z$/, " UTC");
}

export function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

const NUMERIC = new Set(["integer", "decimal"]);
export const isNumeric = (type?: string) => !!type && NUMERIC.has(type);

/**
 * Stable React keys for an ordered list with no ids: the item's text plus how many earlier items
 * share that text, so reordering-free lists get unique keys that do not depend on the raw index.
 */
export function keyed<T>(
  items: readonly T[],
  text: (item: T) => string,
): { key: string; item: T }[] {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const t = text(item);
    const n = seen.get(t) ?? 0;
    seen.set(t, n + 1);
    return { key: `${t}#${n}`, item };
  });
}
