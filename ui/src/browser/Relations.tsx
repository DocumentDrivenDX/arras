// SPDX-License-Identifier: MIT OR Apache-2.0
// The relationship groups of a node page (DESIGN-GB, Screen 3): the accessible equivalent of the
// picture, and always complete. A neighbour is a link with its label, or a "Not available" row that
// carries no key, type or reason, or a retry row when its label read failed for cost or a backend.

import { shortName } from "../api/gql";
import type { Ref } from "../api/types";
import { type GroupLinks, groupLinks } from "../kit";
import { linkProps, useBrowser } from "./context";
import { InverseMore } from "./InverseMore";
import { Glyph, Icon } from "./icons";
import { AddLink, RemoveLink } from "./LinkControls";
import type { TypeEntry } from "./meta";
import { findQualified } from "./meta";
import type { GroupPlan } from "./planner";
import { MAX_KEYS, PAGE_LABELS, refId } from "./planner";
import { toneClass } from "./tones";
import type { Labels } from "./useLabels";

export interface RelationsProps {
  groups: GroupPlan[];
  labels: Labels;
  shown: Record<string, number>;
  onMore: (field: string) => void;
  centre: { entry: TypeEntry; key: string };
}

const mark = (entry: TypeEntry | undefined) => (
  <span className={`gb-ico ${toneClass(entry?.view.tone)}`}>
    <Icon name={entry?.view.icon ?? "circle"} size={16} />
  </span>
);

function Neighbour({
  item,
  labels,
  removal,
}: {
  item: Ref;
  labels: Labels;
  /** Edit mode's remove control, where the group's relationship has an unlink action. */
  removal?: { links: GroupLinks; centre: { entry: TypeEntry; key: string } };
}) {
  const { meta, go } = useBrowser();
  const entry = findQualified(meta, item.type);
  const label = labels.labels[refId(item)];
  const typeText = `${entry?.view.label ?? item.type} · ${item.key}`;
  if (!label)
    return (
      <li className={`gb-rel-row gb-loading ${toneClass(entry?.view.tone)}`} aria-busy="true">
        {mark(entry)}
        <span>
          {item.key}
          <br />
          <span className="gb-ty">Loading</span>
        </span>
      </li>
    );
  if (label.state === "na")
    return (
      <li className="gb-rel-row gb-na">
        <span className="gb-ico">
          <Glyph name="lock" size={16} />
        </span>
        <span>Not available</span>
      </li>
    );
  if (label.state === "retry")
    return (
      <li className={`gb-rel-row gb-retry ${toneClass(entry?.view.tone)}`}>
        {mark(entry)}
        <span>
          {item.key}
          <br />
          <span className="gb-ty">Could not be read</span>
        </span>
        <button type="button" className="gb-btn gb-small" onClick={() => labels.retry(refId(item))}>
          Retry
        </button>
      </li>
    );
  const loc = { module: item.module, type: shortName(item.type), key: item.key };
  return (
    <li className={`${toneClass(entry?.view.tone)}${removal ? " gb-rel-removable" : ""}`}>
      <a className="gb-rel-row" {...linkProps(go, loc)}>
        {mark(entry)}
        <span>
          {label.title}
          <br />
          <span className="gb-ty">{typeText}</span>
        </span>
        <span className="gb-go" aria-hidden="true">
          <Glyph name="arrow" size={14} />
        </span>
      </a>
      {removal && (
        <RemoveLink item={item} title={label.title} links={removal.links} centre={removal.centre} />
      )}
    </li>
  );
}

function Count({ group }: { group: GroupPlan }) {
  const n = group.refs.length;
  return <span className="gb-count">{n >= MAX_KEYS ? `${MAX_KEYS} or more` : n}</span>;
}

function Group({ group, p }: { group: GroupPlan; p: RelationsProps }) {
  const { editing } = useBrowser();
  const links = editing
    ? groupLinks(p.centre.entry.module, p.centre.entry.type.name, group.field)
    : undefined;
  const removal = links?.remove ? { links, centre: p.centre } : undefined;
  const limit = p.shown[group.field] ?? PAGE_LABELS;
  const visible = group.refs.slice(0, limit);
  const rest = group.refs.length - visible.length;
  const exhausted = group.refs.length >= MAX_KEYS && rest === 0;
  return (
    <section className="gb-card gb-rel" aria-labelledby={`gb-rel-${group.field}`}>
      <h3 id={`gb-rel-${group.field}`} className="gb-rel-h">
        <span>{group.label}</span>
        <Count group={group} />
      </h3>
      {group.refs.length === 0 ? (
        <p className="gb-none">None</p>
      ) : (
        <ul>
          {visible.map((r) => (
            <Neighbour key={refId(r)} item={r} labels={p.labels} removal={removal} />
          ))}
        </ul>
      )}
      {rest > 0 && (
        <button type="button" className="gb-more" onClick={() => p.onMore(group.field)}>
          Show more ({Math.min(rest, PAGE_LABELS)} of {rest}
          {group.refs.length >= MAX_KEYS ? "+" : ""})
        </button>
      )}
      {exhausted && <InverseMore group={group} centre={p.centre} />}
      {links?.add && (
        <div className="gb-rel-edit">
          <AddLink group={group} links={links} centre={p.centre} />
        </div>
      )}
    </section>
  );
}

export function Relations(p: RelationsProps) {
  const { editing } = useBrowser();
  // An empty group the reader may add to is shown while editing, hidden or not.
  const addable = (g: GroupPlan) =>
    editing && !!groupLinks(p.centre.entry.module, p.centre.entry.type.name, g.field)?.add;
  const groups = [...p.groups]
    .filter((g) => !(g.hideWhenEmpty && g.refs.length === 0) || addable(g))
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
  return (
    <>
      {groups.map((g) => (
        <Group key={g.field} group={g} p={p} />
      ))}
    </>
  );
}
