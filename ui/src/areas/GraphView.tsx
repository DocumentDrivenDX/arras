// SPDX-License-Identifier: MIT OR Apache-2.0
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { type LaneSpec, layoutLanes, neighbourhood } from "../lib/graph";
import { arrowTarget, EdgePath, isArrow, LaneBand, NodeView, pickTabId } from "./graphViewParts";

export type NodeStatus = "created" | "updated" | "deleted" | "touched";
export type EdgeStatus = "added" | "removed";

export interface VNode {
  id: string;
  type: string;
  key: string;
  label: string;
  stub?: boolean;
  status?: NodeStatus;
  /** Marked after a change was applied (the changed-by banner). */
  changed?: boolean;
}
export interface VEdge {
  id: string;
  rel: string;
  from: string;
  to: string;
  status?: EdgeStatus;
}

export interface GraphViewProps {
  nodes: VNode[];
  edges: VEdge[];
  lanes: LaneSpec[];
  /** Compact: smaller nodes for the impact panel. */
  compact?: boolean;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** Nodes drawn faded (a text filter that does not match). */
  dimmed?: Set<string>;
  showKeys?: boolean;
  /** Applied (solid) rather than previewed (dashed) change styling. */
  applied?: boolean;
  ariaLabel: string;
  testId?: string;
  maxHeight?: number | string;
}

function watchWidth(el: HTMLElement, setW: (w: number) => void, fallback: number) {
  const read = () => setW(Math.max(280, Math.floor(el.clientWidth)) || fallback);
  read();
  if (typeof ResizeObserver === "undefined") return undefined;
  const ro = new ResizeObserver(read);
  ro.observe(el);
  return () => ro.disconnect();
}

function useWidth(ref: React.RefObject<HTMLElement | null>, fallback: number) {
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    return el ? watchWidth(el, setW, fallback) : undefined;
  }, [ref, fallback]);
  return w;
}

/** Typed lanes of nodes with curved edges. Hover or focus lights a node's edges; Enter selects. */
export function GraphView({
  nodes,
  edges,
  lanes,
  compact = false,
  selectedId = null,
  onSelect,
  dimmed,
  showKeys = false,
  applied = false,
  ariaLabel,
  testId = "graph",
  maxHeight,
}: GraphViewProps) {
  const wrap = useRef<HTMLFieldSetElement | null>(null);
  const width = useWidth(wrap, compact ? 460 : 900);
  const nodeW = compact ? 150 : 250;
  const rowH = compact ? 26 : 30;
  const nodeH = rowH - 5;
  const layout = useMemo(
    () =>
      layoutLanes(nodes, edges, lanes, {
        nodeW,
        rowH,
        width,
        headerH: 30,
        padX: 16,
        maxGap: compact ? 170 : 260,
      }),
    [nodes, edges, lanes, nodeW, rowH, width, compact],
  );
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const [hot, setHot] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const active = hot ?? selectedId;
  const near = useMemo(() => (active ? neighbourhood(active, edges) : null), [active, edges]);
  const firstId = layout.order.find((l) => l.length)?.[0] ?? null;
  const tabId = pickTabId(focusId, selectedId, (id) => byId.has(id), firstId);

  // Bring the changed entity into view when a change has just been applied.
  const firstChanged = nodes.find((n) => n.changed)?.id;
  useEffect(() => {
    if (firstChanged)
      refs.current.get(firstChanged)?.scrollIntoView?.({ block: "center", inline: "center" });
  }, [firstChanged]);

  const move = (e: KeyboardEvent, id: string) => {
    if (e.key === "Escape") setHot(null);
    const p = layout.pos.get(id);
    if (!p) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect?.(id);
      return;
    }
    if (!isArrow(e.key)) return;
    e.preventDefault();
    const next = arrowTarget(e.key, layout, p);
    if (next) {
      setFocusId(next);
      refs.current.get(next)?.focus();
    }
  };

  const keyChars = compact || showKeys ? 0 : 14;
  const charsFit = Math.floor(
    (nodeW - 22 - (keyChars ? keyChars * 5.9 + 8 : 0)) / (compact ? 6 : 6.4),
  );
  const laneBands = lanes.map((l, i) => ({ l, x: layout.laneX[i] ?? 0 }));

  return (
    <fieldset
      ref={wrap}
      aria-label={ariaLabel}
      className="m-0 min-h-0 min-w-0 flex-1 overflow-auto border-0 p-0"
      style={maxHeight ? { maxHeight } : undefined}
      data-testid={testId}
    >
      <svg width={layout.width} height={layout.height} className="block">
        <title>{ariaLabel ?? "Graph"}</title>
        {laneBands.map(({ l, x }, i) => (
          <LaneBand key={l.id} lane={l} x={x} index={i} nodeW={nodeW} height={layout.height} />
        ))}

        <g fill="none">
          {edges.map((e) => (
            <EdgePath
              key={e.id}
              e={e}
              layout={layout}
              nodeW={nodeW}
              nodeH={nodeH}
              near={near}
              applied={applied}
              labelOf={(id) => byId.get(id)?.label ?? id}
            />
          ))}
        </g>

        {nodes.map((n) => {
          const p = layout.pos.get(n.id);
          if (!p) return null;
          return (
            <NodeView
              key={n.id}
              n={n}
              p={p}
              nodeW={nodeW}
              nodeH={nodeH}
              compact={compact}
              showKeys={showKeys}
              applied={applied}
              selectedId={selectedId}
              near={near}
              dimmed={dimmed}
              tabId={tabId}
              keyChars={keyChars}
              charsFit={charsFit}
              refs={refs}
              onSelect={onSelect}
              onHot={setHot}
              onLeave={(id) => setHot((h) => (h === id ? null : h))}
              onFocusNode={setFocusId}
              onMove={move}
            />
          );
        })}
      </svg>
    </fieldset>
  );
}
