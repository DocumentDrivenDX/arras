// SPDX-License-Identifier: MIT OR Apache-2.0
import type { SearchSegment } from "../api/types";
import { hitLine, type PaletteGroup, type PaletteItem } from "./paletteItems";

/** An excerpt as text, with the matched segments in `<mark>` (a segment is never markup). */
function Excerpt({ segments }: { segments: SearchSegment[] }) {
  let at = 0;
  return (
    <span className="cp-excerpt">
      {segments.map((s) => {
        const key = at;
        at += s.text.length;
        return s.mark ? <mark key={key}>{s.text}</mark> : <span key={key}>{s.text}</span>;
      })}
    </span>
  );
}

function Option({
  item,
  active,
  id,
  onPick,
  onHover,
}: {
  item: PaletteItem;
  active: boolean;
  id: string;
  onPick: () => void;
  onHover: () => void;
}) {
  const { hit, command } = item;
  return (
    // Focus stays in the field (aria-activedescendant); a press must not move it.
    // biome-ignore lint/a11y/useKeyWithClickEvents: the field's keys drive the options
    <div
      id={id}
      role="option"
      tabIndex={-1}
      aria-selected={active}
      aria-label={item.name}
      className={`cp-option${active ? " cp-active" : ""}`}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
      onMouseMove={onHover}
    >
      {hit ? (
        <>
          <span className="cp-line">{hitLine(hit)}</span>
          {hit.excerpt && <Excerpt segments={hit.excerpt} />}
        </>
      ) : (
        <>
          <span className="cp-kind">{command?.kind}</span>
          <span className="cp-line">{command?.label}</span>
          {command?.detail && <span className="cp-excerpt">{command.detail}</span>}
        </>
      )}
    </div>
  );
}

/** An option's DOM id: by position, so a key with a space or a colon is never an id. */
export const optionDomId = (listId: string, index: number) => `${listId}-o${index}`;

const GROUPS: PaletteGroup[] = ["Entities", "Commands"];

/** The listbox: group headings, then the options, each with a stable id for `aria-activedescendant`. */
export function PaletteResults({
  listId,
  items,
  activeId,
  busy,
  onPick,
  onHover,
}: {
  listId: string;
  items: PaletteItem[];
  activeId: string | undefined;
  busy: boolean;
  onPick: (item: PaletteItem) => void;
  onHover: (item: PaletteItem) => void;
}) {
  return (
    <div id={listId} role="listbox" aria-label="Results" aria-busy={busy} className="cp-list">
      {GROUPS.map((g) => {
        const rows = items.filter((i) => i.group === g);
        if (rows.length === 0) return null;
        return (
          // biome-ignore lint/a11y/useSemanticElements: a fieldset is not a child a listbox may have
          <div key={g} role="group" aria-labelledby={`${listId}-${g}`}>
            <div id={`${listId}-${g}`} role="presentation" className="cp-heading">
              {g}
            </div>
            {rows.map((item) => (
              <Option
                key={item.id}
                item={item}
                id={optionDomId(listId, items.indexOf(item))}
                active={item.id === activeId}
                onPick={() => onPick(item)}
                onHover={() => onHover(item)}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
