// SPDX-License-Identifier: MIT OR Apache-2.0
// The picture's card: the layout built from the groups the page read and the labels it has so far,
// its footer ("7 of 7 neighbours shown"), and, in a narrow window, the button that opens it
// (DESIGN-GB, Narrow window). The relationship list beside it is always the complete view.
import { useEffect, useMemo, useState } from "react";
import { shortName } from "../api/gql";
import type { MetaData } from "../api/types";
import { useBrowser } from "./context";
import { type Group, type Layout, type LayoutNode, layoutGroups, MAX_NODES } from "./layoutGroups";
import { formatExplore } from "./location";
import { findQualified, type TypeEntry } from "./meta";
import { Picture } from "./Picture";
import { type GroupPlan, MAX_KEYS, pictureRefs, refId } from "./planner";
import type { Labels } from "./useLabels";

export interface NeighbourhoodProps {
  entry: TypeEntry;
  centreKey: string;
  centreTitle: string;
  groups: GroupPlan[];
  labels: Labels;
}

export function buildLayout(p: NeighbourhoodProps, meta: MetaData): Layout {
  const picked = new Set(pictureRefs(p.groups, MAX_NODES).map(refId));
  const groups: Group[] = p.groups.map((g) => ({
    id: g.field,
    label: g.label,
    order: g.order,
    total: g.refs.length,
    capped: g.refs.length >= MAX_KEYS,
    members: g.refs.flatMap((r) => {
      const label = p.labels.labels[refId(r)];
      const entry = findQualified(meta, r.type);
      if (!picked.has(refId(r)) || label?.state !== "ok" || !entry) return [];
      return [
        {
          type: r.type,
          key: r.key,
          title: label.title,
          typeLabel: entry.view.label,
          tone: entry.view.tone,
          icon: entry.view.icon,
        },
      ];
    }),
  }));
  return layoutGroups(
    {
      type: p.entry.type.name,
      key: p.centreKey,
      title: p.centreTitle,
      typeLabel: p.entry.view.label,
      tone: p.entry.view.tone,
      icon: p.entry.view.icon,
    },
    groups,
  );
}

function useNarrow(): boolean {
  const query = "(max-width: 419px)";
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

function Footer({ layout, atLeast }: { layout: Layout; atLeast: boolean }) {
  return (
    <div className="gb-pic-f">
      <span data-testid="gb-picture-count">
        {layout.shown} of {layout.total}
        {atLeast ? "+" : ""} neighbours shown
      </span>
      <span>Arrow keys move, Enter opens</span>
    </div>
  );
}

function Drawn({ p, layout }: { p: NeighbourhoodProps; layout: Layout }) {
  const { go } = useBrowser();
  const name = `Neighbourhood of ${p.centreTitle}: ${layout.total} ${layout.total === 1 ? "neighbour" : "neighbours"}. The lists have the same links.`;
  const linkFor = (n: LayoutNode) => {
    const loc = { module: p.entry.module.name, type: shortName(n.type), key: n.key };
    return { href: formatExplore(loc), open: () => go(loc) };
  };
  const module = p.entry.module.name;
  return (
    <>
      <div className="gb-fade" key={`${module}/${p.entry.type.name}/${p.centreKey}`}>
        <Picture layout={layout} name={name} linkFor={linkFor} />
      </div>
      <Footer layout={layout} atLeast={p.groups.some((g) => g.refs.length >= MAX_KEYS)} />
    </>
  );
}

export function Neighbourhood(p: NeighbourhoodProps) {
  const { meta } = useBrowser();
  const narrow = useNarrow();
  const [shown, setShown] = useState(false);
  const layout = useMemo(() => buildLayout(p, meta), [p, meta]);
  if (layout.total === 0)
    return (
      <section className="gb-card gb-pic" aria-label="Neighbourhood">
        <p className="gb-none">No relationships</p>
      </section>
    );
  if (narrow && !shown)
    return (
      <button type="button" className="gb-btn gb-wide" onClick={() => setShown(true)}>
        Show neighbourhood picture
      </button>
    );
  return (
    <section className="gb-card gb-pic" aria-label="Neighbourhood">
      <div className="gb-pic-h">
        <h3 className="gb-pic-title">Neighbourhood</h3>
      </div>
      <Drawn p={p} layout={layout} />
    </section>
  );
}
