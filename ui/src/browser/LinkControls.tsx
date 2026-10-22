// SPDX-License-Identifier: MIT OR Apache-2.0
// The controls of a relationship group in edit mode: Add, which opens the picker, and a remove
// control on each member, which asks once. Each is the module's declared link or unlink action
// (`groupLinks`), shown only where one exists and only while the reader has edit mode on.

import { useEffect, useRef, useState } from "react";
import type { Ref } from "../api/types";
import { Button } from "../ds";
import { type GroupLinks, linkInputs, planTakes } from "../kit";
import { useBrowser } from "./context";
import { EditGlyph } from "./EditGlyph";
import { LinkDialog } from "./LinkDialog";
import { findQualified, type TypeEntry } from "./meta";
import type { GroupPlan } from "./planner";
import { refId } from "./planner";
import { useAction } from "./useAction";

export function AddLink({
  group,
  links,
  centre,
}: {
  group: GroupPlan;
  links: GroupLinks;
  centre: { entry: TypeEntry; key: string };
}) {
  const { meta } = useBrowser();
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLSpanElement>(null);
  const plan = links.add;
  if (!plan) return null;
  // Only the type the action's other input takes: the key alone is sent.
  const ends = links.otherTypes
    .filter((t) => planTakes(plan, t))
    .flatMap((t) => findQualified(meta, t) ?? []);
  return (
    <>
      <span ref={opener} style={{ display: "contents" }}>
        <Button
          variant="secondary"
          size="sm"
          aria-haspopup="dialog"
          aria-label={`Add to ${group.label}`}
          disabled={ends.length === 0}
          onClick={() => setOpen(true)}
        >
          <EditGlyph name="plus" size={12} /> Add
        </Button>
      </span>
      {open && (
        <LinkDialog
          title={`Add to ${group.label}`}
          module={centre.entry.module}
          pageKey={centre.key}
          plan={plan}
          links={links}
          linked={new Set(group.refs.map(refId))}
          ends={ends}
          onClose={() => {
            setOpen(false);
            opener.current?.querySelector("button")?.focus(); // the Add button, where the dialog was opened from
          }}
        />
      )}
    </>
  );
}

/** The remove control of one member, and the question it asks before it removes. */
export function RemoveLink({
  item,
  title,
  links,
  centre,
}: {
  item: Ref;
  title: string;
  links: GroupLinks;
  centre: { entry: TypeEntry; key: string };
}) {
  const [asking, setAsking] = useState(false);
  const action = useAction(centre.entry.module);
  const plan = links.remove;
  const icon = useRef<HTMLButtonElement>(null);
  const confirm = useRef<HTMLFieldSetElement>(null);
  const cancelled = useRef(false);
  // The question takes focus on its first button; Cancel hands it back to the icon it replaced.
  useEffect(() => {
    if (asking) confirm.current?.querySelector("button")?.focus();
    else if (cancelled.current) icon.current?.focus();
    cancelled.current = false;
  }, [asking]);
  if (!plan || !planTakes(plan, item.type)) return null;
  if (!asking)
    return (
      <button
        ref={icon}
        type="button"
        className="gb-edit-btn gb-rel-remove"
        aria-label={`Remove link to ${title}`}
        title={`Remove link to ${title}`}
        onClick={() => setAsking(true)}
      >
        <EditGlyph name="unlink" size={12} />
      </button>
    );
  const done = async () => {
    if (await action.run(plan.action, linkInputs(plan, centre.key, item.key))) setAsking(false);
  };
  return (
    <fieldset className="gb-rel-confirm" ref={confirm}>
      <legend className="gb-sr">Remove link to {title}</legend>
      <span>Remove the link to {title}?</span>
      <Button size="sm" busy={action.saving} disabled={action.saving} onClick={() => void done()}>
        Remove
      </Button>
      <Button
        variant="secondary"
        size="sm"
        disabled={action.saving}
        onClick={() => {
          action.clearError();
          cancelled.current = true;
          setAsking(false);
        }}
      >
        Cancel
      </Button>
      <span role="alert" className="gb-edit-error">
        {action.error}
      </span>
    </fieldset>
  );
}
