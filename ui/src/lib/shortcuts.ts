// SPDX-License-Identifier: MIT OR Apache-2.0
import { AREA_LABELS, ENTITY_TYPE, EXPLORE, OPERATE } from "./vocabulary";

/**
 * The interface's keyboard shortcuts, in one table for both modes: the handlers read the keys they match
 * from it and the shortcuts help lists it, so the two cannot disagree. `mode` says where a key works:
 * `both`, `explore` or `operate`. `single` marks a plain character key, the kind the "Single-key shortcuts"
 * switch turns off; a modified key (Ctrl/Cmd+K) is never `single`.
 */
export type ShortcutMode = "both" | "operate" | "explore";
export type ShortcutGroup = "global" | "search" | "tabs" | "table" | "graph" | "entity" | "query";

export interface Shortcut {
  id: string;
  group: ShortcutGroup;
  mode: ShortcutMode;
  /** The `KeyboardEvent.key` values the shell-level handler matches; empty where the control itself handles the key. */
  keys: readonly string[];
  /** The key caps shown for it, joined by "+" when more than one. */
  caps: readonly string[];
  label: string;
  single: boolean;
}

export const GROUP_TITLES: Record<ShortcutGroup, string> = {
  global: "Anywhere",
  search: "Search box",
  tabs: `Tabs (areas, mode, ${ENTITY_TYPE}s)`,
  table: `${AREA_LABELS.entities} table`,
  graph: AREA_LABELS.graph,
  entity: "Entity panel",
  query: "Query",
};

/** Where each group's keys work; every entry of a group has its group's mode. */
export const GROUP_MODES: Record<ShortcutGroup, ShortcutMode> = {
  global: "both",
  search: "explore",
  tabs: "operate",
  table: "operate",
  graph: "operate",
  entity: "operate",
  query: "operate",
};

/** The digit keys that switch to the n-th area shown, Changes last when it is served. */
export const AREA_KEYS = ["1", "2", "3", "4", "5", "6"] as const;

const entry = (
  id: string,
  group: ShortcutGroup,
  caps: string[],
  label: string,
  o: { keys?: readonly string[]; single?: boolean } = {},
): Shortcut => ({
  id,
  group,
  mode: GROUP_MODES[group],
  caps,
  label,
  keys: o.keys ?? [],
  single: o.single ?? false,
});

export const SHORTCUTS: readonly Shortcut[] = [
  entry(
    "find",
    "global",
    ["/"],
    "Find: focus the search box when there is one, otherwise open the command palette",
    { keys: ["/"], single: true },
  ),
  entry("palette", "global", ["Ctrl/⌘", "K"], "Open the command palette"),
  entry("help", "global", ["?"], "Show these shortcuts", { keys: ["?"], single: true }),
  entry("search-clear", "search", ["Esc"], "Clear the search"),
  entry(
    "area",
    "tabs",
    ["1–6"],
    `Switch to the n-th area (${AREA_LABELS.changes} is last, when shown)`,
    { keys: AREA_KEYS, single: true },
  ),
  entry("tabs-step", "tabs", ["← →"], "Previous or next tab (selects it)"),
  entry("tabs-ends", "tabs", ["Home / End"], "First or last tab"),
  entry("row-move", "table", ["↑ ↓"], "Move between rows"),
  entry("row-open", "table", ["Enter"], "Open the focused row"),
  entry("row-filter", "table", ["/"], "Filter (from a focused row)", { single: true }),
  entry("filter-back", "table", ["Esc"], "From the filter, back to the rows"),
  entry("node-move", "graph", ["← ↑ ↓ →"], "Move between entities"),
  entry("node-open", "graph", ["Enter"], "Open the focused entity"),
  entry("panel-close", "entity", ["Esc"], "Close the panel; focus returns to its row"),
  entry(
    "menu-move",
    "entity",
    ["↑ ↓", "Home / End"],
    `Move in the ${AREA_LABELS.actions} menu (Enter chooses, Esc closes)`,
  ),
  entry("query-run", "query", ["Ctrl/⌘", "Enter"], "Run the statement"),
];

const ORDER = Object.keys(GROUP_TITLES) as ShortcutGroup[];

type Where = "explore" | "operate";

/** Does a shortcut of this mode work in `mode`? */
export const worksIn = (s: { mode: ShortcutMode }, mode: Where) =>
  s.mode === "both" || s.mode === mode;

/** The table by group, in the order the help shows it; `mode` narrows it to one mode's keys. */
export function shortcutGroups(
  mode?: Where,
): { group: ShortcutGroup; title: string; items: Shortcut[] }[] {
  return ORDER.map((group) => ({
    group,
    title: GROUP_TITLES[group],
    items: SHORTCUTS.filter((s) => s.group === group && (!mode || worksIn(s, mode))),
  })).filter((g) => g.items.length > 0);
}

export interface ShortcutSection {
  mode: ShortcutMode;
  /** The section's heading: the mode's name from the vocabulary, or "Anywhere" for both. */
  title: string;
  groups: ReturnType<typeof shortcutGroups>;
}

/** The help's sections: keys that work in both modes, then Explore's, then Operate's (when offered). */
export function shortcutSections(operate: boolean): ShortcutSection[] {
  const heading: Record<ShortcutMode, string> = {
    both: GROUP_TITLES.global,
    explore: EXPLORE,
    operate: OPERATE,
  };
  const modes: ShortcutMode[] = operate ? ["both", "explore", "operate"] : ["both", "explore"];
  return modes.map((mode) => ({
    mode,
    title: heading[mode],
    groups: shortcutGroups().filter((g) => GROUP_MODES[g.group] === mode),
  }));
}

/** The shortcut a plain key triggers in `mode`, if any. */
export const shortcutForKey = (key: string, mode: Where): Shortcut | undefined =>
  SHORTCUTS.find((s) => s.keys.includes(key) && worksIn(s, mode));

export const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);

/** A modal dialog is open (the shortcuts help, an edit or link dialog): the keys belong to it. */
export const dialogOpen = () =>
  document.querySelector('[role="dialog"][aria-modal="true"], dialog[open]') !== null;

/** What a key press means at the interface level. */
export type KeyIntent =
  | { kind: "help" }
  | { kind: "find" }
  | { kind: "palette" }
  | { kind: "area"; index: number };

type KeyLike = Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "target">;

/**
 * The interface-level meaning of a key press in `mode`, from the table. Ctrl/Cmd+K opens the palette
 * from anywhere, a field included; a plain key never means anything with a modifier, while typing in a
 * field, or while a dialog is open.
 */
export function keyIntent(e: KeyLike, mode: Where): KeyIntent | null {
  if (dialogOpen()) return null;
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k")
    return { kind: "palette" };
  if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return null;
  switch (shortcutForKey(e.key, mode)?.id) {
    case "help":
      return { kind: "help" };
    case "find":
      return { kind: "find" };
    case "area":
      return { kind: "area", index: AREA_KEYS.indexOf(e.key as (typeof AREA_KEYS)[number]) };
    default:
      return null;
  }
}

/** Is this intent one the "Single-key shortcuts" switch turns off? */
export const isSingleKey = (i: KeyIntent): boolean => i.kind !== "palette";
