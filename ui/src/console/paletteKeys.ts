// SPDX-License-Identifier: MIT OR Apache-2.0
// The palette's keys, as pure functions over its list.
import type { Place } from "../lib/paletteCommands";
import type { Route } from "../route";
import type { PaletteItem } from "./paletteItems";

/** Up and Down wrap round the list; Home and End go to its ends. Undefined for any other key. */
export function moveActive(key: string, index: number, count: number): number | undefined {
  if (count === 0) return undefined;
  switch (key) {
    case "ArrowDown":
      return (index + 1) % count;
    case "ArrowUp":
      return (index - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return undefined;
  }
}

/**
 * Where Enter goes: the item's own place; Shift+Enter its Graph and Alt+Enter its History when it is
 * an entity (on any other item those chords do nothing).
 */
export function chosenRoute(
  item: PaletteItem,
  mods: { shiftKey: boolean; altKey: boolean },
): Route | undefined {
  if (mods.altKey) return item.history;
  if (mods.shiftKey) return item.graph;
  return item.route;
}

/** Where Enter goes: an Operate route, an Explore place, or (Open in Operate) the host's move to Operate. */
export type Chosen = { route: Route } | { place: Place } | { operate: true };

/** In Explore the chords of Operate (Shift: Graph, Alt: History) do nothing; Enter opens the place. */
export function chosenTarget(
  item: PaletteItem,
  mods: { shiftKey: boolean; altKey: boolean },
  mode: "operate" | "explore",
): Chosen | undefined {
  if (mode === "operate") {
    const route = chosenRoute(item, mods);
    return route && { route };
  }
  if (mods.shiftKey || mods.altKey) return undefined;
  if (item.place) return { place: item.place };
  return item.command?.kind === "mode" ? { operate: true } : undefined;
}

const FOCUSABLE = 'input, button:not([disabled]), select, textarea, [href], [tabindex="0"]';

/** Tab stays inside the dialog: from its last control to its first, and from its first back to its last. */
export function trapTab(root: HTMLElement | null, shift: boolean): HTMLElement | undefined {
  const items = [...(root?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
  const first = items[0];
  const last = items[items.length - 1];
  if (shift && document.activeElement === first) return last;
  if (!shift && document.activeElement === last) return first;
  return undefined;
}
