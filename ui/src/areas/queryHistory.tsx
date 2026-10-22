// SPDX-License-Identifier: MIT OR Apache-2.0
import {
  createContext,
  type MutableRefObject,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type { QueryConsistency } from "../api/types";

/** The most entries the history keeps; the oldest is dropped (US-078). */
export const HISTORY_MAX = 50;

export type QueryOutcome = { kind: "rows"; rows: number } | { kind: "failed"; reason: string };

export interface QueryHistoryEntry {
  id: number;
  /** The module the statement read: running it again reads the same one (OPR-17). */
  module: string;
  sql: string;
  consistency: QueryConsistency;
  /** When it ran (ISO 8601). */
  at: string;
  outcome: QueryOutcome;
}

/** What the editor holds, kept above the Query area so that moving between tabs does not lose a draft. */
export interface QueryDraft {
  sql: string;
  consistency: QueryConsistency;
  /** The module the text reads when it came from a history entry; absent, the module being viewed. */
  module?: string;
}

export interface QuerySession {
  /** Newest first. */
  entries: QueryHistoryEntry[];
  draft: QueryDraft;
  setDraft: (d: QueryDraft) => void;
  /** Add a run. The same module, text and consistency as the newest entry replaces it (listed once, latest time). */
  record: (e: Omit<QueryHistoryEntry, "id">) => void;
  clear: () => void;
  /** The last starter the area handled, so remounting the area with the same starter does not apply it twice. */
  starterSeen: MutableRefObject<unknown>;
}

/**
 * The session's query history and draft, in memory only (OPR-17, OPR-07): React state, never `localStorage`,
 * `sessionStorage`, IndexedDB, a cookie or a URL. It lives in whatever component calls this hook; the console's
 * shell calls it, so it survives moving between the console's tabs and is gone when the console is mounted
 * afresh (a reload, or another person chosen, which remounts the console).
 */
export function useQuerySessionState(): QuerySession {
  const [entries, setEntries] = useState<QueryHistoryEntry[]>([]);
  const [draft, setDraft] = useState<QueryDraft>({ sql: "", consistency: "latest" });
  const record = useCallback((e: Omit<QueryHistoryEntry, "id">) => {
    setEntries((list) => {
      const next = { ...e, id: (list[0]?.id ?? 0) + 1 };
      const rest =
        list[0] &&
        list[0].module === e.module &&
        list[0].sql === e.sql &&
        list[0].consistency === e.consistency
          ? list.slice(1)
          : list;
      return [next, ...rest].slice(0, HISTORY_MAX);
    });
  }, []);
  const clear = useCallback(() => setEntries([]), []);
  const starterSeen = useRef<unknown>(null);
  return useMemo(
    () => ({ entries, draft, setDraft, record, clear, starterSeen }),
    [entries, draft, record, clear],
  );
}

const Ctx = createContext<QuerySession | null>(null);

export function QuerySessionProvider({
  session,
  children,
}: {
  session: QuerySession;
  children: ReactNode;
}) {
  return <Ctx.Provider value={session}>{children}</Ctx.Provider>;
}

/** The session held above the area, or (a host mounting the area alone) one of the area's own. */
export function useQuerySession(): QuerySession {
  const own = useQuerySessionState();
  return useContext(Ctx) ?? own;
}
