// SPDX-License-Identifier: MIT OR Apache-2.0
// The Graph Browser's `RefInput` (SD-013, D3): a reference field drawn as the link picker is. The
// entities of the referenced type are listed at once in a dropdown, narrowed as the reader types in
// the filter above it, or searched for when the type has more than the list holds. The value is the
// chosen entity's key. Where the type is not one the viewer may read, or its list cannot be read, the
// kit's key field stands in and the reader types the key.
import { Select, TextField } from "../ds";
import { KeyRefInput, type RefInputProps } from "../kit";
import { useBrowser } from "./context";
import { findQualified, findType, type TypeEntry } from "./meta";
import { type Row, usePick } from "./usePick";

/** The options: the rows, with the chosen key kept in even where the filter has narrowed it away. */
function optionsFor(rows: Row[], value: string) {
  const list = rows.map((r) => ({ value: r.key, label: r.label }));
  return value && !list.some((o) => o.value === value) ? [{ value, label: value }, ...list] : list;
}

function Picker({ entry, ...p }: RefInputProps & { entry: TypeEntry }) {
  const pick = usePick([entry]);
  if (!pick.listable) return <KeyRefInput {...p} />;
  return (
    <div className="gb-ref-picker">
      <TextField
        id={p.id ? `${p.id}-filter` : undefined}
        label={`Filter or search ${entry.view.pluralLabel.toLowerCase()}`}
        autoComplete="off"
        value={pick.text}
        disabled={p.disabled}
        onChange={(e) => pick.setText(e.target.value)}
      />
      <Select
        id={p.id}
        label={p.label ?? p.spec.name}
        hint={p.hint ?? pick.hint}
        error={p.error}
        placeholder={pick.loading ? "Loading…" : "Choose…"}
        disabled={p.disabled || pick.loading}
        value={p.value}
        options={optionsFor(pick.rows, p.value)}
        aria-required={p.spec.cardinality === "one" || undefined}
        onChange={(e) => p.onChange(e.target.value)}
        onBlur={p.onBlur}
      />
    </div>
  );
}

export function RefPicker(p: RefInputProps) {
  const { meta } = useBrowser();
  const entry = p.type.includes(".")
    ? findQualified(meta, p.type)
    : findType(meta, p.module, p.type);
  return entry ? <Picker entry={entry} {...p} /> : <KeyRefInput {...p} />;
}
