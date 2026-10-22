// SPDX-License-Identifier: MIT OR Apache-2.0
// What the palette lists and says: its result items (entities from the search, then commands) and the
// one polite status line. Pure; the search itself is `api/search.ts`.

import type { ApiError } from "../api/errors";
import type { EntitySearch, PaletteHit } from "../api/search";
import type { Command, Place } from "../lib/paletteCommands";
import type { Route } from "../route";

export type PaletteGroup = "Entities" | "Commands";

export interface PaletteItem {
  id: string;
  group: PaletteGroup;
  /** The option's accessible name, as a person would read it out. */
  name: string;
  /** Operate: where Enter opens it. */
  route?: Route;
  /** Explore: the entity page or list Enter opens (the Open in Operate command has none). */
  place?: Place;
  /** An entity's other places: its history in Audit and its place in the Graph. */
  history?: Route;
  graph?: Route;
  hit?: PaletteHit;
  command?: Command;
}

const KIND: Record<Command["kind"], string> = {
  area: "Area",
  type: "Type",
  action: "Action",
  mode: "Mode",
};

export function commandItem(c: Command): PaletteItem {
  return {
    id: c.id,
    group: "Commands",
    name: `${KIND[c.kind]} · ${c.label}${c.detail ? `, ${c.detail}` : ""}`,
    route: c.route,
    place: c.place,
    command: c,
  };
}

/** `<Type> · <title> (<key>)`: a hit as one line. */
export const hitLine = (h: PaletteHit) => `${h.type} · ${h.label} (${h.key})`;

export function entityItem(module: string, h: PaletteHit): PaletteItem {
  const at = (area: "entities" | "graph" | "changes"): Route => ({
    module,
    area,
    type: `${module}.${h.type}`,
    key: h.key,
  });
  const excerpt = h.excerpt?.map((s) => s.text).join("");
  return {
    id: `entity:${h.type}:${h.key}`,
    group: "Entities",
    name: excerpt ? `${hitLine(h)}, ${excerpt}` : hitLine(h),
    route: at("entities"),
    history: at("changes"),
    graph: at("graph"),
    hit: h,
  };
}

/** In Explore an entity result is the entity's page, with none of Operate's other places. */
export function browseEntityItem(module: string, h: PaletteHit): PaletteItem {
  const excerpt = h.excerpt?.map((s) => s.text).join("");
  return {
    id: `entity:${h.type}:${h.key}`,
    group: "Entities",
    name: excerpt ? `${hitLine(h)}, ${excerpt}` : hitLine(h),
    place: { module, type: h.type, key: h.key },
    hit: h,
  };
}

export const itemsOf = (
  module: string,
  hits: PaletteHit[],
  commands: Command[],
  mode: "operate" | "explore" = "operate",
): PaletteItem[] => [
  ...hits.map((h) => (mode === "explore" ? browseEntityItem(module, h) : entityItem(module, h))),
  ...commands.map(commandItem),
];

const REASON: Record<string, string> = {
  no_searchable_property: "has nothing to search",
  no_capability: "is not searchable on its backend",
  unavailable: "is unavailable",
  over_budget: "was left out to keep the search small",
};

const CODE_NOTE: Record<string, string> = {
  BAD_QUERY: "That text cannot be searched; try other words.",
  UNSUPPORTED: "This module has no text search.",
  UNAVAILABLE: "Entity search is unavailable just now.",
};

/** A modest line for a failed search, from the error's code only (never the server's words). */
export const errorNote = (e: ApiError) =>
  `${CODE_NOTE[e.code ?? ""] ?? "Entity search failed."} Commands still work.`;

const CHECK_NOTE = {
  empty: "",
  short: "Type at least 2 characters to search entities.",
  long: "Entity search takes up to 200 characters.",
  words: "Entity search takes up to 6 words.",
} as const;

export interface StatusInput {
  searchable: boolean;
  search: EntitySearch;
  loading: boolean;
}

/** The status line: why there is no entity group, what was not searched, whether more were found. */
export function statusLine({ searchable, search, loading }: StatusInput): string {
  if (!searchable) return "Entity search is not available for this module; commands only.";
  if (!search.check.ok) return CHECK_NOTE[search.check.reason];
  if (search.error) return errorNote(search.error);
  const d = search.data;
  if (!d) return loading ? "Searching…" : "";
  const parts: string[] = [];
  if (loading) parts.push("Searching…");
  else parts.push(d.hits.length === 0 ? "No entities found." : `${d.hits.length} found.`);
  if (d.truncated) parts.push(`Showing the first ${d.hits.length}; type more.`);
  for (const n of d.notSearched)
    parts.push(`${n.type} not searched: ${REASON[n.reason] ?? "not searched"}.`);
  return parts.join(" ");
}
