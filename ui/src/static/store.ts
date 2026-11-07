// SPDX-License-Identifier: MIT OR Apache-2.0
// The in-memory graph of the static read-only profile (CONTRACT-012): a module's entities and
// relationships read from an `arras.graph` file, held as the Python in-memory adapter holds them
// (`fakes_import.py`, `fakes_state.py`). Reads are served from indexes built once at load; nothing is
// written after it. A record the Python import would reject fails the load, naming every rejection:
// a published graph is built, so a bad record is a build fault, never a silent omission.
import type { GraphFile } from "../api/graphFile";
import {
  type Dec,
  type Domain,
  decimalText,
  integerFault,
  parseDecimal,
  storedDecimal,
} from "./domain";
import {
  type EntityType,
  entityTypeOf,
  type ModuleModel,
  type Prop,
  relationshipsOf,
} from "./model";
import { byCodePoint } from "./text";
import type { ResolvedModule, ResolvedView } from "./view";

export const BACKEND = "static";
const KEY_VALUE = /^[A-Za-z0-9._:-]{1,128}$/;
const TIMESTAMP =
  /^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:(Z|z)|([+-])(\d{2}):(\d{2}))$/;
const BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const NOT_FINITE = /^[+-]?(?:nan|snan|inf|infinity)$/i;
const DECIMAL = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

export interface Rejection {
  kind: string;
  ident: string;
  reason: string;
}

/** A graph file the registry could not hold: every record it would have rejected. */
export class GraphLoadError extends Error {
  readonly rejections: Rejection[];
  constructor(rejections: Rejection[]) {
    const shown = rejections
      .slice(0, 10)
      .map((r) => `${r.kind} ${r.ident}: ${r.reason}`)
      .join("; ");
    super(`${rejections.length} record(s) cannot be loaded: ${shown}`);
    this.rejections = rejections;
  }
}

export interface Entity {
  type: EntityType;
  key: string;
  /** The stored properties, each read as its field's type, the key included. */
  props: Record<string, unknown>;
  originalAuthor: string | null;
  originalAt: string | null;
}

const pad = (n: number, width: number) => String(n).padStart(width, "0");

/**
 * An RFC 3339 timestamp as Python's `datetime.isoformat()` writes it: the offset as authored (`Z` is
 * `+00:00`), microseconds only when not zero. `null` for any other text or an impossible date.
 */
export function isoTimestamp(text: string): string | null {
  const m = TIMESTAMP.exec(text);
  if (!m) return null;
  const [, y, mo, d, h, mi, s, frac, z, sign, oh, om] = m;
  if (!z && (Number(oh) > 23 || Number(om) > 59)) return null;
  const date = new Date(
    Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s)),
  );
  const ok =
    date.getUTCFullYear() === Number(y) &&
    date.getUTCMonth() === Number(mo) - 1 &&
    date.getUTCDate() === Number(d) &&
    Number(h) < 24 &&
    Number(mi) < 60 &&
    Number(s) < 60;
  if (!ok) return null;
  const micros = Number((frac ?? "0").slice(0, 6).padEnd(6, "0"));
  const time = `${y}-${mo}-${d}T${h}:${mi}:${s}${micros ? `.${pad(micros, 6)}` : ""}`;
  return `${time}${z ? "+00:00" : `${sign}${oh}:${om}`}`;
}

type Reader = (v: unknown) => unknown;

const isInteger = (v: unknown): v is number | bigint =>
  typeof v === "bigint" || (typeof v === "number" && Number.isInteger(v));

const READERS: Record<string, Reader> = {
  string: (v) => {
    if (typeof v !== "string") throw new Error("not a string");
    return v;
  },
  integer: (v) => {
    if (!isInteger(v)) throw new Error("not an integer");
    return v;
  },
  decimal: (v) => {
    if (isInteger(v)) return String(v);
    if (typeof v === "string" && NOT_FINITE.test(v)) throw new Error("not a finite decimal");
    if (typeof v !== "string" || !DECIMAL.test(v)) throw new Error("not a decimal");
    return v;
  },
  boolean: (v) => {
    if (typeof v !== "boolean") throw new Error("not a boolean");
    return v;
  },
  timestamp: (v) => {
    if (typeof v !== "string") throw new Error("not an ISO timestamp");
    const iso = isoTimestamp(v);
    if (iso === null) throw new Error("not an ISO timestamp with an offset");
    return iso;
  },
  binary: (v) => {
    if (typeof v !== "string" || !BASE64.test(v)) throw new Error("not base64 text");
    return v;
  },
};

/** A value a numeric field holds: a decimal at its scale, an integer within its width (`domain.ts`). */
function held(p: Prop, v: unknown, domain: Domain | undefined): unknown {
  if (p.type === "decimal") return storedDecimal(domain, v as string);
  if (p.type === "integer" && domain && integerFault(domain, BigInt(v as number | bigint))) {
    throw new Error(integerFault(domain, BigInt(v as number | bigint)) as string);
  }
  return v;
}

function coerce(p: Prop, v: unknown, domain: Domain | undefined): unknown {
  const read = READERS[p.type];
  if (v === null || v === undefined || !p.scalar || !read) return v;
  if (p.cardinality === "many") {
    if (!Array.isArray(v)) throw new Error("not a list");
    const items = v.map(read);
    // a list is held as read: its decimals are written as `Decimal` writes them, at no scale
    return p.type === "decimal"
      ? items.map((x) => decimalText(parseDecimal(x as string) as Dec))
      : items;
  }
  return held(p, read(v), domain);
}

type Obj = Record<string, unknown>;

function readProps(module: ModuleModel, t: EntityType, props: Obj): Obj {
  const kinds = new Map(t.properties.map((p) => [p.name, p]));
  const out: Obj = {};
  for (const [k, v] of Object.entries(props)) {
    try {
      out[k] = coerce(kinds.get(k) as Prop, v, module.domains.get(`${t.local}\u0000${k}`));
    } catch (e) {
      throw new Error(`${k}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  return out;
}

type Checked = { ok: true; entity: Entity } | { ok: false; ident: string; reason: string };

const optionalText = (v: unknown): string | null =>
  v === undefined || v === null ? null : String(v);

/** The reason a record's properties cannot be the type's: a required one missing, or one undeclared. */
function propertyFault(t: EntityType, props: Obj): string | null {
  const declared = new Set(t.properties.map((p) => p.name));
  const missing = t.properties
    .filter((p) => p.cardinality === "one" && p.name !== t.key && !(p.name in props))
    .map((p) => p.name);
  const extra = Object.keys(props)
    .filter((k) => !declared.has(k))
    .sort();
  if (missing.length === 0 && extra.length === 0) return null;
  return `missing [${missing.join(", ")}], undeclared [${extra.join(", ")}]`;
}

/** `null` for a record of an entity already held (skipped); otherwise the entity or why it is refused. */
function checkEntity(
  module: ModuleModel,
  byKey: Map<string, Map<string, Entity>>,
  r: Obj,
): Checked | null {
  const key = String(r.key ?? "");
  const ident = `${module.name}.${String(r.type)}:${key}`;
  const fail = (reason: string): Checked => ({ ok: false, ident, reason });
  const t = entityTypeOf(module, String(r.type));
  if (!t || !KEY_VALUE.test(key)) return fail("unknown type or not a key");
  const props = (r.properties ?? {}) as Obj;
  const fault = propertyFault(t, props);
  if (fault) return fail(fault);
  if (byKey.get(t.local)?.has(key)) return null;
  let stored: Obj;
  try {
    stored = readProps(module, t, props);
  } catch (e) {
    return fail(e instanceof Error ? e.message : String(e));
  }
  const at = optionalText(r.original_at);
  const iso = at === null ? null : isoTimestamp(at);
  if (at !== null && iso === null) return fail("original_at: not an ISO timestamp with an offset");
  const entity: Entity = {
    type: t,
    key,
    props: { ...stored, [t.key]: key },
    originalAuthor: optionalText(r.original_author),
    originalAt: iso,
  };
  return { ok: true, entity };
}

type Found =
  | { ok: true; triple: [string, string, string] }
  | { ok: false; kind: string; ident: string; reason: string };

/** A relationship record as the canonical (relationship, source, target), or why it is refused. */
function checkRelation(
  module: ModuleModel,
  byKey: Map<string, Map<string, Entity>>,
  r: Obj,
): Found {
  const name = String(r.relationship);
  const ident = `${name}/${String(r.source)}/${String(r.target)}`;
  const rel = module.relationships.find((x) => x.name === name || x.inverse === name);
  if (!rel)
    return { ok: false, kind: "record", ident, reason: "neither an entity nor a relationship" };
  const [s, t] =
    rel.name === name ? [String(r.source), String(r.target)] : [String(r.target), String(r.source)];
  const has = (types: string[], key: string) => types.some((q) => byKey.get(localOf(q))?.has(key));
  if (!has(rel.source, s) || !has(rel.target, t))
    return {
      ok: false,
      kind: "relationship",
      ident,
      reason: "an endpoint is missing or of the wrong type",
    };
  return { ok: true, triple: [rel.name, s, t] };
}

/** An entity as the graph file writes it: only what is set, properties in key order, the key apart. */
function entityRecord(t: EntityType, e: Entity): Obj {
  const props: Obj = {};
  for (const k of Object.keys(e.props).sort(byCodePoint)) {
    const v = e.props[k];
    if (k !== t.key && v !== null && v !== undefined) props[k] = v;
  }
  const rec: Obj = { type: t.local, key: e.key, properties: props };
  if (e.originalAuthor !== null) rec.original_author = e.originalAuthor;
  if (e.originalAt !== null) rec.original_at = e.originalAt;
  return rec;
}

export interface Revision {
  [backend: string]: number | null;
}

export class Store {
  readonly entities = new Map<string, Entity[]>();
  private readonly byKey = new Map<string, Map<string, Entity>>();
  /** field name (a relationship or its inverse) → type local name → near key → far keys, sorted. */
  private readonly related = new Map<string, Map<string, Map<string, string[]>>>();
  readonly revision: Revision;
  /** Position of every read: the digest of the graph file's text, as opaque as any backend's. */
  readonly asOf: string;
  readonly at: string;
  /** Records in canonical order (entities by type then key, then relationships), for `export`. */
  readonly records: Obj[] = [];

  constructor(
    readonly module: ModuleModel,
    readonly resolved: ResolvedModule,
    graph: GraphFile,
    digest: string,
    loadedAt: Date = new Date(),
  ) {
    if (graph.module !== module.name)
      throw new GraphLoadError([
        {
          kind: "graph",
          ident: graph.module,
          reason: `the graph is of module ${graph.module}, the document defines ${module.name}`,
        },
      ]);
    for (const t of module.entityTypes) {
      this.entities.set(t.local, []);
      this.byKey.set(t.local, new Map());
    }
    this.asOf = `static:${digest}`;
    this.at = loadedAt.toISOString().replace("Z", "+00:00");
    const rejected: Rejection[] = [];
    for (const r of graph.records) if ("type" in r) this.importEntity(r, rejected);
    const found = new Map<string, [string, string, string]>();
    for (const r of graph.records) if (!("type" in r)) this.importRelation(r, found, rejected);
    const triples = [...found.values()];
    if (rejected.length) throw new GraphLoadError(rejected);
    this.index(triples);
    this.revision = { [BACKEND]: 1 };
    this.canonical(triples);
  }

  private importEntity(r: Obj, rejected: Rejection[]): void {
    const checked = checkEntity(this.module, this.byKey, r);
    if (checked === null) return; // a repeated record is skipped, as the import skips it
    if (!checked.ok) {
      rejected.push({ kind: "entity", ident: checked.ident, reason: checked.reason });
      return;
    }
    const e = checked.entity;
    this.entities.get(e.type.local)?.push(e);
    this.byKey.get(e.type.local)?.set(e.key, e);
  }

  private importRelation(
    r: Obj,
    triples: Map<string, [string, string, string]>,
    rejected: Rejection[],
  ): void {
    const found = checkRelation(this.module, this.byKey, r);
    if (!found.ok) {
      rejected.push({ kind: found.kind, ident: found.ident, reason: found.reason });
      return;
    }
    triples.set(found.triple.join("\u0000"), found.triple);
  }

  private index(triples: [string, string, string][]): void {
    const add = (field: string, near: string, nearType: string, far: string) => {
      const byType = this.related.get(field) ?? new Map<string, Map<string, string[]>>();
      const byKey = byType.get(nearType) ?? new Map<string, string[]>();
      const keys = byKey.get(near) ?? [];
      keys.push(far);
      byKey.set(near, keys);
      byType.set(nearType, byKey);
      this.related.set(field, byType);
    };
    for (const [name, s, t] of triples) {
      const rel = this.module.relationships.find((x) => x.name === name);
      if (!rel) continue;
      add(name, s, localOf(rel.source[0]), t);
      if (rel.inverse) add(rel.inverse, t, localOf(rel.target[0]), s);
    }
    for (const byType of this.related.values())
      for (const byKey of byType.values())
        for (const keys of byKey.values()) keys.sort(byCodePoint);
    for (const list of this.entities.values()) list.sort((a, b) => byCodePoint(a.key, b.key));
  }

  private canonical(triples: [string, string, string][]): void {
    for (const t of this.module.entityTypes)
      for (const e of this.entities.get(t.local) ?? []) this.records.push(entityRecord(t, e));
    for (const rel of this.module.relationships) {
      const mine = triples
        .filter((x) => x[0] === rel.name)
        .sort((a, b) => byCodePoint(a[1], b[1]) || byCodePoint(a[2], b[2]));
      for (const [, s, t] of mine)
        this.records.push({ relationship: rel.name, source: s, target: t });
    }
  }

  viewOf(local: string): ResolvedView {
    return this.resolved.types.get(local) as ResolvedView;
  }

  get(local: string, key: string): Entity | undefined {
    return this.byKey.get(local)?.get(key);
  }

  /** The keys at the other end of `field` from `e`, sorted by key; every one, uncapped. */
  relatedKeys(e: Entity, field: string): string[] {
    return this.related.get(field)?.get(e.type.local)?.get(e.key) ?? [];
  }

  relationFieldsOf(t: EntityType): [string, string][] {
    return relationshipsOf(this.module, t);
  }
}

const localOf = (qualified: string | undefined): string =>
  qualified ? qualified.slice(qualified.indexOf(".") + 1) : "";

export const keyOf = (e: Entity): string => e.key;
