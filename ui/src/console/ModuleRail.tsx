// SPDX-License-Identifier: MIT OR Apache-2.0

import type { ModuleInfo } from "../api/types";
import { Select } from "../ds";

/** The module list: a rail beside the module (a screen at `md` or wider; Shell shows the picker below it). */
export function ModuleRail({
  modules,
  current,
  onPick,
}: {
  modules: ModuleInfo[];
  current: ModuleInfo | undefined;
  onPick: (mod: ModuleInfo) => void;
}) {
  return (
    <nav
      aria-label="Modules"
      className="shrink-0 overflow-auto border-b border-line bg-surface p-2 md:w-44 md:border-b-0 md:border-r"
    >
      <div className="mb-1 hidden px-1 text-[11px] font-semibold uppercase tracking-wide text-muted md:block">
        Modules
      </div>
      <ul className="m-0 flex list-none gap-1 p-0 md:block md:space-y-0.5">
        {modules.map((mod) => (
          <li key={mod.name}>
            <button
              type="button"
              aria-current={mod.name === current?.name ? "page" : undefined}
              onClick={() => onPick(mod)}
              className={`w-full rounded px-2 py-1.5 text-left ${mod.name === current?.name ? "bg-accentsoft font-semibold" : "hover:bg-surface2"}`}
            >
              {mod.name}
              <div className="text-[11px] font-normal text-muted">{mod.record}</div>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/**
 * The module choice on a narrow screen, in the console header: a select in place of the rail. A single module
 * needs no choice, so it shows nothing then.
 */
export function ModulePicker({
  modules,
  current,
  onPick,
}: {
  modules: ModuleInfo[];
  current: ModuleInfo | undefined;
  onPick: (mod: ModuleInfo) => void;
}) {
  if (modules.length < 2) return null;
  return (
    <nav aria-label="Modules" className="min-w-0 flex-1">
      <Select
        label={<span className="sr-only">Module</span>}
        value={current?.name ?? ""}
        options={modules.map((mod) => ({ value: mod.name, label: mod.name }))}
        onChange={(e) => {
          const mod = modules.find((x) => x.name === e.target.value);
          if (mod) onPick(mod);
        }}
      />
    </nav>
  );
}
