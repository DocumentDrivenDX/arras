// SPDX-License-Identifier: MIT OR Apache-2.0
// In-place editing on a node page: a pencil beside a value opens an input that takes its place, with
// Save and Cancel, or, where the property can only change with others, a popup form (`EditDialog`). It shows only for an operator and only where the module declares an
// action that updates that property (`editPlan`).

import { type ReactNode, useContext, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { FieldView } from "../api/types";
import { Button } from "../ds";
import { editPlan, groupLinks, retirePlan } from "../kit";
import { useBrowser } from "./context";
import { EditDialog } from "./EditDialog";
import { EditGlyph } from "./EditGlyph";
import { EditTargetContext as Ctx, type Target } from "./editContext";
import { draftOf, labelOf } from "./editing";
import { useEdit } from "./useEdit";

export { EditTarget } from "./editContext";

function Editor({
  target,
  field,
  value,
  onClose,
  plan,
}: {
  target: Target;
  field: FieldView;
  value: unknown;
  onClose: () => void;
  plan: NonNullable<ReturnType<typeof editPlan>>;
}) {
  const { entry, keyText } = target;
  const [text, setText] = useState(draftOf(value));
  const edit = useEdit(entry, keyText, plan);
  const msg = useId();
  const box = useRef<HTMLElement>(null);
  useEffect(() => box.current?.focus(), []);
  const long = field.format === "prose" || text.includes("\n");
  const done = async () => {
    if (await edit.save({ [field.property]: text })) onClose();
  };
  const common = {
    value: text,
    disabled: edit.saving,
    "aria-label": field.label,
    "aria-invalid": edit.error !== null,
    "aria-describedby": msg,
    className: "arras-field__input",
    onChange: (e: { target: { value: string } }) => {
      setText(e.target.value);
      edit.clearError();
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !long && !e.nativeEvent.isComposing) {
        e.preventDefault();
        void done();
      }
    },
  };
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: Escape cancels from any control of the editor
    <div className="gb-edit" onKeyDown={(e) => e.key === "Escape" && !edit.saving && onClose()}>
      {/* The field's own label is the row's term, so the widget's markup is used on the bare element (ADR-029). */}
      {long ? (
        <textarea rows={5} ref={box as never} {...common} />
      ) : (
        <input type="text" ref={box as never} {...common} />
      )}
      <div className="gb-edit-bar">
        <Button size="sm" busy={edit.saving} disabled={edit.saving} onClick={() => void done()}>
          Save
        </Button>
        <Button variant="secondary" size="sm" disabled={edit.saving} onClick={onClose}>
          Cancel
        </Button>
      </div>
      <div id={msg} role="alert" className="gb-edit-error">
        {edit.error}
      </div>
    </div>
  );
}

/** The lock for edit mode: closed while editing is off, open while the controls show. Shown only where the host offers edits. */
export function EditLock({ inline = false }: { inline?: boolean }) {
  const { canEdit, editing, setEditing } = useBrowser();
  if (!canEdit) return null;
  return (
    <button
      type="button"
      className={inline ? "gb-edit-toggle gb-edit-toggle-inline" : "gb-edit-toggle"}
      aria-pressed={editing}
      aria-label="Edit mode"
      title={editing ? "Lock editing" : "Unlock editing"}
      onClick={() => setEditing(!editing)}
    >
      <EditGlyph name={editing ? "unlock" : "lock"} size={16} />
    </button>
  );
}

/** The lock on a node page: shown where the host offers edits and the page has an edit. */
export function EditToggle() {
  const target = useContext(Ctx);
  const { canEdit } = useBrowser();
  if (!target || !canEdit) return null;
  const { entry } = target;
  const editable =
    entry.view.fields.some((f) => editPlan(entry.module, entry.type, f.property)) ||
    entry.view.relationships.some((r) => groupLinks(entry.module, entry.type.name, r.field)) ||
    retirePlan(entry.module, entry.type.name) !== undefined;
  return editable ? <EditLock /> : null;
}

/** A property's value, with an edit control beside it where the viewer may change it. */
export function Editable({
  field,
  value,
  children,
  pencil: withPencil = true,
}: {
  field: FieldView;
  value: unknown;
  children: ReactNode;
  /** False where another control on the page already edits the same action's properties. */
  pencil?: boolean;
}) {
  const target = useContext(Ctx);
  const { editing } = useBrowser();
  const [open, setOpen] = useState(false);
  const pencil = useRef<HTMLButtonElement>(null);
  const giveBack = useRef(false);
  const close = () => {
    giveBack.current = true;
    setOpen(false);
  };
  // The pencil is drawn again once the editor or dialog is gone: it takes focus back.
  useEffect(() => {
    if (open || !giveBack.current) return;
    giveBack.current = false;
    pencil.current?.focus();
  });
  const plan =
    target && editing
      ? editPlan(target.entry.module, target.entry.type, field.property)
      : undefined;
  if (!target || !plan || !withPencil) return <>{children}</>;
  if (open && plan.form)
    return (
      <>
        {children}
        {/* Out of the heading it was opened from, which would otherwise size and weight its text. */}
        {createPortal(
          <EditDialog
            target={target}
            plan={plan}
            title={`Edit ${plan.fields.map((f) => labelOf(target.entry, f.property)).join(", ")}`}
            onClose={close}
          />,
          document.querySelector(".gb") ?? document.body,
        )}
      </>
    );
  if (open)
    return <Editor target={target} field={field} value={value} plan={plan} onClose={close} />;
  return (
    <span className="gb-editable">
      {children}
      <button
        ref={pencil}
        type="button"
        className="gb-edit-btn"
        aria-label={`Edit ${field.label}`}
        title={
          plan.form
            ? `Edit ${field.label} with ${plan.fields.length - 1} more`
            : `Edit ${field.label}`
        }
        aria-haspopup={plan.form ? "dialog" : undefined}
        onClick={() => setOpen(true)}
      >
        <EditGlyph name="pencil" size={12} />
      </button>
    </span>
  );
}
