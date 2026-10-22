// SPDX-License-Identifier: MIT OR Apache-2.0
// A popup form for an action that changes several properties together: one input for each, started
// from the node's current values, saved with one validate and invoke (`useEdit`).

import { useEffect, useId, useRef, useState } from "react";
import { Button, Notice, TextArea, TextField } from "../ds";
import type { EditPlan } from "../kit";
import { useDialogKeys } from "./dialogKeys";
import type { Target } from "./editContext";
import { draftOf } from "./editing";
import { useEdit } from "./useEdit";

export function EditDialog({
  target,
  plan,
  title,
  onClose,
}: {
  target: Target;
  plan: EditPlan;
  title: string;
  onClose: () => void;
}) {
  const { entry, keyText, entity } = target;
  const edit = useEdit(entry, keyText, plan);
  const [texts, setTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(plan.fields.map((f) => [f.property, draftOf(entity[f.property])])),
  );
  const root = useRef<HTMLDivElement>(null);
  const heading = useId();
  const first = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  useEffect(() => first.current?.focus(), []);
  const done = async () => {
    if (await edit.save(texts)) onClose();
  };
  const onKeyDown = useDialogKeys(root, onClose, edit.saving);
  return (
    <div className="gb-dialog-backdrop">
      <div
        ref={root}
        className="gb-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={heading}
        onKeyDown={onKeyDown}
      >
        <h2 id={heading} className="gb-dialog-h">
          {title}
        </h2>
        <p className="gb-dialog-note">
          These change together. A field left empty is kept as it is.
        </p>
        <form
          className="gb-dialog-form"
          onSubmit={(e) => {
            e.preventDefault();
            void done();
          }}
        >
          {plan.fields.map(({ property, input }, i) => {
            const field = entry.view.fields.find((f) => f.property === property);
            const base = field?.label ?? property;
            const long = field?.format === "prose" || (texts[property] ?? "").includes("\n");
            const common = {
              label: input.cardinality === "one" ? `${base} (required)` : base,
              value: texts[property] ?? "",
              disabled: edit.saving,
              ref: i === 0 ? first : undefined,
              onChange: (ev: { target: { value: string } }) => {
                setTexts((t) => ({ ...t, [property]: ev.target.value }));
                edit.clearError();
              },
            };
            return long ? (
              <TextArea key={property} rows={4} {...common} />
            ) : (
              <TextField key={property} {...common} />
            );
          })}
          {edit.error && (
            <Notice tone="error" role="alert">
              {edit.error}
            </Notice>
          )}
          <div className="gb-edit-bar">
            <Button type="submit" size="sm" busy={edit.saving} disabled={edit.saving}>
              Save
            </Button>
            <Button variant="secondary" size="sm" disabled={edit.saving} onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
