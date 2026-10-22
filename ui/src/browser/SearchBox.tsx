// SPDX-License-Identifier: MIT OR Apache-2.0
// The search box (the `search` landmark): focused by `/` anywhere outside a text field (while the
// host's single-key shortcuts are on), cleared by Escape. It holds what the reader types; the search itself waits for a pause (useSearch).
import { useEffect, useRef } from "react";
import { Glyph } from "./icons";

const isTyping = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
};

const dialogOpen = () =>
  !!document.querySelector('[role="dialog"][aria-modal="true"], dialog[open]');

export function SearchBox({
  value,
  onChange,
  label,
  slashFocus = true,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  slashFocus?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!slashFocus) return;
    const on = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (dialogOpen()) return;
      e.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [slashFocus]);
  return (
    <search className="gb-search">
      <Glyph name="search" size={18} />
      <input
        ref={input}
        type="text"
        value={value}
        autoComplete="off"
        spellCheck={false}
        placeholder="Search"
        aria-label={label}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onChange("");
        }}
      />
      <kbd>/</kbd>
    </search>
  );
}
