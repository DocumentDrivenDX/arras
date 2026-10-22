// SPDX-License-Identifier: MIT OR Apache-2.0
// The parts of an entity action's dialog (FR-70): the fields, what validating found, and the receipt.
// All of them are the kit's pieces; what is the browser's is where a touched entity opens (its own
// router) and that an entity of a type the viewer cannot read is counted, never named.

import { useMemo } from "react";
import { ApiError } from "../api/errors";
import { moduleOf, shortName } from "../api/gql";
import type { Effect, Receipt } from "../api/types";
import { SignInButton } from "../components/ui";
import { Notice } from "../ds";
import {
  ActionFields,
  type ActionFormModel,
  CrossAnchor,
  EffectsSummary,
  generalViolations,
  ReceiptSummary,
  reasonOf,
  type TouchedRef,
} from "../kit";
import { useBrowser } from "./context";
import { formatExplore } from "./location";
import { findQualified } from "./meta";
import { refId, type Target } from "./planner";
import { RefPicker } from "./RefPicker";
import { useLabels } from "./useLabels";

/** The inputs the reader fills; the entity's own key is the page's, so it is not asked for again. */
export function FieldsView({
  action,
  module,
  form,
  fields,
  idPrefix = "act",
}: {
  action: string;
  module: string;
  form: ActionFormModel;
  fields: ActionFormModel["specs"];
  idPrefix?: string;
}) {
  if (fields.length === 0) return <p className="gb-dialog-note">This action takes no inputs.</p>;
  return (
    <ActionFields
      action={action}
      module={module}
      idPrefix={idPrefix}
      RefInput={RefPicker}
      specs={fields}
      values={form.values}
      errors={visibleErrors(form)}
      violations={form.fresh?.violations}
      disabled={form.locked}
      onChange={form.onChange}
      onBlur={form.onBlur}
    />
  );
}

/** The client's encoding errors of the inputs the reader has been at. */
function visibleErrors(form: ActionFormModel): Record<string, string> {
  return Object.fromEntries(
    Object.entries(form.built.errors).filter(([name]) => form.touched[name]),
  );
}

/** What validating found: the effects as text, the failed preconditions and the violations no field shows. */
export function ReviewView({ form }: { form: ActionFormModel }) {
  const problems = [
    ...generalViolations(form.fresh?.violations ?? []),
    ...form.failures.map((f) => f.reason),
    ...(form.error && form.error.kind !== "sign_in" ? [reasonOf(form.error)] : []),
  ];
  const signIn = form.error instanceof ApiError && form.error.kind === "sign_in";
  return (
    <>
      {form.conflict && (
        <Notice tone="warning" role="alert">
          <strong>The module changed while this was open.</strong> It was reloaded and the form
          rebuilt. Nothing was applied; review and apply again.
        </Notice>
      )}
      {signIn && (
        <>
          <Notice tone="error" role="alert">
            Your session has expired. What you typed is kept.
          </Notice>
          <div>
            <SignInButton error={form.error} />
          </div>
        </>
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
      {form.checked && form.valid && <EffectsSummary effects={form.effects} status={form.status} />}
    </>
  );
}

const targetOfRef = (r: TouchedRef): Target => ({
  id: refId(r),
  module: moduleOf(r.type),
  type: r.type,
  key: r.key,
});

const sameEntity = (a: { type: string; key: string }, b: { type: string; key: string }) =>
  shortName(a.type) === shortName(b.type) && a.key === b.key;

/** The receipt of an apply, taking focus; each entity it touched opens in the browser. */
export function ReceiptView({
  receipt,
  effects,
  module,
  onLeave,
}: {
  receipt: Receipt;
  effects: readonly Effect[];
  module: string;
  /** The dialog is closed before the browser goes to an entity (focus follows the page). */
  onLeave: () => void;
}) {
  const { meta, go, toOperate } = useBrowser();
  // An entity is named only once the normal read says the viewer can read it, as in History. One
  // the action deleted or created is the viewer's own key and is named: nothing is left to read
  // after a delete, and the reader can lag behind a create (of a type the viewer can describe). Only a definitive "not available" is
  // counted as unreadable; a read that failed for now ("retry") is neither named nor counted.
  const targets = useMemo(() => receipt.refs.map(targetOfRef), [receipt.refs]);
  const { labels } = useLabels(meta, targets);
  const own = (r: TouchedRef) =>
    effects.some(
      (e) =>
        (e.kind === "delete" ||
          (e.kind === "create" && findQualified(meta, r.type) !== undefined)) &&
        sameEntity(e.ref, r),
    );
  const readable = receipt.refs.filter((r) => own(r) || labels[refId(r)]?.state === "ok");
  const unread = receipt.refs.filter(
    (r) => !readable.includes(r) && labels[refId(r)]?.state === "na",
  ).length;
  const linkFor = (r: TouchedRef) => {
    const loc = {
      module: r.type.slice(0, r.type.lastIndexOf(".")),
      type: shortName(r.type),
      key: r.key,
    };
    return {
      href: formatExplore(loc),
      go: () => {
        onLeave();
        go(loc);
      },
    };
  };
  const adminLink =
    toOperate && receipt.group ? toOperate({ group: { module, id: receipt.group } }) : null;
  return (
    <div data-testid="action-receipt">
      <ReceiptSummary
        receipt={{ ...receipt, refs: readable }}
        effects={effects}
        linkFor={linkFor}
        focusOnMount
      />
      {unread > 0 && (
        <p className="gb-dialog-note">
          {unread === 1 ? "1 more entity" : `${unread} more entities`} you cannot read{" "}
          {unread === 1 ? "was" : "were"} touched.
        </p>
      )}
      {adminLink && (
        <p className="m-0 mt-1">
          <CrossAnchor link={adminLink} className="gb-xlink">
            Open this group of changes in Operate
          </CrossAnchor>
        </p>
      )}
    </div>
  );
}
