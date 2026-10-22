// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "../components/ui";

export interface MenuItem {
  id: string;
  label: string;
  title?: string;
  onSelect: () => void;
}

const itemsOf = (root: HTMLElement | null) => [
  ...(root?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []),
];
const items0 = (root: HTMLElement | null) => itemsOf(root)[0];

/**
 * An overflow menu: a button with `aria-haspopup` and `aria-expanded`, items reached with the arrow
 * keys (Home and End too), Enter or Space to choose, Escape to close and give the focus back.
 * Escape here closes only the menu, never the panel around it.
 */
export function ActionMenu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // The first item takes the focus when the menu opens.
  useEffect(() => {
    if (open) items0(root.current)?.focus();
  }, [open]);

  // A press outside closes it.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };

  const move = (to: (i: number, n: number) => number) => {
    const list = itemsOf(root.current);
    const at = list.indexOf(document.activeElement as HTMLElement);
    list[to(at, list.length)]?.focus();
  };

  const onMenuKey = (e: React.KeyboardEvent) => {
    const moves: Record<string, (i: number, n: number) => number> = {
      ArrowDown: (i, n) => (i + 1) % n,
      ArrowUp: (i, n) => (i <= 0 ? n - 1 : i - 1),
      Home: () => 0,
      End: (_, n) => n - 1,
    };
    const step = moves[e.key];
    if (step) {
      e.preventDefault();
      move(step);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === "Tab") close(false);
  };

  if (items.length === 0) return null;
  return (
    <div ref={root} className="relative">
      <Button
        ref={trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          } else if (e.key === "Escape" && open) {
            e.stopPropagation();
            setOpen(false);
          }
        }}
      >
        {label} <span aria-hidden="true">▾</span>
      </Button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          tabIndex={-1}
          onKeyDown={onMenuKey}
          className="absolute left-0 z-20 mt-1 max-h-72 min-w-48 overflow-auto rounded border border-strong bg-surface py-1 shadow-lg"
        >
          {items.map((it) => (
            <button
              key={it.id}
              type="button"
              role="menuitem"
              title={it.title}
              className="block w-full px-3 py-1 text-left text-[12px] hover:bg-surface2 focus:bg-surface2"
              onClick={() => {
                close(false);
                it.onSelect();
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
