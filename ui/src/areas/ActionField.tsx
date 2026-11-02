// SPDX-License-Identifier: MIT OR Apache-2.0
import { useId } from "react";
import { shortName } from "../api/gql";
import type { InputSpec } from "../api/types";
import { Chip } from "../components/ui";
import { keyed } from "../lib/format";
import { type FieldValue, isMany, isRequired } from "../lib/inputs";

const SCALAR_HINTS = new Map([
  ["timestamp", "RFC 3339 with an offset, e.g. 2026-10-09T14:02:11Z"],
  ["decimal", "a decimal number, sent as text"],
  ["integer", "an integer; beyond 53 bits it is sent as text"],
  ["binary", "base64 text"],
]);

function hintFor(spec: InputSpec, many: boolean): string {
  if (spec.kind === "record") {
    return many
      ? "a JSON array of objects"
      : `a JSON object (${spec.type}); no generated form for records`;
  }
  if (many) return "one value per line";
  if (spec.kind === "ref") return `the key of a ${shortName(spec.type)}`;
  return SCALAR_HINTS.get(spec.type) ?? "";
}

function FieldLabel({ spec, id }: { spec: InputSpec; id: string }) {
  return (
    <label htmlFor={id} className="mb-0.5 flex flex-wrap items-center gap-1.5 font-medium">
      <span className="arras-mono">{spec.name}</span>
      {isRequired(spec) && (
        <span className="text-bad">
          <span aria-hidden="true">*</span>
          <span className="sr-only">required</span>
        </span>
      )}
      <Chip>{spec.kind === "ref" ? `ref ${shortName(spec.type)}` : spec.type}</Chip>
      <Chip>{spec.kind}</Chip>
      {spec.cardinality !== "one" && <Chip>{spec.cardinality}</Chip>}
    </label>
  );
}

function FieldControl({
  spec,
  common,
  onChange,
}: {
  spec: InputSpec;
  common: Record<string, unknown> & { className: string };
  onChange: (v: string) => void;
}) {
  const many = isMany(spec);
  if (spec.type === "boolean" && spec.kind === "scalar" && !many) {
    return (
      <select {...common} onChange={(e) => onChange(e.target.value)}>
        <option value="">{isRequired(spec) ? "Choose…" : "(unset)"}</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  }
  if (many || spec.kind === "record" || spec.type === "binary") {
    return (
      <textarea
        {...common}
        rows={spec.kind === "record" ? 5 : 3}
        spellCheck={false}
        className={`${common.className} ${spec.kind === "record" ? "arras-mono" : ""}`}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      {...common}
      type="text"
      autoComplete="off"
      spellCheck={false}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function FieldMessages({
  spec,
  id,
  hint,
  error,
  serverErrors,
}: {
  spec: InputSpec;
  id: string;
  hint: string;
  error?: string;
  serverErrors: string[];
}) {
  return (
    <div id={`${id}-msg`} className="mt-0.5 min-h-4 text-[12px]">
      {hint && !error && serverErrors.length === 0 && <span className="text-muted">{hint}</span>}
      {error && (
        <div role="alert" className="text-bad" data-testid={`err-${spec.name}`}>
          Expected {error === "required" ? "a value (required)" : error}
        </div>
      )}
      {keyed(serverErrors, (m) => m).map(({ key, item: m }) => (
        <div key={key} role="alert" className="text-bad" data-testid={`violation-${spec.name}`}>
          {m}
        </div>
      ))}
    </div>
  );
}

export function Field({
  spec,
  value,
  error,
  serverErrors,
  disabled,
  onChange,
  onBlur,
}: {
  spec: InputSpec;
  value: FieldValue | undefined;
  error?: string;
  serverErrors: string[];
  disabled: boolean;
  onChange: (v: string) => void;
  onBlur: () => void;
}) {
  const id = useId();
  const common = {
    id,
    "data-action-input": spec.name,
    disabled,
    value: Array.isArray(value) ? value.join("\n") : (value ?? ""),
    "aria-invalid": !!error || serverErrors.length > 0,
    "aria-describedby": `${id}-msg`,
    onBlur,
    className:
      "w-full rounded border border-strong bg-surface px-2 py-1 text-[13px] text-fg aria-[invalid=true]:border-bad disabled:opacity-60",
  };
  return (
    <div className="mb-3" data-testid={`field-${spec.name}`}>
      <FieldLabel spec={spec} id={id} />
      <FieldControl spec={spec} common={common} onChange={onChange} />
      <FieldMessages
        spec={spec}
        id={id}
        hint={hintFor(spec, isMany(spec))}
        error={error}
        serverErrors={serverErrors}
      />
    </div>
  );
}
