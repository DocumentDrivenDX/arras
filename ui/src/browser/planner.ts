// SPDX-License-Identifier: MIT OR Apache-2.0
// The request planner (SD-011, Node page requests): one query cannot hold a page, its neighbours'
// labels and a picture inside CONTRACT-006's limits (50 selections, 20 targets here, 1,000 entities),
// so a node page is read in steps. The page request reads the entity's own properties, attribution,
// freshness and each relationship's keys, never a `target`. Labels are separate requests of at most
// 20 targets and 50 selections, one group of requests per module endpoint.
import { byKeyField, MAX_SELECTIONS } from "../api/gql";
import type { Ref, TypeView } from "../api/types";
import { LABEL_TARGETS, packLabels, refId, type Wanted } from "../lib/relLabels";
import { titleProperties } from "../lib/template";
import type { TypeEntry } from "./meta";

/**
 * The most label targets in one request. A target costs a by-key field and one selection per
 * placeholder of its type's title (the key when there is none), so a request holds
 * `min(MAX_TARGETS, floor(50 / (1 + placeholders)))` targets: `packLabels` (lib/relLabels.ts) packs
 * targets by their summed cost against the 50 selections, which is that count for one type.
 */
export const MAX_TARGETS = LABEL_TARGETS;
export const MAX_KEYS = 100;
export const PAGE_LABELS = 20;
const ATTRIBUTION_SELECTION = "version createdBy createdAt updatedBy updatedAt";
const FRESH = "freshness { backend asOf at consistency }";
const REF = "module type key";

// -- the page request ---------------------------------------------------------------------------

interface Item {
  text: string;
  cost: number;
}

/** The selections a page needs: each property once, each relationship field with its keys. */
function itemsOf(entry: TypeEntry): Item[] {
  const props = entry.view.fields.map((f): Item => ({ text: f.property, cost: 1 }));
  const rels = entry.view.relationships.map(
    (r): Item => ({ text: `${r.field} { ${REF} }`, cost: 1 + REF.split(" ").length }),
  );
  return [...props, ...rels];
}

const ROOT_COST = 1; // the by-key field
const FIRST_FIXED = 2 + 5 + 5; // key, type, attribution, freshness
const NEXT_FIXED = 1 + 5; // key, freshness

/** The page as one query, or several when its selections would pass the limit: properties, then relationships. */
export function pageQueries(entry: TypeEntry): string[] {
  const chunks: string[][] = [[]];
  let cost = ROOT_COST + FIRST_FIXED;
  for (const item of itemsOf(entry)) {
    if (cost + item.cost > MAX_SELECTIONS) {
      chunks.push([]);
      cost = ROOT_COST + NEXT_FIXED;
    }
    chunks[chunks.length - 1]?.push(item.text);
    cost += item.cost;
  }
  const field = byKeyField(entry.type.name);
  return chunks.map((sel, i) => {
    const head = i === 0 ? `key type ${ATTRIBUTION_SELECTION}` : "key";
    return `query($key: String!) { ${field}(key: $key) { ${head} ${sel.join(" ")} ${FRESH} } }`;
  });
}

// -- relationship groups ----------------------------------------------------------------------

export interface GroupPlan {
  field: string;
  label: string;
  hideWhenEmpty: boolean;
  order: number;
  refs: Ref[];
}

const isRef = (v: unknown): v is Ref =>
  !!v && typeof v === "object" && "key" in v && "type" in v && "module" in v;

/** The groups of a page: one per relationship field the view names, with the keys the page read. */
export function groupsOf(view: TypeView, entity: Record<string, unknown>): GroupPlan[] {
  return view.relationships.map((r) => {
    const v = entity[r.field];
    return {
      field: r.field,
      label: r.label,
      hideWhenEmpty: r.hideWhenEmpty,
      order: r.order,
      refs: Array.isArray(v) ? v.filter(isRef) : [],
    };
  });
}

export { refId };

/** The picture's neighbours: one key per group in turn (the order the keys came), at most `cap`. */
export function pictureRefs(groups: GroupPlan[], cap: number): Ref[] {
  const out: Ref[] = [];
  const seen = new Set<string>();
  for (let i = 0; out.length < cap; i++) {
    let any = false;
    for (const g of groups) {
      const r = g.refs[i];
      if (!r) continue;
      any = true;
      if (out.length < cap && !seen.has(refId(r))) {
        seen.add(refId(r));
        out.push(r);
      }
    }
    if (!any) break;
  }
  return out;
}

/** The first `n` keys of each group, plus the picture's: the labels a page asks for, each once. */
export function wantedRefs(groups: GroupPlan[], shown: Record<string, number>, cap: number): Ref[] {
  const out = new Map<string, Ref>();
  for (const g of groups)
    for (const r of g.refs.slice(0, shown[g.field] ?? PAGE_LABELS)) out.set(refId(r), r);
  for (const r of pictureRefs(groups, cap)) out.set(refId(r), r);
  return [...out.values()];
}

// -- label requests ---------------------------------------------------------------------------

export interface Target {
  id: string;
  module: string;
  /** The qualified type name, `catalog.Solution`. */
  type: string;
  key: string;
}

export const targetOf = (r: Ref): Target => ({
  id: refId(r),
  module: r.module,
  type: r.type,
  key: r.key,
});

export interface LabelPlan {
  module: string;
  targets: Target[];
  query: string;
  variables: Record<string, string>;
}

/** The properties a title reads, as selected for a label (the key is always selected). */
export function titleSelection(entry: TypeEntry): string[] {
  return titleProperties(
    entry.view.title,
    entry.type.properties.map((p) => p.name),
  );
}

/**
 * Label requests for `targets`: grouped by module endpoint in order, each chunk at most 20 targets
 * and 50 selections (`packLabels`). A target whose type the viewer cannot describe has no plan: it
 * is not available.
 */
export function planLabels(
  targets: Target[],
  entryOf: (qualified: string) => TypeEntry | undefined,
): LabelPlan[] {
  const byModule = new Map<string, Wanted<Target>[]>();
  for (const target of targets) {
    const entry = entryOf(target.type);
    if (!entry) continue;
    const props = titleSelection(entry);
    const wanted = byModule.get(target.module) ?? [];
    wanted.push({ target, select: props.length ? props : ["key"] });
    byModule.set(target.module, wanted);
  }
  return [...byModule].flatMap(([module, wanted]) =>
    packLabels(wanted).map((c) => ({ module, ...c })),
  );
}

export type LabelState = { state: "ok"; title: string } | { state: "na" } | { state: "retry" };

const GONE = new Set(["REFUSED", "NOT_FOUND"]);

export interface LabelAnswer {
  data: Record<string, Record<string, unknown> | null> | null;
  errors: { code?: string; path?: (string | number)[] }[];
}

/**
 * What an answer says about each target: a row is its title; a null with no error, or a refusal, is
 * "not available" (the same for absent and unreadable); any other error (cost, a backend down) is a
 * retry, never "not available".
 */
export function readLabels(
  plan: LabelPlan,
  answer: LabelAnswer,
  titleFor: (t: Target, row: Record<string, unknown>) => string,
): Record<string, LabelState> {
  const out: Record<string, LabelState> = {};
  plan.targets.forEach((t, i) => {
    const alias = `t${i}`;
    const row = answer.data?.[alias];
    const err = answer.errors.find((e) => e.path?.[0] === alias);
    if (row) out[t.id] = { state: "ok", title: titleFor(t, row) };
    else if (err && !GONE.has(err.code ?? "")) out[t.id] = { state: "retry" };
    else if (!err && !answer.data) out[t.id] = { state: "retry" };
    else out[t.id] = { state: "na" };
  });
  return out;
}

export const allAs = (plan: LabelPlan, s: LabelState): Record<string, LabelState> =>
  Object.fromEntries(plan.targets.map((t) => [t.id, s]));
