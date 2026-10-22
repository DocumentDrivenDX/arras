// SPDX-License-Identifier: MIT OR Apache-2.0
// The document title names the place, most specific first, with the brand last. A node read that is
// loading is the type, the module and the brand: the key never enters the title. A readable entity
// is its title, then the type, the module and the brand. The chooser and a page that is not
// available (an unknown module or type, an unreadable or absent key) carry the brand alone.
import type { MetaData } from "../api/types";
import { titleName, useBrand } from "../lib/brand";
import { joinTitle, moduleTitle, useDocumentTitle } from "../lib/documentTitle";
import { findType } from "./meta";
import { entityTitle } from "./NodeCard";
import type { Resolved } from "./resolve";
import { type NodeState, useNode } from "./useNode";

/** The title of a resolved location: the pure rule `usePageTitle` applies; `state` is the node's read. */
export function browseTitle(
  brand: string,
  meta: MetaData | undefined,
  resolved: Resolved | undefined,
  state: NodeState,
): string {
  const node = resolved?.kind === "node" ? resolved : undefined;
  let parts: (string | undefined)[] = [];
  if (node && state.status !== "na") {
    const { entry, key } = node;
    const place = [entry.view.pluralLabel, moduleTitle(entry.module)];
    parts =
      state.status === "ready" ? [entityTitle(entry.view, state.entity, key), ...place] : place;
  } else if (resolved?.kind === "entry") {
    const { module, type } = resolved;
    const listed = meta && type ? findType(meta, module.name, type) : undefined;
    parts = [listed?.view.pluralLabel, moduleTitle(module)];
  }
  return joinTitle(parts, brand);
}

export function usePageTitle(meta: MetaData | undefined, resolved: Resolved | undefined) {
  const brand = titleName(useBrand());
  const node = resolved?.kind === "node" ? resolved : undefined;
  const { state } = useNode(node?.entry, node?.key);
  useDocumentTitle(browseTitle(brand, meta, resolved, state));
}
