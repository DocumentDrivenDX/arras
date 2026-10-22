// SPDX-License-Identifier: MIT OR Apache-2.0
// JSON that keeps every integer exactly. `JSON.parse` reads a number as a double, so an integer past
// 2^53 comes back as a different integer; the graph file must write the digits the server sent. An
// integer a double cannot hold is read as a `bigint`, and a runtime whose `JSON.parse` does not tell a
// reviver the source text of a number refuses such a document instead of rounding it.
//
// A graph file carries no other number: a decimal travels as a string, so `1.0`, `1.5` and `1e3` are
// refused, naming where they are, by `assertIntegers` (the number is judged by its text, which a parsed
// value no longer has: `1.0` and `1` are both the double 1). `NaN`, `Infinity` and `-Infinity` are not JSON,
// so `JSON.parse` refuses them without saying where; the text is then searched for them, and they are named
// by their path as any other number that is not an integer.

type Reviver = (key: string, value: unknown, context?: { source?: string }) => unknown;

const INTEGER = /^-?\d+$/;

/** Where a number is, as `records[3].properties.n`, and its text. */
export interface Found {
  path: string;
  token: string;
}

interface Frame {
  array: boolean;
  index: number;
  key: string;
  /** In an object: the next string is a member's name. */
  name: boolean;
}

const pathOf = (stack: Frame[]): string =>
  stack.map((f, i) => (f.array ? `[${f.index}]` : `${i === 0 ? "" : "."}${f.key}`)).join("");

/** The index of the closing quote of the string that starts at `i`, in well-formed JSON text. */
function stringEnd(text: string, i: number): number {
  let j = i + 1;
  while (j < text.length && text[j] !== '"') j += text[j] === "\\" ? 2 : 1;
  return j;
}

/** The string at `i`, which names the member of an object when one is expected: where it ends. */
function readString(stack: Frame[], text: string, i: number): number {
  const end = stringEnd(text, i);
  const f = stack[stack.length - 1];
  if (f && !f.array && f.name) {
    f.key = JSON.parse(text.slice(i, end + 1)) as string;
    f.name = false;
  }
  return end;
}

/** A bracket or a comma moves where the next value is. */
function punctuate(stack: Frame[], c: string): void {
  const f = stack[stack.length - 1];
  if (c === "{" || c === "[") stack.push({ array: c === "[", index: 0, key: "", name: c === "{" });
  else if (c === "}" || c === "]") stack.pop();
  else if (c === "," && f?.array) f.index += 1;
  else if (c === "," && f) f.name = true;
}

const startsWord = (c: string) => c === "-" || /[\dA-Za-z]/.test(c);

/** The index after the number, or the `NaN` or `Infinity` word, that starts at `i`. */
function numberEnd(text: string, i: number): number {
  let end = i + 1;
  while (/[-+.\w]/.test(text.charAt(end))) end++;
  return end;
}

/** JavaScript and Python write these three for a number that has no JSON spelling. */
const NOT_JSON_NUMBER = /^-?(?:NaN|Infinity)$/;

/**
 * The first number in `text`, in the order the file has them, that `isBad` says is not one a graph file
 * has, with its path. `under` limits it to what is in the top-level member of that name.
 */
function firstNumber(
  text: string,
  isBad: (token: string) => boolean,
  under?: string,
): Found | null {
  const stack: Frame[] = [];
  for (let i = 0; i < text.length; i++) {
    const c = text.charAt(i);
    if (c === '"') {
      i = readString(stack, text, i);
    } else if (startsWord(c)) {
      const end = numberEnd(text, i);
      const token = text.slice(i, end);
      const path = pathOf(stack);
      const scoped = under === undefined || path === under || path.startsWith(`${under}[`);
      if (scoped && isBad(token)) return { path, token };
      i = end - 1;
    } else {
      punctuate(stack, c);
    }
  }
  return null;
}

/**
 * The first number in well-formed JSON `text` that is not written as an integer (it has a fraction or an
 * exponent), with its path. `under` limits it to what is in the top-level member of that name.
 */
export const findNonInteger = (text: string, under?: string): Found | null =>
  firstNumber(text, (t) => /^-?\d/.test(t) && /[.eE]/.test(t), under);

/** The first `NaN`, `Infinity` or `-Infinity` in `text`, which need not be well-formed JSON, with its path. */
const findNotJsonNumber = (text: string): Found | null =>
  firstNumber(text, (t) => NOT_JSON_NUMBER.test(t));

/** The sentence that says a number is not an integer and what to write instead. */
export const notAnInteger = (f: Found): string =>
  `${f.path || "the document"}: ${f.token} is not an integer (a decimal is written as a string)`;

/** The error for a number that is not an integer: its message names the path. */
export class NotIntegerError extends Error {}

/**
 * Throw, naming its path, when `text` has a number that is not an integer. `under` limits the check to the
 * member of that name at the top (the export page's `items`; its other members, such as a freshness's lag,
 * are not records).
 */
export function assertIntegers(text: string, under?: string): void {
  const found = findNonInteger(text, under);
  if (found) throw new NotIntegerError(notAnInteger(found));
}

/** Parse `text`, reading each integer that is not a safe integer as a `bigint`. */
export function parseLossless(text: string): unknown {
  const reviver: Reviver = (_key, value, context) => {
    if (typeof value !== "number" || Number.isSafeInteger(value)) return value;
    const source = context?.source;
    if (source === undefined) {
      if (!Number.isInteger(value)) return value;
      throw new Error("an integer beyond 2^53 cannot be read exactly by this browser");
    }
    return INTEGER.test(source) ? BigInt(source) : value;
  };
  try {
    return JSON.parse(text, reviver as (key: string, value: unknown) => unknown);
  } catch (e) {
    const found = findNotJsonNumber(text);
    if (found) throw new NotIntegerError(notAnInteger(found));
    throw e;
  }
}

/**
 * Parse `text` whose records, the top-level member `under`, carry no number that is not an integer (a
 * decimal is a string) and keep every integer exactly. Its other members are read as they are.
 */
export function parseRecords(text: string, under: string): unknown {
  const body = parseLossless(text);
  assertIntegers(text, under);
  return body;
}
