// SPDX-License-Identifier: MIT OR Apache-2.0
// The picture's layout: a pure function from the centre and its relationship groups to coordinates
// (SD-011, Layout of the picture; DESIGN-GB, Picture geometry). No animation, no randomness: the same
// input always gives the same picture, so the layout is tested as numbers (layout.vectors.json).

import { fitLines, MAX_LINES } from "./fitText";

export const WIDTH = 440;
export const MAX_NODES = 40;
export const NODE_H = 36;
const CENTRE_W = 146;
const CENTRE_H = 48;
const LEFT_W = 134;
const RIGHT_W = 134;
const ROW_W = 150;
const GUTTER = 12;
const PAD = 4;
const CAPTION_H = 16;
const PER_ROW = 2;
/** Where a node's text starts, and the room left of its right edge, in the picture's units. */
export const NODE_TEXT_X = 38;
const CENTRE_TEXT_X = 48;
const TEXT_PAD = 4;

export interface Member {
  type: string;
  key: string;
  title: string;
  typeLabel: string;
  tone: string;
  icon: string;
}
export interface Group {
  id: string;
  label: string;
  order: number;
  members: Member[];
  /** How many members the relationship has, when more than `members` were given. */
  total?: number;
  /** The relationship returned its key limit, so `total` is a lower bound: "+60 or more". */
  capped?: boolean;
}
export interface Centre {
  type: string;
  key: string;
  title: string;
  typeLabel: string;
  tone: string;
  icon: string;
}

export type Side = "left" | "right" | "bottom" | "top";
const SIDES: Side[] = ["left", "right", "bottom", "top"];

export interface LayoutNode extends Member {
  id: string;
  /** The reading order: group by group, in the group's own order. */
  seq: number;
  group: string;
  relation: string;
  side: Side;
  x: number;
  y: number;
  w: number;
  h: number;
  /** The label as shown, on one line: the title, cut to fit. */
  label: string;
  /** The same text as the lines it is drawn in (one or two). */
  lines: string[];
}
export interface Edge {
  id: string;
  d: string;
}
export interface Caption {
  id: string;
  x: number;
  y: number;
  text: string;
}
export interface Layout {
  size: { w: number; h: number };
  centre: Centre & {
    x: number;
    y: number;
    w: number;
    h: number;
    label: string;
    lines: string[];
  };
  nodes: LayoutNode[];
  edges: Edge[];
  captions: Caption[];
  /** Neighbours drawn, and neighbours the centre has (self links and duplicates excluded). */
  shown: number;
  total: number;
  /** Relationships whose members were left out, with how many. */
  omitted: { label: string; count: number }[];
  /** The relationships by which the centre links to itself. */
  selfLinks: string[];
}

export const idOf = (m: { type: string; key: string }) => `${m.type}:${m.key}`;

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

export function clip(text: string, max: number): string {
  const chars = Array.from(text);
  return chars.length <= max ? text : `${chars.slice(0, max - 1).join("")}…`;
}

interface Prepared {
  group: Group;
  members: Member[];
  total: number;
  picked: Member[];
}

/** Groups by order then label, members by title then key; an entity in two groups stays in its first. */
function prepare(centre: Centre, groups: Group[]): { prepared: Prepared[]; selfLinks: string[] } {
  const ordered = [...groups].sort((a, b) => a.order - b.order || cmp(a.label, b.label));
  const seen = new Set<string>([idOf(centre)]);
  const selfLinks: string[] = [];
  const prepared: Prepared[] = [];
  for (const group of ordered) {
    const members: Member[] = [];
    for (const m of group.members) {
      if (idOf(m) === idOf(centre)) selfLinks.push(group.label);
      else if (!seen.has(idOf(m))) members.push(m);
      seen.add(idOf(m));
    }
    members.sort((a, b) => cmp(a.title.toLowerCase(), b.title.toLowerCase()) || cmp(a.key, b.key));
    const total = Math.max(group.total ?? group.members.length, members.length);
    if (total > 0) prepared.push({ group, members, total, picked: [] });
  }
  return { prepared, selfLinks };
}

/** One member per group in turn, in group order, until the cap: every group is represented. */
function roundRobin(prepared: Prepared[], cap: number): void {
  let count = 0;
  for (let i = 0; count < cap; i++) {
    let any = false;
    for (const p of prepared) {
      const m = p.members[i];
      if (m && count < cap) {
        p.picked.push(m);
        count++;
        any = true;
      }
    }
    if (!any) break;
  }
}

/** A group of more than this many drawn members is a block of rows, not a column that would run the card's height. */
const BIG = 8;
const BIG_PER_ROW = 3;
const BIG_W = 134;
const isBig = (p: Prepared) => p.picked.length > BIG;
const perRow = (p: Prepared) => (isBig(p) ? BIG_PER_ROW : PER_ROW);
const rowW = (p: Prepared) => (isBig(p) ? BIG_W : ROW_W);

const stackHeight = (n: number) => n * NODE_H + (n - 1) * GUTTER;

/** The height one group takes on its side: a column is one per node, a row holds two. */
function groupHeight(side: Side, p: Prepared): number {
  const n = p.picked.length;
  const rows = side === "left" || side === "right" ? n : Math.ceil(n / perRow(p));
  return CAPTION_H + (n === 0 ? 0 : stackHeight(rows));
}

const blockHeight = (heights: number[]) =>
  heights.reduce((a, b) => a + b, 0) + Math.max(0, heights.length - 1) * GUTTER;

/**
 * The side of every group: group n on side n mod 4, except that a block (a big group) goes to
 * whichever of the top and bottom bands is the shorter so far, the top on a tie, so the centre
 * stays between blocks instead of falling to the foot of one.
 */
function assignSides(prepared: Prepared[]): Record<Side, Prepared[]> {
  const bySide: Record<Side, Prepared[]> = { left: [], right: [], bottom: [], top: [] };
  const height = (side: Side) => blockHeight(bySide[side].map((p) => groupHeight(side, p)));
  prepared.forEach((p, i) => {
    const preferred = SIDES[i % 4] ?? "left";
    const side: Side = !isBig(p) ? preferred : height("top") <= height("bottom") ? "top" : "bottom";
    bySide[side].push(p);
  });
  return bySide;
}

interface Bands {
  top: number;
  middle: number;
  bottom: number;
}

function bandsOf(bySide: Record<Side, Prepared[]>): Bands {
  const h = (side: Side) => blockHeight(bySide[side].map((p) => groupHeight(side, p)));
  const column = Math.max(h("left"), h("right"), CENTRE_H);
  const top = h("top");
  const bottom = h("bottom");
  return { top: top ? top + GUTTER : 0, middle: column, bottom: bottom ? bottom + GUTTER : 0 };
}

function caption(p: Prepared, max: number): string {
  const left = p.total - p.picked.length;
  const base = clip(p.group.label.toUpperCase(), max);
  return left > 0 ? `${base} · +${left} ${p.group.capped ? "or more" : "more"}` : base;
}

interface Placed {
  nodes: LayoutNode[];
  captions: Caption[];
}

function labelOf(title: string, width: number, bold: boolean) {
  const lines = fitLines(title, width, MAX_LINES, 12, bold);
  return { lines, label: lines.join(" ") };
}

function node(
  p: Prepared,
  m: Member,
  side: Side,
  at: { x: number; y: number; w: number },
): LayoutNode {
  return {
    ...m,
    id: idOf(m),
    seq: 0,
    group: p.group.id,
    relation: p.group.label,
    side,
    x: at.x,
    y: at.y,
    w: at.w,
    h: NODE_H,
    ...labelOf(m.title, at.w - NODE_TEXT_X - TEXT_PAD, false),
  };
}

function placeColumn(side: "left" | "right", list: Prepared[], top: number, span: number): Placed {
  const total = blockHeight(list.map((p) => groupHeight(side, p)));
  let y = top + Math.round((span - total) / 2);
  const w = side === "left" ? LEFT_W : RIGHT_W;
  const x = side === "left" ? PAD : WIDTH - PAD - RIGHT_W;
  const out: Placed = { nodes: [], captions: [] };
  for (const p of list) {
    out.captions.push({
      id: `cap:${p.group.id}`,
      x,
      y: y + 11,
      text: caption(p, side === "left" ? 22 : 19),
    });
    y += CAPTION_H;
    for (const m of p.picked) {
      out.nodes.push(node(p, m, side, { x, y, w }));
      y += NODE_H + GUTTER;
    }
  }
  return out;
}

function placeRows(side: "top" | "bottom", list: Prepared[], start: number): Placed {
  let y = start;
  const out: Placed = { nodes: [], captions: [] };
  for (const p of list) {
    const per = perRow(p);
    const w = rowW(p);
    const first = Math.min(per, p.picked.length);
    const firstX = Math.round((WIDTH - (first * w + (first - 1) * GUTTER)) / 2);
    out.captions.push({ id: `cap:${p.group.id}`, x: firstX, y: y + 11, text: caption(p, 40) });
    y += CAPTION_H;
    for (let i = 0; i < p.picked.length; i += per) {
      const row = p.picked.slice(i, i + per);
      const x0 = Math.round((WIDTH - (row.length * w + (row.length - 1) * GUTTER)) / 2);
      row.forEach((m, k) => {
        out.nodes.push(node(p, m, side, { x: x0 + k * (w + GUTTER), y, w }));
      });
      y += NODE_H + GUTTER;
    }
  }
  return out;
}

const CX = (WIDTH - CENTRE_W) / 2;

function edgeFor(n: LayoutNode, cy: number): string {
  const ny = n.y + NODE_H / 2;
  if (n.side === "left")
    return `M${CX} ${cy} C${CX - 10} ${cy} ${CX - 10} ${ny} ${n.x + n.w} ${ny}`;
  if (n.side === "right")
    return `M${CX + CENTRE_W} ${cy} C${CX + CENTRE_W + 18} ${cy} ${CX + CENTRE_W + 18} ${ny} ${n.x} ${ny}`;
  const nx = n.x + n.w / 2;
  const mid = WIDTH / 2;
  const sx = Math.min(mid + 40, Math.max(mid - 40, nx));
  const sy = n.side === "bottom" ? cy + CENTRE_H / 2 : cy - CENTRE_H / 2;
  const ey = n.side === "bottom" ? n.y : n.y + NODE_H;
  const my = Math.round((sy + ey) / 2);
  return `M${sx} ${sy} C${sx} ${my} ${nx} ${my} ${nx} ${ey}`;
}

/** A block of members is one bundled edge, a vertical line between the block and the centre. */
function bundleFor(id: string, members: LayoutNode[], cy: number): Edge {
  const x = WIDTH / 2;
  const below = members[0]?.side === "bottom";
  if (below) {
    const top = Math.min(...members.map((m) => m.y)) - CAPTION_H;
    return { id: `edge:group:${id}`, d: `M${x} ${cy + CENTRE_H / 2} L${x} ${top}` };
  }
  const foot = Math.max(...members.map((m) => m.y + NODE_H));
  return { id: `edge:group:${id}`, d: `M${x} ${cy - CENTRE_H / 2} L${x} ${foot}` };
}

/** An edge per neighbour, except that a block of members shares the one bundled edge. */
function edgesOf(nodes: LayoutNode[], prepared: Prepared[], cy: number): Edge[] {
  const blocks = new Set(prepared.filter(isBig).map((p) => p.group.id));
  const single = nodes
    .filter((n) => !blocks.has(n.group))
    .map((n) => ({ id: `edge:${n.id}`, d: edgeFor(n, cy) }));
  const bundled = [...blocks].map((id) =>
    bundleFor(
      id,
      nodes.filter((n) => n.group === id),
      cy,
    ),
  );
  return [...single, ...bundled];
}

function loopFor(cy: number): string {
  const x = CX + CENTRE_W;
  return `M${x} ${cy - 10} C${x + 30} ${cy - 34} ${x + 30} ${cy + 34} ${x} ${cy + 10}`;
}

/** The picture of `centre` and its relationship groups. */
export function layoutGroups(centre: Centre, groups: Group[]): Layout {
  const { prepared, selfLinks } = prepare(centre, groups);
  roundRobin(prepared, MAX_NODES);
  const bySide = assignSides(prepared);
  const bands = bandsOf(bySide);
  const midTop = PAD + bands.top;
  const cy = midTop + Math.round(bands.middle / 2);
  const placed = [
    placeRows("top", bySide.top, PAD),
    placeColumn("left", bySide.left, midTop, bands.middle),
    placeColumn("right", bySide.right, midTop, bands.middle),
    placeRows("bottom", bySide.bottom, midTop + bands.middle + GUTTER),
  ];
  const order = new Map(prepared.flatMap((p) => p.picked).map((m, i) => [idOf(m), i]));
  const nodes = placed
    .flatMap((p) => p.nodes)
    .map((n) => ({ ...n, seq: order.get(n.id) ?? 0 }))
    .sort((a, b) => a.seq - b.seq);
  const edges = edgesOf(nodes, prepared, cy);
  if (selfLinks.length) edges.push({ id: "edge:self", d: loopFor(cy) });
  const total = prepared.reduce((n, p) => n + p.total, 0);
  return {
    size: { w: WIDTH, h: PAD + bands.top + bands.middle + bands.bottom + PAD },
    centre: {
      ...centre,
      x: CX,
      y: cy - CENTRE_H / 2,
      w: CENTRE_W,
      h: CENTRE_H,
      ...labelOf(centre.title, CENTRE_W - CENTRE_TEXT_X - TEXT_PAD, true),
    },
    nodes,
    edges,
    captions: placed.flatMap((p) => p.captions),
    shown: nodes.length,
    total,
    omitted: prepared
      .filter((p) => p.total > p.picked.length)
      .map((p) => ({ label: p.group.label, count: p.total - p.picked.length })),
    selfLinks,
  };
}
