// SPDX-License-Identifier: MIT OR Apache-2.0
import { useEffect, useRef } from "react";
import { ApiError } from "../api/errors";
import { shortName } from "../api/gql";
import type { ActionInfo, InputSpec, Receipt } from "../api/types";
import { ErrorPanel, Spinner } from "../components/ui";
import { takeInputFocus, useFormFocus } from "../lib/formFocus";
import { Field } from "./ActionField";
import {
  ConfirmBar,
  EffectsPreview,
  FormNotices,
  GeneralViolations,
  PreconditionList,
  ReceiptSection,
} from "./ActionPanels";
import type { ImpactState } from "./ImpactPanel";
import { useActionForm } from "./useActionForm";

export { EffectList, ReceiptView } from "./ActionEffects";

export interface ActionFormProps {
  module: string;
  action: string;
  /** Initial text by input name (for example a ref input prefilled from an entity row). */
  prefill?: Record<string, string>;
  onDone?: (r: Receipt) => void;
  /** Told what the form has validated, and what it applied, for the impact view; null when nothing. */
  onState?: (s: ImpactState | null) => void;
  /** Offered after an apply: show the changed entities in the graph. `ids` are `type:key`. */
  onViewInGraph?: (change: { label: string; ids: string[] }) => void;
}

type Form = ReturnType<typeof useActionForm>;

function FieldList({ form, specs }: { form: Form; specs: InputSpec[] }) {
  return (
    <>
      {specs.length === 0 && <div className="mb-3 text-muted">This action takes no inputs.</div>}
      {specs.map((s) => (
        <Field
          key={s.name}
          spec={s}
          value={form.values[s.name]}
          error={form.touched[s.name] ? form.built.errors[s.name] : undefined}
          serverErrors={form.violations.byField[s.name] ?? []}
          disabled={form.locked}
          onChange={(v) => form.onChange(s.name, v)}
          onBlur={() => form.onBlur(s.name)}
        />
      ))}
      <GeneralViolations messages={form.violations.general} />
    </>
  );
}

function ReviewSections({ form, info }: { form: Form; info: ActionInfo }) {
  return (
    <>
      <PreconditionList info={info} failures={form.failures} ok={form.fresh?.ok} />
      <EffectsPreview
        fresh={form.fresh}
        stale={form.stale}
        validating={form.validating}
        module={form.m?.name}
      />
    </>
  );
}

/**
 * US-062: a form built from a declared action's `inputSpecs`. Types are checked as the operator
 * types; validate runs when a field loses focus and before confirmation (never per keystroke);
 * effects are shown before an explicit confirmation; invoke carries a generated idempotency key and
 * the module revision the form was built from.
 */
export function ActionForm({ onViewInGraph, ...args }: ActionFormProps) {
  const root = useRef<HTMLFormElement>(null);
  const formFocus = useFormFocus();
  const form = useActionForm(args);
  const { m, info, meta } = form;
  // A property's "Change" control asks for its input to take the focus when the form opens.
  const name = info?.name;
  useEffect(() => {
    const input = name ? takeInputFocus(formFocus, name) : undefined;
    if (input)
      Array.from(root.current?.querySelectorAll<HTMLElement>("[data-action-input]") ?? [])
        .find((element) => element.dataset.actionInput === input)
        ?.focus();
  }, [name, formFocus]);
  if (meta.isPending) return <Spinner label="Loading action" />;
  if (meta.error) return <ErrorPanel error={meta.error} />;
  if (!m || !info) return <ErrorPanel error={new ApiError(404, { message: "not found" })} />;

  return (
    <form
      key={form.epoch}
      ref={root}
      className="max-w-[600px] p-3"
      aria-label={`Action ${info.name}`}
      onSubmit={(e) => {
        e.preventDefault();
        void form.validate();
      }}
      data-testid="action-form"
    >
      <h2 className="m-0 text-[15px] font-semibold">
        {shortName(info.name)}{" "}
        <span className="ml-1 text-[12px] font-normal text-muted">{info.name}</span>
      </h2>
      <p className="mb-3 mt-0.5 text-muted">{info.description}</p>

      <FormNotices
        conflict={form.conflict}
        revision={form.revision}
        refusal={form.refusal}
        error={form.error}
      />
      <FieldList form={form} specs={form.specs} />
      {form.receipt ? (
        <ReceiptSection
          receipt={form.receipt}
          receiptRef={form.receiptRef}
          module={m}
          info={info}
          checked={form.checked?.result ?? null}
          onViewInGraph={onViewInGraph}
          onReset={form.reset}
          onEdit={form.editAgain}
        />
      ) : (
        <>
          <ReviewSections form={form} info={info} />
          <ConfirmBar
            locked={form.locked}
            validating={form.validating}
            refused={!!form.refusal}
            fresh={form.fresh}
            canConfirm={form.canConfirm}
            stale={form.stale}
            submitting={form.submitting}
            revision={form.revision}
            onConfirm={() => void form.confirm()}
          />
        </>
      )}
    </form>
  );
}
