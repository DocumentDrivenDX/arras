// SPDX-License-Identifier: MIT OR Apache-2.0
import type { KeyboardEvent, RefObject } from "react";
import { useId } from "react";
import { QUERY_MAX_CHARS, type QueryConsistency } from "../api/types";
import { Button } from "../components/ui";
import type { QueryDraft } from "./queryHistory";

const fmt = (n: number) => n.toLocaleString("en-US");

function ConsistencyChoice({
  value,
  onChange,
}: {
  value: QueryConsistency;
  onChange: (c: QueryConsistency) => void;
}) {
  return (
    <fieldset aria-label="Consistency" className="m-0 flex min-w-0 border-0 p-0">
      {(["latest", "bulk"] as const).map((c) => (
        <button
          key={c}
          type="button"
          aria-pressed={value === c}
          onClick={() => onChange(c)}
          title={c === "latest" ? "Read the record store" : "Read the replica (may lag)"}
          className={`border border-strong px-2 py-0.5 text-[12px] first:rounded-l last:rounded-r ${value === c ? "bg-accent text-accentfg" : "bg-surface text-fg hover:bg-surface2"}`}
        >
          {c.toUpperCase()}
        </button>
      ))}
    </fieldset>
  );
}

/** The query box: text, consistency, a character counter against the surface's bound, and Run (Ctrl or Cmd+Enter). */
export function QueryEditor({
  module,
  draft,
  onDraft,
  count,
  running,
  inputRef,
  onRun,
}: {
  module: string;
  draft: QueryDraft;
  onDraft: (d: QueryDraft) => void;
  /** The text's length in characters. */
  count: number;
  running: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onRun: () => void;
}) {
  const inputId = useId();
  const countId = useId();
  const over = count > QUERY_MAX_CHARS;
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onRun();
    }
  };
  return (
    <form
      className="border-b border-line bg-surface px-3 py-2"
      onSubmit={(e) => {
        e.preventDefault();
        onRun();
      }}
    >
      <label
        htmlFor={inputId}
        className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-muted"
      >
        Query (Weft SQL, read-only)
      </label>
      <p className="m-0 mb-1 text-[11px] text-muted" data-testid="query-module">
        reads module <span className="arras-mono">{module}</span>
      </p>
      <textarea
        id={inputId}
        ref={inputRef}
        data-testid="query-input"
        className="arras-mono block min-h-[4.5rem] w-full resize-y rounded border border-strong bg-surface p-2 text-fg"
        rows={4}
        spellCheck={false}
        data-dd-privacy="mask"
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        aria-describedby={countId}
        aria-invalid={over}
        placeholder={`SELECT u.code, u.name FROM ${module}.<Type> u`}
        value={draft.sql}
        onChange={(e) => onDraft({ ...draft, sql: e.target.value })}
        onKeyDown={onKey}
      />
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <ConsistencyChoice
          value={draft.consistency}
          onChange={(consistency) => onDraft({ ...draft, consistency })}
        />
        <Button
          type="submit"
          variant="primary"
          aria-disabled={running || draft.sql.trim() === "" || over || undefined}
          data-testid="query-run"
        >
          {running ? "Running…" : "Run"}
        </Button>
        <span className="text-[11px] text-muted">
          <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Enter</kbd> runs
        </span>
        <span
          id={countId}
          data-testid="query-chars"
          className={`ml-auto text-[11px] ${over ? "font-semibold text-bad" : "text-muted"}`}
        >
          {fmt(count)} / {fmt(QUERY_MAX_CHARS)} characters
        </span>
      </div>
      {over && (
        <div role="alert" data-testid="query-too-long" className="mt-1 text-[12px] text-bad">
          The query is {fmt(count - QUERY_MAX_CHARS)} characters over the {fmt(QUERY_MAX_CHARS)}
          -character limit. Shorten it to run it.
        </div>
      )}
    </form>
  );
}
