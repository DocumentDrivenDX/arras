// SPDX-License-Identifier: MIT OR Apache-2.0
// The template grammar of CONTRACT-010 for the static read-only profile: `{name}`, `[` optional group `]` and the
// escapes `\{ \} \[ \] \\`. A port of `parse_template` and `evaluate` in `arras/view.py`; the vectors in
// `tests/vectors/template.json` hold the two to one reading. The result is text, never markup.

export class TemplateError extends Error {}

type Node = string | { name: string } | { group: Node[] };
const ESCAPABLE = "{}[]\\";
const PLACEHOLDER = /^[A-Za-z][A-Za-z0-9_]*$/;

function placeholderAt(text: string, i: number): [string, number] {
  const end = text.indexOf("}", i);
  const name = end > 0 ? text.slice(i + 1, end) : "";
  if (!PLACEHOLDER.test(name))
    throw new TemplateError("a { starts a {name} placeholder; write \\{ for a brace");
  return [name, end + 1];
}

type Step = { text: string; at: number } | { node: Node; at: number } | { close: true; at: number };

/** What the template has at `i`: literal text, a placeholder or group (both end where it ends), or the group's close. */
function stepAt(text: string, i: number, nested: boolean): Step {
  const c = text.charAt(i);
  const next = text.charAt(i + 1);
  if (c === "\\" && i + 1 < text.length && ESCAPABLE.includes(next))
    return { text: next, at: i + 2 };
  if (c === "{") {
    const [name, at] = placeholderAt(text, i);
    return { node: { name }, at };
  }
  if (c === "[") {
    const [group, at] = parseNodes(text, i + 1, true);
    return { node: { group }, at };
  }
  if (c === "]") {
    if (!nested) throw new TemplateError("a ] closes no [; write \\] for a bracket");
    return { close: true, at: i + 1 };
  }
  if (c === "}") throw new TemplateError("a } closes no {; write \\} for a brace");
  return { text: c, at: i + 1 };
}

function parseNodes(text: string, start: number, nested: boolean): [Node[], number] {
  const nodes: Node[] = [];
  let buf = "";
  let i = start;
  const flush = () => {
    if (buf) nodes.push(buf);
    buf = "";
  };
  while (i < text.length) {
    const step = stepAt(text, i, nested);
    i = step.at;
    if ("close" in step) {
      flush();
      return [nodes, i];
    }
    if ("node" in step) {
      flush();
      nodes.push(step.node);
    } else buf += step.text;
  }
  if (nested) throw new TemplateError("a [ is never closed; write \\[ for a bracket");
  flush();
  return [nodes, i];
}

const parsed = new Map<string, Node[]>();
export function parseTemplate(text: string): Node[] {
  let nodes = parsed.get(text);
  if (!nodes) {
    nodes = parseNodes(text, 0, false)[0];
    if (parsed.size > 2048) parsed.clear();
    parsed.set(text, nodes);
  }
  return nodes;
}

function namesIn(nodes: Node[], found: string[]): void {
  for (const n of nodes) {
    if (typeof n === "string") continue;
    if ("name" in n) {
      if (!found.includes(n.name)) found.push(n.name);
    } else namesIn(n.group, found);
  }
}

/** The property names a template names, in order of first appearance. */
export function placeholders(template: string): string[] {
  const found: string[] = [];
  namesIn(parseTemplate(template), found);
  return found;
}

/** A property's value as the text a template shows. */
export function asText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map(asText).join(", ");
  return String(value);
}

function evalNodes(nodes: Node[], row: Record<string, unknown>): [string, boolean] {
  let out = "";
  let filled = true;
  for (const n of nodes) {
    if (typeof n === "string") {
      out += n;
    } else if ("name" in n) {
      const text = asText(row[n.name]);
      if (pyStrip(text) === "") filled = false;
      else out += text;
    } else {
      const [text, ok] = evalNodes(n.group, row);
      filled = filled && ok;
      if (ok) out += text;
    }
  }
  return [out, filled];
}

/** Python's `str.strip()`: whitespace by Unicode `White_Space`, which `trim` also uses. */
export const pyStrip = (s: string) => s.trim();

/** The template over an entity's properties; a missing value, and an optional group with one, give no text. */
export const evaluate = (template: string, row: Record<string, unknown>): string =>
  evalNodes(parseTemplate(template), row)[0];

/** An entity's title: its template over the row, or its key when that is empty. */
