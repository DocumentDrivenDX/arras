// SPDX-License-Identifier: MIT OR Apache-2.0
import type { KeyboardEvent, MutableRefObject } from "react";
import type { layoutLanes, neighbourhood } from "../lib/graph";
import type { EdgeStatus, NodeStatus, VEdge, VNode } from "./GraphView";

export type Layout = ReturnType<typeof layoutLanes>;
export type Near = ReturnType<typeof neighbourhood> | null;
type Pos = NonNullable<ReturnType<Layout["pos"]["get"]>>;

const GLYPH: Record<NodeStatus, string> = { created: "+", updated: "~", deleted: "×", touched: "" };

export const clip = (s: string, n: number) =>
  s.length > n ? `${s.slice(0, Math.max(1, n - 1))}…` : s;

const FILL_BY_STATUS: Partial<Record<NodeStatus, string>> = {
  created: "var(--ok-soft)",
  updated: "var(--warn-soft)",
  deleted: "var(--bad-soft)",
};
const STROKE_BY_STATUS: Partial<Record<NodeStatus, string>> = {
  created: "var(--ok)",
  updated: "var(--warn)",
  deleted: "var(--bad)",
};

function nodeFill(n: VNode, selectedId: string | null): string {
  const byStatus = n.status && FILL_BY_STATUS[n.status];
  if (byStatus) return byStatus;
  if (n.changed) return "var(--warn-soft)";
  return n.id === selectedId ? "var(--accent-soft)" : "var(--surface)";
}

function nodeStroke(n: VNode, selectedId: string | null): string {
  const byStatus = n.status && STROKE_BY_STATUS[n.status];
  if (byStatus) return byStatus;
  return n.id === selectedId ? "var(--accent)" : "var(--line-strong)";
}

/** Which node an arrow key moves to, or `undefined` at an edge of the layout. */
export function arrowTarget(key: string, layout: Layout, p: Pos): string | undefined {
  const column = layout.order[p.lane] ?? [];
  if (key === "ArrowDown") return column[p.order + 1];
  if (key === "ArrowUp") return column[p.order - 1];
  const step = key === "ArrowRight" ? 1 : -1;
  for (let l = p.lane + step; l >= 0 && l < layout.order.length; l += step) {
    const found = closestInLane(layout, l, p.y);
    if (found) return found;
  }
  return undefined;
}

function closestInLane(layout: Layout, lane: number, y: number): string | undefined {
  let best = Infinity;
  let next: string | undefined;
  for (const c of layout.order[lane] ?? []) {
    const d = Math.abs((layout.pos.get(c)?.y ?? Number.POSITIVE_INFINITY) - y);
    if (d < best) {
      best = d;
      next = c;
    }
  }
  return next;
}

export const isArrow = (key: string) =>
  key === "ArrowDown" || key === "ArrowUp" || key === "ArrowRight" || key === "ArrowLeft";

export function pickTabId(
  focusId: string | null,
  selectedId: string | null,
  has: (id: string) => boolean,
  firstId: string | null,
): string | null {
  if (focusId && has(focusId)) return focusId;
  if (selectedId && has(selectedId)) return selectedId;
  return firstId;
}

export function LaneBand({
  lane,
  x,
  index,
  nodeW,
  height,
}: {
  lane: { id: string; title: string; foreign: boolean; count?: number };
  x: number;
  index: number;
  nodeW: number;
  height: number;
}) {
  return (
    <g data-testid="lane">
      <rect
        x={x - 8}
        y={4}
        width={nodeW + 16}
        height={height - 8}
        rx={6}
        fill="var(--surface-2)"
        opacity={index % 2 ? 0.35 : 0.6}
      />
      <text
        x={x}
        y={21}
        fontSize={11}
        fontWeight={700}
        fill={lane.foreign ? "var(--fg-muted)" : "var(--fg)"}
        letterSpacing="0.03em"
      >
        {lane.foreign ? "↗ " : ""}
        {lane.title.toUpperCase()}
        {lane.count !== undefined ? `  ${lane.count}` : ""}
      </text>
    </g>
  );
}

function edgePathData(a: Pos, b: Pos, nodeW: number, nodeH: number): string {
  const same = a.lane === b.lane;
  const forward = a.lane <= b.lane;
  const x1 = forward ? a.x + nodeW : a.x;
  const x2 = same ? b.x + nodeW : forward ? b.x : b.x + nodeW;
  const y1 = a.y + nodeH / 2;
  const y2 = b.y + nodeH / 2;
  const bend = same ? 34 : Math.max(24, Math.abs(x2 - x1) / 2);
  const dir = forward ? 1 : -1;
  return `M${x1} ${y1} C${x1 + dir * bend} ${y1} ${x2 - (same ? -1 : dir) * bend} ${y2} ${x2} ${y2}`;
}

const EDGE_STROKE: Record<EdgeStatus, string> = { added: "var(--ok)", removed: "var(--bad)" };

function edgeStroke(status: EdgeStatus | undefined, lit: boolean): string {
  if (status) return EDGE_STROKE[status];
  return lit ? "var(--accent)" : "var(--fg-muted)";
}

function edgeDash(status: EdgeStatus | undefined, applied: boolean): string | undefined {
  if (status === "removed") return "5 3";
  return status === "added" && !applied ? "5 3" : undefined;
}

function edgeOpacity(status: EdgeStatus | undefined, lit: boolean, fade: boolean): number {
  if (fade) return 0.08;
  return status || lit ? 1 : 0.45;
}

function edgeStatusNote(status: EdgeStatus | undefined, applied: boolean): string {
  if (!status) return "";
  const verb = status === "added" ? "added" : "removed";
  return ` (${applied ? verb : `would be ${verb}`})`;
}

export function EdgePath({
  e,
  layout,
  nodeW,
  nodeH,
  near,
  applied,
  labelOf,
}: {
  e: VEdge;
  layout: Layout;
  nodeW: number;
  nodeH: number;
  near: Near;
  applied: boolean;
  labelOf: (id: string) => string;
}) {
  const a = layout.pos.get(e.from);
  const b = layout.pos.get(e.to);
  if (!a || !b) return null;
  const lit = near?.edges.has(e.id) ?? false;
  const fade = near !== null && !lit;
  const status = e.status;
  return (
    <path
      data-testid="edge"
      data-rel={e.rel}
      data-status={status ?? "plain"}
      d={edgePathData(a, b, nodeW, nodeH)}
      stroke={edgeStroke(status, lit)}
      strokeWidth={status || lit ? 2 : 1.25}
      strokeDasharray={edgeDash(status, applied)}
      opacity={edgeOpacity(status, lit, fade)}
    >
      <title>
        {e.rel}: {labelOf(e.from)} → {labelOf(e.to)}
        {edgeStatusNote(status, applied)}
      </title>
    </path>
  );
}

function nodeAriaLabel(n: VNode, applied: boolean): string {
  const type = n.type.slice(n.type.lastIndexOf(".") + 1);
  const parts = [`${type} ${n.label}${n.label !== n.key ? ` (${n.key})` : ""}`];
  if (n.status) parts.push(`${n.status}${applied ? "" : " by this change"}`);
  if (n.changed) parts.push("changed");
  if (n.stub) parts.push("not loaded");
  return parts.join(", ");
}

export interface NodeViewProps {
  n: VNode;
  p: Pos;
  nodeW: number;
  nodeH: number;
  compact: boolean;
  showKeys: boolean;
  applied: boolean;
  selectedId: string | null;
  near: Near;
  dimmed?: Set<string>;
  tabId: string | null;
  keyChars: number;
  charsFit: number;
  refs: MutableRefObject<Map<string, HTMLButtonElement>>;
  onSelect?: (id: string) => void;
  onHot: (id: string | null) => void;
  onLeave: (id: string) => void;
  onFocusNode: (id: string) => void;
  onMove: (e: KeyboardEvent, id: string) => void;
}

function NodeText({ v, glyph }: { v: NodeViewProps; glyph: string }) {
  const { n, nodeW, nodeH, compact, showKeys, keyChars } = v;
  const text = showKeys ? n.key : n.label;
  return (
    <>
      {glyph && (
        <text
          x={7}
          y={nodeH / 2 + 4}
          fontSize={13}
          fontWeight={800}
          fill={nodeStroke(n, v.selectedId)}
        >
          {glyph}
        </text>
      )}
      <text
        x={glyph ? 20 : 8}
        y={nodeH / 2 + 4}
        fontSize={compact ? 11 : 12}
        fill={n.stub ? "var(--fg-muted)" : "var(--fg)"}
        fontStyle={n.stub ? "italic" : undefined}
        fontFamily={showKeys ? "var(--font-mono)" : undefined}
        textDecoration={n.status === "deleted" ? "line-through" : undefined}
      >
        {clip(text, v.charsFit - (glyph ? 2 : 0))}
      </text>
      {keyChars > 0 && n.label !== n.key && (
        <text
          x={nodeW - 7}
          y={nodeH / 2 + 3.5}
          fontSize={10}
          textAnchor="end"
          fill="var(--fg-muted)"
          fontFamily="var(--font-mono)"
        >
          {clip(n.key, keyChars)}
        </text>
      )}
    </>
  );
}

function NodeButton({ v }: { v: NodeViewProps }) {
  const { n, onSelect } = v;
  return (
    <foreignObject width={v.nodeW} height={v.nodeH} overflow="visible">
      <button
        type="button"
        ref={(el) => {
          if (el) v.refs.current.set(n.id, el);
          else v.refs.current.delete(n.id);
        }}
        data-node-id={n.id}
        tabIndex={n.id === v.tabId ? 0 : -1}
        aria-pressed={onSelect ? n.id === v.selectedId : undefined}
        aria-label={nodeAriaLabel(n, v.applied)}
        className="arras-node-hit"
        style={{ cursor: onSelect ? "pointer" : "default" }}
        onFocus={() => {
          v.onHot(n.id);
          v.onFocusNode(n.id);
        }}
        onBlur={() => v.onLeave(n.id)}
        onMouseEnter={() => v.onHot(n.id)}
        onMouseLeave={() => v.onLeave(n.id)}
        onClick={() => onSelect?.(n.id)}
        onKeyDown={(e) => v.onMove(e, n.id)}
      />
    </foreignObject>
  );
}

function ChangedRing({ nodeW, nodeH }: { nodeW: number; nodeH: number }) {
  return (
    <rect
      x={-4}
      y={-4}
      width={nodeW + 8}
      height={nodeH + 8}
      rx={7}
      fill="none"
      stroke="var(--warn)"
      strokeWidth={2.5}
    />
  );
}

function nodeDash(n: VNode, applied: boolean): string | undefined {
  if (n.status === "created" && !applied) return "4 3";
  return n.stub ? "3 3" : undefined;
}

export function NodeView(v: NodeViewProps) {
  const { n, p, nodeW, nodeH, selectedId, near, dimmed, applied } = v;
  const lit = near?.nodes.has(n.id) ?? false;
  const fade = (near !== null && !lit) || (dimmed?.has(n.id) ?? false);
  const glyph = n.status ? GLYPH[n.status] : "";
  const status = n.status;
  return (
    <g
      data-testid="node"
      data-node-id={n.id}
      data-status={status ?? "plain"}
      data-changed={n.changed ? "true" : undefined}
      data-selected={n.id === selectedId ? "true" : undefined}
      data-dimmed={dimmed?.has(n.id) ? "true" : undefined}
      transform={`translate(${p.x} ${p.y})`}
      opacity={fade ? 0.28 : 1}
      className="arras-node"
    >
      <title>{`${n.label} · ${n.key}${n.stub ? " (another module or not loaded)" : ""}`}</title>
      {n.changed && <ChangedRing nodeW={nodeW} nodeH={nodeH} />}
      <rect
        className="arras-node-box"
        width={nodeW}
        height={nodeH}
        rx={4}
        fill={nodeFill(n, selectedId)}
        stroke={nodeStroke(n, selectedId)}
        strokeWidth={status || n.id === selectedId ? 1.75 : 1}
        strokeDasharray={nodeDash(n, applied)}
      />
      <NodeText v={v} glyph={glyph} />
      <NodeButton v={v} />
    </g>
  );
}
