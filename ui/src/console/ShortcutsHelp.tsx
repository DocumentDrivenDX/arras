// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useId, useRef } from "react";
import { useBrand } from "../lib/brand";
import { SHORTCUTS, type ShortcutSection, shortcutSections, worksIn } from "../lib/shortcuts";
import { KEYBOARD_SHORTCUTS } from "../lib/vocabulary";

const FOCUSABLE = 'input, button:not([disabled]), [href], select, textarea, [tabindex="0"]';

/** Tab stays inside `root`: from its last control to its first and back, and in from outside it. */
function trapTab(e: globalThis.KeyboardEvent, root: HTMLElement) {
  const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)];
  const edge = e.shiftKey ? items[0] : items[items.length - 1];
  const at = document.activeElement;
  if (at === root || !root.contains(at) || at === edge) {
    e.preventDefault();
    (e.shiftKey ? items[items.length - 1] : items[0])?.focus();
  }
}

/** The plain keys the switch governs, as caps, for the hint. */
function singleCaps(operate: boolean): string[] {
  const caps = SHORTCUTS.filter(
    (s) => s.single && s.keys.length > 0 && (operate || worksIn(s, "explore")),
  ).map((s) => s.caps.join("+"));
  return [...new Set(caps)];
}

function Section({ section, singleKeys }: { section: ShortcutSection; singleKeys: boolean }) {
  return (
    <section className="mb-3" aria-label={section.title}>
      <h3 className="m-0 mb-1 border-b border-line pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
        {section.title}
      </h3>
      {section.groups.map((g) => (
        <div key={g.group} className="mb-2">
          {g.title !== section.title && (
            <h4 className="m-0 mb-1 text-[12px] font-semibold text-fg">{g.title}</h4>
          )}
          <dl className="m-0 grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-3 gap-y-1">
            {g.items.map((s) => (
              <div key={s.id} className="contents" data-shortcut={s.id}>
                <dt className="whitespace-nowrap">
                  {s.caps.map((c, i) => (
                    <span key={c}>
                      {i > 0 && "+"}
                      <kbd>{c}</kbd>
                    </span>
                  ))}
                </dt>
                <dd className="m-0">
                  {s.label}
                  {s.single && !singleKeys && <span className="text-muted"> (off)</span>}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </section>
  );
}

/**
 * The shortcuts help: one modal dialog listing `SHORTCUTS` for both modes (Operate's keys only where the
 * viewer is offered Operate), headed with the brand, with the switch that turns the single-key ones off for
 * the page's lifetime. Focus moves in, Tab stays inside, Escape closes and the focus returns to where it was.
 */
export function ShortcutsHelp({
  operate,
  singleKeys,
  onSingleKeys,
  onClose,
}: {
  /** Whether Operate is offered to this viewer: its keys are listed only then. */
  operate: boolean;
  singleKeys: boolean;
  onSingleKeys: (on: boolean) => void;
  onClose: () => void;
}) {
  const brand = useBrand();
  const root = useRef<HTMLDivElement>(null);
  const title = useId();
  const hint = useId();
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const before = document.activeElement;
    const el = root.current;
    el?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      } else if (e.key === "Tab" && el) trapTab(e, el);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, []);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-fg/40 p-4">
      <div
        ref={root}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title}
        tabIndex={-1}
        className="w-full max-w-lg rounded border border-line bg-surface p-4 text-fg shadow-[var(--shadow)]"
      >
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 id={title} className="m-0 text-[15px] font-semibold">
            {brand.name} · {KEYBOARD_SHORTCUTS}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-strong bg-surface px-2 py-0.5 text-[12px] hover:bg-surface2"
          >
            Close
          </button>
        </div>
        <label className="mb-1 flex items-center gap-2">
          <input
            type="checkbox"
            role="switch"
            checked={singleKeys}
            aria-checked={singleKeys}
            aria-describedby={hint}
            onChange={(e) => onSingleKeys(e.target.checked)}
          />
          <span className="font-medium">Single-key shortcuts</span>
        </label>
        <p id={hint} className="m-0 mb-3 text-[12px] text-muted">
          Keys that act without a modifier ({singleCaps(operate).join(", ")}). Turn them off if they
          get in the way of typing or assistive technology; this lasts until the page is reloaded.
        </p>
        {shortcutSections(operate).map((section) => (
          <Section key={section.mode} section={section} singleKeys={singleKeys} />
        ))}
      </div>
    </div>
  );
}
