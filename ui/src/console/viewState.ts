// SPDX-License-Identifier: MIT OR Apache-2.0
import { useState } from "react";
import type { ChangedBy } from "../areas/GraphArea";

/**
 * What the console holds in memory. The open entity, the graph selection, the audit-history entity
 * and the action prefill are not here: they are in the route (`route.ts`), so a refresh, Back and a
 * shared link restore them.
 */
export interface ViewState {
  /** The last action opened, so the Actions tab returns to it. */
  lastAction: string | undefined;
  setLastAction: (a: string | undefined) => void;
  /** A type to show alone in the graph, from the UMF source view; for that visit only. */
  graphType: string | null;
  setGraphType: (t: string | null) => void;
  /** The change to outline in the graph, from an applied action. */
  changed: ChangedBy | null;
  setChanged: (c: ChangedBy | null) => void;
}

export function useViewState(): ViewState {
  const [lastAction, setLastAction] = useState<string | undefined>();
  const [graphType, setGraphType] = useState<string | null>(null);
  const [changed, setChanged] = useState<ChangedBy | null>(null);
  return { lastAction, setLastAction, graphType, setGraphType, changed, setChanged };
}
