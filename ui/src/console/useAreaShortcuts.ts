// SPDX-License-Identifier: MIT OR Apache-2.0

import { useEffect } from "react";
import { usePageEffects } from "../lib/pageEffects";
import { type KeyIntent, keyIntent } from "../lib/shortcuts";
import { AREAS, type Area } from "../route";
import type { Go } from "./useRoute";

interface Handling {
  shown: Area[];
  current: { name: string } | undefined;
  go: Go;
  lastAction: string | undefined;
  onHelp: (() => void) | undefined;
}

/** What the console does with a key's meaning: open the help (when it holds one) or switch area. True when the key was used. */
function act(intent: KeyIntent | null, h: Handling): boolean {
  if (intent?.kind === "help" && h.onHelp) {
    h.onHelp();
    return true;
  }
  const area = intent?.kind === "area" ? h.shown[intent.index] : undefined;
  if (!area || !h.current) return false;
  h.go({
    module: h.current.name,
    area,
    action: area === "actions" ? h.lastAction : undefined,
  });
  return true;
}

/**
 * The console-level single-key shortcuts of `SHORTCUTS`: the area digits and, where the console holds its
 * own help, `?`. They never fire with a modifier, while typing in a field, while a dialog is open, or when
 * the Single-key shortcuts switch is off. A shell that hosts the console handles `?` itself (no `onHelp`).
 */
export function useAreaShortcuts(
  current: { name: string } | undefined,
  auditShown: boolean,
  go: Go,
  lastAction: string | undefined,
  keys: { enabled: boolean; onHelp?: () => void },
) {
  const { enabled, onHelp } = keys;
  const pageEffects = usePageEffects();
  useEffect(() => {
    if (!enabled || !pageEffects) return;
    const shown = AREAS.filter((a) => a !== "changes" || auditShown);
    const on = (e: KeyboardEvent) => {
      if (act(keyIntent(e, "operate"), { shown, current, go, lastAction, onHelp }))
        e.preventDefault();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [current, auditShown, go, lastAction, enabled, onHelp, pageEffects]);
}
