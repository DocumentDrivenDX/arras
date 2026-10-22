// SPDX-License-Identifier: MIT OR Apache-2.0
import { weftName, weftType } from "../api/gql";
import type { EntityTypeInfo, ModuleInfo } from "../api/types";
import { Button, Chip } from "../components/ui";
import { fmtTime } from "../lib/format";
import type { QueryHistoryEntry } from "./queryHistory";

const SCALARS = new Set(["string", "integer", "decimal", "boolean"]);

/** A type's columns a query can name, what only `x.*` returns, its relationships, and a starting query. */
function summaryOf(t: EntityTypeInfo, m: ModuleInfo) {
  const cols = t.properties
    .filter((p) => p.required && p.cardinality === "one" && SCALARS.has(p.type))
    .map((p) => p.name);
  const others = t.properties.filter((p) => !cols.includes(p.name)).map((p) => p.name);
  const rels = [
    ...m.relationships.filter((r) => r.source.includes(t.name)).map((r) => r.name),
    ...m.relationships.flatMap((r) => (r.inverse && r.target.includes(t.name) ? [r.inverse] : [])),
  ];
  const projection = cols.length ? cols.map((c) => `x.${weftName(c)}`).join(", ") : "x.*";
  return { cols, others, rels, projection };
}

/**
 * A starting statement for a type: its names as Weft quoted identifiers, in key order, with a LIMIT one row
 * over the page so that `truncated` says when the type holds more than a page.
 */
export function templateOf(type: EntityTypeInfo, projection: string, size: number): string {
  return `SELECT ${projection} FROM ${weftType(type.name)} x ORDER BY x.${weftName(type.key)} LIMIT ${size + 1}`;
}

function Listing({ label, names }: { label: string; names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div>
      {label}: <span className="arras-mono">{names.join(", ")}</span>
    </div>
  );
}

function TypeEntry({
  type,
  module,
  size,
  onInsert,
}: {
  type: EntityTypeInfo;
  module: ModuleInfo;
  size: number;
  onInsert: (sql: string) => void;
}) {
  const { cols, others, rels, projection } = summaryOf(type, module);
  const columns = templateOf(type, projection, size);
  const whole = templateOf(type, "x.*", size);
  return (
    <div data-testid="query-type">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="arras-mono rounded border border-strong bg-surface px-1.5 py-0.5 font-semibold hover:bg-surface2"
          title={`Put ${columns} in the editor`}
          onClick={() => onInsert(columns)}
        >
          {type.name}
        </button>
        <button
          type="button"
          className="arras-mono rounded border border-line px-1 py-0.5 text-muted hover:bg-surface2"
          aria-label={`Put every property of ${type.name} in the editor`}
          onClick={() => onInsert(whole)}
        >
          x.*
        </button>
      </div>
      <div className="mt-0.5 text-muted">
        <Listing label="columns" names={cols} />
        <Listing label="optional, not filtered" names={others} />
        <Listing label="relationships" names={rels} />
      </div>
    </div>
  );
}

/** "What can I query?": the viewed module's types, from the meta query the console already holds. */
export function QueryTypesPanel({
  module,
  pending,
  size,
  onInsert,
}: {
  module: ModuleInfo | undefined;
  pending: boolean;
  /** The rows a page shows: a template asks for one more. */
  size: number;
  onInsert: (sql: string) => void;
}) {
  return (
    <details className="border-b border-line px-3 py-2" data-testid="query-types">
      <summary className="cursor-pointer font-semibold">What can I query?</summary>
      {pending && <div className="mt-1 text-muted">Loading the schema…</div>}
      {module && (
        <div className="mt-1 space-y-2 text-[12px]">
          <p className="m-0 text-muted">
            Choose a type to put a query for it in the editor. Columns listed are required,
            single-valued scalars, which a filter may use; an optional one is selected but not
            filtered on; <span className="arras-mono">x.*</span> returns every property.
          </p>
          {module.entityTypes.length === 0 && (
            <div className="text-muted">{module.name} declares no types.</div>
          )}
          {module.entityTypes.map((t) => (
            <TypeEntry key={t.name} type={t} module={module} size={size} onInsert={onInsert} />
          ))}
        </div>
      )}
    </details>
  );
}

const oneLine = (sql: string) => sql.replace(/\s+/g, " ").trim();
const rowsText = (n: number) => `${n} ${n === 1 ? "row" : "rows"}`;

function HistoryEntry({
  entry: h,
  running,
  onChoose,
  onRunAgain,
}: {
  entry: QueryHistoryEntry;
  running: boolean;
  onChoose: (h: QueryHistoryEntry) => void;
  onRunAgain: (h: QueryHistoryEntry) => void;
}) {
  return (
    <li data-testid="history-entry" className="rounded border border-line p-1.5">
      <button
        type="button"
        className="block w-full text-left hover:bg-surface2"
        title="Put this query and its module in the editor without running it"
        onClick={() => onChoose(h)}
      >
        <span id={`query-h-${h.id}`} data-dd-privacy="mask" className="arras-mono block truncate">
          {oneLine(h.sql)}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <span className="arras-mono" data-testid="history-module" title="The module it read">
            {h.module}
          </span>
          <Chip tone={h.consistency === "bulk" ? "warn" : "ok"}>{h.consistency.toUpperCase()}</Chip>
          <time dateTime={h.at}>{fmtTime(h.at).slice(11)}</time>
          {h.outcome.kind === "rows" ? (
            <span>{rowsText(h.outcome.rows)}</span>
          ) : (
            <span className="text-bad">{h.outcome.reason}</span>
          )}
        </span>
      </button>
      <Button
        className="mt-1"
        aria-disabled={running || undefined}
        aria-describedby={`query-h-${h.id}`}
        onClick={() => !running && onRunAgain(h)}
      >
        Run again
      </Button>
    </li>
  );
}

/** This session's queries, newest first, held in memory only (OPR-17). */
export function QueryHistoryPanel({
  entries,
  running,
  onChoose,
  onRunAgain,
  onClear,
}: {
  entries: QueryHistoryEntry[];
  running: boolean;
  onChoose: (h: QueryHistoryEntry) => void;
  onRunAgain: (h: QueryHistoryEntry) => void;
  onClear: () => void;
}) {
  return (
    <section aria-labelledby="query-history-h" className="px-3 py-2" data-testid="query-history">
      <div className="mb-1 flex items-center gap-2">
        <h2 id="query-history-h" className="m-0 text-[13px] font-semibold">
          History
        </h2>
        <span className="text-[11px] text-muted">this session, in memory only</span>
        <Button
          className="ml-auto"
          aria-disabled={entries.length === 0 || undefined}
          onClick={() => entries.length > 0 && onClear()}
        >
          Clear history
        </Button>
      </div>
      {entries.length === 0 ? (
        <p className="m-0 text-muted" data-testid="query-history-empty">
          No queries run yet.
        </p>
      ) : (
        <ul className="m-0 list-none space-y-1.5 p-0">
          {entries.map((h) => (
            <HistoryEntry
              key={h.id}
              entry={h}
              running={running}
              onChoose={onChoose}
              onRunAgain={onRunAgain}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
