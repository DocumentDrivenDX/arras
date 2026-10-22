// SPDX-License-Identifier: MIT OR Apache-2.0
import { createContext, useContext } from "react";
import type { MetaData } from "../api/types";
import type { LinkTo } from "../kit";
import { type ExploreLocation, formatExplore } from "./location";

export interface BrowserContext {
  meta: MetaData;
  /** Open a location (the fragment, or the host's `onLocation`). */
  go: (loc: ExploreLocation, opts?: { replace?: boolean }) => void;
  /** The host's offer of the writes to this viewer (an operator): edit, Retire, Actions and New (CONTRACT-010 E, F). */
  canEdit: boolean;
  /** Edit mode: the edit controls show only while it is on, and it is on only where `canEdit`. */
  editing: boolean;
  setEditing: (on: boolean) => void;
  /** The link into Operate, present only where the shell offers it to this viewer (Rule 7). */
  toOperate?: LinkTo;
}

const Ctx = createContext<BrowserContext | null>(null);
export const BrowserProvider = Ctx.Provider;

export function useBrowser(): BrowserContext {
  const c = useContext(Ctx);
  if (!c) throw new Error("Graph Browser parts must be rendered inside <GraphBrowser>");
  return c;
}

/** A plain click goes through the browser's router; a modified click (new tab) keeps the link. */
export function linkProps(go: (loc: ExploreLocation) => void, loc: ExploreLocation) {
  return {
    href: formatExplore(loc),
    onClick: (e: React.MouseEvent) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      go(loc);
    },
  };
}
