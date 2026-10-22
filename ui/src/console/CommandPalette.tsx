// SPDX-License-Identifier: MIT OR Apache-2.0
// The command palette (FEAT-010 OPR-19): `/` or Ctrl/Cmd+K opens a modal with one search field over
// two groups, the current module's entities (the `_search` read) and its commands. In Operate the
// commands are areas, types and declared actions and Enter opens the result in the console; in Explore
// they are the module's types and, for an operator, Open in Operate, and an entity result opens its
// page. The typed text lives in this component's state only: never in the address, a log, history or
// storage.

import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useEntitySearch } from "../api/search";
import type { ModuleInfo } from "../api/types";
import { Button, TextField } from "../ds";
import {
  browseCommandsFor,
  commandsFor,
  type Place,
  rankCommands,
  searchServed,
} from "../lib/paletteCommands";
import { optionDomId, PaletteResults } from "./PaletteResults";
import { itemsOf, type PaletteItem, statusLine } from "./paletteItems";
import { chosenTarget, moveActive, trapTab } from "./paletteKeys";
import { usePaletteShortcut } from "./usePaletteShortcut";
import type { Go } from "./useRoute";

/** What the palette does with a result: the host supplies the ones its mode uses. */
export interface PaletteTargets {
  /** Operate: open a console route. */
  go?: Go;
  /** Explore: open an entity page or a type's list. */
  open?: (place: Place) => void;
  /** Explore, for an operator: the same place in Operate. Absent: the command is not offered. */
  toOperate?: () => void;
}

export type PaletteMode = "operate" | "explore";

interface DialogProps {
  mode: PaletteMode;
  module: ModuleInfo;
  auditShown: boolean;
  targets: PaletteTargets;
  onClose: () => void;
}

const FOOT: Record<PaletteMode, string> = {
  operate: "Enter opens · Shift+Enter Graph · Alt+Enter History · Esc closes",
  explore: "Enter opens · Esc closes",
};

export function PaletteDialog({ mode, module, auditShown, targets, onClose }: DialogProps) {
  const [text, setText] = useState("");
  const [chosen, setChosen] = useState<string | undefined>();
  const root = useRef<HTMLDivElement>(null);
  const opener = useRef(document.activeElement);
  const listId = useId();
  const searchable = searchServed(module);
  const search = useEntitySearch(module, text, searchable);
  const offerAdmin = targets.toOperate !== undefined;
  const commands = useMemo(
    () =>
      mode === "explore" ? browseCommandsFor(module, offerAdmin) : commandsFor(module, auditShown),
    [mode, module, auditShown, offerAdmin],
  );
  const items = itemsOf(module.name, search.data?.hits ?? [], rankCommands(commands, text), mode);
  const index = Math.max(
    0,
    items.findIndex((i) => i.id === chosen),
  );
  const active = items[index];
  const busy = !!search.data && !search.current;
  // Closing gives focus back to what had it when the palette opened.
  useEffect(() => {
    const el = opener.current;
    return () => {
      if (el instanceof HTMLElement && el.isConnected) el.focus();
    };
  }, []);

  const pick = (item: PaletteItem | undefined, mods = { shiftKey: false, altKey: false }) => {
    const to = item && chosenTarget(item, mods, mode);
    if (!to) return;
    if ("route" in to) targets.go?.(to.route);
    else if ("place" in to) targets.open?.(to.place);
    else targets.toOperate?.();
    onClose();
  };

  const onFieldKey = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      pick(active, e);
      return;
    }
    const to = moveActive(e.key, index, items.length);
    if (to === undefined) return;
    e.preventDefault();
    setChosen(items[to]?.id);
  };

  const onDialogKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    } else if (e.key === "Tab") {
      const to = trapTab(root.current, e.shiftKey);
      if (to) {
        e.preventDefault();
        to.focus();
      }
    }
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: a press outside the dialog closes it; the keys are the dialog's
    <div className="cp-backdrop" onMouseDown={onClose} role="presentation">
      <div
        ref={root}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="cp-dialog"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onDialogKey}
      >
        <p className="cp-scope">
          Searching in <strong>{module.name}</strong>
        </p>
        <TextField
          label="Search entities and commands"
          value={text}
          autoFocus
          autoComplete="off"
          spellCheck={false}
          role="combobox"
          aria-expanded={items.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active ? optionDomId(listId, index) : undefined}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onFieldKey}
        />
        <p role="status" aria-live="polite" className="cp-status">
          {statusLine({ searchable, search, loading: busy })}
        </p>
        <PaletteResults
          listId={listId}
          items={items}
          activeId={active?.id}
          busy={busy}
          onPick={(item) => pick(item)}
          onHover={(item) => setChosen(item.id)}
        />
        {items.length === 0 && <p className="cp-empty">Nothing matches.</p>}
        <div className="cp-foot">
          <span>{FOOT[mode]}</span>
          <Button variant="text" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * The palette of a mode. Left alone it owns its keys (`/` and Ctrl/Cmd+K) and its open state, as a
 * standalone console's does; given `controlled` it is opened and closed by the host (the shell, which owns
 * the keys for both modes). It renders nothing until it is open, and nothing without a module.
 */
export function CommandPalette({
  mode = "operate",
  module,
  auditShown,
  go,
  targets,
  controlled,
}: {
  mode?: PaletteMode;
  module: ModuleInfo | undefined;
  auditShown: boolean;
  go?: Go;
  targets?: PaletteTargets;
  controlled?: { open: boolean; onClose: () => void };
}) {
  const [ownOpen, setOwnOpen] = useState(false);
  const onOpen = useCallback(() => {
    if (module) setOwnOpen(true);
  }, [module]);
  usePaletteShortcut(onOpen, controlled === undefined);
  const close = useCallback(() => setOwnOpen(false), []);
  const own = useMemo(() => ({ go }), [go]);
  const open = controlled ? controlled.open : ownOpen;
  if (!open || !module) return null;
  return (
    <PaletteDialog
      mode={mode}
      module={module}
      auditShown={auditShown}
      targets={targets ?? own}
      onClose={controlled ? controlled.onClose : close}
    />
  );
}
