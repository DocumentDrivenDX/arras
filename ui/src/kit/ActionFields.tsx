// SPDX-License-Identifier: MIT OR Apache-2.0
// Every input of a declared action as a field (SD-013): text, number, boolean, a reference through
// the injected `RefInput`, a list one value per line, a record as JSON. Errors are associated with
// their field by `aria-describedby` (the widgets wire it from `error` and `hint`).

import { type ComponentType, type ReactNode, useEffect, useId, useRef } from "react";
import { shortName } from "../api/gql";
import type { InputSpec, Violation } from "../api/types";
import { Select, TextArea, TextField } from "../ds";
import { takeInputFocus, useFormFocus } from "../lib/formFocus";
import { type FieldValue, isMany, isRequired, violationsByField } from "../lib/inputs";
import { KeyRefInput, type RefInputProps } from "./RefInput";

const SCALAR_HINTS = new Map([
  ["timestamp", "RFC 3339 with an offset, e.g. 2026-10-09T14:02:11Z"],
  ["decimal", "a decimal number, sent as text"],
  ["integer", "an integer; beyond 53 bits it is sent as text"],
  ["binary", "base64 text"],
]);

function hintFor(spec: InputSpec): string {
  if (spec.kind === "record") {
    return isMany(spec) ? "a JSON array of objects" : `a JSON object (${spec.type})`;
  }
  if (isMany(spec)) {
    return spec.kind === "ref"
      ? `the keys of ${shortName(spec.type)} entities, one per line`
      : "one value per line";
  }
  if (spec.kind === "ref") return `the key of a ${shortName(spec.type)}`;
  return SCALAR_HINTS.get(spec.type) ?? "";
}

/** The label: the name, with a required mark that is also read aloud. */
function labelOf(spec: InputSpec): ReactNode {
  return (
    <>
      <span className="arras-mono">{spec.name}</span>
      {isRequired(spec) && (
        <>
          <span aria-hidden="true"> *</span>
          <span className="sr-only"> (required)</span>
        </>
      )}
    </>
  );
}

const textOf = (v: FieldValue | undefined) => (Array.isArray(v) ? v.join("\n") : (v ?? ""));

/** What JSON.parse says of a record's text, shown at the field; undefined when it parses or is empty. */
function jsonError(spec: InputSpec, text: string): string | undefined {
  if (spec.kind !== "record" || text.trim() === "") return undefined;
  try {
    JSON.parse(text);
    return undefined;
  } catch (e) {
    return `Not valid JSON: ${e instanceof Error ? e.message : "unreadable"}`;
  }
}

/** The one message a field shows: its own, the client's, then the server's. */
function messageFor(error: string | undefined, json: string | undefined, server: string[]) {
  const own = error ? [`Expected ${error === "required" ? "a value (required)" : error}`] : [];
  const all = [...(json ? [json] : own), ...server];
  return all.length ? all.join("; ") : undefined;
}

/** The violations no field shows: those whose path names no input. The caller renders them. */
export const generalViolations = (violations: Violation[]): string[] =>
  violationsByField(violations).general;

export interface ActionFieldsProps {
  /** The action's name, so a pending request to focus one of its inputs finds it. */
  action: string;
  /** The module the action belongs to. */
  module: string;
  specs: InputSpec[];
  values: Record<string, FieldValue>;
  /** The client's encoding errors by input name (`buildInputs`). */
  errors?: Record<string, string>;
  /**
   * The server's violations; those whose path names an input are shown at that field. Violations
   * with no field path (`general`, see `generalViolations`) are not rendered here: the caller shows them.
   */
  violations?: Violation[];
  disabled?: boolean;
  onChange: (name: string, text: string) => void;
  onBlur?: (name: string) => void;
  /** What asks for a reference; the key field when not given. */
  RefInput?: ComponentType<RefInputProps>;
  /** Makes field ids unique where two forms are on one page. */
  idPrefix?: string;
}

interface FieldProps {
  spec: InputSpec;
  id: string;
  text: string;
  message: string | undefined;
  disabled: boolean;
  module: string;
  onChange: (text: string) => void;
  onBlur: () => void;
  RefInput: ComponentType<RefInputProps>;
}

function BooleanField({ spec, id, text, message, disabled, onChange, onBlur }: FieldProps) {
  return (
    <Select
      id={id}
      label={labelOf(spec)}
      error={message}
      value={text}
      disabled={disabled}
      aria-required={isRequired(spec) || undefined}
      placeholder={isRequired(spec) ? "Choose…" : "(unset)"}
      options={[
        { value: "true", label: "true" },
        { value: "false", label: "false" },
      ]}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}

function AreaField({ spec, id, text, message, disabled, onChange, onBlur }: FieldProps) {
  return (
    <TextArea
      id={id}
      label={labelOf(spec)}
      hint={hintFor(spec)}
      error={message}
      value={text}
      rows={spec.kind === "record" ? 5 : 3}
      disabled={disabled}
      aria-required={isRequired(spec) || undefined}
      spellCheck={false}
      className={spec.kind === "record" ? "arras-mono" : undefined}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}

function LineField({ spec, id, text, message, disabled, onChange, onBlur }: FieldProps) {
  const numeric = spec.type === "integer" || spec.type === "decimal";
  return (
    <TextField
      id={id}
      label={labelOf(spec)}
      hint={hintFor(spec)}
      error={message}
      value={text}
      disabled={disabled}
      aria-required={isRequired(spec) || undefined}
      inputMode={numeric ? (spec.type === "integer" ? "numeric" : "decimal") : undefined}
      autoComplete="off"
      spellCheck={false}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}

function Field(p: FieldProps) {
  const { spec } = p;
  if (spec.kind === "ref" && !isMany(spec)) {
    return (
      <p.RefInput
        spec={spec}
        id={p.id}
        value={p.text}
        error={p.message}
        module={p.module}
        type={spec.type}
        disabled={p.disabled}
        label={labelOf(spec)}
        onChange={p.onChange}
        onBlur={p.onBlur}
      />
    );
  }
  if (spec.kind === "scalar" && spec.type === "boolean" && !isMany(spec)) {
    return <BooleanField {...p} />;
  }
  if (isMany(spec) || spec.kind === "record" || spec.type === "binary") {
    return <AreaField {...p} />;
  }
  return <LineField {...p} />;
}

export function ActionFields({
  action,
  module,
  specs,
  values,
  errors = {},
  violations = [],
  disabled = false,
  onChange,
  onBlur,
  RefInput = KeyRefInput,
  idPrefix: givenPrefix,
}: ActionFieldsProps) {
  const generatedPrefix = useId();
  const idPrefix = givenPrefix ?? generatedPrefix;
  const root = useRef<HTMLDivElement>(null);
  const formFocus = useFormFocus();
  const { byField } = violationsByField(violations);
  useEffect(() => {
    const name = takeInputFocus(formFocus, action);
    if (name)
      Array.from(root.current?.querySelectorAll<HTMLElement>("[id]") ?? [])
        .find((element) => element.id === `${idPrefix}-${name}`)
        ?.focus();
  }, [action, idPrefix, formFocus]);
  return (
    <div ref={root} className="space-y-3" data-testid="action-fields">
      {specs.map((spec) => {
        const text = textOf(values[spec.name]);
        const message = messageFor(
          errors[spec.name],
          jsonError(spec, text),
          byField[spec.name] ?? [],
        );
        return (
          <div key={spec.name} data-testid={`field-${spec.name}`}>
            <Field
              spec={spec}
              id={`${idPrefix}-${spec.name}`}
              text={text}
              message={message}
              disabled={disabled}
              module={module}
              onChange={(t) => onChange(spec.name, t)}
              onBlur={() => onBlur?.(spec.name)}
              RefInput={RefInput}
            />
          </div>
        );
      })}
    </div>
  );
}
