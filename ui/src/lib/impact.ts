// SPDX-License-Identifier: MIT OR Apache-2.0
// What a validated change would do to the graph, drawn over the neighbourhood it touches.
// Pure functions: the effects come from `validate` (CONTRACT-009), the neighbourhood from the
// graph the console already read, "before" values from by-key reads. Nothing here writes.

import { shortName } from "../api/gql";
import type { ActionInfo, Effect, EffectDecl, EntityRef, ModuleInfo, Receipt } from "../api/types";
import type { EntityData } from "../areas/entity";
import type { EdgeStatus, NodeStatus, VEdge, VNode } from "../areas/GraphView";
import { fmtValue } from "./format";
import { type LaneSpec, labelProp, type ModuleGraph, nodeId } from "./graph";
import { refAccepts } from "./inputs";

export interface PropChange {
  prop: string;
  before: string | null; // null: not known
  after: string;
}
export interface NodeChange {
  id: string;
  type: string;
  key: string;
  label: string;
  status: NodeStatus;
  props: PropChange[];
}
export interface ImpactModel {
  nodes: VNode[];
  edges: VEdge[];
  lanes: LaneSpec[];
  changes: NodeChange[];
  counts: { created: number; updated: number; deleted: number; linked: number; unlinked: number };
  /** Links of a deleted entity that go with it. */
  severed: number;
  /** Direct neighbours left out to keep the picture small. */
  omitted: number;
}

const qualify = (m: ModuleInfo, type: string) => (type.includes(".") ? type : `${m.name}.${type}`);
const idOf = (m: ModuleInfo, r: EntityRef) => nodeId(qualify(m, r.type), r.key);
const show = (v: unknown) =>
  typeof v === "string" ? JSON.stringify(v) : v === null || v === undefined ? "—" : fmtValue(v);

const NEIGHBOUR_CAP = 16;

interface LinkEffect {
  id: string;
  rel: string;
  from: string;
  to: string;
  kind: "link" | "unlink";
}

interface ImpactState {
  m: ModuleInfo;
  gnodes: Map<string, VNodeSource>;
  before: Map<string, EntityData | null | undefined>;
  status: Map<string, NodeStatus>;
  meta: Map<string, { type: string; key: string; label?: string }>;
  changes: Map<string, NodeChange>;
  counts: ImpactModel["counts"];
  linkEffects: LinkEffect[];
}

type VNodeSource = ModuleGraph["nodes"][number];

function touch(st: ImpactState, r: EntityRef) {
  const id = idOf(st.m, r);
  if (!st.meta.has(id)) st.meta.set(id, { type: qualify(st.m, r.type), key: r.key });
  return id;
}

function applyCreate(st: ImpactState, e: Extract<Effect, { kind: "create" }>) {
  const { m } = st;
  const id = touch(st, e.ref);
  st.status.set(id, "created");
  st.counts.created++;
  const t = m.entityTypes.find((x) => x.name === qualify(m, e.ref.type));
  const lp = t ? labelProp(t) : undefined;
  const lv = lp ? e.properties[lp] : undefined;
  const label = typeof lv === "string" && lv ? lv : e.ref.key || "(new)";
  const created = st.meta.get(id);
  if (created) created.label = label;
  st.changes.set(id, {
    id,
    type: qualify(m, e.ref.type),
    key: e.ref.key,
    label,
    status: "created",
    props: Object.entries(e.properties).map(([prop, v]) => ({
      prop,
      before: null,
      after: show(v),
    })),
  });
}

function applyUpdate(st: ImpactState, e: Extract<Effect, { kind: "update" }>) {
  const id = touch(st, e.ref);
  if (st.status.get(id) !== "created") st.status.set(id, "updated");
  st.counts.updated++;
  const was = st.before.get(id)?.props;
  const beforeOf = (prop: string) => (was && prop in was ? show(was[prop]) : null);
  const props: PropChange[] = [
    ...Object.entries(e.set).map(([prop, v]) => ({ prop, before: beforeOf(prop), after: show(v) })),
    ...e.unset.map((prop) => ({ prop, before: beforeOf(prop), after: "(unset)" })),
  ];
  const prior = st.changes.get(id);
  st.changes.set(id, {
    id,
    type: qualify(st.m, e.ref.type),
    key: e.ref.key,
    label: st.gnodes.get(id)?.label ?? e.ref.key,
    status: prior?.status ?? "updated",
    props: [...(prior?.props ?? []), ...props],
  });
}

function applyDelete(st: ImpactState, e: Extract<Effect, { kind: "delete" }>) {
  const id = touch(st, e.ref);
  st.status.set(id, "deleted");
  st.counts.deleted++;
  st.changes.set(id, {
    id,
    type: qualify(st.m, e.ref.type),
    key: e.ref.key,
    label: st.gnodes.get(id)?.label ?? e.ref.key,
    status: "deleted",
    props: [],
  });
}

function applyLink(st: ImpactState, e: Extract<Effect, { kind: "link" | "unlink" }>) {
  const from = touch(st, e.source);
  const to = touch(st, e.target);
  if (e.kind === "link") st.counts.linked++;
  else st.counts.unlinked++;
  st.linkEffects.push({
    id: `${e.relationship}|${from}|${to}`,
    rel: e.relationship,
    from,
    to,
    kind: e.kind,
  });
}

function applyEffect(st: ImpactState, e: Effect) {
  if (e.kind === "create") applyCreate(st, e);
  else if (e.kind === "update") applyUpdate(st, e);
  else if (e.kind === "delete") applyDelete(st, e);
  else applyLink(st, e);
}

/** Direct neighbours from the graph already read, up to the cap; the rest are counted. */
function pickNeighbours(gedges: { from: string; to: string }[], affected: Set<string>) {
  const neighbours = new Set<string>();
  let omitted = 0;
  for (const ed of gedges) {
    const a = affected.has(ed.from);
    const b = affected.has(ed.to);
    if (a === b) continue;
    const other = a ? ed.to : ed.from;
    if (neighbours.has(other)) continue;
    if (neighbours.size >= NEIGHBOUR_CAP) omitted++;
    else neighbours.add(other);
  }
  return { neighbours, omitted };
}

function buildEdges(
  gedges: ModuleGraph["edges"],
  shown: Set<string>,
  affected: Set<string>,
  status: Map<string, NodeStatus>,
  linkEffects: LinkEffect[],
) {
  const edges = new Map<string, VEdge>();
  let severed = 0;
  for (const ed of gedges) {
    if (!shown.has(ed.from) || !shown.has(ed.to)) continue;
    if (!affected.has(ed.from) && !affected.has(ed.to)) continue;
    const removed = status.get(ed.from) === "deleted" || status.get(ed.to) === "deleted";
    if (removed) severed++;
    edges.set(ed.id, { ...ed, status: removed ? "removed" : undefined });
  }
  for (const l of linkEffects) {
    const st: EdgeStatus = l.kind === "link" ? "added" : "removed";
    edges.set(l.id, { id: l.id, rel: l.rel, from: l.from, to: l.to, status: st });
  }
  return { edges, severed };
}

function buildNodes(st: ImpactState, shown: Set<string>, affected: Set<string>): VNode[] {
  return [...shown].flatMap((id): VNode[] => {
    const g = st.gnodes.get(id);
    const mt = st.meta.get(id);
    const type = g?.type ?? mt?.type;
    const key = g?.key ?? mt?.key;
    if (type === undefined || key === undefined) return [];
    const status = st.status.get(id);
    const unknown = !g && status !== "created";
    return [
      {
        id,
        type,
        key,
        label: status === "created" ? (mt?.label ?? key) : (g?.label ?? key),
        stub: g?.stub || unknown,
        status: status ?? (affected.has(id) ? "touched" : undefined),
      },
    ];
  });
}

function buildLanes(m: ModuleInfo, nodes: VNode[]): LaneSpec[] {
  const present = new Set(nodes.map((n) => n.type));
  return [
    ...m.entityTypes
      .filter((t) => present.has(t.name))
      .map((t) => ({ id: t.name, title: shortName(t.name), foreign: false })),
    ...[...present]
      .filter((t) => !m.entityTypes.some((x) => x.name === t))
      .map((t) => ({ id: t, title: shortName(t), foreign: true })),
  ];
}

export function buildImpact(
  m: ModuleInfo,
  graph: ModuleGraph | null,
  effects: Effect[],
  before: Map<string, EntityData | null | undefined>,
  receipt?: Receipt | null,
): ImpactModel {
  const gedges = graph?.edges ?? [];
  const st: ImpactState = {
    m,
    gnodes: new Map((graph?.nodes ?? []).map((n) => [n.id, n])),
    before,
    status: new Map(),
    meta: new Map(),
    changes: new Map(),
    counts: { created: 0, updated: 0, deleted: 0, linked: 0, unlinked: 0 },
    linkEffects: [],
  };
  for (const e of effects) applyEffect(st, e);

  const affected = new Set(st.meta.keys());
  const { neighbours, omitted } = pickNeighbours(gedges, affected);
  const shown = new Set([...affected, ...neighbours]);
  const { edges, severed } = buildEdges(gedges, shown, affected, st.status, st.linkEffects);
  const nodes = buildNodes(st, shown, affected);
  // The receipt's versions are not needed to draw; it is accepted so applied views can pass it.
  void receipt;
  return {
    nodes,
    edges: [...edges.values()],
    lanes: buildLanes(m, nodes),
    changes: [...st.changes.values()],
    counts: st.counts,
    severed,
    omitted,
  };
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function typesWith(model: ImpactModel, status: NodeStatus): string {
  const by = new Map<string, number>();
  for (const n of model.nodes) if (n.status === status) by.set(n.type, (by.get(n.type) ?? 0) + 1);
  return [...by].map(([t, n]) => plural(n, shortName(t))).join(" and ");
}

/** The change in plain words, present tense for a preview and past for an applied change. */
export function summarize(model: ImpactModel, applied: boolean): string {
  const { created, updated, deleted, linked, unlinked } = model.counts;
  const types = (status: NodeStatus) => typesWith(model, status);
  const v = (now: string, past: string) => (applied ? past : now);
  const entities = (n: number, status: NodeStatus, now: string, past: string) =>
    n ? [`${v(now, past)} ${types(status) || plural(n, "entity", "entities")}`] : [];
  const links = (n: number, now: string, past: string) =>
    n ? [`${v(now, past)} ${plural(n, "relationship")}`] : [];
  const parts: string[] = [
    ...entities(created, "created", "creates", "created"),
    ...entities(updated, "updated", "updates", "updated"),
    ...entities(deleted, "deleted", "deletes", "deleted"),
    ...links(linked, "links", "linked"),
    ...links(unlinked, "unlinks", "unlinked"),
  ];
  if (parts.length === 0) return applied ? "Nothing changed." : "Changes nothing.";
  if (!updated && (created || linked)) parts.push(v("updates nothing", "updated nothing"));
  const text = parts.join("; ");
  const sentence = `${text.charAt(0).toUpperCase() + text.slice(1)}.`;
  return model.severed ? `${sentence} ${severedNote(model.severed, applied)}` : sentence;
}

const severedNote = (n: number, applied: boolean) =>
  `${plural(n, "link")} to other entities ${applied ? "went" : "would go"} with it.`;

// -- next steps ------------------------------------------------------------------------------

const declType = (e: EffectDecl) => String((e.type ?? e.ref_type ?? e.refType ?? "") as string);
const short = (t: string) => t.slice(t.lastIndexOf(".") + 1);

export interface NextStep {
  action: ActionInfo;
  /** Why it could reverse the change. */
  why: string;
  prefill: Record<string, string>;
}

// The declared op that reverses (or corrects) an effect of each kind.
const REVERSAL: Record<Effect["kind"], string> = {
  create: "delete",
  delete: "create",
  update: "update",
  link: "unlink",
  unlink: "link",
};

/** The step a declared effect `d` offers for the effect `e`, if it reverses or corrects it. */
function stepFor(e: Effect, d: EffectDecl): { why: string; ref?: EntityRef } | undefined {
  if (d.op !== REVERSAL[e.kind]) return undefined;
  if (!("ref" in e)) {
    if (declType(d) !== e.relationship) return undefined;
    const verb = e.kind === "link" ? "unlinks" : "links";
    return { why: `${verb} ${e.relationship}`, ref: e.source };
  }
  const t = short(e.ref.type);
  if (short(declType(d)) !== t) return undefined;
  if (e.kind === "create") return { why: `deletes the ${t} it created`, ref: e.ref };
  if (e.kind === "delete") return { why: `creates a ${t} again` };
  return { why: `corrects the ${t} again`, ref: e.ref };
}

/**
 * Declared actions that could reverse (or correct) what a change did, matched on their declared
 * effects: delete for a create, create for a delete, update for an update, unlink for a link and
 * link for an unlink. Nothing here is invented: no match is no step.
 */
export function nextSteps(m: ModuleInfo, effects: Effect[], self?: string): NextStep[] {
  const out = new Map<string, NextStep>();
  const add = (a: ActionInfo, why: string, ref?: EntityRef) => {
    if (a.name === self && !why.startsWith("corrects")) return;
    const spec = ref ? a.inputSpecs.find((s) => refAccepts(s, qualify(m, ref.type))) : undefined;
    const key = `${a.name}|${why}`;
    if (!out.has(key))
      out.set(key, {
        action: a,
        why,
        prefill: spec && ref && !ref.generated ? { [spec.name]: ref.key } : {},
      });
  };
  for (const e of effects) {
    for (const a of m.actions) {
      for (const d of a.effects) {
        const step = stepFor(e, d);
        if (step) add(a, step.why, step.ref);
      }
    }
  }
  return [...out.values()];
}
