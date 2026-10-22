// SPDX-License-Identifier: MIT OR Apache-2.0
// Readable names for the entities a relationship points at. A name is the resolved view's `title`
// template (CONTRACT-010) evaluated over a by-key read of the template's placeholders, aliased into
// requests of at most 20 targets and 50 selections (CONTRACT-006); never with `target`, which a
// follow selects alone. The browser plans its labels through the same `packLabels` (browser/planner.ts), so an entity has one name.
import { byKeyField, MAX_SELECTIONS, shortName } from "../api/gql";
import type { EntityTypeInfo, ModuleInfo, Ref } from "../api/types";
import { titleOf, titleProperties } from "./template";

/**
 * The most label targets in one request. A target costs a by-key field and one selection per
 * placeholder of its type's title (the key when there is none), so a request holds
 * `min(LABEL_TARGETS, floor(50 / (1 + placeholders)))` targets, packed by their summed cost.
 */
export const LABEL_TARGETS = 20;
/** The most labels one panel reads; the chips past it show their keys. */
export const MAX_LABELS = 60;

/** The properties a label read selects for this type: its title's placeholders, else the key. */
export function titleSelection(t: EntityTypeInfo): string[] | undefined {
  if (!t.view) return undefined;
  const props = titleProperties(
    t.view.title,
    t.properties.map((p) => p.name),
  );
  return props.length ? props : ["key"];
}

export const refId = (r: { type: string; key: string }) => `${r.type}:${r.key}`;

export interface LabelRequest {
  query: string;
  variables: Record<string, string>;
  /** The refs asked for, by alias `t0`, `t1`, ... */
  refs: Ref[];
  /** The title template of each ref's type. */
  titles: string[];
}

/** One label wanted: the target, and the properties its title reads (the key when there are none). */
export interface Wanted<T extends { type: string; key: string }> {
  target: T;
  select: string[];
}

/** One aliased request for the targets of a chunk: `t0`, `t1`, ... by their keys `$k0`, `$k1`, .... */
export interface Chunk<T> {
  query: string;
  variables: Record<string, string>;
  targets: T[];
}

/**
 * The one label planner: `wanted` in order, split where a request would pass `LABEL_TARGETS` targets
 * or 50 selections, each chunk an aliased by-key read of one module's endpoint (CONTRACT-006). Both
 * the console's chips and the browser's node page plan their labels through it.
 */
export function packLabels<T extends { type: string; key: string }>(
  wanted: Wanted<T>[],
): Chunk<T>[] {
  const groups: Wanted<T>[][] = [];
  let cost = 0;
  for (const w of wanted) {
    const c = 1 + w.select.length;
    const last = groups[groups.length - 1];
    if (last && last.length < LABEL_TARGETS && cost + c <= MAX_SELECTIONS) {
      last.push(w);
      cost += c;
    } else {
      groups.push([w]);
      cost = c;
    }
  }
  return groups.map((chunk) => {
    const variables: Record<string, string> = {};
    const sel = chunk.map(({ target, select }, n) => {
      variables[`k${n}`] = target.key;
      return `t${n}: ${byKeyField(target.type)}(key: $k${n}) { ${select.join(" ")} }`;
    });
    const decl = chunk.map((_, n) => `$k${n}: String!`).join(", ");
    return {
      query: `query(${decl}) { ${sel.join(" ")} }`,
      variables,
      targets: chunk.map((c) => c.target),
    };
  });
}

interface Wants extends Wanted<Ref> {
  title: string;
}

function wantedOf(m: ModuleInfo, refs: Ref[]): Wants[] {
  const seen = new Set<string>();
  const wanted: Wants[] = [];
  for (const r of refs) {
    if (r.module !== m.name || seen.has(refId(r)) || wanted.length >= MAX_LABELS) continue;
    seen.add(refId(r));
    const t = m.entityTypes.find((x) => shortName(x.name) === shortName(r.type));
    const select = t && titleSelection(t);
    if (t?.view && select) wanted.push({ target: r, title: t.view.title, select });
  }
  return wanted;
}

/** Requests for the labels of `refs` of this module whose type has a resolved view. */
export function planRefLabels(m: ModuleInfo, refs: Ref[]): LabelRequest[] {
  const wanted = wantedOf(m, refs);
  const titles = new Map(wanted.map((w) => [refId(w.target), w.title]));
  return packLabels(wanted).map((chunk) => ({
    query: chunk.query,
    variables: chunk.variables,
    refs: chunk.targets,
    titles: chunk.targets.map((r) => titles.get(refId(r)) ?? ""),
  }));
}

/**
 * The labels an answer holds, by `type:key`: each the title template over the row, as the browser
 * names the entity. A target that is absent or unreadable, or whose title is only its key, has none.
 */
export function readRefLabels(
  req: LabelRequest,
  data: Record<string, Record<string, unknown> | null> | null | undefined,
): Record<string, string> {
  const out: Record<string, string> = {};
  req.refs.forEach((r, n) => {
    const row = data?.[`t${n}`];
    if (!row) return;
    const title = titleOf(req.titles[n] ?? "", row, r.key);
    if (title !== r.key) out[refId(r)] = title;
  });
  return out;
}
