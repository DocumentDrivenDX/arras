// SPDX-License-Identifier: MIT OR Apache-2.0
// Pure formatting for the `format` set of CONTRACT-010: numbers, dates, links and emptiness. The
// server resolved which format a property uses; this only renders the value it was given.

export const isEmpty = (v: unknown): boolean =>
  v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function groupSeparator(locale?: string): string {
  const parts = new Intl.NumberFormat(locale).formatToParts(1_000_000);
  return parts.find((p) => p.type === "group")?.value ?? ",";
}

/**
 * The integer part grouped by the viewer's locale, the stored digits otherwise unchanged: a value
 * is text on the wire (a BigInt or a decimal), so it is never turned into a float.
 */
export function formatNumber(v: unknown, locale?: string): string {
  const text = String(v);
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(text);
  if (!m) return text;
  const [, sign = "", int = "", frac = ""] = m;
  const sep = groupSeparator(locale);
  return `${sign}${int.replace(/\B(?=(\d{3})+(?!\d))/g, sep)}${frac}`;
}

const stamp = (v: unknown): Date | null => {
  const d = new Date(String(v));
  return Number.isNaN(d.getTime()) ? null : d;
};

/** A local, readable date; the stored text when it does not parse. */
export function formatDate(v: unknown, locale?: string): string {
  const d = stamp(v);
  return d
    ? d.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" })
    : String(v);
}

export function formatDateTime(v: unknown, locale?: string): string {
  const d = stamp(v);
  if (!d) return String(v);
  const date = d.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
  const time = d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}

const SAFE_SCHEMES = new Set(["http:", "https:", "mailto:"]);

export interface SafeLink {
  href: string;
  display: string;
}

const LONG_URL = 44;

function shortUrl(u: URL, raw: string): string {
  if (raw.length <= LONG_URL || u.protocol === "mailto:") return raw;
  const last = u.pathname.split("/").filter(Boolean).pop();
  return last ? `${u.host}/…/${last}` : u.host;
}

/** An `http`, `https` or `mailto` address, or null: anything else is shown as text (CONTRACT-010). */
export function safeLink(value: string): SafeLink | null {
  let u: URL;
  try {
    u = new URL(value.trim());
  } catch {
    return null;
  }
  if (!SAFE_SCHEMES.has(u.protocol)) return null;
  return { href: u.href, display: shortUrl(u, value.trim()) };
}

export const yesNo = (v: unknown): string => (v === true || v === "true" ? "Yes" : "No");

export function jsonText(v: unknown): string {
  return JSON.stringify(v, null, 2) ?? "";
}

/** `text` of a list value: its entries joined, for formats that show a list as one string. */
export const listOf = (v: unknown): string[] =>
  Array.isArray(v) ? v.map((x) => String(x)) : isEmpty(v) ? [] : [String(v)];
