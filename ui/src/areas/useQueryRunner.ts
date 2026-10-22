// SPDX-License-Identifier: MIT OR Apache-2.0
import { useRef, useState } from "react";
import { useClient } from "../api/context";
import { ApiError, describeError } from "../api/errors";
import { QUERY_MAX_CHARS, type QueryConsistency, type QueryResult } from "../api/types";
import type { QueryHistoryEntry } from "./queryHistory";

/** The surface's bound counts characters, not UTF-16 units. */
export const chars = (s: string) => Array.from(s).length;

/** The words a history entry keeps of a failure: its kind and status, never the body. */
function reasonOf(e: unknown): string {
  const t = describeError(e).title;
  return e instanceof ApiError && e.status ? `${t} (${e.status})` : t;
}

export interface Ran {
  module: string;
  sql: string;
  consistency: QueryConsistency;
}

/**
 * Runs a statement over the viewed module (US-077): the text that was run is kept; a new run clears the previous
 * grid and error; an answer that arrives after a newer request started is dropped. A next page is the statement's
 * own (a keyset predicate), so there is no cursor to follow. Each run is recorded in the history with its outcome.
 */
export function useQueryRunner(
  module: string,
  size: number,
  record: (e: Omit<QueryHistoryEntry, "id">) => void,
) {
  const client = useClient();
  const [ran, setRan] = useState<Ran | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  const seq = useRef(0);

  /** Run `text` over `over` (the viewed module unless a history entry names its own). */
  async function run(text: string, consistency: QueryConsistency, over: string = module) {
    if (running || text.trim() === "" || chars(text) > QUERY_MAX_CHARS) return;
    const id = ++seq.current;
    const module = over;
    setRan({ module, sql: text, consistency });
    setResult(null);
    setFailure(null);
    setRunning(true);
    const at = new Date().toISOString();
    try {
      const r = await client.query({ module, sql: text, consistency, limit: size });
      record({
        module,
        sql: text,
        consistency,
        at,
        outcome: { kind: "rows", rows: r.rows.length },
      });
      if (id === seq.current) setResult(r);
    } catch (e) {
      record({
        module,
        sql: text,
        consistency,
        at,
        outcome: { kind: "failed", reason: reasonOf(e) },
      });
      if (id === seq.current) setFailure(e ?? new Error("failed"));
    } finally {
      if (id === seq.current) setRunning(false);
    }
  }

  return { ran, result, failure, running, run };
}
