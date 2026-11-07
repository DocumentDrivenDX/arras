// SPDX-License-Identifier: MIT OR Apache-2.0
// The pure parts of search for the static read-only profile (CONTRACT-010 C, CONTRACT-012): the fold,
// the words, ranking and excerpts. A port of `arras/searchplan.py`. Python indexes strings by code point
// and tests whitespace and alphanumerics with its own tables, so this works on arrays of code points and
// states those tables, rather than trusting `\s` or `String.length` to agree.

export const MIN_CHARS = 2;
export const MAX_CHARS = 200;
export const MAX_WORDS = 6;
export const MAX_LIMIT = 50;
export const CANDIDATES = 50;
export const MAX_TYPES = 20;
export const MAX_ENTITIES = 1000;
const EXCERPT_CHARS = 160;
const EXCERPT_BEFORE = 40;
const BOUNDARY_SLACK = 16;
const ELLIPSIS = "…";

/** Python `str.isspace` for one character. */
// biome-ignore lint/suspicious/noControlCharactersInRegex: the control characters are the point: Python counts them as space
const SPACE = /^[\t\n\v\f\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/;
const isSpace = (c: string | undefined): boolean => c !== undefined && SPACE.test(c);
/** Python `str.isalnum` for one character: a letter or a number. */
const ALNUM = /^[\p{L}\p{N}]$/u;
const isAlnum = (c: string | undefined): boolean => c !== undefined && ALNUM.test(c);

/** Python `str.split()` with no argument: runs of whitespace separate, none is kept. */
const splitWhitespace = (text: string): string[] => {
  const out: string[] = [];
  let cur = "";
  for (const c of text) {
    if (isSpace(c)) {
      if (cur) out.push(cur);
      cur = "";
    } else cur += c;
  }
  if (cur) out.push(cur);
  return out;
};

/** `text` lowercased one character at a time (Unicode lowercase, no compatibility normalisation). */
export const lower = (text: string): string => Array.from(text, (c) => c.toLowerCase()).join("");

/** Trimmed, whitespace runs collapsed to one space, then lowercased with `lower`. */
export const fold = (text: string): string => lower(splitWhitespace(text).join(" "));

export class BadText extends Error {}

/** The folded text and its words, or `BadText`. The message never repeats the text. */
export function checkText(text: string): { folded: string; words: string[] } {
  const folded = fold(text);
  const words = folded ? folded.split(" ") : [];
  const n = Array.from(folded).length;
  if (n < MIN_CHARS || n > MAX_CHARS)
    throw new BadText(`text is ${MIN_CHARS} to ${MAX_CHARS} characters`);
  if (words.length > MAX_WORDS) throw new BadText(`text is at most ${MAX_WORDS} words`);
  return { folded, words };
}

/** How a folded value matches a folded word: 4 equal, 3 starts with it, 2 a word within it starts with it, 1 contains it, 0 not. */
export function tier(value: string, word: string): number {
  if (value === word) return 4;
  if (value.startsWith(word)) return 3;
  let at = value.indexOf(word);
  while (at > 0) {
    const prev = Array.from(value.slice(Math.max(0, at - 2), at)).pop();
    if (!isAlnum(prev)) return 2;
    at = value.indexOf(word, at + 1);
  }
  return value.includes(word) ? 1 : 0;
}

export interface Ranked {
  score: number;
  matched: string[];
}

/** `null` unless every word is in at least one property; per word the best tier scaled by position, summed. */
export function rank(
  words: string[],
  properties: string[],
  row: Record<string, unknown>,
): Ranked | null {
  const values = new Map<string, string>();
  for (const p of properties) {
    const v = row[p];
    if (typeof v === "string") values.set(p, lower(v));
  }
  const n = properties.length;
  let score = 0;
  const matched = new Set<string>();
  for (const word of words) {
    let best = 0;
    properties.forEach((p, i) => {
      const value = values.get(p);
      const t = value === undefined ? 0 : tier(value, word);
      if (t) {
        matched.add(p);
        best = Math.max(best, t * (n - i));
      }
    });
    if (best === 0) return null;
    score += best;
  }
  return { score, matched: properties.filter((p) => matched.has(p)) };
}

export interface Segment {
  text: string;
  mark: boolean;
}

function foldedWithOrigins(value: string[]): { folded: string[]; origins: number[] } {
  const folded: string[] = [];
  const origins: number[] = [];
  value.forEach((c, i) => {
    for (const x of c.toLowerCase()) {
      folded.push(x);
      origins.push(i);
    }
  });
  return { folded, origins };
}

function indexOfRun(hay: string[], needle: string[], from: number): number {
  for (let i = from; i + needle.length <= hay.length; i++) {
    let j = 0;
    while (j < needle.length && hay[i + j] === needle[j]) j++;
    if (j === needle.length) return i;
  }
  return -1;
}

/** The matched ranges of `value`, merged and in order. */
function spans(value: string[], words: string[]): [number, number][] {
  const { folded, origins } = foldedWithOrigins(value);
  const found: [number, number][] = [];
  for (const word of new Set(words)) {
    const w = Array.from(word);
    if (w.length === 0) continue;
    let at = indexOfRun(folded, w, 0);
    while (at >= 0) {
      found.push([origins[at] as number, (origins[at + w.length - 1] as number) + 1]);
      at = indexOfRun(folded, w, at + w.length);
    }
  }
  found.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged: [number, number][] = [];
  for (const [lo, hi] of found) {
    const last = merged[merged.length - 1];
    if (last && lo <= last[1]) last[1] = Math.max(last[1], hi);
    else merged.push([lo, hi]);
  }
  return merged;
}

/** Up to 160 characters around the first match, moved to word boundaries where one is near. */
function window(value: string[], first: [number, number]): [number, number] {
  if (value.length <= EXCERPT_CHARS) return [0, value.length];
  let lo = Math.max(0, first[0] - EXCERPT_BEFORE);
  let hi = Math.min(value.length, lo + EXCERPT_CHARS);
  if (lo > 0) {
    for (let i = lo; i < Math.min(first[0], lo + BOUNDARY_SLACK); i++) {
      if (isSpace(value[i - 1]) && !isSpace(value[i])) {
        lo = i;
        break;
      }
    }
  }
  if (hi < value.length) {
    for (let i = hi; i > Math.max(first[1], hi - BOUNDARY_SLACK); i--) {
      if (isSpace(value[i])) {
        hi = i;
        break;
      }
    }
  }
  return [lo, hi];
}

type Piece = [string, boolean];

function joinEllipsis(pieces: Piece[], front: boolean): Piece[] {
  const edge = (front ? pieces[0] : pieces[pieces.length - 1]) as Piece;
  if (edge[1]) return front ? [[ELLIPSIS, false], ...pieces] : [...pieces, [ELLIPSIS, false]];
  const joined: Piece = front ? [ELLIPSIS + edge[0], false] : [edge[0] + ELLIPSIS, false];
  return front ? [joined, ...pieces.slice(1)] : [...pieces.slice(0, -1), joined];
}

/**
 * The part of `value` around its first match, as consecutive segments: `mark` is true for the matched
 * text. A cut start or end is an ellipsis. Empty when `value` contains no word.
 */
export function excerpt(text: string, words: string[]): Segment[] {
  const value = Array.from(text);
  const found = spans(value, words);
  const firstSpan = found[0];
  if (!firstSpan) return [];
  const [lo, hi] = window(value, firstSpan);
  let pieces: Piece[] = [];
  let at = lo;
  for (const [s0, e0] of found) {
    const s = Math.max(s0, lo);
    const e = Math.min(e0, hi);
    if (s >= e) continue;
    if (s > at) pieces.push([value.slice(at, s).join(""), false]);
    pieces.push([value.slice(s, e).join(""), true]);
    at = e;
  }
  if (at < hi) pieces.push([value.slice(at, hi).join(""), false]);
  if (lo > 0) pieces = joinEllipsis(pieces, true);
  if (hi < value.length) pieces = joinEllipsis(pieces, false);
  return pieces.map(([t, m]) => ({ text: t, mark: m }));
}

const SURROGATE = /[\ud800-\udfff]/;

/** Python's code point ordering of strings, which `<` on UTF-16 does not give. */
export function byCodePoint(a: string, b: string): number {
  if (a === b) return 0;
  if (!SURROGATE.test(a) && !SURROGATE.test(b)) return a < b ? -1 : 1; // no pair: UTF-16 order is code point order
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = (x[i]?.codePointAt(0) ?? 0) - (y[i]?.codePointAt(0) ?? 0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}
