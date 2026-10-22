// SPDX-License-Identifier: MIT OR Apache-2.0
// A small GraphQL reader for the browser's fetch double: queries with variables, aliases, arguments,
// nested selections and inline fragments. It parses what the Graph Browser sends and projects rows
// onto the selection, as the real server does; it counts selections to enforce CONTRACT-006's 50.

export interface Field {
  alias?: string;
  name: string;
  args: Record<string, unknown>;
  on?: string;
  children?: Field[];
}

const TOKEN = /\.\.\.|[{}()[\]:!=$,]|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*/g;

class Parser {
  private i = 0;
  private readonly tokens: string[];
  constructor(
    query: string,
    private readonly vars: Record<string, unknown>,
  ) {
    // Commas are insignificant in GraphQL.
    this.tokens = (query.match(TOKEN) ?? []).filter((t) => t !== ",");
  }

  private peek = () => {
    if (this.i >= this.tokens.length) throw new Error("unexpected end of query");
    return this.tokens[this.i];
  };
  private next = () => this.tokens[this.i++] ?? "";

  private list(): unknown[] {
    const out: unknown[] = [];
    while (this.peek() !== "]") out.push(this.value());
    this.next();
    return out;
  }

  private object(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    while (this.peek() !== "}") {
      const k = this.next();
      this.next(); // :
      out[k] = this.value();
    }
    this.next();
    return out;
  }

  private value(): unknown {
    const t = this.next();
    if (t === "$") return this.vars[this.next()];
    if (t === "[") return this.list();
    if (t === "{") return this.object();
    if (t.startsWith('"')) return JSON.parse(t);
    return /^-?\d/.test(t) ? Number(t) : t;
  }

  private args(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    if (this.peek() !== "(") return out;
    this.next();
    while (this.peek() !== ")") {
      const k = this.next();
      this.next(); // :
      out[k] = this.value();
    }
    this.next();
    return out;
  }

  private field(): Field {
    let name = this.next();
    let alias: string | undefined;
    if (this.peek() === ":") {
      this.next();
      alias = name;
      name = this.next();
    }
    const f: Field = { alias, name, args: this.args() };
    if (this.peek() === "{") f.children = this.selection();
    return f;
  }

  selection(): Field[] {
    const out: Field[] = [];
    this.next(); // {
    while (this.peek() !== "}") {
      if (this.peek() === "...") {
        this.next();
        this.next(); // on
        const on = this.next();
        out.push({ name: "...", on, args: {}, children: this.selection() });
      } else out.push(this.field());
    }
    this.next(); // }
    return out;
  }

  /** Skip `query($a: T!, ...)` up to the selection set. */
  header() {
    if (this.peek() !== "query") return;
    this.next();
    if (this.peek() !== "(") return;
    let depth = 0;
    do {
      const t = this.next();
      if (t === "(") depth++;
      if (t === ")") depth--;
    } while (depth > 0);
  }
}

export function parseQuery(query: string, vars: Record<string, unknown>): Field[] {
  const p = new Parser(query, vars);
  p.header();
  return p.selection();
}

/** Field selections, as CONTRACT-006 counts them: every field, not the inline fragments around them. */
export function countSelections(fields: Field[]): number {
  return fields.reduce(
    (n, f) => n + (f.name === "..." ? 0 : 1) + countSelections(f.children ?? []),
    0,
  );
}

/** Project a row onto a selection; an inline fragment applies when its type is the row's. */
export function project(row: unknown, fields: Field[], typeOf: (r: unknown) => string): unknown {
  if (row === null || row === undefined) return null;
  if (Array.isArray(row)) return row.map((r) => project(r, fields, typeOf));
  const obj = row as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.name === "...") {
      if (!f.on || f.on === "Entity" || f.on === typeOf(row))
        Object.assign(out, project(row, f.children ?? [], typeOf) as object);
      continue;
    }
    const v = obj[f.name] ?? null;
    out[f.alias ?? f.name] = f.children ? project(v, f.children, typeOf) : v;
  }
  return out;
}
