// SPDX-License-Identifier: MIT OR Apache-2.0
// The slot a surface fills to ask for a reference: the console with a key field, the Graph Browser
// with its picker (SD-013, D3). The kit supplies the key field as the default.

import type { ReactNode } from "react";
import { shortName } from "../api/gql";
import type { InputSpec } from "../api/types";
import { TextField } from "../ds";

export interface RefInputProps {
  spec: InputSpec;
  /** The key as typed. */
  value: string;
  onChange: (value: string) => void;
  /** The message to show at the field, if any. */
  error?: string;
  /** The module the action belongs to, so a picker can read that module's entities. */
  module: string;
  /** The referenced entity type, as the input spec names it. */
  type: string;
  /** The id the field carries, so a label, a description and focus find it. */
  id?: string;
  disabled?: boolean;
  label?: ReactNode;
  hint?: ReactNode;
  onBlur?: () => void;
}

/** A text field for the entity's key. */
export function KeyRefInput({
  spec,
  value,
  onChange,
  error,
  type,
  id,
  disabled,
  label,
  hint,
  onBlur,
}: RefInputProps) {
  return (
    <TextField
      id={id}
      label={label ?? spec.name}
      hint={hint ?? `the key of a ${shortName(type)}`}
      error={error}
      value={value}
      disabled={disabled}
      aria-required={spec.cardinality === "one" || undefined}
      autoComplete="off"
      spellCheck={false}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
    />
  );
}
