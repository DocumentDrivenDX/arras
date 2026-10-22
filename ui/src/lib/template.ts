// SPDX-License-Identifier: MIT OR Apache-2.0
// The template grammar of CONTRACT-010 A, read as the server's evaluator reads it (src/arras/view.py;
// tests/vectors/template.json holds the cases both sides pass): `{name}` is a property's value as
// text, `[ ... ]` an optional group shown only when every placeholder inside it, nested groups
// included, has a value, and `\{ \} \[ \] \\` a literal character. A backslash before anything
// else is itself plain text. Nothing else is interpreted; the output is text, never markup. The
// server refuses a malformed template at registration, so one that arrives here anyway reads as its
// own text.

export type TemplateNode =
  | { t: "text"; v: string }
  | { t: "ph"; name: string }
  | { t: "opt"; nodes: TemplateNode[] };

const ESCAPABLE = new Set(["{", "}", "[", "]", "\\"]);

class Malformed extends Error {}

const NAME = /^[A-Za-z][A-Za-z0-9_]*$/;

/** A recursive-descent reader over the template text. */
class Reader {
  private i = 0;
  constructor(private readonly src: string) {}

  /** Nodes up to the end of the text, or up to the `]` that closes a group. */
  nodes(inGroup: boolean): TemplateNode[] {
    const out: TemplateNode[] = [];
    let text = "";
    const flush = () => {
      if (text) out.push({ t: "text", v: text });
      text = "";
    };
    while (this.i < this.src.length) {
      const c = this.src.charAt(this.i);
      if (c === "]") {
        if (!inGroup) throw new Malformed();
        this.i++;
        flush();
        return out;
      }
      if (c === "{" || c === "[") {
        flush();
        out.push(c === "{" ? this.placeholder() : this.group());
      } else text += this.literal(c);
    }
    if (inGroup) throw new Malformed();
    flush();
    return out;
  }

  private literal(c: string): string {
    if (c === "}") throw new Malformed();
    const next = this.src.charAt(this.i + 1);
    if (c === "\\" && ESCAPABLE.has(next)) {
      this.i += 2;
      return next;
    }
    this.i++;
    return c;
  }

  private placeholder(): TemplateNode {
    const end = this.src.indexOf("}", this.i);
    const name = this.src.slice(this.i + 1, end);
    if (end < 0 || !NAME.test(name)) throw new Malformed();
    this.i = end + 1;
    return { t: "ph", name };
  }

  private group(): TemplateNode {
    this.i++;
    return { t: "opt", nodes: this.nodes(true) };
  }
}

/** The parsed template, or null when it is malformed. */
export function parseTemplate(src: string): TemplateNode[] | null {
  try {
    return new Reader(src).nodes(false);
  } catch (e) {
    if (e instanceof Malformed) return null;
    throw e;
  }
}

/** The property names a template reads, in order, once each. */
export function placeholders(src: string | null | undefined): string[] {
  const out: string[] = [];
  const walk = (nodes: TemplateNode[]) => {
    for (const n of nodes) {
      if (n.t === "ph" && !out.includes(n.name)) out.push(n.name);
      if (n.t === "opt") walk(n.nodes);
    }
  };
  walk(parseTemplate(src ?? "") ?? []);
  return out;
}

type Lookup = (name: string) => string;

function render(nodes: TemplateNode[], get: Lookup): { text: string; complete: boolean } {
  let text = "";
  let complete = true;
  for (const n of nodes) {
    if (n.t === "text") text += n.v;
    else if (n.t === "ph") {
      const v = get(n.name);
      if (v.trim() === "") complete = false;
      else text += v;
    } else {
      const inner = render(n.nodes, get);
      complete = complete && inner.complete;
      if (inner.complete) text += inner.text;
    }
  }
  return { text, complete };
}

/** The template's text for one entity, as the server composes it (not trimmed); a missing or
 *  empty property produces no text. */
export function evaluate(src: string, get: Lookup): string {
  const nodes = parseTemplate(src);
  if (!nodes) return src;
  return render(nodes, get).text;
}

/** A piece of a template's output: literal text, or a property's value with the property's name. */
export interface Segment {
  text: string;
  property?: string;
}

function segmentsOf(nodes: TemplateNode[], get: Lookup): { segs: Segment[]; complete: boolean } {
  const segs: Segment[] = [];
  let complete = true;
  for (const n of nodes) {
    if (n.t === "text") segs.push({ text: n.v });
    else if (n.t === "ph") {
      const v = get(n.name);
      if (v.trim() === "") complete = false;
      segs.push({ text: v, property: n.name });
    } else {
      const inner = segmentsOf(n.nodes, get);
      complete = complete && inner.complete;
      if (inner.complete) segs.push(...inner.segs);
    }
  }
  return { segs, complete };
}

/** The same output as `evaluate`, as the pieces a view can attach controls to: each placeholder
 *  outside an optional group is a segment even when empty; a group that is left out is not. */
export function segments(src: string, get: Lookup): Segment[] {
  const nodes = parseTemplate(src);
  return nodes ? segmentsOf(nodes, get).segs : [{ text: src }];
}

/** A row's value as the text a template places: lists joined with a comma and a space. */
export function valueText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(valueText).join(", ");
  return "";
}

/** The properties a label read selects for a title: the template's placeholders that the type declares. */
export function titleProperties(title: string, declared: Iterable<string>): string[] {
  const known = new Set(declared);
  return placeholders(title).filter((n) => known.has(n));
}

/** The title of an entity: its `title` template, or its key when that comes out empty. */
export function titleOf(template: string, row: Record<string, unknown>, key: string): string {
  return evaluate(template, (n) => valueText(row[n])).trim() || key;
}
