// SPDX-License-Identifier: MIT OR Apache-2.0
import { type KeyboardEvent, type ReactNode, useRef } from "react";

export interface TabItem {
  id: string;
  label: ReactNode;
}

/** The tab to move to for a key, by the WAI-ARIA tabs pattern (Left/Right wrap; Home/End); else null. */
export function tabTarget(key: string, index: number, count: number): number | null {
  if (count === 0) return null;
  switch (key) {
    case "ArrowRight":
      return (index + 1) % count;
    case "ArrowLeft":
      return (index - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/**
 * A horizontal tablist after the WAI-ARIA tabs pattern: the selected tab is the one tab stop
 * (roving tabindex), Left/Right/Home/End move to a tab and select it, and `aria-selected` says
 * which is chosen. Tab panels belong to the caller.
 */
export function TabList({
  label,
  items,
  selected,
  onSelect,
  className,
  tabClass,
}: {
  label: string;
  items: TabItem[];
  /** The id of the chosen tab; when none is chosen the first tab is the tab stop. */
  selected: string | undefined;
  onSelect: (id: string) => void;
  className?: string;
  tabClass: (selected: boolean) => string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const chosen = items.findIndex((i) => i.id === selected);
  const stop = chosen < 0 ? 0 : chosen;
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const at = refs.current.indexOf(document.activeElement as HTMLButtonElement);
    if (at < 0) return;
    const to = tabTarget(e.key, at, items.length);
    const next = to === null ? undefined : items[to];
    if (!next) return;
    e.preventDefault();
    refs.current[to ?? 0]?.focus();
    onSelect(next.id);
  };
  return (
    <div role="tablist" aria-label={label} className={className} onKeyDown={onKeyDown}>
      {items.map((it, i) => (
        <button
          key={it.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="tab"
          type="button"
          aria-selected={it.id === selected}
          tabIndex={i === stop ? 0 : -1}
          onClick={() => onSelect(it.id)}
          className={tabClass(it.id === selected)}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
