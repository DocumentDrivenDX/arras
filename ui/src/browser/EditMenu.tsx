// SPDX-License-Identifier: MIT OR Apache-2.0
// The menu of an entity's page in edit mode (SD-013 D4): one button in the card's header that opens a
// list of what the viewer may do to the entity: Retire, offered where a declared action deletes the type
// (`retirePlan`), then each declared action that takes the type and no edit, link, retire or create
// plan claims (`entityActionsOf`), each opening its dialog.
// `role="menu"`: arrow keys move, Home and End jump, Escape closes and returns focus to the button.
import { type KeyboardEvent, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import { shortName } from "../api/gql";
import { type EntityAction, entityActionsOf, retirePlan } from "../kit";
import { ActionDialog } from "./ActionDialog";
import { useBrowser } from "./context";
import { EditGlyph } from "./EditGlyph";
import { EditTargetContext } from "./editContext";
import { RetireDialog } from "./RetireDialog";

export interface MenuItem {
  id: string;
  label: ReactNode;
  onSelect: () => void;
}

/** The index the arrow, Home or End key moves to from `at` among `count` items, or null for another key. */
export function stepOf(key: string, at: number, count: number): number | null {
  if (key === "ArrowDown") return (at + 1) % count;
  if (key === "ArrowUp") return (at - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

function Menu({ label, items }: { label: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const entries = () => [
    ...(list.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []),
  ];
  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      setOpen(false);
      opener.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    } else {
      const all = entries();
      const next = stepOf(e.key, all.indexOf(document.activeElement as HTMLElement), all.length);
      if (next === null) return;
      e.preventDefault();
      all[next]?.focus();
    }
  };
  return (
    <div className="gb-menu-wrap" ref={wrap}>
      <button
        ref={opener}
        type="button"
        className="gb-menu-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        <EditGlyph name="more" size={16} />
      </button>
      {open && (
        <div ref={list} className="gb-menu" role="menu" aria-label={label} onKeyDown={onKeyDown}>
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              tabIndex={-1}
              className="gb-menu-item"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const labelOf = (a: EntityAction) => shortName(a.action.name);

/** An entity action's menu entry: its label, with its description beneath where it says more. */
function ActionItem({ entityAction }: { entityAction: EntityAction }) {
  const label = labelOf(entityAction);
  const text = entityAction.action.description;
  return (
    <>
      <span>{label}</span>
      {text && text !== label && <span className="gb-menu-sub">{text}</span>}
    </>
  );
}

/** What the menu has open: Retire's confirmation, or one entity action's dialog. */
type Opened = "retire" | EntityAction | null;

/**
 * The edit-mode menu in a node card's header; nothing unless the host offers edits, edit mode is on and
 * an item applies: Retire where a declared action deletes the type, then each action no plan claims.
 */
export function EditMenu() {
  const target = useContext(EditTargetContext);
  const { canEdit, editing } = useBrowser();
  const [opened, setOpened] = useState<Opened>(null);
  const host = useRef<HTMLDivElement>(null);
  if (!target || !canEdit || !editing) return null;
  const { module, type } = target.entry;
  const plan = retirePlan(module, type.name);
  const actions = entityActionsOf(module, type.name);
  if (!plan && actions.length === 0) return null;
  const items: MenuItem[] = [
    ...(plan ? [{ id: "retire", label: "Retire", onSelect: () => setOpened("retire") }] : []),
    ...actions.map((a) => ({
      id: `action:${a.action.name}`,
      label: <ActionItem entityAction={a} />,
      onSelect: () => setOpened(a),
    })),
  ];
  const close = (returnFocus = true) => {
    setOpened(null);
    if (returnFocus) host.current?.querySelector<HTMLElement>(".gb-menu-btn")?.focus();
  };
  return (
    <div ref={host} className="gb-menu-host">
      <Menu label="Entity menu" items={items} />
      {opened === "retire" && plan && (
        <RetireDialog target={target} plan={plan} onClose={() => close()} />
      )}
      {opened && opened !== "retire" && (
        <ActionDialog target={target} entityAction={opened} onClose={close} />
      )}
    </div>
  );
}
