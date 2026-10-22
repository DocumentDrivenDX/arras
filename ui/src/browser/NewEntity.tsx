// SPDX-License-Identifier: MIT OR Apache-2.0
// New (FR-67, SD-013 Rule 2): on a type's list, in edit mode, a button opens a form built from the
// declared action that creates the type. Every input of the action is asked for, a reference through
// the picker; Validate shows the effects as text and the failed preconditions, Create invokes and
// opens the created entity from the validated key. A refusal shows in the dialog and nothing is made.
// Focus starts in the first field, stays inside, returns to the button on Cancel or Escape and goes
// to the new page's title after a create. Where several declared actions create the type, a Select
// offers them, the one with fewest inputs first.

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { shortName } from "../api/gql";
import { Button, Select } from "../ds";
import { type CreatePlan, createPlans } from "../kit";
import { FieldsView, ReceiptView, ReviewView } from "./ActionDialogParts";
import { useBrowser } from "./context";
import { useDialogKeys } from "./dialogKeys";
import { EditLock } from "./Editable";
import { EditGlyph } from "./EditGlyph";
import type { TypeEntry } from "./meta";
import { useNewEntity } from "./useNewEntity";

interface FormProps {
  entry: TypeEntry;
  plan: CreatePlan;
  onClose: (returnFocus?: boolean) => void;
  /** Told whether a Validate or Create is in flight, so the dialog's Escape waits for it. */
  onBusy: (busy: boolean) => void;
}

/** The form of one plan: its fields, what validating found, and the buttons. */
function NewForm({ entry, plan, onClose, onBusy }: FormProps) {
  const leave = useCallback(() => onClose(false), [onClose]);
  const { form, created } = useNewEntity(entry, plan, leave);
  const { validate: check, confirm, submitting: busy } = form;
  useEffect(() => {
    onBusy(busy);
    return () => onBusy(false);
  }, [busy, onBusy]);
  if (form.receipt && created === undefined) {
    return (
      <>
        <ReceiptView
          receipt={form.receipt}
          effects={form.effects}
          module={entry.module.name}
          onLeave={leave}
        />
        <div className="gb-edit-bar">
          <Button type="button" variant="secondary" size="sm" onClick={() => onClose()}>
            Close
          </Button>
        </div>
      </>
    );
  }
  return (
    <form
      key={form.epoch}
      className="gb-dialog-form"
      onSubmit={(e) => {
        e.preventDefault();
        void check();
      }}
    >
      <FieldsView
        action={plan.action}
        module={entry.module.name}
        idPrefix="new"
        form={form}
        fields={form.specs}
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
          Create
        </Button>
      </div>
    </form>
  );
}

function NewDialog({
  entry,
  plans,
  onClose,
}: {
  entry: TypeEntry;
  plans: CreatePlan[];
  onClose: (returnFocus?: boolean) => void;
}) {
  const [chosen, setChosen] = useState(plans[0]?.action);
  const plan = plans.find((p) => p.action === chosen) ?? plans[0];
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const heading = useId();
  useEffect(() => {
    const first = root.current?.querySelector<HTMLElement>("input, textarea, select");
    (first ?? root.current?.querySelector<HTMLElement>("[data-autofocus]"))?.focus();
  }, []);
  const onKeyDown = useDialogKeys(root, () => onClose(), busy);
  if (!plan) return null;
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
          {`New ${entry.view.label.toLowerCase()}`}
        </h2>
        {plans.length > 1 && (
          <Select
            label="Create with"
            value={plan.action}
            options={plans.map((p) => ({ value: p.action, label: shortName(p.action) }))}
            onChange={(e) => setChosen(e.target.value)}
          />
        )}
        <NewForm key={plan.action} entry={entry} plan={plan} onClose={onClose} onBusy={setBusy} />
      </div>
    </div>
  );
}

/** The lock and, while editing, the New button, on a type's list where a declared action creates the type. */
export function NewEntity({ entry }: { entry: TypeEntry }) {
  const { canEdit, editing } = useBrowser();
  const plans = useMemo(() => createPlans(entry.module, entry.type.name), [entry]);
  const [open, setOpen] = useState(false);
  const tools = useRef<HTMLDivElement>(null);
  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) tools.current?.querySelector<HTMLElement>("button[aria-haspopup]")?.focus();
  }, []);
  if (!canEdit || plans.length === 0) return null;
  return (
    <div ref={tools} className="gb-list-tools">
      {editing && (
        <Button variant="secondary" size="sm" aria-haspopup="dialog" onClick={() => setOpen(true)}>
          <EditGlyph name="plus" size={12} /> {`New ${entry.view.label.toLowerCase()}`}
        </Button>
      )}
      <EditLock inline />
      {open && editing && <NewDialog entry={entry} plans={plans} onClose={close} />}
    </div>
  );
}
