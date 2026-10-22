// SPDX-License-Identifier: MIT OR Apache-2.0
import type { FormEvent } from "react";
import { shortName } from "../api/gql";
import { useModule, useStatus } from "../api/queries";
import type { ChangesQuery, ModuleInfo } from "../api/types";
import { Button, Chip, Notice } from "../components/ui";
import { useBrand } from "../lib/brand";

export type AuditMode = "changes" | "receipt" | "loads";

export interface AuditForm {
  type: string;
  key: string;
  by: string;
  action: string;
  since: string;
  until: string;
  group: string;
}

const toIso = (v: string) => (v ? new Date(v).toISOString() : undefined);

/** The query a filter form asks for; "needs_type" for a key without a type, null for nothing to ask. */
export function buildQuery(
  name: string,
  provider: string | undefined,
  mode: AuditMode,
  form: AuditForm,
): ChangesQuery | "needs_type" | null {
  const q: ChangesQuery = { module: name, ...(provider ? { provider } : {}) };
  if (mode === "receipt") {
    if (!form.group.trim()) return null;
    return { ...q, group: form.group.trim() };
  }
  if (mode !== "changes") return q;
  // A key names an entity of a type (CONTRACT-001): the server refuses a key without one.
  if (form.key.trim() && !form.type) return "needs_type";
  const fields: [keyof ChangesQuery, string | undefined][] = [
    ["type", form.type],
    ["key", form.key.trim()],
    ["by", form.by.trim()],
    ["action", form.action],
    ["since", toIso(form.since)],
    ["until", toIso(form.until)],
  ];
  return { ...q, ...Object.fromEntries(fields.filter(([, v]) => v)) };
}

export function NoHistory({ module }: { module: string }) {
  const { module: m } = useModule(module);
  const status = useStatus();
  const brand = useBrand();
  const backends = m ? [m.record, ...m.replicas] : [];
  return (
    <div className="m-3" data-testid="no-history">
      <Notice tone="warn" role="status">
        <strong>No change history.</strong> This module's record store keeps no journal that{" "}
        {brand.name} can read, so there is nothing to list. The replica feed is reported instead.
        <ul className="m-0 mt-1 list-none p-0">
          {status.data
            ?.filter((s) => backends.includes(s.backend))
            .map((s) => (
              <li key={s.backend}>
                <span className="arras-mono">{s.backend}</span>: feed position{" "}
                <span className="arras-mono">{s.position ?? "unknown"}</span>, lag{" "}
                <span className="arras-mono">{s.lag ?? "n/a"}</span>
                {!s.available && <Chip tone="bad">unavailable</Chip>}
              </li>
            ))}
        </ul>
      </Notice>
    </div>
  );
}

export function ModeTabs({ mode, onMode }: { mode: AuditMode; onMode: (m: AuditMode) => void }) {
  const tabs: readonly (readonly [AuditMode, string])[] = [
    ["changes", "Changes"],
    ["receipt", "Receipt by group"],
    ["loads", "Import loads"],
  ];
  return (
    <div role="tablist" aria-label="Changes views" className="mb-2 flex gap-1">
      {tabs.map(([k, label]) => (
        <button
          key={k}
          role="tab"
          type="button"
          aria-selected={mode === k}
          onClick={() => onMode(k)}
          className={`rounded border px-3 py-1 text-[12px] ${mode === k ? "border-accent bg-accentsoft font-semibold" : "border-line text-muted hover:text-fg"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

const inputCls = "w-full rounded border border-strong bg-surface px-1.5 py-1 text-[12px] text-fg";

export function ProviderSelect({
  journals,
  value,
  record,
  onChange,
}: {
  journals: string[];
  value: string;
  record: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="mb-2 block text-[12px]">
      Provider
      <select
        className={`${inputCls} ml-1 !w-auto`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {journals.map((j) => (
          <option key={j} value={j}>
            {j}
            {j === record ? " (record store)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

interface FilterProps {
  form: AuditForm;
  setForm: (f: AuditForm) => void;
  m: ModuleInfo | undefined;
  keyError: boolean;
  /** A date was typed: told apart from the other fields, so the address can follow it. */
  onDate?: (form: AuditForm) => void;
}

function ChangeFilters({ form, setForm, m, keyError, onDate }: FilterProps) {
  const set = (field: keyof AuditForm) => (e: { target: { value: string } }) =>
    setForm({ ...form, [field]: e.target.value });
  const setDate = (field: "since" | "until") => (e: { target: { value: string } }) =>
    (onDate ?? setForm)({ ...form, [field]: e.target.value });
  return (
    <>
      <label>
        Type
        <select className={inputCls} value={form.type} onChange={set("type")}>
          <option value="">any</option>
          {m?.entityTypes.map((t) => (
            <option key={t.name} value={t.name}>
              {shortName(t.name)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Key
        <input
          className={inputCls}
          value={form.key}
          aria-invalid={keyError}
          aria-describedby={keyError ? "audit-key-msg" : undefined}
          onChange={set("key")}
        />
        {keyError && (
          <span id="audit-key-msg" role="alert" className="block text-[11px] text-bad">
            Choose the key's type too.
          </span>
        )}
      </label>
      <label>
        Person
        <input className={inputCls} value={form.by} onChange={set("by")} />
      </label>
      <label>
        Action
        <select className={inputCls} value={form.action} onChange={set("action")}>
          <option value="">any</option>
          {m?.actions.map((a) => (
            <option key={a.name} value={a.name}>
              {shortName(a.name)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Since
        <input
          type="datetime-local"
          className={inputCls}
          value={form.since}
          onChange={setDate("since")}
        />
      </label>
      <label>
        Until
        <input
          type="datetime-local"
          className={inputCls}
          value={form.until}
          onChange={setDate("until")}
        />
      </label>
    </>
  );
}

export function FilterForm({
  mode,
  onSubmit,
  ...props
}: FilterProps & { mode: AuditMode; onSubmit: (e?: FormEvent) => void }) {
  const { form, setForm } = props;
  return (
    <form
      onSubmit={onSubmit}
      className="mb-2 grid grid-cols-2 items-end gap-2 md:grid-cols-4 xl:grid-cols-7"
      aria-label="Changes filter"
    >
      {mode === "receipt" ? (
        <label className="col-span-2">
          Group id
          <input
            className={inputCls}
            value={form.group}
            onChange={(e) => setForm({ ...form, group: e.target.value })}
            placeholder="g-481"
          />
        </label>
      ) : (
        <ChangeFilters {...props} />
      )}
      <Button type="submit" variant="primary">
        Search
      </Button>
    </form>
  );
}

export function Pager({
  page,
  nextCursor,
  asOf,
  onNewer,
  onOlder,
}: {
  page: number;
  nextCursor: string | null;
  asOf: string | undefined;
  onNewer: () => void;
  onOlder: () => void;
}) {
  return (
    <div className="mt-2 flex items-center gap-2">
      <Button disabled={page === 0} onClick={onNewer}>
        ← Newer
      </Button>
      <span className="text-muted">Page {page + 1}</span>
      <Button disabled={!nextCursor} onClick={onOlder}>
        Older →
      </Button>
      {asOf && <Chip>as of {asOf}</Chip>}
    </div>
  );
}
