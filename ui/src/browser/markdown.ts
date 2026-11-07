// SPDX-License-Identifier: MIT OR Apache-2.0
// The `markdown` format of the `arras.view` vocabulary, version 0.2.0 (CONTRACT-010 A, ADR-032): a closed
// subset of Markdown read into a small tree that `MarkdownText` draws as React elements. Nothing here makes
// markup out of text: raw HTML is text, an image is its alt text, and a link is kept only if it is an
// `http`, `https` or `mailto` address with no credentials in it. The subset is: ATX headings, paragraphs,
// bullet and numbered lists (nested by indentation), pipe tables, fenced code, block quotes, thematic breaks,
// `code`, `**strong**`, `*emphasis*` and `_emphasis_`, `[text](address)`, and `\` escapes. Anything else is text.
import { safeLink } from "./valueFormat";

export type Inline =
  | { id: number; t: "text" | "code"; v: string }
  | { id: number; t: "strong" | "em"; c: Inline[] }
  | { id: number; t: "link"; href: string; c: Inline[] };

export interface ListItem {
  id: number;
  c: Inline[];
  sub: Block | null;
}
export type Block =
  | { id: number; t: "h"; level: number; c: Inline[] }
  | { id: number; t: "p"; c: Inline[] }
  | { id: number; t: "ul" | "ol"; items: ListItem[] }
  | { id: number; t: "code"; v: string }
  | { id: number; t: "quote"; c: Block[] }
  | { id: number; t: "hr" }
  | { id: number; t: "table"; head: Inline[][]; rows: Inline[][][] };

/** Input past this is shown as it is, unparsed: a bound on the work a value can ask for. */
export const MAX_MARKDOWN_CHARS = 200_000;

let next = 0;
const nid = () => next++;

/** Nesting (quotes inside quotes, emphasis inside links, lists inside lists) deeper than this is read as text. */
const MAX_DEPTH = 12;
let depth = 0;
/** `fn` one level deeper; at the bound, `over` instead, so no input can ask for unbounded recursion. */
function deeper<T>(fn: () => T, over: () => T): T {
  if (depth >= MAX_DEPTH) return over();
  depth += 1;
  try {
    return fn();
  } finally {
    depth -= 1;
  }
}

// -- inline -----------------------------------------------------------------------------------

const CODE = /`([^`\n]+)`/y;
const STRONG = /\*\*(?=\S)([\s\S]*?\S)\*\*/y;
const EM_STAR = /\*(?=[^\s*])([^*\n]*?[^\s*])\*/y;
const EM_UNDER = /_(?=[^\s_])([^_\n]*?[^\s_])_(?![A-Za-z0-9])/y;
const IMAGE = /!\[([^\]\n]*)\]\([^)\n]*\)/y;
const LINK = /\[([^\]\n]+)\]\(([^)\s]+)\)/y;
const ESCAPE = /\\([\\`*_{}[\]()#+\-.!|>~])/y;
const SPECIAL = /[`*_[!\\]/g;

const at = (re: RegExp, s: string, i: number): RegExpExecArray | null => {
  re.lastIndex = i;
  return re.exec(s);
};

/** The address of a link, or null: `http`, `https` or `mailto`, and no user name or password. */
export function linkHref(raw: string): string | null {
  const safe = safeLink(raw);
  if (!safe) return null;
  const u = new URL(safe.href);
  return u.username || u.password ? null : safe.href;
}

function link(m: RegExpExecArray): Inline | null {
  const href = linkHref(m[2] as string);
  return href ? { id: nid(), t: "link", href, c: parseInline(m[1] as string) } : null;
}

const done = (n: Inline, m: RegExpExecArray, i: number): [Inline, number] => [n, i + m[0].length];

type Try = (s: string, i: number) => [Inline, number] | null;

const tryEscape: Try = (s, i) => {
  const m = at(ESCAPE, s, i);
  return m && done({ id: nid(), t: "text", v: m[1] as string }, m, i);
};
const tryCode: Try = (s, i) => {
  const m = at(CODE, s, i);
  return m && done({ id: nid(), t: "code", v: m[1] as string }, m, i);
};
const tryImage: Try = (s, i) => {
  const m = at(IMAGE, s, i);
  return m && done({ id: nid(), t: "text", v: m[1] as string }, m, i);
};
const tryLink: Try = (s, i) => {
  const m = at(LINK, s, i);
  const l = m && link(m);
  return m && l ? done(l, m, i) : null;
};
const tryStrong: Try = (s, i) => {
  const m = at(STRONG, s, i);
  return m && done({ id: nid(), t: "strong", c: parseInline(m[1] as string) }, m, i);
};
const tryEmStar: Try = (s, i) => {
  const m = at(EM_STAR, s, i);
  return m && done({ id: nid(), t: "em", c: parseInline(m[1] as string) }, m, i);
};
const tryEmUnder: Try = (s, i) => {
  if (/[A-Za-z0-9]/.test(s.charAt(i - 1))) return null; // `snake_case` is not emphasis
  const m = at(EM_UNDER, s, i);
  return m && done({ id: nid(), t: "em", c: parseInline(m[1] as string) }, m, i);
};

const STARTS: Record<string, Try[]> = {
  "\\": [tryEscape],
  "`": [tryCode],
  "!": [tryImage],
  "[": [tryLink],
  "*": [tryStrong, tryEmStar],
  _: [tryEmUnder],
};

/** The inline element that starts at `i`, and where it ends; null when the text there is just text. */
function inlineAt(s: string, i: number): [Inline, number] | null {
  for (const attempt of STARTS[s.charAt(i)] ?? []) {
    const found = attempt(s, i);
    if (found) return found;
  }
  return null;
}

export function parseInline(s: string): Inline[] {
  return deeper(
    () => inlineRun(s),
    () => [{ id: nid(), t: "text", v: s }],
  );
}

function inlineRun(s: string): Inline[] {
  const out: Inline[] = [];
  let i = 0;
  let text = "";
  const flush = () => {
    if (text) out.push({ id: nid(), t: "text", v: text });
    text = "";
  };
  while (i < s.length) {
    SPECIAL.lastIndex = i;
    const found = SPECIAL.exec(s);
    const stop = found ? found.index : s.length;
    text += s.slice(i, stop);
    i = stop;
    if (i >= s.length) break;
    const el = inlineAt(s, i);
    if (el) {
      flush();
      out.push(el[0]);
      i = el[1];
    } else {
      text += s.charAt(i);
      i += 1;
    }
  }
  flush();
  return out;
}

// -- blocks -----------------------------------------------------------------------------------

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const FENCE = /^```/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const BULLET = /^(\s*)[-*+]\s+(.*)$/;
const ORDERED = /^(\s*)\d{1,9}[.)]\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?(\s*:?-{1,}:?\s*\|)+\s*:?-{0,}:?\s*\|?\s*$/;

const isBlank = (l: string) => l.trim() === "";

/** The cells of a pipe-table row; `\|` is a pipe in a cell. */
function cells(line: string): string[] {
  const body = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return body.split(/(?<!\\)\|/).map((c) => c.trim().replaceAll("\\|", "|"));
}

function table(lines: string[], i: number): [Block, number] | null {
  const head = lines[i];
  const rule = lines[i + 1];
  if (!head || !rule || !TABLE_ROW.test(head) || !TABLE_RULE.test(rule)) return null;
  const rows: Inline[][][] = [];
  let j = i + 2;
  while (j < lines.length && TABLE_ROW.test(lines[j] as string)) {
    rows.push(cells(lines[j] as string).map(parseInline));
    j += 1;
  }
  return [{ id: nid(), t: "table", head: cells(head).map(parseInline), rows }, j];
}

function fence(lines: string[], i: number): [Block, number] {
  const body: string[] = [];
  let j = i + 1;
  while (j < lines.length && !FENCE.test(lines[j] as string)) {
    body.push(lines[j] as string);
    j += 1;
  }
  return [{ id: nid(), t: "code", v: body.join("\n") }, Math.min(j + 1, lines.length)];
}

const quote = (lines: string[], i: number): [Block, number] => {
  const body: string[] = [];
  let j = i;
  while (j < lines.length) {
    const m = QUOTE.exec(lines[j] as string);
    if (!m) break;
    body.push(m[1] as string);
    j += 1;
  }
  return [
    {
      id: nid(),
      t: "quote",
      c: deeper(
        () => parseBlocks(body),
        () => [{ id: nid(), t: "p", c: [{ id: nid(), t: "text", v: body.join(" ") }] }],
      ),
    },
    j,
  ];
};

const itemOf = (l: string) => BULLET.exec(l) ?? ORDERED.exec(l);
/** The indent of a list line, or -1 for a line that is not one. */
const indentOf = (l: string): number => {
  const m = itemOf(l);
  return m ? (m[1] as string).length : -1;
};

/** A list starting at `i`: its lines are items at one indent, with deeper lines as the item's own list. */
function list(lines: string[], i: number): [Block, number] {
  const first = itemOf(lines[i] as string) as RegExpExecArray;
  const indent = (first[1] as string).length;
  const ordered = ORDERED.test(lines[i] as string) && !BULLET.test(lines[i] as string);
  const items: ListItem[] = [];
  let j = i;
  while (j < lines.length) {
    const m = itemOf(lines[j] as string);
    if (!m || (m[1] as string).length !== indent) break;
    const inner: string[] = [];
    j += 1;
    while (j < lines.length && indentOf(lines[j] as string) > indent) {
      inner.push(lines[j] as string);
      j += 1;
    }
    items.push({
      id: nid(),
      c: parseInline(m[2] as string),
      sub: inner.length
        ? deeper(
            () => list(inner, 0)[0],
            () => null,
          )
        : null,
    });
  }
  return [{ id: nid(), t: ordered ? "ol" : "ul", items }, j];
}

function paragraph(lines: string[], i: number): [Block, number] {
  const body: string[] = [];
  let j = i;
  while (j < lines.length && !isBlank(lines[j] as string) && (j === i || !startsBlock(lines, j))) {
    body.push((lines[j] as string).trim());
    j += 1;
  }
  return [{ id: nid(), t: "p", c: parseInline(body.join(" ")) }, j];
}

function startsBlock(lines: string[], i: number): boolean {
  const l = lines[i] as string;
  return (
    HEADING.test(l) ||
    FENCE.test(l) ||
    RULE.test(l) ||
    QUOTE.test(l) ||
    itemOf(l) !== null ||
    table(lines, i) !== null
  );
}

/** The block that starts at `i` and the line after it. */
function blockAt(lines: string[], i: number): [Block, number] {
  const l = lines[i] as string;
  const h = HEADING.exec(l);
  if (h)
    return [
      { id: nid(), t: "h", level: (h[1] as string).length, c: parseInline(h[2] as string) },
      i + 1,
    ];
  if (FENCE.test(l)) return fence(lines, i);
  if (RULE.test(l) && !itemOf(l)) return [{ id: nid(), t: "hr" }, i + 1];
  if (QUOTE.test(l)) return quote(lines, i);
  if (itemOf(l)) return list(lines, i);
  return table(lines, i) ?? paragraph(lines, i);
}

export function parseBlocks(lines: string[]): Block[] {
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    if (isBlank(lines[i] as string)) {
      i += 1;
      continue;
    }
    const [block, end] = blockAt(lines, i);
    out.push(block);
    i = Math.max(end, i + 1);
  }
  return out;
}

/** The tree for `text`, or null when the text is too long to read as Markdown (it is then shown as text). */
export function parseMarkdown(text: string): Block[] | null {
  if (text.length > MAX_MARKDOWN_CHARS) return null;
  next = 0;
  depth = 0;
  return parseBlocks(text.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n"));
}
