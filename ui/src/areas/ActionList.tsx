// SPDX-License-Identifier: MIT OR Apache-2.0
import { useState } from "react";
import { shortName } from "../api/gql";
import type { ActionInfo, ModuleInfo } from "../api/types";
import { Chip } from "../components/ui";
import {
  type ActionGroup,
  type EntityContext,
  groupActions,
  matchesFilter,
} from "../lib/actionGroups";
import { relevantTo } from "./actionRelevance";

type Refusals = Record<string, { kind: string } | undefined>;

export interface ActionListProps {
  module: ModuleInfo;
  current: string;
  /** The entity the area was opened for, when it was opened from one. */
  context?: EntityContext;
  refusals: Refusals;
  onPick: (action: string) => void;
}

/** The sections of the list: those relevant to the entity in context first, then one per target type. */
export function listSections(
  m: ModuleInfo,
  filter: string,
  ctx: EntityContext | undefined,
): ActionGroup[] {
  const relevant = relevantTo(m, ctx).filter((a) => matchesFilter(a, filter));
  const taken = new Set(relevant.map((a) => a.name));
  const groups = groupActions(m, filter)
    .map((g) => ({ ...g, actions: g.actions.filter((a) => !taken.has(a.name)) }))
    .filter((g) => g.actions.length > 0);
  const head =
    ctx && relevant.length > 0 ? [{ title: `For ${ctx.type} ${ctx.key}`, actions: relevant }] : [];
  return [...head, ...groups];
}

function ActionButton({
  a,
  active,
  refused,
  onPick,
}: {
  a: ActionInfo;
  active: boolean;
  refused: { kind: string } | undefined;
  onPick: (name: string) => void;
}) {
  return (
    <button
      type="button"
      data-action={a.name}
      aria-current={active ? "true" : undefined}
      onClick={() => onPick(a.name)}
      className={`w-full rounded px-2 py-1.5 text-left ${active ? "bg-accentsoft font-semibold" : "hover:bg-surface2"}`}
    >
      <div className="flex items-center gap-1">
        <span className="truncate">{shortName(a.name)}</span>
        {refused && (
          <Chip tone="bad">{refused.kind === "not_offered" ? "not offered" : "no access"}</Chip>
        )}
      </div>
      <div className="truncate text-[11px] font-normal text-muted">{a.description}</div>
    </button>
  );
}

const buttonsIn = (root: HTMLElement) => [
  ...root.querySelectorAll<HTMLButtonElement>("button[data-action]"),
];

/** Arrow keys, Home and End move between the actions listed; Enter or Space on one chooses it. */
function onListKey(e: React.KeyboardEvent<HTMLElement>) {
  const list = buttonsIn(e.currentTarget);
  const at = list.indexOf(e.target as HTMLButtonElement);
  const to: Record<string, number> = {
    ArrowDown: Math.min(at + 1, list.length - 1),
    ArrowUp: Math.max(at - 1, 0),
    Home: 0,
    End: list.length - 1,
  };
  const next = to[e.key];
  if (next === undefined || at < 0) return;
  e.preventDefault();
  list[next]?.focus();
}

function FilterBox({
  text,
  onText,
  shown,
  total,
}: {
  text: string;
  onText: (t: string) => void;
  shown: number;
  total: number;
}) {
  return (
    <div className="mb-2">
      <div className="flex items-center gap-1">
        <input
          type="search"
          aria-label="Filter actions"
          placeholder="Filter actions"
          value={text}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && text) {
              e.preventDefault();
              onText("");
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              e.currentTarget
                .closest("nav")
                ?.querySelector<HTMLElement>("button[data-action]")
                ?.focus();
            }
          }}
          className="min-w-0 flex-1 rounded border border-strong bg-surface px-2 py-1 text-[12px] text-fg"
        />
        {text && (
          <button
            type="button"
            aria-label="Clear filter"
            className="rounded px-1.5 text-muted hover:bg-surface2"
            onClick={() => onText("")}
          >
            ✕
          </button>
        )}
      </div>
      <div role="status" aria-live="polite" className="mt-0.5 text-[11px] text-muted">
        {text.trim() ? `${shown} of ${total} actions` : `${total} actions`}
      </div>
    </div>
  );
}

/** The module's actions: a filter, then the actions in sections by the type they act on. */
export function ActionList({ module: m, current, context, refusals, onPick }: ActionListProps) {
  const [text, setText] = useState("");
  const sections = listSections(m, text, context);
  const shown = sections.reduce((n, g) => n + g.actions.length, 0);
  return (
    <nav
      aria-label="Actions"
      onKeyDown={onListKey}
      className="min-h-0 overflow-auto border-b border-line bg-surface p-2 md:row-span-2 md:border-b-0 md:border-r min-[1280px]:row-span-1"
    >
      <FilterBox text={text} onText={setText} shown={shown} total={m.actions.length} />
      {shown === 0 && <div className="px-2 py-1 text-muted">No action matches.</div>}
      {sections.map((g, i) => (
        <div key={g.title} className="mb-2">
          <h3
            className={`m-0 mb-0.5 px-2 text-[11px] font-semibold uppercase tracking-wide ${i === 0 && context && g.title.startsWith("For ") ? "text-accent" : "text-muted"}`}
          >
            {g.title}
          </h3>
          <ul aria-label={g.title} className="m-0 list-none space-y-0.5 p-0">
            {g.actions.map((a) => (
              <li key={a.name}>
                <ActionButton
                  a={a}
                  active={a.name === current}
                  refused={refusals[a.name]}
                  onPick={onPick}
                />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
