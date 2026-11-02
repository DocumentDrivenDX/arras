// SPDX-License-Identifier: MIT OR Apache-2.0

import { useEffect } from "react";
import { usePageEffects } from "../lib/pageEffects";
import { isSingleKey, type KeyIntent, keyIntent } from "../lib/shortcuts";
import type { Mode } from "./modeRoute";
import type { ShellState } from "./ShellState";

/** Explore's search box is on the page (it handles `/` itself: it focuses). */
const searchBoxShown = () => document.querySelector("search.gb-search input") !== null;

type Keys = Pick<ShellState, "singleKeys" | "openHelp" | "openPalette">;

/** Does the shell act on this intent in this mode? The digits are the console's; Explore's search box takes `/`. */
function shellActs(intent: KeyIntent | null, where: "explore" | "operate", keys: Keys): boolean {
  if (!intent || intent.kind === "area") return false;
  if (isSingleKey(intent) && !keys.singleKeys) return false;
  return !(intent.kind === "find" && where === "explore" && searchBoxShown());
}

/**
 * The shell's keys, for both modes, from the one table (`lib/shortcuts.ts`): `?` opens the help, Ctrl/Cmd+K
 * the palette from anywhere, and `/` is find: Explore's search box takes it when it is served (this yields),
 * otherwise it opens the palette. The digits are the console's own. A plain key never fires with a
 * modifier, while typing in a field, while a dialog is open, or with the single-key switch off.
 */
export function useShellShortcuts(mode: Mode, keys: Keys) {
  const { singleKeys, openHelp, openPalette } = keys;
  const pageEffects = usePageEffects();
  useEffect(() => {
    if (!pageEffects) return;
    const where = mode === "admin" ? "operate" : "explore";
    const on = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const intent = keyIntent(e, where);
      if (!shellActs(intent, where, { singleKeys, openHelp, openPalette })) return;
      e.preventDefault();
      if (intent?.kind === "help") openHelp();
      else openPalette();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [mode, singleKeys, openHelp, openPalette, pageEffects]);
}
