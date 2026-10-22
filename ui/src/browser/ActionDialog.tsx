// SPDX-License-Identifier: MIT OR Apache-2.0
// An entity action opened from the entity's menu (FR-70): the declared action's inputs with the page's
// entity prefilled, validate, the effects as text, apply, and the receipt. It is the kit's form model
// (`useEntityAction`) and the kit's pieces; a refusal shows here, inline, and nothing is applied. A
// batch is not offered. Focus starts in the first field (Cancel where there is none), stays inside,
// moves to the receipt after an apply and returns to the menu button when the dialog closes.

import { useEffect, useId, useRef } from "react";
import { shortName } from "../api/gql";
import { Button } from "../ds";
import type { EntityAction } from "../kit";
import { titleOf } from "../lib/template";
import { FieldsView, ReceiptView, ReviewView } from "./ActionDialogParts";
import { useDialogKeys } from "./dialogKeys";
import type { Target } from "./editContext";
import { useEntityAction } from "./useEntityActions";

export function ActionDialog({
  target,
  entityAction,
  onClose,
}: {
  target: Target;
  entityAction: EntityAction;
  /** Close the dialog; `returnFocus` false where the browser is going to another page. */
  onClose: (returnFocus?: boolean) => void;
}) {
  const { entry, keyText, entity } = target;
  const { form, fields } = useEntityAction(entry, keyText, entityAction);
  const root = useRef<HTMLDivElement>(null);
  const heading = useId();
  useEffect(() => {
    const first = root.current?.querySelector<HTMLElement>("input, textarea, select");
    (first ?? root.current?.querySelector<HTMLElement>("[data-autofocus]"))?.focus();
  }, []);
  const { validate: check, confirm, submitting: busy } = form;
  const onKeyDown = useDialogKeys(root, () => onClose(), busy);
  const label = shortName(entityAction.action.name);
  const title = titleOf(entry.view.title, entity, keyText);
  return (
    <div className="gb-dialog-backdrop">
      <div
        ref={root}
        className="gb-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={heading}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <h2 id={heading} className="gb-dialog-h">
          {label}
        </h2>
        <p className="gb-dialog-note">
          {entityAction.action.description} On the {entry.view.label.toLowerCase()} <b>{title}</b>.
        </p>
        {form.receipt ? (
          <>
            <ReceiptView
              receipt={form.receipt}
              effects={form.effects}
              module={entry.module.name}
              onLeave={() => onClose(false)}
            />
            <div className="gb-edit-bar">
              <Button type="button" variant="secondary" size="sm" onClick={() => onClose()}>
                Close
              </Button>
            </div>
          </>
        ) : (
          <form
            key={form.epoch}
            className="gb-dialog-form"
            onSubmit={(e) => {
              e.preventDefault();
              void check();
            }}
          >
            <FieldsView
              action={entityAction.action.name}
              module={entry.module.name}
              form={form}
              fields={fields}
            />
            <ReviewView form={form} />
            <div className="gb-edit-bar">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => onClose()}
                data-autofocus
              >
                Cancel
              </Button>
              <Button type="submit" variant="secondary" size="sm" disabled={busy}>
                Validate
              </Button>
              <Button
                type="button"
                size="sm"
                busy={busy}
                disabled={!form.canConfirm}
                onClick={() => void confirm()}
              >
                Apply
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
