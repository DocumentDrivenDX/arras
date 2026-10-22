// SPDX-License-Identifier: MIT OR Apache-2.0
// Scopes the library's compiled stylesheet to the `.arras-root` element, so loading it in a host page
// styles only Arras's own subtree (ADR-027). A PostCSS plugin run on `src/styles.css`, after Tailwind:
//
//   - every top-level selector gets `.arras-root ` in front, so a utility, a `.arras-*` class or a preflight
//     element rule reaches nothing outside the root;
//   - `:root`, `:host`, `html` and `body` are the root element itself (the tokens, the font, the margin);
//   - `*` and the pseudo-elements keep their reach, inside the root (preflight's reset);
//   - `@layer` blocks stay as they are: the library's own cascade (its unlayered `.arras-*` classes over its layered
//     utilities and reset) is unchanged. A host's unlayered element rule (`button { ... }`) therefore outranks the
//     library's layered rules inside the root; a host's layered ones (Tailwind's own) do not, because the root's
//     selectors are the more specific;
//   - nested rules (`&:hover`), keyframes, `@property` and `@font-face` are left as they are.
//
// `check()` is the same test the build's output must pass: no selector outside the root.
import type { AtRule, Container, Plugin, Root, Rule } from "postcss";

export const ROOT = ".arras-root";
const ROOT_ELEMENTS = new Set([":root", ":host", "html", "body", ":root:host"]);
const GLOBAL_PSEUDOS = /^(::?(before|after|backdrop|file-selector-button))$/;

interface Scan {
  depth: number; // inside () or []
  quote: string; // inside a quoted string: its quote character
  escaped: boolean; // the last character was a backslash
}

function advance(s: Scan, c: string): void {
  if (s.escaped) s.escaped = false;
  else if (c === "\\") s.escaped = true;
  else if (s.quote) s.quote = c === s.quote ? "" : s.quote;
  else if (c === '"' || c === "'") s.quote = c;
  else if (c === "(" || c === "[") s.depth++;
  else if (c === ")" || c === "]") s.depth--;
}

/** Splits a selector list at its top-level commas (not those in (), [], a string or escaped). */
export function splitSelectors(list: string): string[] {
  const scan: Scan = { depth: 0, quote: "", escaped: false };
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < list.length; i++) {
    const c = list[i] as string;
    if (c === "," && scan.depth === 0 && !scan.quote && !scan.escaped) {
      out.push(list.slice(start, i).trim());
      start = i + 1;
    }
    advance(scan, c);
  }
  out.push(list.slice(start).trim());
  return out.filter(Boolean);
}

/** One selector as scoped: the root element itself, or something inside it. */
export function scopeSelector(selector: string): string[] {
  if (selector.includes(ROOT)) return [selector];
  if (ROOT_ELEMENTS.has(selector)) return [ROOT];
  if (selector === "*") return [ROOT, `${ROOT} *`]; // the root is itself reset
  if (GLOBAL_PSEUDOS.test(selector)) return [`${ROOT} ${selector}`];
  return [`${ROOT} ${selector}`];
}

const insideRule = (node: { parent?: Container | undefined }) => {
  for (let p = node.parent; p; p = (p as { parent?: Container }).parent)
    if (p.type === "rule") return true;
  return false;
};
const inKeyframes = (rule: Rule) => {
  const p = rule.parent as AtRule | undefined;
  return p?.type === "atrule" && /keyframes$/i.test(p.name);
};

export function scopeRoot(root: Root): void {
  root.walkRules((rule) => {
    if (insideRule(rule) || inKeyframes(rule)) return;
    const scoped = splitSelectors(rule.selector).flatMap(scopeSelector);
    rule.selector = [...new Set(scoped)].join(",\n");
  });
}

/** `from` ends with this file (the plugin leaves page-level and other sheets alone). */
export function scopeCss(file = /[\\/]src[\\/]styles\.css(\?.*)?$/): Plugin {
  return {
    postcssPlugin: "arras-scope-css",
    Once(root, { result }) {
      if (file.test(result.opts.from ?? "")) scopeRoot(root);
    },
  };
}
scopeCss.postcss = true;

/** The selectors of a stylesheet that reach outside the root (for the build check). */
export function unscoped(root: Root): string[] {
  const bad: string[] = [];
  root.walkRules((rule) => {
    if (insideRule(rule) || inKeyframes(rule)) return;
    for (const s of splitSelectors(rule.selector)) if (!s.includes(ROOT)) bad.push(s);
  });
  return bad;
}
