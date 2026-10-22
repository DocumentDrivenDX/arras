// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect } from "react";
import { useSingleKeys } from "../components/SingleKeys";
import { keyIntent } from "../lib/shortcuts";

/**
 * Opens the command palette of a standalone console: `/` outside a text field and Ctrl/Cmd+K anywhere.
 * `/` is a single key, so the Single-key shortcuts switch turns it off. (A hosting shell opens the
 * palette itself, for both modes: `shell/useShellShortcuts.ts`; it turns this one off.)
 */
export function usePaletteShortcut(onOpen: () => void, enabled = true) {
  const singleKeys = useSingleKeys();
  useEffect(() => {
    if (!enabled) return;
    const on = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const intent = keyIntent(e, "operate");
      if (intent?.kind !== "palette" && !(intent?.kind === "find" && singleKeys)) return;
      e.preventDefault();
      onOpen();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onOpen, singleKeys, enabled]);
}
