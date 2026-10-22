// SPDX-License-Identifier: MIT OR Apache-2.0
// The type chips (DESIGN-GB, Navigation and Active State): a single choice, "All" first and one chip
// per readable type, exactly one selected. A radio group (`role="radio"`, `aria-checked`, a roving
// tabindex, arrow keys) with a visible check mark; the number of hits once a search has been made,
// and a dashed "not searched" for a type the search could not cover.

import type { KeyboardEvent } from "react";
import { shortName } from "../api/gql";
import type { NotSearched, SearchCount } from "../api/types";
import { Glyph, Icon } from "./icons";
import type { TypeEntry } from "./meta";
import { toneClass } from "./tones";

export interface ChipsProps {
  entries: TypeEntry[];
  /** The selected type's short name, or null for "All". */
  selected: string | null;
  onSelect: (type: string | null) => void;
  counts?: SearchCount[];
  notSearched?: NotSearched[];
}

const total = (counts: SearchCount[]) => ({
  n: counts.reduce((sum, c) => sum + c.count, 0),
  more: counts.some((c) => c.atLeast),
});

/** Arrow keys move the selection (and focus) round the group, as a radio group does. */
function move(
  e: KeyboardEvent<HTMLElement>,
  values: (string | null)[],
  at: number,
  onSelect: ChipsProps["onSelect"],
) {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  const last = values.length - 1;
  const to = e.key === "Home" ? 0 : e.key === "End" ? last : step ? at + step : undefined;
  if (to === undefined) return;
  e.preventDefault();
  const next = values[(to + values.length) % values.length] ?? null;
  onSelect(next);
  const radios = e.currentTarget.parentElement?.querySelectorAll<HTMLElement>('[role="radio"]');
  radios?.[(to + values.length) % values.length]?.focus();
}

function Count({ n, more }: { n: number; more: boolean }) {
  return (
    <span className="gb-n">
      {n}
      {more ? "+" : ""}
    </span>
  );
}

export function TypeChips({ entries, selected, onSelect, counts, notSearched }: ChipsProps) {
  const values = [null, ...entries.map((e) => shortName(e.type.name))];
  const at = Math.max(0, values.indexOf(selected));
  const radio = (i: number, on: boolean, off: boolean, cls: string) => ({
    type: "button" as const,
    role: "radio" as const,
    "aria-checked": on,
    tabIndex: i === at ? 0 : -1,
    className: `gb-chip ${cls}${off ? " gb-off" : ""}`,
    onClick: () => onSelect(values[i] ?? null),
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => move(e, values, i, onSelect),
  });
  const check = (on: boolean) =>
    on && (
      <span className="gb-check">
        <Glyph name="check" size={14} />
      </span>
    );
  const all = counts ? total(counts) : undefined;
  return (
    <div className="gb-chips" role="radiogroup" aria-label="Narrow by type">
      <button {...radio(0, at === 0, false, "gb-chip-all")}>
        All
        {all && <Count n={all.n} more={all.more} />}
        {check(at === 0)}
      </button>
      {entries.map((e, j) => {
        const name = shortName(e.type.name);
        const count = counts?.find((c) => c.type === name);
        const off = !!notSearched?.some((n) => n.type === name);
        const on = at === j + 1;
        return (
          <button key={e.type.name} {...radio(j + 1, on, off, toneClass(e.view.tone))}>
            <span className="gb-ico">
              <Icon name={e.view.icon} size={14} />
            </span>
            {e.view.pluralLabel}
            {off ? (
              <span className="gb-n">not searched</span>
            ) : count ? (
              <Count n={count.count} more={count.atLeast} />
            ) : null}
            {check(on)}
          </button>
        );
      })}
    </div>
  );
}
