// SPDX-License-Identifier: MIT OR Apache-2.0
// The graph of a module as the console reads it: entities as nodes, relationships as edges.
// Nodes come from one `<type>List` read per type (key, a label property and each relationship's
// `{ module type key }`); nothing here is written back. Layout is deterministic: one lane per type,
// nodes ordered by a few barycentre sweeps so connected entities sit near each other.

import { listField, MAX_SELECTIONS, relationFields, shortName } from "../api/gql";
import type { EntityTypeInfo, Freshness, ModuleInfo, RelationshipInfo } from "../api/types";

export const GRAPH_PAGE = 100; // entities read per type
export const GRAPH_CAP = 150; // nodes drawn in all

export interface GNode {
  id: string; // `${type}:${key}`
  type: string; // qualified, for example catalog.Solution
  module: string;
  key: string;
  label: string;
  /** An entity of another module, or one this read did not load: its key only. */
  stub: boolean;
}
export interface GEdge {
  id: string;
  rel: string; // the declared relationship's name
  from: string; // node id (source)
  to: string; // node id (target)
}
export interface TypeStat {
  type: string;
  loaded: number;
  shown: number;
  /** More entities exist than were read (the list had a next page). */
  more: boolean;
  error?: unknown;
}
export interface ModuleGraph {
  nodes: GNode[];
  edges: GEdge[];
  types: TypeStat[];
  /** Entities of this module read, before the cap. */
  loaded: number;
  shown: number;
  more: boolean;
  /** Links dropped because an end was not read or fell outside the cap. */
  hiddenEdges: number;
  freshness: Freshness | null;
  pending: number;
}

export const nodeId = (type: string, key: string) => `${type}:${key}`;

const LABELS = ["name", "title", "label", "summary", "description"];
/** The property used to name a node: a conventional one, else the first string that is not the key. */
export function labelProp(t: EntityTypeInfo): string | undefined {
  for (const l of LABELS) if (t.properties.some((p) => p.name === l && p.name !== t.key)) return l;
  return t.properties.find((p) => p.type === "string" && p.name !== t.key)?.name;
}

interface RelField {
  field: string;
  rel: RelationshipInfo;
  /** This type is the relationship's source (the field is the relationship's own name). */
  forward: boolean;
}
export function relFieldsOf(m: ModuleInfo, type: string): RelField[] {
  const fields = new Set(relationFields(m, type).map((r) => r.field));
  const out: RelField[] = [];
  for (const rel of m.relationships) {
    if (rel.source.includes(type) && fields.has(rel.name))
      out.push({ field: rel.name, rel, forward: true });
    if (rel.target.includes(type) && rel.inverse && fields.has(rel.inverse))
      out.push({ field: rel.inverse, rel, forward: false });
  }
  return out;
}

export function buildGraphQuery(m: ModuleInfo, t: EntityTypeInfo): string {
  const label = labelProp(t);
  const base = 1 + 1 + (label ? 1 : 0) + 3 + 5 + 1; // list, items, key, label, paging, freshness
  const room = Math.max(0, Math.floor((MAX_SELECTIONS - base) / 4)); // each relationship costs 4
  const rels = relFieldsOf(m, t.name).slice(0, room);
  const sel = ["key", label, ...rels.map((r) => `${r.field} { module type key }`)]
    .filter(Boolean)
    .join(" ");
  return `query($limit: Int, $consistency: Consistency) { ${listField(t.name)}(limit: $limit, consistency: $consistency) { items { ${sel} } truncated freshness { backend asOf at consistency } } }`;
}

export interface TypeRead {
  items: Record<string, unknown>[];
  /** The limit cut the read: there are more entities of the type than were loaded. */
  truncated: boolean;
  freshness: Freshness | null;
}
interface RefLike {
  module: string;
  type: string;
  key: string;
}

interface TypeReadResult {
  type: EntityTypeInfo;
  read?: TypeRead | null;
  error?: unknown;
  pending?: boolean;
}

interface Collected {
  nodes: Map<string, GNode>;
  edges: Map<string, GEdge>;
  stubs: Map<string, GNode>;
  types: TypeStat[];
  freshness: Freshness | null;
  pending: number;
}

function addEdges(
  c: Collected,
  m: ModuleInfo,
  id: string,
  raw: Record<string, unknown>,
  fields: RelField[],
) {
  for (const f of fields) {
    const refs = raw[f.field];
    if (!Array.isArray(refs)) continue;
    for (const r of refs as RefLike[]) {
      const other = nodeId(r.type, r.key);
      const [from, to] = f.forward ? [id, other] : [other, id];
      const eid = `${f.rel.name}|${from}|${to}`;
      if (!c.edges.has(eid)) c.edges.set(eid, { id: eid, rel: f.rel.name, from, to });
      if (r.module !== m.name && !c.stubs.has(other))
        c.stubs.set(other, {
          id: other,
          type: r.type,
          module: r.module,
          key: r.key,
          label: r.key,
          stub: true,
        });
    }
  }
}

function nodeLabel(raw: Record<string, unknown>, label: string | undefined, key: string): string {
  const text = label ? raw[label] : null;
  return text == null || text === "" ? key : String(text);
}

function collectReads(m: ModuleInfo, reads: TypeReadResult[]): Collected {
  const c: Collected = {
    nodes: new Map(),
    edges: new Map(),
    stubs: new Map(),
    types: [],
    freshness: null,
    pending: 0,
  };
  for (const { type: t, read, error, pending: isPending } of reads) {
    if (isPending) c.pending++;
    const label = labelProp(t);
    const items = read?.items ?? [];
    c.types.push({ type: t.name, loaded: items.length, shown: 0, more: !!read?.truncated, error });
    if (read && !c.freshness) c.freshness = read.freshness;
    const fields = relFieldsOf(m, t.name);
    for (const raw of items) {
      const key = String(raw.key);
      const id = nodeId(t.name, key);
      c.nodes.set(id, {
        id,
        type: t.name,
        module: m.name,
        key,
        label: nodeLabel(raw, label, key),
        stub: false,
      });
      addEdges(c, m, id, raw, fields);
    }
  }
  return c;
}

/** The cap: connected entities first, spread fairly over the types. */
function nodesByType(nodes: Map<string, GNode>, edges: Map<string, GEdge>): Map<string, GNode[]> {
  const degree = new Map<string, number>();
  for (const e of edges.values()) {
    degree.set(e.from, (degree.get(e.from) ?? 0) + 1);
    degree.set(e.to, (degree.get(e.to) ?? 0) + 1);
  }
  const byType = new Map<string, GNode[]>();
  for (const n of nodes.values()) byType.set(n.type, [...(byType.get(n.type) ?? []), n]);
  for (const list of byType.values())
    list.sort(
      (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.key.localeCompare(b.key),
    );
  return byType;
}

function quotas(byType: Map<string, GNode[]>, cap: number, loaded: number): Map<string, number> {
  const quota = new Map<string, number>();
  let left = Math.min(cap, loaded);
  const open = new Set(byType.keys());
  while (left > 0 && open.size > 0) {
    const share = Math.max(1, Math.floor(left / open.size));
    for (const t of [...open]) {
      const have = quota.get(t) ?? 0;
      const size = byType.get(t)?.length ?? 0;
      const give = Math.min(share, size - have, left);
      quota.set(t, have + give);
      left -= give;
      if (have + give >= size) open.delete(t);
      if (left === 0) break;
    }
  }
  return quota;
}

/** Fold the per-type reads into one graph, capping the nodes drawn at `cap`. */
export function assembleGraph(
  m: ModuleInfo,
  reads: TypeReadResult[],
  cap = GRAPH_CAP,
): ModuleGraph {
  const { nodes, edges, stubs, types, freshness, pending } = collectReads(m, reads);
  const byType = nodesByType(nodes, edges);
  const loaded = nodes.size;
  const quota = quotas(byType, cap, loaded);
  const kept = new Map<string, GNode>();
  for (const [t, list] of byType)
    for (const n of list.slice(0, quota.get(t) ?? 0)) kept.set(n.id, n);
  for (const s of stubs.values()) kept.set(s.id, s);

  const keptEdges = [...edges.values()].filter((e) => kept.has(e.from) && kept.has(e.to));
  const hiddenEdges = edges.size - keptEdges.length;
  for (const s of types)
    s.shown = [...kept.values()].filter((n) => n.type === s.type && !n.stub).length;
  const ordered = [...kept.values()].sort(
    (a, b) => a.type.localeCompare(b.type) || a.key.localeCompare(b.key),
  );
  return {
    nodes: ordered,
    edges: keptEdges,
    types,
    loaded,
    shown: [...kept.values()].filter((n) => !n.stub).length,
    more: types.some((s) => s.more),
    hiddenEdges,
    freshness,
    pending,
  };
}

// -- layout ----------------------------------------------------------------------------------

export interface LaneSpec {
  id: string; // a qualified type name
  title: string;
  foreign: boolean;
  count?: number;
}
export interface LayoutOpts {
  nodeW: number;
  rowH: number;
  width: number; // available width; lanes spread over it
  headerH: number;
  padX: number;
  maxGap: number;
}
export interface Placed {
  x: number;
  y: number;
  lane: number;
  order: number;
}
export interface Layout {
  pos: Map<string, Placed>;
  laneX: number[];
  width: number;
  height: number;
  order: string[][]; // node ids per lane, top to bottom
}

type LaneItem = { id: string; label: string };

function laneLists(nodes: { id: string; type: string; label: string }[], lanes: LaneSpec[]) {
  const laneIndex = new Map(lanes.map((l, i) => [l.id, i]));
  const lists: LaneItem[][] = lanes.map(() => []);
  for (const n of nodes) {
    const i = laneIndex.get(n.type);
    if (i !== undefined) lists[i]?.push(n);
  }
  for (const l of lists)
    l.sort((a, b) => a.label.localeCompare(b.label) || a.id.localeCompare(b.id));
  return lists;
}

function neighbours(edges: { from: string; to: string }[], laneOf: Map<string, number>) {
  const nbrs = new Map<string, string[]>();
  for (const e of edges) {
    if (!laneOf.has(e.from) || !laneOf.has(e.to)) continue;
    nbrs.set(e.from, [...(nbrs.get(e.from) ?? []), e.to]);
    nbrs.set(e.to, [...(nbrs.get(e.to) ?? []), e.from]);
  }
  return nbrs;
}

function rankLane(l: LaneItem[], rank: Map<string, number>) {
  l.forEach((n, i) => {
    rank.set(n.id, l.length > 1 ? i / (l.length - 1) : 0.5);
  });
}

function sweepLane(
  l: LaneItem[],
  li: number,
  nbrs: Map<string, string[]>,
  laneOf: Map<string, number>,
  rank: Map<string, number>,
) {
  const score = new Map<string, number>();
  for (const n of l) {
    const others = (nbrs.get(n.id) ?? []).filter((x) => laneOf.get(x) !== li);
    score.set(
      n.id,
      others.length ? others.reduce((s, x) => s + (rank.get(x) ?? 0), 0) / others.length : Infinity,
    );
  }
  const base = new Map(l.map((n, i) => [n.id, i]));
  l.sort((a, b) => {
    const sa = score.get(a.id) ?? Number.POSITIVE_INFINITY;
    const sb = score.get(b.id) ?? Number.POSITIVE_INFINITY;
    if (sa === sb) return (base.get(a.id) ?? 0) - (base.get(b.id) ?? 0);
    return sa - sb; // Infinity (no neighbours) sinks
  });
  rankLane(l, rank);
}

function orderLanes(lists: LaneItem[][], edges: { from: string; to: string }[]) {
  const laneOf = new Map<string, number>();
  lists.forEach((l, i) => {
    for (const n of l) laneOf.set(n.id, i);
  });
  const nbrs = neighbours(edges, laneOf);
  const rank = new Map<string, number>();
  for (const l of lists) rankLane(l, rank);
  for (let sweep = 0; sweep < 4; sweep++) {
    const idx =
      sweep % 2 === 0 ? lists.map((_, i) => i) : lists.map((_, i) => lists.length - 1 - i);
    for (const li of idx) {
      const l = lists[li];
      if (l) sweepLane(l, li, nbrs, laneOf, rank);
    }
  }
}

/** Lanes in order of `lanes`; nodes by barycentre sweeps over their neighbours in other lanes. */
export function layoutLanes(
  nodes: { id: string; type: string; label: string }[],
  edges: { from: string; to: string }[],
  lanes: LaneSpec[],
  o: LayoutOpts,
): Layout {
  const lists = laneLists(nodes, lanes);
  orderLanes(lists, edges);
  const n = lanes.length;
  const inner = Math.max(o.nodeW, o.width - 2 * o.padX);
  const gap = n > 1 ? Math.min(o.maxGap, Math.max(40, (inner - n * o.nodeW) / (n - 1))) : 0;
  const total = n * o.nodeW + (n - 1) * gap;
  const left = o.padX + Math.max(0, (inner - total) / 2);
  const laneX = lanes.map((_, i) => left + i * (o.nodeW + gap));
  const pos = new Map<string, Placed>();
  const order: string[][] = [];
  let rows = 0;
  lists.forEach((l, li) => {
    order.push(l.map((x) => x.id));
    rows = Math.max(rows, l.length);
    l.forEach((x, i) => {
      pos.set(x.id, { x: laneX[li] ?? 0, y: o.headerH + i * o.rowH, lane: li, order: i });
    });
  });
  return {
    pos,
    laneX,
    width: Math.max(o.width, left + total + o.padX),
    height: o.headerH + Math.max(rows, 1) * o.rowH + 12,
    order,
  };
}

/** The ids reached from `id` by one edge, and the edges between. */
export function neighbourhood(id: string, edges: { id: string; from: string; to: string }[]) {
  const nodes = new Set([id]);
  const es = new Set<string>();
  for (const e of edges) {
    if (e.from === id || e.to === id) {
      nodes.add(e.from);
      nodes.add(e.to);
      es.add(e.id);
    }
  }
  return { nodes, edges: es };
}

export const laneTitle = (type: string) => shortName(type);
