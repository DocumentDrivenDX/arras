// SPDX-License-Identifier: MIT OR Apache-2.0
// The browser's location (ADR-024, CONTRACT-010 D): the node is in the URL fragment as
// `#/explore/<module>/<type>/<key>`, each segment percent-encoded; `.../<key>/history` is the
// entity's History panel, and a bare type list may carry its position as `?after=<key>` (a key,
// never search text). Nothing else is in the URL. View state (the search text, the chosen types,
// the scroll position) lives in the history entry's own state, never in any part of the URL. A host may own the location instead (`location`, `onLocation`).
import { useCallback, useEffect, useMemo, useState } from "react";

export interface ExploreLocation {
  module?: string;
  type?: string;
  key?: string;
  /** The entity's History panel: `#/explore/<module>/<type>/<key>/history`. */
  history?: boolean;
  /** A type list's position: `#/explore/<module>/<type>?after=<key>`. */
  after?: string;
}

/** What a fragment says: an Explore location, someone else's route, or one that does not parse. */
export type Parsed =
  | { kind: "explore"; loc: ExploreLocation }
  | { kind: "other" }
  | { kind: "invalid" };

export const EXPLORE = "explore";
/** An alias of the prefix (`browse`): accepted, and rewritten to `explore`. */
export const EXPLORE_ALIAS = "browse";

const HISTORY = "history";
const AFTER = "after=";

export function parseExplore(hash: string): Parsed {
  const full = hash.replace(/^#\/?/, "");
  const q = full.indexOf("?");
  const raw = q < 0 ? full : full.slice(0, q);
  const query = q < 0 ? undefined : full.slice(q + 1);
  const segments = raw === "" ? [] : raw.split("/");
  if (segments[0] !== EXPLORE && segments[0] !== EXPLORE_ALIAS) return { kind: "other" };
  const rest = segments.slice(1);
  if (rest.length > 4 || rest.some((s) => s === "")) return { kind: "invalid" };
  const history = rest.length === 4;
  if (history && rest[3] !== HISTORY) return { kind: "invalid" };
  if (
    query !== undefined &&
    (rest.length !== 2 ||
      !query.startsWith(AFTER) ||
      query.length === AFTER.length ||
      query.includes("&"))
  )
    return { kind: "invalid" };
  try {
    const [module, type, key] = rest.slice(0, 3).map((s) => decodeURIComponent(s));
    const loc: ExploreLocation = { module, type, key };
    if (history) loc.history = true;
    if (query !== undefined) loc.after = decodeURIComponent(query.slice(AFTER.length));
    return { kind: "explore", loc };
  } catch {
    return { kind: "invalid" };
  }
}

export function formatExplore(loc: ExploreLocation): string {
  const parts = [loc.module, loc.module ? loc.type : undefined, loc.type ? loc.key : undefined]
    .filter((x): x is string => !!x)
    .map(encodeURIComponent);
  const hasKey = parts.length === 3;
  if (hasKey && loc.history) parts.push(HISTORY);
  const path = `#/${[EXPLORE, ...parts].join("/")}`;
  return parts.length === 2 && loc.after
    ? `${path}?${AFTER}${encodeURIComponent(loc.after)}`
    : path;
}

export const sameLocation = (a: ExploreLocation, b: ExploreLocation) =>
  a.module === b.module &&
  a.type === b.type &&
  a.key === b.key &&
  !!a.history === !!b.history &&
  a.after === b.after;

// -- view state, in the history entry's own state ----------------------------------------------

export interface ViewState {
  text?: string;
  types?: string[];
  scroll?: number;
  /** The picture's hops: always 1 in this release. */
  hops?: number;
  /** This entry is an entity's History opened from the entity, so closing it goes back. */
  fromEntity?: boolean;
}

const GB = "gb";

export function readViewState(): ViewState {
  const s: unknown = window.history.state;
  const v = s && typeof s === "object" ? (s as Record<string, unknown>)[GB] : undefined;
  return v && typeof v === "object" ? (v as ViewState) : {};
}

/** Merge into the current history entry; the URL is not touched. */
export function saveViewState(patch: ViewState): void {
  const s: unknown = window.history.state;
  const base = s && typeof s === "object" ? (s as Record<string, unknown>) : {};
  const next = { ...base, [GB]: { ...readViewState(), ...patch } };
  window.history.replaceState(next, "");
}

// -- the router --------------------------------------------------------------------------------

export interface LocationProps {
  /** A host that owns the location passes it; the browser then neither reads nor writes the URL. */
  location?: ExploreLocation;
  /** Told of every move; `replace` says the entry is rewritten (Show next, Retire), not added. */
  onLocation?: (l: ExploreLocation, opts?: { replace?: boolean }) => void;
}

export interface Router {
  parsed: Parsed;
  go: (loc: ExploreLocation, opts?: { replace?: boolean }) => void;
}

const current = (): Parsed => parseExplore(window.location.hash);

export function useBrowserLocation({ location, onLocation }: LocationProps): Router {
  const controlled = location !== undefined;
  const [hashParsed, setHashParsed] = useState<Parsed>(current);
  useEffect(() => {
    if (controlled) return;
    const on = () => setHashParsed(current());
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => {
      window.removeEventListener("hashchange", on);
      window.removeEventListener("popstate", on);
    };
  }, [controlled]);
  const go = useCallback(
    (loc: ExploreLocation, opts?: { replace?: boolean }) => {
      onLocation?.(loc, opts);
      if (controlled) return;
      const hash = formatExplore(loc);
      if (opts?.replace) {
        window.history.replaceState(window.history.state, "", hash);
        setHashParsed(current());
      } else {
        window.location.hash = hash;
      }
    },
    [controlled, onLocation],
  );
  const parsed = useMemo<Parsed>(
    () => (controlled ? { kind: "explore", loc: location } : hashParsed),
    [controlled, location, hashParsed],
  );
  return { parsed, go };
}
