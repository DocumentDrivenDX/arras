// SPDX-License-Identifier: MIT OR Apache-2.0
// One entity as a row of a list: a single link with a tone icon tile, the type's label, the title,
// an excerpt or summary line and a badge (DESIGN-GB, Screen 1). A hit's matched text is a `mark`
// element around text; every segment is rendered as text.

import { shortName } from "../api/gql";
import { badgeField } from "../api/search";
import type { SearchSegment } from "../api/types";
import { linkProps, useBrowser } from "./context";
import { Icon } from "./icons";
import type { TypeEntry } from "./meta";
import { toneClass } from "./tones";
import { Badge } from "./Value";

export interface RowData {
  key: string;
  title: string;
  summary?: string;
  excerpt?: SearchSegment[] | null;
  /** The entity's selected fields, for the badge. */
  fields: Record<string, unknown>;
}

export function Excerpt({ segments }: { segments: SearchSegment[] }) {
  let offset = 0;
  return (
    <>
      {segments.map((s) => {
        const at = offset;
        offset += s.text.length;
        return s.mark ? <mark key={`${at}`}>{s.text}</mark> : <span key={`${at}`}>{s.text}</span>;
      })}
    </>
  );
}

function RowBadge({ entry, fields }: { entry: TypeEntry; fields: Record<string, unknown> }) {
  const field = badgeField(entry);
  const value = field ? fields[field.property] : undefined;
  if (!field || typeof value !== "string" || value === "") return null;
  return <Badge tone={field.tones?.[value]}>{value}</Badge>;
}

/** An excerpt that only repeats the title says nothing the row does not already show. */
const showsExcerpt = (row: RowData) =>
  !!row.excerpt?.length && row.excerpt.map((s) => s.text).join("") !== row.title;

export function EntityRow({ entry, row }: { entry: TypeEntry; row: RowData }) {
  const { go } = useBrowser();
  const loc = { module: entry.module.name, type: shortName(entry.type.name), key: row.key };
  return (
    <a className={`gb-hit ${toneClass(entry.view.tone)}`} {...linkProps(go, loc)}>
      <span className="gb-ico gb-ico-md">
        <Icon name={entry.view.icon} size={22} />
      </span>
      <span className="gb-hit-body">
        <span className="gb-type">{entry.view.label}</span>
        <span className="gb-t">{row.title}</span>
        {showsExcerpt(row) ? (
          <span className="gb-ex">
            <Excerpt segments={row.excerpt ?? []} />
          </span>
        ) : row.summary ? (
          <span className="gb-ex">{row.summary}</span>
        ) : null}
      </span>
      <span className="gb-meta">
        <RowBadge entry={entry} fields={row.fields} />
      </span>
    </a>
  );
}
