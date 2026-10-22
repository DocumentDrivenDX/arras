// SPDX-License-Identifier: MIT OR Apache-2.0
// Fitting a label to its box. The picture's layout is a pure function with no DOM to measure, so a
// label's width is an estimate from a per-character table for the system sans-serif at the picture's
// 12-unit text, a little generous so a label is never wider than its box. A label wraps at word breaks
// onto at most `MAX_LINES`; a word too wide for a line breaks after a separator (`-`, `.`, `_`, `/`);
// only the last line is cut, with an ellipsis, so a long title keeps its beginning and a short one is
// whole.

export const MAX_LINES = 2;

const NARROW = new Set(Array.from("iljtfrI!|.,:;'\"` "));
const WIDE = new Set(Array.from("mwMW@"));
const SLACK = 1.06;
const SEPARATOR = /[-._/]/;

const charEm = (ch: string): number => {
  if (NARROW.has(ch)) return 0.29;
  if (WIDE.has(ch)) return 0.86;
  if (ch >= "A" && ch <= "Z") return 0.68;
  if (ch >= "0" && ch <= "9") return 0.58;
  return 0.55;
};

/** The estimated width of `text` at `size`, in the picture's units; bold text is a little wider. */
export function measure(text: string, size = 12, bold = false): number {
  let em = 0;
  for (const ch of text) em += charEm(ch);
  return em * size * SLACK * (bold ? 1.08 : 1);
}

/** Cut `text` to what fits in `width`, ending in an ellipsis. */
function ellipsize(text: string, width: number, size: number, bold: boolean): string {
  const chars = Array.from(text.trimEnd());
  while (chars.length > 1 && measure(`${chars.join("")}…`, size, bold) > width) chars.pop();
  let out = chars.join("").trimEnd();
  // A word cut to a stub ("contract r…") reads worse than the words before it ("contract…").
  const stub = /\s\S{1,2}$/.exec(out);
  if (stub && out.length > stub[0].length) out = out.slice(0, stub.index).trimEnd();
  return `${out}…`;
}

/** Break a word that is wider than a line into pieces that fit, after a separator where there is one. */
function pieces(word: string, width: number, size: number, bold: boolean): string[] {
  if (measure(word, size, bold) <= width) return [word];
  const out: string[] = [];
  let line = "";
  for (const ch of word) {
    if (line && measure(line + ch, size, bold) > width) {
      const at = Array.from(line).findLastIndex((c) => SEPARATOR.test(c));
      const chars = Array.from(line);
      if (at > 0) {
        out.push(chars.slice(0, at + 1).join(""));
        line = chars.slice(at + 1).join("");
      } else {
        out.push(line);
        line = "";
      }
    }
    line += ch;
  }
  return line ? [...out, line] : out;
}

interface Token {
  text: string;
  /** True for a piece that continues the word before it: no space joins them. */
  glue: boolean;
}

const tokensOf = (text: string, width: number, size: number, bold: boolean): Token[] =>
  text
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .flatMap((w) => pieces(w, width, size, bold).map((p, i) => ({ text: p, glue: i > 0 })));

const joinTokens = (tokens: Token[]) =>
  tokens.reduce((out, t, i) => out + (i > 0 && !t.glue ? " " : "") + t.text, "");

/**
 * `text` as at most `maxLines` lines no wider than `width`: words kept whole where they fit, the last
 * line ending in an ellipsis when something was left out.
 */
export function fitLines(
  text: string,
  width: number,
  maxLines = MAX_LINES,
  size = 12,
  bold = false,
): string[] {
  const rest = tokensOf(text, width, size, bold);
  const lines: string[] = [];
  let line: Token[] = [];
  while (rest.length > 0 && lines.length < maxLines - 1) {
    const next = rest[0];
    if (!next) break;
    const start = line.length === 0;
    const token = start ? { ...next, glue: false } : next;
    if (start || measure(joinTokens([...line, token]), size, bold) <= width) {
      line.push(token);
      rest.shift();
    } else {
      lines.push(joinTokens(line));
      line = [];
    }
  }
  const last = joinTokens([...line, ...rest]);
  if (last)
    lines.push(measure(last, size, bold) <= width ? last : ellipsize(last, width, size, bold));
  return lines.length > 0 ? lines : [""];
}
