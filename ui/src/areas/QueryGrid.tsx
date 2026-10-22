// SPDX-License-Identifier: MIT OR Apache-2.0
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";
import type { QueryColumn } from "../api/types";
import { fmtTime, isNumeric, keyed } from "../lib/format";

/** What a cell shows is capped, and its title more tightly, so one huge value cannot make the page unusable. */
export const CELL_MAX_CHARS = 10_000;
export const TITLE_MAX_CHARS = 500;
function cap(text: string, max: number): { text: string; cut: boolean } {
  if (text.length <= max) return { text, cut: false };
  let end = max;
  const last = text.charCodeAt(end - 1);
  if (last >= 0xd800 && last <= 0xdbff) end--; // never end on half a pair
  return { text: `${text.slice(0, end)}…`, cut: true };
}
const titleOf = (text: string) => cap(text, TITLE_MAX_CHARS).text;

function Shown({ text }: { text: string }) {
  const c = cap(text, CELL_MAX_CHARS);
  return (
    <>
      {c.text}
      {c.cut && <span className="ml-1 text-muted">[truncated in view]</span>}
    </>
  );
}

/** A cell's text, for its title and for the clipped display. */
function textOf(col: QueryColumn, v: unknown): string {
  if (Array.isArray(v))
    return v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(", ");
  if (typeof v === "string") return col.type === "timestamp" ? fmtTime(v) : v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

/** The cell's content and title, by what the value is: null, a list, empty text, or text. */
function shownValue(
  col: QueryColumn,
  value: unknown,
): { title: string; className: string; body: ReactNode } {
  if (value === null || value === undefined) {
    return { title: "null", className: "", body: <i className="text-muted">null</i> };
  }
  if (Array.isArray(value)) {
    const text = textOf(col, value);
    return {
      title: titleOf(text) || "empty list",
      className: "arras-mono",
      body: value.length === 0 ? <span className="text-muted">(none)</span> : <Shown text={text} />,
    };
  }
  if (value === "")
    return { title: "empty text", className: "", body: <span className="text-muted">""</span> };
  const text = textOf(col, value);
  const num = col.scalar && isNumeric(col.type);
  return { title: titleOf(text), className: num ? "num" : "", body: <Shown text={text} /> };
}

/** The first cell of a row holds its one tab stop: a button that opens the row (shows all its text). */
interface RowStop {
  tabbable: boolean;
  open: boolean;
  setRef: (el: HTMLButtonElement | null) => void;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void;
  onFocus: () => void;
  onToggle: () => void;
}

/** The result's key column, resolved to the type whose key it holds (see `keyedType`): its cells open the entity. */
export interface KeyLink {
  column: string;
  /** The qualified type name. */
  type: string;
  onOpen: (type: string, key: string) => void;
}

/** A key cell's own link, beside the cell's text (which may be the row's tab stop). The key is only text. */
function OpenKey({ link, value }: { link: KeyLink; value: unknown }) {
  if ((typeof value !== "string" && typeof value !== "number") || value === "") return null;
  const key = String(value);
  const label = `Open ${link.type.slice(link.type.lastIndexOf(".") + 1)} ${titleOf(key)}`;
  return (
    <button
      type="button"
      className="shrink-0 p-0 leading-none text-accent underline"
      data-testid="query-key-link"
      aria-label={label}
      title={label}
      onClick={() => link.onOpen(link.type, key)}
    >
      <span aria-hidden="true">↗</span>
    </button>
  );
}

function Cell({
  col,
  value,
  stop,
  link,
}: {
  col: QueryColumn;
  value: unknown;
  stop?: RowStop;
  link?: KeyLink;
}) {
  const { title, className, body } = shownValue(col, value);
  return (
    <td title={title} className={className}>
      {/* The key's link sits beside its text on one line, so a linked row is as tall as any other. */}
      <div className={link ? "flex items-baseline gap-1" : undefined}>
        {stop ? (
          <button
            type="button"
            className="arras-cell-button"
            data-row-stop
            ref={stop.setRef}
            tabIndex={stop.tabbable ? 0 : -1}
            aria-expanded={stop.open}
            onKeyDown={stop.onKeyDown}
            onFocus={stop.onFocus}
            onClick={stop.onToggle}
          >
            {body}
          </button>
        ) : (
          body
        )}
        {link && <OpenKey link={link} value={value} />}
      </div>
    </td>
  );
}

/**
 * A query's answer as a table: one column per `columns[]` in order, a sticky header, null apart from empty text,
 * a list as joined text, a number aligned right, long text clipped with the value in the cell's title. The first
 * cell of each row is its one tab stop (Up, Down, Home, End move between rows); Enter or a click opens the row, and
 * a row with focus shows its whole text. Read-only: there is no cell editing.
 */
export function QueryGrid({
  columns,
  rows,
  label = "Query result",
  keyLink,
}: {
  columns: QueryColumn[];
  rows: Record<string, unknown>[];
  label?: string;
  /** Present when the statement reads one known type: its key column's cells link to the entity. */
  keyLink?: KeyLink;
}) {
  const [focus, setFocus] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const stops = useRef<(HTMLButtonElement | null)[]>([]);
  const cols = useMemo(() => keyed(columns, (c) => c.name), [columns]);
  const keyedRows = useMemo(() => keyed(rows, (r) => JSON.stringify(r)), [rows]);
  const go = (i: number) => {
    const n = Math.max(0, Math.min(rows.length - 1, i));
    setFocus(n);
    stops.current[n]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const target = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: rows.length - 1 }[e.key];
    if (target === undefined) return;
    e.preventDefault();
    go(target);
  };
  return (
    <div className="min-h-0 flex-1 overflow-auto bg-surface" data-testid="query-scroll">
      <table className="arras-table arras-query" aria-label={label} aria-rowcount={rows.length + 1}>
        <thead>
          <tr>
            {cols.map(({ key, item: c }) => (
              <th
                key={key}
                scope="col"
                className={c.scalar && isNumeric(c.type) ? "num" : ""}
                title={`${c.name} (${c.type})`}
              >
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keyedRows.map(({ key: rowKey, item: row }, i) => (
            <tr
              key={rowKey}
              aria-rowindex={i + 2}
              data-open={open === rowKey || undefined}
              data-testid="query-row"
            >
              {cols.map(({ key, item: c }, ci) => (
                <Cell
                  key={key}
                  col={c}
                  value={row[c.name]}
                  link={keyLink && c.name === keyLink.column ? keyLink : undefined}
                  stop={
                    ci === 0
                      ? {
                          tabbable: i === Math.min(focus, rows.length - 1),
                          open: open === rowKey,
                          setRef: (el) => {
                            stops.current[i] = el;
                          },
                          onKeyDown: (e) => onKey(e, i),
                          onFocus: () => setFocus(i),
                          onToggle: () => setOpen(open === rowKey ? null : rowKey),
                        }
                      : undefined
                  }
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
