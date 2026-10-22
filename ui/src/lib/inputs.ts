// SPDX-License-Identifier: MIT OR Apache-2.0
// Client-side typing of action inputs and their wire encodings (src/arras/inputs.py,
// CONTRACT-009): decimals, timestamps and integers beyond 53 bits travel as text, binary as base64,
// a ref as its key, a record as a JSON object, a list as an array. The server checks again.

import { shortName } from "../api/gql";
import type { InputSpec, Violation } from "../api/types";

export type FieldValue = string | string[]; // text as typed; "many" scalars are one per line

const INT = /^[+-]?\d+$/;
const DEC = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
// RFC 3339 as src/arras/inputs.py reads it (datetime.fromisoformat, then an offset is required):
// `T`, `t` or a space between date and time, seconds optional, a fraction, and `Z`/`z` or ±hh:mm.
const TS =
  /^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:[Zz]|[+-](\d{2}):?(\d{2}))$/;
const B64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const SAFE = BigInt(2) ** BigInt(53);

const daysIn = (y: number, m: number) =>
  [
    31,
    y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ][m - 1] ?? 0;

/** An RFC 3339 timestamp with an offset and a real calendar date and time (no 2026-02-30, no 24:00). */
export function isTimestamp(t: string): boolean {
  const m = TS.exec(t);
  if (!m) return false;
  const [, y, mo, d, h, mi, s, oh, om] = m;
  const n = (x: string | undefined) => Number(x ?? "0");
  if (n(mo) < 1 || n(mo) > 12 || n(d) < 1 || n(d) > daysIn(n(y), n(mo))) return false;
  if (n(h) > 23 || n(mi) > 59 || n(s) > 59) return false;
  return n(oh) <= 23 && n(om) <= 59;
}

/** Is `raw` (trimmed) a value of the scalar `type`? The check the form makes before any request. */
export function checkScalar(type: string, raw: string): Encoded {
  return scalar(type, raw);
}

export const SCALARS = ["string", "integer", "decimal", "boolean", "timestamp", "binary"];

export function isMany(s: InputSpec) {
  return s.cardinality === "many";
}
export function isRequired(s: InputSpec) {
  return s.cardinality === "one";
}

export interface Encoded {
  value: unknown; // undefined = omit
  error?: string;
}

const bad = (error: string): Encoded => ({ value: undefined, error });

function integer(t: string): Encoded {
  if (!INT.test(t)) return bad("an integer");
  const n = BigInt(t);
  return { value: n < SAFE && n > -SAFE ? Number(n) : t };
}

function boolean(t: string): Encoded {
  const v = t.toLowerCase();
  if (v === "true") return { value: true };
  if (v === "false") return { value: false };
  return bad("true or false");
}

// Each reads the trimmed text; a type not listed here is taken as typed.
const SCALAR_READERS: Record<string, (t: string) => Encoded> = {
  integer,
  decimal: (t) => (DEC.test(t) ? { value: t } : bad("a decimal number, for example 12.50")),
  boolean,
  timestamp: (t) =>
    isTimestamp(t)
      ? { value: t }
      : bad("an RFC 3339 timestamp with an offset, for example 2026-10-09T14:02:11Z"),
  binary: (t) => (B64.test(t) ? { value: t } : bad("base64 text")),
};

function scalar(type: string, raw: string): Encoded {
  const read = SCALAR_READERS[type];
  return read ? read(raw.trim()) : { value: raw };
}

function record(raw: string): Encoded {
  try {
    const v: unknown = JSON.parse(raw);
    if (v === null || typeof v !== "object" || Array.isArray(v)) return bad("a JSON object");
    return { value: v };
  } catch {
    return bad("valid JSON");
  }
}

const isObject = (x: unknown) => x !== null && typeof x === "object" && !Array.isArray(x);

function recordList(raw: FieldValue): Encoded {
  try {
    const v: unknown = JSON.parse(Array.isArray(raw) ? raw.join("\n") : raw);
    if (!(Array.isArray(v) && v.every(isObject))) return bad("a JSON array of objects");
    return { value: v };
  } catch {
    return bad("valid JSON");
  }
}

function encodeOne(spec: InputSpec, s: string): Encoded {
  if (spec.kind === "record") return record(s);
  if (spec.kind === "ref") return { value: s.trim() };
  return scalar(spec.type, s);
}

function encodeMany(spec: InputSpec, raw: FieldValue): Encoded {
  if (spec.kind === "record") return recordList(raw);
  const lines = (Array.isArray(raw) ? raw : raw.split("\n")).map((l) => l.trim()).filter(Boolean);
  const out: unknown[] = [];
  for (const [i, l] of lines.entries()) {
    const e = encodeOne(spec, l);
    if (e.error) return bad(`line ${i + 1}: ${e.error}`);
    out.push(e.value);
  }
  return { value: out };
}

const isEmpty = (raw: FieldValue | undefined) =>
  raw === undefined || (Array.isArray(raw) ? raw.length === 0 : raw.trim() === "");

/** Encode one field's text. Empty optional fields are omitted; an empty required one is an error. */
export function encodeField(spec: InputSpec, raw: FieldValue | undefined): Encoded {
  if (raw === undefined || isEmpty(raw)) {
    return isRequired(spec) ? bad("required") : { value: undefined };
  }
  if (isMany(spec)) return encodeMany(spec, raw);
  return encodeOne(spec, Array.isArray(raw) ? (raw[0] ?? "") : raw);
}

export interface Built {
  inputs: Record<string, unknown>;
  errors: Record<string, string>; // by input name
}

export function buildInputs(specs: InputSpec[], values: Record<string, FieldValue>): Built {
  const inputs: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const s of specs) {
    const e = encodeField(s, values[s.name]);
    if (e.error) errors[s.name] = e.error;
    else if (e.value !== undefined) inputs[s.name] = e.value;
  }
  return { inputs, errors };
}

/** Map server violation paths (`inputs.level`, `inputs.tags[2]`, `items[3].inputs.x`) to input names. */
export function violationsByField(vs: Violation[]): {
  byField: Record<string, string[]>;
  general: string[];
} {
  const byField: Record<string, string[]> = {};
  const general: string[] = [];
  for (const v of vs) {
    const m = /(?:^|\.)inputs\.([^.[\]]+)/.exec(v.path) ?? /^inputs$/.exec(v.path);
    const name = m?.[1];
    const text = `${v.message} (${v.code})`;
    if (name) {
      byField[name] ??= [];
      byField[name].push(text);
    } else general.push(`${v.path ? `${v.path}: ` : ""}${text}`);
  }
  return { byField, general };
}

/** Does a ref input of this spec accept an entity of `entityType` (qualified, e.g. catalog.Solution)? */
export function refAccepts(spec: InputSpec, entityType: string): boolean {
  return spec.kind === "ref" && shortName(spec.type) === shortName(entityType);
}

export function newKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  );
}
