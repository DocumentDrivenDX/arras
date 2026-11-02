// SPDX-License-Identifier: MIT OR Apache-2.0
import { useId } from "react";
import { moduleOf, shortName } from "../api/gql";
import type { ModuleInfo } from "../api/types";

interface Node {
  id: string;
  x: number;
  y: number;
  foreign: boolean;
}
const W = 130;
const H = 34;

function layout(m: ModuleInfo): { nodes: Node[]; width: number; height: number } {
  const own = m.entityTypes.map((t) => t.name);
  const foreign = new Set<string>();
  for (const r of m.relationships)
    for (const t of [...r.source, ...r.target]) if (!own.includes(t)) foreign.add(t);
  const all = [
    ...own.map((id) => ({ id, foreign: false })),
    ...[...foreign].map((id) => ({ id, foreign: true })),
  ];
  const n = all.length;
  if (n <= 3) {
    // a short row: a few types need no ring
    const step = W + 110;
    const width = Math.max(300, n * step);
    return {
      nodes: all.map((a, i) => ({ ...a, x: step / 2 + i * step, y: 60 })),
      width,
      height: 120,
    };
  }
  const R = Math.max(110, n * 28);
  const width = Math.max(520, 2 * R + W + 120);
  const height = Math.max(240, 2 * R + H + 100);
  const cx = width / 2;
  const cy = height / 2;
  const nodes = all.map((a, i) => {
    const ang = n === 1 ? 0 : (2 * Math.PI * i) / n - Math.PI / 2;
    return {
      ...a,
      x: n === 1 ? cx : cx + R * 1.25 * Math.cos(ang),
      y: n === 1 ? cy : cy + R * Math.sin(ang),
    };
  });
  return { nodes, width, height };
}

/** Where the line from a box centre toward (tx, ty) leaves the box. */
function edgePoint(n: Node, tx: number, ty: number) {
  const dx = tx - n.x;
  const dy = ty - n.y;
  if (dx === 0 && dy === 0) return { x: n.x, y: n.y };
  const s = Math.min(
    dx !== 0 ? W / 2 / Math.abs(dx) : Infinity,
    dy !== 0 ? H / 2 / Math.abs(dy) : Infinity,
  );
  return { x: n.x + dx * s, y: n.y + dy * s };
}

/** Types as boxes, relationships as labelled arrows with their multiplicities (US-060). */
export function Diagram({ module }: { module: ModuleInfo }) {
  const marker = useId();
  const { nodes, width, height } = layout(module);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges: {
    key: string;
    s: Node;
    t: Node;
    label: string;
    mult: [string, string];
    inverse: string | null;
    offset: number;
    at: number;
  }[] = [];
  const pairCount = new Map<string, number>();
  for (const r of module.relationships) {
    for (const src of r.source) {
      for (const tgt of r.target) {
        const s = byId.get(src);
        const t = byId.get(tgt);
        if (!s || !t) continue;
        const pk = [src, tgt].sort().join("|");
        const c = pairCount.get(pk) ?? 0;
        pairCount.set(pk, c + 1);
        edges.push({
          key: `${r.name}:${src}>${tgt}`,
          s,
          t,
          label: r.name,
          mult: [r.sourceMultiplicity, r.targetMultiplicity],
          inverse: r.inverse,
          offset: c,
          // stagger label positions along the arrow so labels of crossing edges don't stack
          at: 0.38 + 0.24 * ((edges.length * 0.618) % 1),
        });
      }
    }
  }
  return (
    <figure className="m-0">
      <svg
        role="img"
        aria-label={`Relationship diagram of module ${module.name}: ${module.entityTypes.length} types, ${module.relationships.length} relationships`}
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto max-h-[320px] w-full rounded border border-line bg-surface"
      >
        <defs>
          <marker
            id={marker}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10 z" fill="var(--fg-muted)" />
          </marker>
        </defs>
        {edges.map((e) => {
          const self = e.s.id === e.t.id;
          if (self) {
            const x = e.s.x + W / 2;
            const y = e.s.y;
            return (
              <g key={e.key} data-testid="diagram-edge">
                <path
                  d={`M${x} ${y - 6} c 40 -30 40 42 0 12`}
                  fill="none"
                  stroke="var(--fg-muted)"
                  strokeWidth="1.3"
                  markerEnd={`url(#${marker})`}
                />
                <text x={x + 34} y={y + 4} fontSize="11" fill="var(--fg)">
                  {e.label} ({e.mult[0]} → {e.mult[1]})
                </text>
              </g>
            );
          }
          const shift = (e.offset % 2 ? 1 : -1) * Math.ceil(e.offset / 2) * 14;
          const dx = e.t.x - e.s.x;
          const dy = e.t.y - e.s.y;
          const len = Math.hypot(dx, dy) || 1;
          const px = (-dy / len) * shift;
          const py = (dx / len) * shift;
          const a = edgePoint(e.s, e.t.x + px, e.t.y + py);
          const b = edgePoint(e.t, e.s.x + px, e.s.y + py);
          const mx = a.x + (b.x - a.x) * e.at + px;
          const my = a.y + (b.y - a.y) * e.at + py;
          return (
            <g key={e.key} data-testid="diagram-edge">
              <line
                x1={a.x + px}
                y1={a.y + py}
                x2={b.x + px}
                y2={b.y + py}
                stroke="var(--fg-muted)"
                strokeWidth="1.3"
                markerEnd={`url(#${marker})`}
              />
              <text
                x={mx}
                y={my - 4}
                fontSize="11"
                textAnchor="middle"
                fill="var(--fg)"
                paintOrder="stroke"
                stroke="var(--surface)"
                strokeWidth="3"
              >
                {e.label}
              </text>
              <text
                x={mx}
                y={my + 9}
                fontSize="10"
                textAnchor="middle"
                fill="var(--fg-muted)"
                paintOrder="stroke"
                stroke="var(--surface)"
                strokeWidth="3"
              >
                {e.mult[0]} → {e.mult[1]}
              </text>
            </g>
          );
        })}
        {nodes.map((n) => (
          <g
            key={n.id}
            transform={`translate(${n.x - W / 2} ${n.y - H / 2})`}
            data-testid="diagram-node"
          >
            <title>{n.foreign ? `${n.id} (another module)` : n.id}</title>
            <rect
              width={W}
              height={H}
              rx="4"
              fill="var(--surface-2)"
              stroke={n.foreign ? "var(--line-strong)" : "var(--accent)"}
              strokeWidth="1.5"
              strokeDasharray={n.foreign ? "4 3" : undefined}
            />
            <text
              x={W / 2}
              y={H / 2 + 4}
              textAnchor="middle"
              fontSize="12"
              fontWeight="600"
              fill="var(--fg)"
            >
              {shortName(n.id)}
            </text>
            {n.foreign && (
              <text x={W / 2} y={H + 11} textAnchor="middle" fontSize="9" fill="var(--fg-muted)">
                module {moduleOf(n.id) || "?"}
              </text>
            )}
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] text-muted">
        Solid boxes are this module's types; dashed boxes are types of another module (name only).
        Labels read source → target multiplicity.
      </figcaption>
    </figure>
  );
}
