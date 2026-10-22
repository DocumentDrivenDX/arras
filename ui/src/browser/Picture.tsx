// SPDX-License-Identifier: MIT OR Apache-2.0
// The neighbourhood picture (DESIGN-GB, Picture geometry): hand-written SVG drawn from layoutGroups.
// The container is a labelled `group` (not an image) so its links stay exposed; it is one Tab stop
// with a roving tabindex, and the arrow keys move between the nodes group by group. Everything in
// it is equivalent to the relationship list beside it.
import { type KeyboardEvent, useRef, useState } from "react";
import { keyed } from "../lib/format";
import { iconPaths } from "./icons";
import { type Layout, type LayoutNode, NODE_TEXT_X } from "./layoutGroups";
import { toneClass } from "./tones";

function Glyph({ name, x, y, size }: { name: string; x: number; y: number; size: number }) {
  return (
    <svg x={x} y={y} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {iconPaths(name).map((d) => (
        <path key={d} className="gb-glyph" d={d} />
      ))}
    </svg>
  );
}

export interface NodeLink {
  href: string;
  /** Open the node's page (the host's router, or the fragment). */
  open: () => void;
}

const plainClick = (e: React.MouseEvent) =>
  e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;

interface NodeProps {
  node: LayoutNode;
  tabIndex: number;
  link: NodeLink;
  onKey: (e: KeyboardEvent) => void;
  onHover: (id: string | null) => void;
  setRef: (id: string, el: HTMLAnchorElement | null) => void;
}

export const nodeName = (n: LayoutNode) => `${n.typeLabel}, ${n.title}, ${n.relation}`;

function Node({ node: n, tabIndex, link, onKey, onHover, setRef }: NodeProps) {
  const keys = (e: KeyboardEvent) => {
    if (e.key !== "Enter") return onKey(e);
    e.preventDefault(); // an SVG link is not activated by Enter in every browser
    link.open();
  };
  return (
    <a
      className={`gb-node ${toneClass(n.tone)}`}
      ref={(el) => setRef(n.id, el)}
      href={link.href}
      onClick={(e) => {
        if (!plainClick(e)) return;
        e.preventDefault();
        link.open();
      }}
      tabIndex={tabIndex}
      aria-label={nodeName(n)}
      data-testid="gb-node"
      onKeyDown={keys}
      onMouseEnter={() => onHover(n.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(n.id)}
      onBlur={() => onHover(null)}
    >
      <rect className="gb-box" x={n.x} y={n.y} width={n.w} height={n.h} rx={10} />
      <rect className="gb-tile" x={n.x + 4} y={n.y + 4} width={28} height={28} rx={8} />
      <Glyph name={n.icon} x={n.x + 9} y={n.y + 9} size={18} />
      <title>{n.title}</title>
      {keyed(n.lines, (l) => l).map(({ key, item: line }, i) => (
        // One <text> per line: axe finds no background for a <tspan>, and flags its contrast.
        <text key={key} x={n.x + NODE_TEXT_X} y={n.y + (n.lines.length > 1 ? 16 : 22) + i * 13}>
          {line}
        </text>
      ))}
    </a>
  );
}

function Centre({ layout }: { layout: Layout }) {
  const c = layout.centre;
  return (
    <g className={`gb-node gb-centre ${toneClass(c.tone)}`}>
      <rect className="gb-box" x={c.x} y={c.y} width={c.w} height={c.h} rx={12} />
      <rect className="gb-tile" x={c.x + 6} y={c.y + 6} width={36} height={36} rx={10} />
      <Glyph name={c.icon} x={c.x + 14} y={c.y + 14} size={20} />
      <title>{c.title}</title>
      {keyed(c.lines, (l) => l).map(({ key, item: line }, i) => (
        <text
          key={key}
          x={c.x + 48}
          y={c.y + (c.lines.length > 1 ? 16 : 22) + i * 13}
          className="gb-centre-title"
        >
          {line}
        </text>
      ))}
      <text x={c.x + 48} y={c.y + (c.lines.length > 1 ? 43 : 37)} className="gb-centre-sub">
        this page
      </text>
    </g>
  );
}

function HoverCard({ node, layout }: { node: LayoutNode; layout: Layout }) {
  const left = ((node.x + node.w / 2) / layout.size.w) * 100;
  const top = ((node.y + node.h) / layout.size.h) * 100;
  const right = left > 50;
  return (
    <div
      className={`gb-hover ${right ? "gb-hover-left" : "gb-hover-right"}`}
      data-testid="gb-hover"
      aria-hidden="true"
      style={{ top: `${top}%`, left: `${left}%` }}
    >
      <strong>{node.title}</strong>
      <span>{node.typeLabel}</span>
      <span>{node.relation}</span>
    </div>
  );
}

const MOVES: Record<string, (i: number, n: number) => number> = {
  ArrowDown: (i, n) => Math.min(i + 1, n - 1),
  ArrowRight: (i, n) => Math.min(i + 1, n - 1),
  ArrowUp: (i) => Math.max(i - 1, 0),
  ArrowLeft: (i) => Math.max(i - 1, 0),
  Home: () => 0,
  End: (_i, n) => n - 1,
};

export interface PictureProps {
  layout: Layout;
  name: string;
  linkFor: (n: LayoutNode) => NodeLink;
}

export function Picture({ layout, name, linkFor }: PictureProps) {
  const [active, setActive] = useState(0);
  const [hover, setHover] = useState<string | null>(null);
  const els = useRef(new Map<string, HTMLAnchorElement>());
  const nodes = layout.nodes;
  const move = (e: KeyboardEvent) => {
    const step = MOVES[e.key];
    if (!step) return;
    e.preventDefault();
    const next = step(Math.min(active, nodes.length - 1), nodes.length);
    const target = nodes[next];
    if (!target) return;
    setActive(next);
    els.current.get(target.id)?.focus();
  };
  const hovered = nodes.find((n) => n.id === hover);
  return (
    <fieldset className="gb-pic-wrap">
      <legend className="gb-sr">{name}</legend>
      <svg
        className="gb-graph"
        role="presentation"
        viewBox={`0 0 ${layout.size.w} ${layout.size.h}`}
        focusable="false"
        data-testid="gb-picture"
      >
        {layout.edges.map((e) => (
          <path key={e.id} className="gb-edge" d={e.d} />
        ))}
        {layout.captions.map((c) => (
          <text key={c.id} className="gb-cap" x={c.x} y={c.y}>
            {c.text}
          </text>
        ))}
        {nodes.map((n, i) => (
          <Node
            key={n.id}
            node={n}
            tabIndex={i === Math.min(active, nodes.length - 1) ? 0 : -1}
            link={linkFor(n)}
            onKey={move}
            onHover={(id) => {
              setHover(id);
              if (id) setActive(i);
            }}
            setRef={(id, el) => {
              if (el) els.current.set(id, el);
              else els.current.delete(id);
            }}
          />
        ))}
        <Centre layout={layout} />
      </svg>
      {hovered && <HoverCard node={hovered} layout={layout} />}
    </fieldset>
  );
}
