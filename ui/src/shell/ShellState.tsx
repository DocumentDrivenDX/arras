// SPDX-License-Identifier: MIT OR Apache-2.0
// What lives at the shell so a switch of mode keeps it (SD-013 D6, "State across a mode switch"): the
// edit-mode lock, the single-key switch, and whether the shortcut help and the command palette are
// open. The one query client and the Query session are the shell's too (ArrasApp). In memory only:
// never in the browser's storage.
import { useCallback, useMemo, useState } from "react";

export interface ShellState {
  /** Edit mode, the lock that shows the edit controls (Explore). */
  editing: boolean;
  setEditing: (on: boolean) => void;
  /** The "Single-key shortcuts" switch. */
  singleKeys: boolean;
  setSingleKeys: (on: boolean) => void;
  helpOpen: boolean;
  openHelp: () => void;
  closeHelp: () => void;
  paletteOpen: boolean;
  openPalette: () => void;
  closePalette: () => void;
}

export function useShellState(): ShellState {
  const [editing, setEditing] = useState(false);
  const [singleKeys, setSingleKeys] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openHelp = useCallback(() => setHelpOpen(true), []);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  return useMemo(
    () => ({
      editing,
      setEditing,
      singleKeys,
      setSingleKeys,
      helpOpen,
      openHelp,
      closeHelp,
      paletteOpen,
      openPalette,
      closePalette,
    }),
    [editing, singleKeys, helpOpen, paletteOpen, openHelp, closeHelp, openPalette, closePalette],
  );
}
