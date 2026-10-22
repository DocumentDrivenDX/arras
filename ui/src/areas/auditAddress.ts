// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ChangesQuery } from "../api/types";
import type { AuditForm, AuditMode } from "./AuditParts";

/**
 * What the Changes route says (CONTRACT-010 D): an entity's history, the filters, one group's
 * receipt, or the import loads. The person typed in the filter form is never in it.
 */
export interface AuditAddress {
  type?: string;
  key?: string;
  action?: string;
  group?: string;
  since?: string;
  until?: string;
  loads?: boolean;
}

/** Asks for an address; `replace` rewrites the current history entry instead of adding one. */
export type WriteAudit = (address: AuditAddress, how: { replace: boolean }) => void;

const pad = (n: number) => String(n).padStart(2, "0");

/** An instant as a `datetime-local` field shows it: the viewer's local time, to the minute. */
export function toLocalInput(iso: string | undefined): string {
  const d = iso ? new Date(iso) : undefined;
  if (!d || Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const toIso = (v: string) => (v ? new Date(v).toISOString() : undefined);

/** The mode an address opens in. */
export const modeOf = (a: AuditAddress): AuditMode =>
  a.loads ? "loads" : a.group ? "receipt" : "changes";

/** The filter form an address fills; the person is not in an address. */
export const formOf = (a: AuditAddress): AuditForm => ({
  type: a.type ?? "",
  key: a.key ?? "",
  by: "",
  action: a.action ?? "",
  since: toLocalInput(a.since),
  until: toLocalInput(a.until),
  group: a.group ?? "",
});

const present = <T extends object>(o: T): T =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== "")) as T;

/** The read an address asks for first. */
export function queryOf(module: string, a: AuditAddress): ChangesQuery {
  if (a.group) return { module, group: a.group };
  return {
    module,
    ...present({
      type: a.type,
      key: a.key,
      action: a.action,
      since: a.since,
      until: a.until,
    }),
  };
}

/** The address of the read in force: what the route keeps of it (never the person or the journal). */
export function addressOf(mode: AuditMode, q: ChangesQuery | undefined): AuditAddress {
  if (mode === "loads") return { loads: true };
  if (!q) return {};
  if (q.group) return { group: q.group };
  return present({
    type: q.type,
    key: q.type ? q.key : undefined,
    action: q.action,
    since: q.since,
    until: q.until,
  });
}

/** The address a form being typed into names, over the one in force. */
export function withDates(base: AuditAddress, form: AuditForm): AuditAddress {
  return present({ ...base, since: toIso(form.since), until: toIso(form.until) });
}

/** A string that is equal for equal addresses. */
export const auditKey = (a: AuditAddress): string =>
  JSON.stringify([a.type, a.key, a.action, a.group, a.since, a.until, !!a.loads]);
