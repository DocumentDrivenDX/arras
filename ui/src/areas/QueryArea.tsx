// SPDX-License-Identifier: MIT OR Apache-2.0
import { useCallback, useMemo, useRef } from "react";
import { useModule } from "../api/queries";
import { QUERY_MAX_LIMIT } from "../api/types";
import { Empty, Notice } from "../components/ui";
import { keyColumn, keyedType } from "../lib/queryKeys";
import { QueryEditor } from "./QueryEditor";
import { QueryError } from "./QueryError";
import { type KeyLink, QueryGrid } from "./QueryGrid";
import { QueryHistoryPanel, QueryTypesPanel } from "./QueryPanels";
import { liveText, ownerOf, QueryInfoBar } from "./QueryResultBar";
import { type QueryHistoryEntry, useQuerySession } from "./queryHistory";
import { chars, useQueryRunner } from "./useQueryRunner";
import { type QueryStarter, StarterOffer, useQueryStarter } from "./useQueryStarter";

export interface QueryAreaProps {
  /** The module being viewed: the statement reads it, and the "What can I query?" panel lists its types. */
  module: string;
  /** Rows per page, 1 to 100 (default 100). */
  pageSize?: number;
  /** Opens the editor on a starter statement for a type, without running it (see `useQueryStarter`). */
  starter?: QueryStarter;
  /** A result cell holding an entity key opens that entity: `type` is the qualified type name. */
  onOpenEntity?: (type: string, key: string) => void;
}

/** US-077: write a read-only query, choose how current the answer must be, read it as a grid. US-078: this session's history. */
export function QueryArea({
  module: name,
  pageSize = QUERY_MAX_LIMIT,
  starter,
  onOpenEntity,
}: QueryAreaProps) {
  const session = useQuerySession();
  const { module: viewed, meta } = useModule(name);
  const { sql, consistency } = session.draft;
  const target = session.draft.module ?? name; // a history entry's own module, else the viewed one
  const size = Math.max(1, Math.min(QUERY_MAX_LIMIT, Math.floor(pageSize)));
  const { ran, result, failure, running, run } = useQueryRunner(name, size, session.record);
  const input = useRef<HTMLTextAreaElement | null>(null);
  const focusInput = useCallback(() => input.current?.focus(), []);
  const offered = useQueryStarter(session, starter, viewed, focusInput);
  // the key column of a statement that reads one known type of the viewed module links to that entity
  const keyLink = useMemo<KeyLink | undefined>(() => {
    if (!(onOpenEntity && ran && result && viewed)) return undefined;
    const type = keyedType(ran.sql, ran.module, viewed.entityTypes);
    const column = keyColumn(result.columns, type);
    return type && column ? { column, type: type.name, onOpen: onOpenEntity } : undefined;
  }, [onOpenEntity, ran, result, viewed]);

  // a template is for the viewed module; a history entry brings its own (US-078-AC2)
  const putInEditor = (text: string, c = consistency, module?: string) => {
    session.setDraft({ sql: text, consistency: c, module });
    input.current?.focus();
  };
  const choose = (h: QueryHistoryEntry) => putInEditor(h.sql, h.consistency, h.module);
  const runAgain = (h: QueryHistoryEntry) => {
    session.setDraft({ sql: h.sql, consistency: h.consistency, module: h.module });
    void run(h.sql, h.consistency, h.module); // the module it read, whichever is viewed now
  };

  const owner = ownerOf(meta.data?.modules ?? [], result?.freshness ?? null, viewed);

  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row" data-testid="query-area">
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="query-live"
      >
        {liveText(running, result)}
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <QueryEditor
          module={target}
          draft={session.draft}
          onDraft={session.setDraft}
          count={chars(sql)}
          running={running}
          inputRef={input}
          onRun={() => void run(sql, consistency, target)}
        />
        {offered.offer && (
          <StarterOffer
            type={offered.offer.type}
            onAccept={offered.accept}
            onDismiss={offered.dismiss}
          />
        )}
        {failure !== null && <QueryError error={failure} />}
        {result && <QueryInfoBar result={result} owner={owner} />}
        {result?.truncated && (
          <div className="px-3 pt-1.5" data-testid="query-truncated">
            <Notice tone="warn">
              Truncated: the limit cut the rows. A next page is the statement&apos;s own: add a
              keyset on the type&apos;s key, such as{" "}
              <span className="arras-mono">WHERE x.&quot;&lt;key&gt;&quot; &gt; :last</span>, with
              the same ORDER BY and LIMIT.
            </Notice>
          </div>
        )}
        {running && !result && <div className="p-3 text-muted">Running the query…</div>}
        {result && result.rows.length > 0 && (
          <QueryGrid columns={result.columns} rows={result.rows} keyLink={keyLink} />
        )}
        {result && result.rows.length === 0 && (
          <Empty title="No rows">The query ran and nothing matched.</Empty>
        )}
        {!(result || running || failure) && (
          <Empty title="Nothing run yet">
            Write a query, or pick a type from the help panel, and run it.
          </Empty>
        )}
      </div>
      <aside
        aria-label="Query help and history"
        className="flex w-full shrink-0 flex-col overflow-auto border-t border-line bg-surface md:w-72 md:border-l md:border-t-0"
      >
        <QueryTypesPanel
          module={viewed}
          pending={meta.isPending}
          size={size}
          onInsert={(text) => putInEditor(text)}
        />
        <QueryHistoryPanel
          entries={session.entries}
          running={running}
          onChoose={choose}
          onRunAgain={runAgain}
          onClear={session.clear}
        />
      </aside>
    </div>
  );
}
