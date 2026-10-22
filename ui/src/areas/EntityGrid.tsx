// SPDX-License-Identifier: MIT OR Apache-2.0
import type { KeyboardEvent, ReactNode, RefObject } from "react";
import type { Column } from "../api/gql";
import type { Ref } from "../api/types";
import { CueScroll } from "../components/CueScroll";
import { Empty, Spinner } from "../components/ui";
import { fmtTime, fmtValue, isNumeric } from "../lib/format";
import { ariaSort, type Sort } from "./pageSort";

/** The first cell of a row holds its one tab stop: a button that looks like the cell's text. */
export interface RowStop {
  index: number;
  tabbable: boolean;
  selected: boolean;
  onKeyDown: (e: KeyboardEvent<HTMLButtonElement>, index: number) => void;
}

function CellBody({ stop, children }: { stop?: RowStop; children: ReactNode }) {
  if (!stop) return children;
  return (
    <button
      type="button"
      className="arras-cell-button"
      data-row-stop
      tabIndex={stop.tabbable ? 0 : -1}
      aria-current={stop.selected ? "true" : undefined}
      onKeyDown={(e) => stop.onKeyDown(e, stop.index)}
    >
      {children}
    </button>
  );
}

function RelCell({ raw, stop }: { raw: unknown; stop?: RowStop }) {
  const refs = (raw as Ref[] | null) ?? [];
  const text = refs.map((r) => r.key).join(", ");
  let body: ReactNode = text;
  if (refs.length === 0) body = <span className="text-muted">—</span>;
  else if (refs.length > 3) body = `${refs.length} keys`;
  return (
    <td title={text} className="arras-mono">
      <CellBody stop={stop}>{body}</CellBody>
    </td>
  );
}

function Cell({ col, raw, stop }: { col: Column; raw: unknown; stop?: RowStop }) {
  if (col.kind === "rel") return <RelCell raw={raw} stop={stop} />;
  const text = col.type === "timestamp" ? fmtTime(raw as string) : fmtValue(raw);
  const num = isNumeric(col.type);
  return (
    <td
      title={text}
      className={`${num ? "num" : ""} ${col.kind === "key" ? "arras-mono font-semibold" : ""}`}
    >
      <CellBody stop={stop}>
        {raw === null || raw === undefined ? <span className="text-muted">—</span> : text}
      </CellBody>
    </td>
  );
}

export interface GridProps {
  typeName: string;
  visible: Column[];
  items: Record<string, unknown>[];
  focus: number;
  selectedKey?: string | null;
  draft: Record<string, string>;
  hasFilter: boolean;
  pending: boolean;
  failed: boolean;
  hasErrors: boolean;
  sort: Sort | null;
  filterName: (c: Column) => string | null;
  firstFilterCol: Column | undefined;
  filterRef: RefObject<HTMLInputElement | null>;
  onSort: (c: Column) => void;
  onRowKey: (e: KeyboardEvent<HTMLButtonElement>, index: number) => void;
  onFilterEscape: () => void;
  onDraft: (name: string, value: string) => void;
  onApplyFilter: () => void;
  onRowClick: (i: number, key: string) => void;
}

function FilterCell({ c, fname, p }: { c: Column; fname: string | null; p: GridProps }) {
  if (!fname) return <th />;
  return (
    <th>
      <input
        ref={c === p.firstFilterCol ? p.filterRef : undefined}
        aria-label={`Filter ${c.label}`}
        placeholder={c.kind === "rel" ? "= key" : "="}
        className="w-full min-w-16 rounded border border-line bg-surface px-1 py-0.5 text-[12px] font-normal text-fg"
        value={p.draft[fname] ?? ""}
        onChange={(e) => p.onDraft(fname, e.target.value)}
        onBlur={p.onApplyFilter}
        onKeyDown={(e) => {
          if (e.key === "Enter") p.onApplyFilter();
          if (e.key === "Escape") p.onFilterEscape();
        }}
      />
    </th>
  );
}

/** A column header: its label as a button that sorts this page by the column (the list read has no other order). */
function HeaderCell({ c, p }: { c: Column; p: GridProps }) {
  const dir = ariaSort(p.sort, c.id);
  return (
    <th
      scope="col"
      aria-sort={dir}
      className={isNumeric(c.type) ? "num" : ""}
      title={`${c.label}: sorts this page`}
    >
      <button type="button" className="arras-sort" onClick={() => p.onSort(c)}>
        {c.label}
        <span aria-hidden="true">{{ ascending: "▲", descending: "▼", none: "" }[dir]}</span>
      </button>
    </th>
  );
}

function GridEmpty({ typeName, hasFilter }: { typeName: string; hasFilter: boolean }) {
  return (
    <Empty title={hasFilter ? "No entries match the filter" : `No ${typeName} entries`}>
      {hasFilter
        ? "Equality filters match whole values."
        : "This type has no entries in this read."}
    </Empty>
  );
}

export function Grid(p: GridProps) {
  const showEmpty = !p.pending && p.items.length === 0 && !p.failed && !p.hasErrors;
  return (
    <CueScroll
      className="arras-cue-table min-h-0 flex-1 bg-surface"
      scrollerClass="min-h-0 flex-1 overflow-auto"
      scrollerTestId="grid-scroll"
      deps={[p.visible.length, p.items.length]}
    >
      <table className="arras-table" aria-label={`${p.typeName} table`}>
        <thead>
          <tr>
            {p.visible.map((c) => (
              <HeaderCell key={c.id} c={c} p={p} />
            ))}
          </tr>
          <tr className="filters">
            {p.visible.map((c) => (
              <FilterCell key={c.id} c={c} fname={p.filterName(c)} p={p} />
            ))}
          </tr>
        </thead>
        <tbody>
          {p.items.map((row, i) => (
            <tr
              key={String(row.key)}
              className={i === p.focus ? "focused cursor-pointer" : "cursor-pointer"}
              onClick={() => p.onRowClick(i, String(row.key))}
            >
              {p.visible.map((c, ci) => (
                <Cell
                  key={c.id}
                  col={c}
                  raw={row[c.field]}
                  stop={
                    ci === 0
                      ? {
                          index: i,
                          tabbable: i === p.focus,
                          selected: p.selectedKey === String(row.key),
                          onKeyDown: p.onRowKey,
                        }
                      : undefined
                  }
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {p.pending && <Spinner label="Loading rows" />}
      {showEmpty && <GridEmpty typeName={p.typeName} hasFilter={p.hasFilter} />}
    </CueScroll>
  );
}
