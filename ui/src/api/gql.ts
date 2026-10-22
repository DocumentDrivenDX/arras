// SPDX-License-Identifier: MIT OR Apache-2.0
// Query builders for CONTRACT-006's generated per-module schemas. A table selects only its visible
// columns (a request is capped at 50 field selections and depth 6); relationship `target` is
// selected only when the operator opens a relationship.

import type { EntityTypeInfo, ModuleInfo } from "./types";

export const MAX_SELECTIONS = 50;
export const MAX_PAGE = 100;

export const shortName = (qualified: string) => qualified.slice(qualified.lastIndexOf(".") + 1);
export const moduleOf = (qualified: string) =>
  qualified.includes(".") ? qualified.slice(0, qualified.lastIndexOf(".")) : "";
const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

const NAME = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

/**
 * A name as a Weft quoted identifier (`"order"`, an embedded quote doubled), so a statement the console writes
 * reads every legal UMF name exactly, a Weft reserved word among them (as `arras.names.quoted` does). Only for
 * a name the registry admitted, from the meta schema; anything else throws, so typed input is never written in.
 */
export function weftName(name: string): string {
  if (!NAME.test(name))
    throw new Error(`${JSON.stringify(name)} is not a name the registry admits`);
  return `"${name.replaceAll('"', '""')}"`;
}

/** A qualified type name, `module.Type`, as Weft quoted identifiers: `"module"."Type"`. */
export const weftType = (qualified: string) =>
  moduleOf(qualified)
    ? `${weftName(moduleOf(qualified))}.${weftName(shortName(qualified))}`
    : weftName(qualified);

export const listField = (type: string) => `${lowerFirst(shortName(type))}List`;
export const byKeyField = (type: string) => lowerFirst(shortName(type));

export const ATTRIBUTION = ["version", "createdBy", "createdAt", "updatedBy", "updatedAt"] as const;
export type AttrName = (typeof ATTRIBUTION)[number];

export interface Column {
  id: string; // unique
  label: string;
  field: string; // the GraphQL field
  kind: "key" | "prop" | "attr" | "rel";
  type?: string; // declared property type
  cost: number; // field selections it adds
}

const REF_FIELDS = "module type key";
const FRESH = "freshness { backend asOf at consistency }";

/** Backends that can answer reads for a module, the record store first. */
function capsOf(m: ModuleInfo, t: EntityTypeInfo) {
  const order = [m.record, ...m.replicas];
  return order.map((b) => t.capabilities[b]).filter((c): c is NonNullable<typeof c> => !!c);
}

/** The columns a filter may use: declared columns and relationships of the record store (CONTRACT-001). */
export function filterable(
  m: ModuleInfo,
  t: EntityTypeInfo,
): { columns: string[]; relationships: string[] } {
  const cap = capsOf(m, t)[0];
  const columns = cap?.columns ?? [t.key];
  const relationships = cap?.relationships ?? relationshipNames(m, t.name);
  return { columns, relationships };
}

export function relationshipNames(m: ModuleInfo, type: string): string[] {
  const names: string[] = [];
  for (const r of m.relationships) {
    if (r.source.includes(type)) names.push(r.name);
    if (r.target.includes(type) && r.inverse) names.push(r.inverse);
  }
  return [...new Set(names)];
}

/** Relationship fields on a type: the relationships it takes part in, by name or inverse (CONTRACT-006). */
export function relationFields(m: ModuleInfo, type: string) {
  const t = m.entityTypes.find((e) => e.name === type);
  const declared = t ? capsOf(m, t)[0]?.relationships : undefined;
  const allowed = new Set(declared ?? relationshipNames(m, type));
  const out: { field: string; targets: string[]; multiplicity: string; lifecycle: string }[] = [];
  for (const r of m.relationships) {
    if (r.source.includes(type) && allowed.has(r.name))
      out.push({
        field: r.name,
        targets: r.target,
        multiplicity: r.targetMultiplicity,
        lifecycle: r.lifecycle,
      });
    if (r.target.includes(type) && r.inverse && allowed.has(r.inverse))
      out.push({
        field: r.inverse,
        targets: r.source,
        multiplicity: r.sourceMultiplicity,
        lifecycle: r.lifecycle,
      });
  }
  return out;
}

export function columnsFor(m: ModuleInfo, t: EntityTypeInfo): Column[] {
  const cols: Column[] = [{ id: "key", label: t.key, field: "key", kind: "key", cost: 1 }];
  for (const p of t.properties) {
    if (p.name === t.key) continue;
    cols.push({
      id: `p:${p.name}`,
      label: p.name,
      field: p.name,
      kind: "prop",
      type: p.type,
      cost: 1,
    });
  }
  for (const a of ATTRIBUTION) {
    cols.push({
      id: `a:${a}`,
      label: a,
      field: a,
      kind: "attr",
      type: a.endsWith("At") ? "timestamp" : a === "version" ? "integer" : "string",
      cost: 1,
    });
  }
  for (const r of relationFields(m, t.name)) {
    cols.push({
      id: `r:${r.field}`,
      label: r.field,
      field: r.field,
      kind: "rel",
      cost: 1 + REF_FIELDS.split(" ").length,
    });
  }
  return cols;
}

export function defaultColumns(cols: Column[]): string[] {
  const props = cols
    .filter((c) => c.kind === "prop")
    .slice(0, 6)
    .map((c) => c.id);
  return ["key", ...props, "a:updatedBy", "a:updatedAt"];
}

/** Field selections a table query would use: the list, items, `truncated`, freshness and the columns. */
export const BASE_COST = 2 + 2 + 5;
export function selectionCost(cols: Column[]): number {
  return BASE_COST + cols.reduce((n, c) => n + c.cost, 0);
}

export interface ListVars {
  filter?: Record<string, string> | null;
  limit: number;
  /** The next page: entities whose key follows this one, the last key of the page before (CONTRACT-006). */
  afterKey?: string | null;
  consistency: "LATEST" | "BULK";
}

/** The `afterKey` of the page after `items`: its last key, when the limit cut the page; `undefined` at the end. */
export function nextAfterKey(
  page: { items: Record<string, unknown>[]; truncated: boolean } | null | undefined,
): string | undefined {
  const last = page?.items.at(-1);
  return page?.truncated && last && last.key != null ? String(last.key) : undefined;
}

export function buildListQuery(type: string, cols: Column[]): string {
  const fields = cols.map((c) => (c.kind === "rel" ? `${c.field} { ${REF_FIELDS} }` : c.field));
  // the key is always read: the last one is the next page's `afterKey`
  const sel = (fields.includes("key") ? fields : ["key", ...fields]).join(" ");
  const f = listField(type);
  return `query($filter: JSON, $limit: Int, $afterKey: String, $consistency: Consistency) { ${f}(filter: $filter, limit: $limit, afterKey: $afterKey, consistency: $consistency) { items { ${sel} } truncated ${FRESH} } }`;
}

function entitySelection(m: ModuleInfo, t: EntityTypeInfo): string {
  const props = t.properties.filter((p) => p.name !== t.key).map((p) => p.name);
  const rels = relationFields(m, t.name).map((r) => `${r.field} { ${REF_FIELDS} }`);
  return ["key type", ...ATTRIBUTION, ...props, ...rels].join(" ");
}

export function buildEntityQuery(m: ModuleInfo, t: EntityTypeInfo): string {
  return `query($key: String!, $consistency: Consistency) { ${byKeyField(t.name)}(key: $key, consistency: $consistency) { ${entitySelection(m, t)} ${FRESH} } }`;
}

/** Follow one relationship of one entity: `target` is selected here and nowhere else. */
export function buildFollowQuery(m: ModuleInfo, t: EntityTypeInfo, field: string): string {
  const rel = relationFields(m, t.name).find((r) => r.field === field);
  const frags = (rel?.targets ?? [])
    .map((name) => m.entityTypes.find((e) => e.name === name))
    .filter((e): e is EntityTypeInfo => !!e)
    .map((e) => {
      const props = e.properties.filter((p) => p.name !== e.key).map((p) => p.name);
      const rels = relationFields(m, e.name).map((r) => `${r.field} { ${REF_FIELDS} }`);
      return `... on ${shortName(e.name)} { ${[...props, ...rels].join(" ")} }`;
    });
  const target = `target { key type ${ATTRIBUTION.join(" ")} ${frags.join(" ")} }`;
  return `query($key: String!) { ${byKeyField(t.name)}(key: $key) { ${field} { ${REF_FIELDS} ${target} } } }`;
}
