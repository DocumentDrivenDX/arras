// SPDX-License-Identifier: MIT OR Apache-2.0
// The command palette's commands: the module's types, the console's areas and the module's declared
// actions, each one a route. Matching is by case-insensitive words (every word of the query must be
// found) ranked word-prefix before substring, with the label before the description; a pure module.
import { shortName } from "../api/gql";
import type { ModuleInfo } from "../api/types";
import { AREAS, type Route } from "../route";
import { AREA_LABELS, OPEN_IN_OPERATE } from "./vocabulary";

export type CommandKind = "area" | "type" | "action" | "mode";

/** A place in Explore: a module, an entity type's list, or one entity (the browser's own grammar, kept neutral here). */
export interface Place {
  module: string;
  type?: string;
  key?: string;
}

export interface Command {
  id: string;
  kind: CommandKind;
  label: string;
  /** Further text the query also matches (an action's description). */
  detail: string;
  /** Operate's commands: the console route they open. */
  route?: Route;
  /** Explore's commands: the place they open (the `mode` command has none; the host moves the mode). */
  place?: Place;
}

/** How many types an empty query lists beside the areas. */
const PRIMARY_TYPES = 5;

/** Does any type of the module have a backend that serves text search? (an older server has none) */
export function searchServed(module: ModuleInfo): boolean {
  return module.entityTypes.some((t) =>
    Object.values(t.capabilities).some((c) => c.search === "substring"),
  );
}

/** Every command of a module: areas (Changes only when it is shown), then types, then actions. */
export function commandsFor(module: ModuleInfo, auditShown: boolean): Command[] {
  const m = module.name;
  const areas = AREAS.filter((a) => a !== "changes" || auditShown).map<Command>((a) => ({
    id: `area:${a}`,
    kind: "area",
    label: AREA_LABELS[a],
    detail: "",
    route: { module: m, area: a },
  }));
  const types = module.entityTypes.map<Command>((t) => ({
    id: `type:${t.name}`,
    kind: "type",
    label: shortName(t.name),
    detail: "",
    route: { module: m, area: "entities", type: t.name },
  }));
  const actions = module.actions.map<Command>((a) => ({
    id: `action:${a.name}`,
    kind: "action",
    label: a.name,
    detail: a.description,
    route: { module: m, area: "actions", action: a.name },
  }));
  return [...areas, ...types, ...actions];
}

/**
 * Explore's commands: the module's types (each opens its list) and, where the host offers Operate to this
 * viewer, Open in Operate. A type the viewer cannot read has no view and is not offered.
 */
export function browseCommandsFor(module: ModuleInfo, offerAdmin: boolean): Command[] {
  const types = module.entityTypes.flatMap<Command>((t) =>
    t.view
      ? [
          {
            id: `type:${t.name}`,
            kind: "type",
            label: t.view.pluralLabel,
            detail: shortName(t.name),
            place: { module: module.name, type: shortName(t.name) },
          },
        ]
      : [],
  );
  const toOperate: Command[] = offerAdmin
    ? [{ id: "mode:operate", kind: "mode", label: OPEN_IN_OPERATE, detail: "" }]
    : [];
  return [...types, ...toOperate];
}

/** The commands an empty query shows: the areas, the first few types and the mode, never an entity read. */
export const primaryCommands = (all: Command[]): Command[] => [
  ...all.filter((c) => c.kind === "area"),
  ...all.filter((c) => c.kind === "type").slice(0, PRIMARY_TYPES),
  ...all.filter((c) => c.kind === "mode"),
];

const wordsOf = (s: string) =>
  s
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);

/** 4 when `word` starts the text, 3 when it starts a word in it, 2 when it is inside one, else 0. */
function fieldScore(text: string, word: string): number {
  const t = text.toLowerCase();
  if (t.startsWith(word)) return 4;
  if (wordsOf(t).some((w) => w.startsWith(word))) return 3;
  return t.includes(word) ? 2 : 0;
}

/** A command's score for the query, or 0 when some word of the query is not found in it. */
export function scoreCommand(c: Command, query: string): number {
  const ws = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (ws.length === 0) return 0;
  let total = 0;
  for (const w of ws) {
    // The label outranks the description: its tiers double, the description's count once.
    const best = Math.max(fieldScore(c.label, w) * 2, fieldScore(c.detail, w));
    if (best === 0) return 0;
    total += best;
  }
  return total;
}

/** The commands matching the query, best first; equal scores keep the commands' own order. */
export function rankCommands(all: Command[], query: string, max = 8): Command[] {
  if (query.trim() === "") return primaryCommands(all).slice(0, max);
  return all
    .map((c, i) => ({ c, i, s: scoreCommand(c, query) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .slice(0, max)
    .map((x) => x.c);
}
