// SPDX-License-Identifier: MIT OR Apache-2.0
// A popup to add a link, drawn with the design system's widgets (ADR-029): the entities at the other
// end are listed at once in a dropdown (up to a page of each type the relationship allows), narrowed
// as the reader types in the filter above it, or searched for when a type has more than the list
// holds; where the list cannot be read, the reader types the key. Picking one and saving sends one
// validate and invoke of the plan's action (`useAction`).

import { useEffect, useId, useRef } from "react";
import type { ModuleInfo } from "../api/types";
import { Button, Notice, Select, TextField } from "../ds";
import { type GroupLinks, type LinkPlan, linkInputs } from "../kit";
import { useDialogKeys } from "./dialogKeys";
import type { TypeEntry } from "./meta";
import { useAction } from "./useAction";
import { idOf, optionsOf, usePick } from "./usePick";

export interface LinkDialogProps {
  title: string;
  /** The page's module, whose action it is, and the page's key. */
  module: ModuleInfo;
  pageKey: string;
  plan: LinkPlan;
  links: GroupLinks;
  /** The ends already linked, as `qualified type:key`, so they are not offered again. */
  linked: Set<string>;
  /** The types the other end may be, as the viewer may read them. */
  ends: TypeEntry[];
  onClose: () => void;
}

export function LinkDialog(p: LinkDialogProps) {
  const action = useAction(p.module);
  const root = useRef<HTMLDivElement>(null);
  const heading = useId();
  const filter = useRef<HTMLInputElement>(null);
  useEffect(() => filter.current?.focus(), []);
  const onKeyDown = useDialogKeys(root, p.onClose, action.saving);
  const { text, setText, picked, setPicked, rows, listable, chosen, loading, hint } = usePick(
    p.ends,
  );
  const what = p.ends.map((e) => e.view.label.toLowerCase()).join(" or ");
  const save = async () => {
    if (!chosen) {
      action.fail(listable ? "Choose what to link to." : "Enter the key to link to.");
      return;
    }
    if (await action.run(p.plan.action, linkInputs(p.plan, p.pageKey, chosen.key))) p.onClose();
  };
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
          {p.title}
        </h2>
        <form
          className="gb-dialog-form"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <TextField
            ref={filter}
            label={listable ? `Filter or search ${what}` : `Key of the ${what}`}
            autoComplete="off"
            value={text}
            disabled={action.saving}
            onChange={(e) => {
              setText(e.target.value);
              setPicked(null);
              action.clearError();
            }}
          />
          {listable && (
            <Select
              label={`Choose ${what}`}
              placeholder={loading ? "Loading…" : "Choose…"}
              hint={hint}
              disabled={action.saving || loading}
              value={picked ? idOf(picked) : ""}
              options={optionsOf(rows, p.linked, p.ends.length > 1)}
              onChange={(e) => {
                setPicked(rows.find((r) => idOf(r) === e.target.value) ?? null);
                action.clearError();
              }}
            />
          )}
          {action.error && (
            <Notice tone="error" role="alert">
              {action.error}
            </Notice>
          )}
          <div className="gb-edit-bar">
            <Button
              type="submit"
              size="sm"
              busy={action.saving}
              disabled={action.saving || !chosen}
            >
              {chosen && listable ? `Add ${chosen.label}` : "Add"}
            </Button>
            <Button variant="secondary" size="sm" disabled={action.saving} onClick={p.onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
