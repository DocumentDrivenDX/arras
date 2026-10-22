// SPDX-License-Identifier: MIT OR Apache-2.0
// A type's entities in key order, in pages of at most 50 (US-066-AC2). The list's address carries
// where it starts (`?after=<key>`); Show next moves that to the page just read, in place, so a
// refresh or a pasted link opens the list where the reader was.
import { useEffect, useRef, useState } from "react";
import { shortName } from "../api/gql";
import { evaluate, titleOf, valueText } from "../lib/template";
import { useBrowser } from "./context";
import { EntityRow, type RowData } from "./EntityRow";
import { takeListFocus } from "./focusAfter";
import type { TypeEntry } from "./meta";
import { NewEntity } from "./NewEntity";
import { ModelLink } from "./OperateLinks";
import { BackendDown, Failed, Skeleton } from "./states";
import { stateOf } from "./useNode";
import { type ListPage, PAGE, useTypeList } from "./useTypeList";

export function toRow(entry: TypeEntry, item: Record<string, unknown>): RowData {
  const key = String(item.key);
  const summary = entry.view.summary
    ? evaluate(entry.view.summary, (n) => valueText(item[n])).trim()
    : "";
  return { key, title: titleOf(entry.view.title, item, key), summary, fields: item };
}

const lastKey = (page: ListPage | undefined) => {
  const key = page?.items.at(-1)?.key;
  return key == null ? undefined : String(key);
};

/**
 * Where the list starts, and the address that says so. A start the list wrote to the address itself
 * keeps what has been read; any other change of the address (Back, a pasted link) starts the list again.
 */
function useListPosition(entry: TypeEntry, after: string | undefined) {
  const { go } = useBrowser();
  const [pos, setPos] = useState({ start: after, at: after });
  if (after !== pos.at) setPos({ start: after, at: after });
  const q = useTypeList(entry, pos.start);
  const count = q.data?.pages.length;
  // The page just read began after the last key of the page before it: that is the new position.
  const before = count && count > 1 ? lastKey(q.data?.pages[count - 2]) : undefined;
  const seen = useRef<{ start: string | undefined; count: number | undefined }>(undefined);
  const { start } = pos;
  const module = entry.module.name;
  const type = shortName(entry.type.name);
  useEffect(() => {
    const was = seen.current;
    seen.current = { start, count };
    if (!was || was.start !== start || !count || !was.count || count <= was.count || !before)
      return;
    setPos((p) => ({ ...p, at: before }));
    go({ module, type, after: before }, { replace: true });
  }, [start, count, before, go, module, type]);
  return q;
}

export function TypeList({ entry, after }: { entry: TypeEntry; after?: string }) {
  const q = useListPosition(entry, after);
  const heading = `gb-list-${entry.type.name}`;
  const ready = !q.isPending && !q.error;
  useEffect(() => {
    if (ready && takeListFocus()) document.getElementById(heading)?.focus();
  }, [ready, heading]);
  if (q.isPending) return <Skeleton />;
  if (q.error) {
    const s = stateOf(q.error);
    return s.status === "down" ? (
      <BackendDown backend={s.backend} onRetry={() => void q.refetch()} />
    ) : (
      <Failed onRetry={() => void q.refetch()} />
    );
  }
  const items = q.data.pages.flatMap((p) => p.items);
  return (
    <section aria-labelledby={heading}>
      <div className="gb-list-head">
        <h2 className="gb-list-h" id={heading} tabIndex={-1}>
          {entry.view.pluralLabel}
        </h2>
        <ModelLink entry={entry} />
        <NewEntity entry={entry} />
      </div>
      <p className="gb-note-line" role="status">
        {items.length} {items.length === 1 ? entry.view.label : entry.view.pluralLabel}{" "}
        {q.hasNextPage ? "so far, in key order" : "in key order"}
      </p>
      {items.length === 0 ? (
        <p className="gb-none">There are none.</p>
      ) : (
        <ul className="gb-hits">
          {items.map((item) => (
            <li key={String(item.key)}>
              <EntityRow entry={entry} row={toRow(entry, item)} />
            </li>
          ))}
        </ul>
      )}
      {q.hasNextPage && (
        <button
          type="button"
          className="gb-btn"
          disabled={q.isFetchingNextPage}
          title={q.isFetchingNextPage ? "Loading the next page" : undefined}
          onClick={() => void q.fetchNextPage()}
        >
          Show next {PAGE}
        </button>
      )}
    </section>
  );
}
