// SPDX-License-Identifier: MIT OR Apache-2.0
// The confirmation before an entity is retired (SD-013 Rule 3, FR-68): what goes with it, named from
// the page's own relationship groups, that its key cannot be used again and that the interface has
// no undo. Confirming validates and invokes the declared action through the kit's form model
// (`useRetire`); a refusal shows here and nothing is applied. On success the browser has moved to the
// type's list, so this dialog is gone with the page.

import { useEffect, useId, useMemo, useRef } from "react";
import { Button, Notice } from "../ds";
import { ActionFields, type RetirePlan, reasonOf } from "../kit";
import { titleOf } from "../lib/template";
import { useDialogKeys } from "./dialogKeys";
import type { Target } from "./editContext";
import { groupsOf, MAX_KEYS } from "./planner";
import { RefPicker } from "./RefPicker";
import { useRetire } from "./useRetire";

/** What goes with the entity: each group of the page that has links, with how many the page read. */
function Goes({ target }: { target: Target }) {
  const groups = useMemo(
    () => groupsOf(target.entry.view, target.entity).filter((g) => g.refs.length > 0),
    [target],
  );
  if (groups.length === 0) return <p className="gb-dialog-note">It has no links.</p>;
  return (
    <>
      <p className="gb-dialog-note">Its links go with it:</p>
      <ul className="gb-retire-groups" data-testid="retire-groups">
        {groups.map((g) => (
          <li key={g.field}>
            {g.label}{" "}
            <span className="gb-retire-count">
              ({g.refs.length >= MAX_KEYS ? `${MAX_KEYS} or more` : g.refs.length})
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

export function RetireDialog({
  target,
  plan,
  onClose,
}: {
  target: Target;
  plan: RetirePlan;
  onClose: () => void;
}) {
  const { entry, keyText, entity } = target;
  const { form, retire, optional } = useRetire(entry, keyText, plan);
  const root = useRef<HTMLDivElement>(null);
  const heading = useId();
  // Focus starts on Cancel: the destructive button is never the first thing a key press reaches.
  useEffect(() => root.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus(), []);
  // Not disabled while a field's blur is validating: pressing the button blurs the field, and a button
  // that disables itself on mousedown never gets its click.
  const busy = form.submitting;
  const onKeyDown = useDialogKeys(root, onClose, busy);
  const title = titleOf(entry.view.title, entity, keyText);
  const problems = [
    ...(form.error ? [reasonOf(form.error)] : []),
    ...form.violations.general,
    ...form.failures.map((f) => f.reason),
  ];
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
          {`Retire ${title}?`}
        </h2>
        <p className="gb-dialog-note">
          This retires the {entry.view.label.toLowerCase()} <b>{title}</b>.
        </p>
        <Goes target={target} />
        <p className="gb-dialog-note">
          Its key <span className="gb-retire-key">{keyText}</span> cannot be used again. The
          interface has no undo.
        </p>
        <form
          className="gb-dialog-form"
          onSubmit={(e) => {
            e.preventDefault();
            void retire();
          }}
        >
          {optional.length > 0 && (
            <ActionFields
              action={plan.action}
              module={entry.module.name}
              idPrefix="retire"
              RefInput={RefPicker}
              specs={optional}
              values={form.values}
              errors={form.built.errors}
              violations={form.fresh?.violations}
              disabled={form.locked}
              onChange={form.onChange}
              onBlur={form.onBlur}
            />
          )}
          {form.conflict && (
            <Notice tone="warning" role="alert">
              <strong>The module changed while this was open.</strong> It was reloaded and the form
              rebuilt. Nothing was retired; review and confirm again.
            </Notice>
          )}
          {problems.length > 0 && (
            <Notice tone="error" role="alert">
              {problems.map((p) => (
                <span key={p} className="block">
                  {p}
                </span>
              ))}
            </Notice>
          )}
          <div className="gb-edit-bar">
            <Button type="submit" size="sm" busy={busy} disabled={busy}>
              Retire
            </Button>
            <Button variant="secondary" size="sm" disabled={busy} onClick={onClose} data-autofocus>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
