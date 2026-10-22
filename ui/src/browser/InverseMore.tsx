// SPDX-License-Identifier: MIT OR Apache-2.0
// Beyond the 100 keys a read returns for one relationship, more are read through the other type's
// list read, filtered by the inverse relationship, when the relationship has one (US-068-AC3), a page
// at a time after the last key read (`afterKey`).
// Without an inverse the group says it shows the first 100.
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useClient } from "../api/context";
import { listField, nextAfterKey, shortName } from "../api/gql";
import type { ModuleInfo, RelationshipInfo } from "../api/types";
import { titleOf } from "../lib/template";
import { linkProps, useBrowser } from "./context";
import { Glyph, Icon } from "./icons";
import { findQualified, revisionKey, type TypeEntry } from "./meta";
import type { GroupPlan } from "./planner";
import { MAX_KEYS, titleSelection } from "./planner";
import { toneClass } from "./tones";

interface Inverse {
  field: string;
  other: string;
}

/** The other end's name for the relationship field on `type`, when the relationship has an inverse. */
export function inverseOf(module: ModuleInfo, type: string, field: string): Inverse | null {
  const find = (r: RelationshipInfo): Inverse | null => {
    if (r.name === field && r.source.includes(type) && r.inverse && r.target[0])
      return { field: r.inverse, other: r.target[0] };
    if (r.inverse === field && r.target.includes(type) && r.source[0])
      return { field: r.name, other: r.source[0] };
    return null;
  };
  for (const r of module.relationships) {
    const found = find(r);
    if (found) return found;
  }
  return null;
}

interface Page {
  items: Record<string, unknown>[];
  truncated: boolean;
}

function useMore(entry: TypeEntry, other: TypeEntry | undefined, inv: Inverse, key: string) {
  const client = useClient();
  const props = other ? titleSelection(other) : [];
  const query = `query($filter: JSON, $limit: Int, $afterKey: String) { ${listField(inv.other)}(filter: $filter, limit: $limit, afterKey: $afterKey) { items { key ${props.join(" ")} } truncated } }`;
  return useInfiniteQuery({
    queryKey: [
      "gb",
      "inverse",
      entry.module.name,
      revisionKey(entry.module),
      inv.other,
      inv.field,
      key,
    ],
    initialPageParam: null as string | null,
    retry: false,
    queryFn: async ({ pageParam }): Promise<Page> => {
      const r = await client.moduleQuery<Record<string, Page | null>>(entry.module.name, query, {
        filter: { [inv.field]: key },
        limit: MAX_KEYS,
        afterKey: pageParam,
      });
      const page = r.data?.[listField(inv.other)];
      if (!page) throw new Error("the read failed");
      return page;
    },
    getNextPageParam: (last) => nextAfterKey(last),
  });
}

function More({
  entry,
  inv,
  group,
  centreKey,
}: {
  entry: TypeEntry;
  inv: Inverse;
  group: GroupPlan;
  centreKey: string;
}) {
  const { meta, go } = useBrowser();
  const other = findQualified(meta, inv.other);
  const q = useMore(entry, other, inv, centreKey);
  const known = useMemo(() => new Set(group.refs.map((r) => r.key)), [group.refs]);
  const rows = (q.data?.pages ?? [])
    .flatMap((p) => p.items)
    .filter((x) => !known.has(String(x.key)));
  const { hasNextPage, isFetching, fetchNextPage } = q;
  // The first pages repeat the keys already shown: read on until something new appears.
  useEffect(() => {
    if (q.data && rows.length === 0 && hasNextPage && !isFetching) void fetchNextPage();
  }, [q.data, rows.length, hasNextPage, isFetching, fetchNextPage]);
  if (q.error)
    return (
      <p className="gb-none">
        More could not be read.{" "}
        <button type="button" className="gb-more-inline" onClick={() => void q.refetch()}>
          Retry
        </button>
      </p>
    );
  return (
    <>
      <ul aria-busy={isFetching}>
        {rows.map((x) => {
          const key = String(x.key);
          const loc = { module: entry.module.name, type: shortName(inv.other), key };
          return (
            <li key={key} className={toneClass(other?.view.tone)}>
              <a className="gb-rel-row" {...linkProps(go, loc)}>
                <span className="gb-ico">
                  <Icon name={other?.view.icon ?? "circle"} size={16} />
                </span>
                <span>
                  {other ? titleOf(other.view.title, x, key) : key}
                  <br />
                  <span className="gb-ty">
                    {other?.view.label ?? inv.other} · {key}
                  </span>
                </span>
                <span className="gb-go" aria-hidden="true">
                  <Glyph name="arrow" size={14} />
                </span>
              </a>
            </li>
          );
        })}
      </ul>
      {hasNextPage && (
        <button
          type="button"
          className="gb-more"
          disabled={isFetching}
          onClick={() => void fetchNextPage()}
        >
          Show more
        </button>
      )}
    </>
  );
}

export function InverseMore({
  group,
  centre,
}: {
  group: GroupPlan;
  centre: { entry: TypeEntry; key: string };
}) {
  const [open, setOpen] = useState(false);
  const inv = inverseOf(centre.entry.module, centre.entry.type.name, group.field);
  if (!inv) return <p className="gb-none">Showing the first {MAX_KEYS}.</p>;
  if (!open)
    return (
      <button type="button" className="gb-more" onClick={() => setOpen(true)}>
        Show more
      </button>
    );
  return <More entry={centre.entry} inv={inv} group={group} centreKey={centre.key} />;
}
