// SPDX-License-Identifier: MIT OR Apache-2.0
// The relationships of a module document, as `arras/umf.py` reads them (CONTRACT-002): endpoints, inverse,
// multiplicity, and the case-folded names a relationship's column shares with its endpoint types' properties.
import type { EntityType, Rel, Violation } from "./model";
import { checkName, doc, list, Names, type Obj, obj, text } from "./umfCommon";

function multiplicity(v: unknown, path: string, out: Violation[]): string | null {
  const m = obj(v);
  const lo = m.min;
  const hi = m.max;
  if (typeof lo !== "number" || !Number.isInteger(lo) || lo < 0) {
    out.push(doc(path, "min is an integer of at least 0"));
    return null;
  }
  if (hi === "*") return `${lo}..*`;
  if (typeof hi !== "number" || !Number.isInteger(hi) || hi < Math.max(lo, 1)) {
    out.push(doc(path, "max is '*' or an integer of at least min and 1"));
    return null;
  }
  return `${lo}..${hi}`;
}

function endpoints(
  rel: Obj,
  side: "source" | "target",
  ctx: {
    path: string;
    module: string;
    entities: EntityType[];
    col: string | null;
    cols: Map<string, Names>;
    out: Violation[];
  },
): string[] {
  const eps: string[] = [];
  for (const ep of list(rel[side]).map(obj)) {
    const m = text(ep.module, `${ctx.path}.${side}`, "an endpoint module", ctx.out);
    const e = text(ep.element, `${ctx.path}.${side}`, "an endpoint type", ctx.out);
    if (m === null || e === null) continue;
    if (m === ctx.module) {
      if (!ctx.entities.some((t) => t.local === e))
        ctx.out.push({
          path: `${ctx.path}.${side}`,
          code: "unknown_type",
          message: `${ctx.module}.${e} is not defined`,
        });
      else if (ctx.col !== null) ctx.cols.get(e)?.add(ctx.col, `${ctx.path}.${side}`);
    }
    eps.push(`${m}.${e}`);
  }
  if (eps.length === 0)
    ctx.out.push(doc(`${ctx.path}.${side}`, "a relationship names its endpoint types"));
  return eps;
}

function inverseOf(rel: Obj, path: string, names: Names, out: Violation[]): string | null {
  if (rel.inverse === undefined || rel.inverse === null) return null;
  if (typeof rel.inverse !== "string") {
    out.push(doc(`${path}.inverse`, "an inverse is a name"));
    return null;
  }
  const bad = checkName(rel.inverse, `${path}.inverse`);
  if (bad) out.push(bad);
  names.add(rel.inverse, `${path}.inverse`);
  return rel.inverse;
}

interface RelContext {
  module: string;
  entities: EntityType[];
  cols: Map<string, Names>;
  names: Names;
  out: Violation[];
}

function readRelationship(raw: unknown, i: number, ctx: RelContext): Rel | null {
  const { out } = ctx;
  const rel = obj(raw);
  const rname = text(rel.name, `relationships[${i}].name`, "a relationship name", out);
  if (rname === null) return null;
  const path = `relationships.${rname}`;
  const bad = checkName(rname, path);
  if (bad) out.push(bad);
  ctx.names.add(rname, path);
  const inverse = inverseOf(rel, path, ctx.names, out);
  const base = { path, module: ctx.module, entities: ctx.entities, cols: ctx.cols, out };
  const source = endpoints(rel, "source", { ...base, col: rname });
  const target = endpoints(rel, "target", { ...base, col: inverse });
  const sm = multiplicity(rel.sourceMultiplicity, `${path}.sourceMultiplicity`, out);
  const tm = multiplicity(rel.targetMultiplicity, `${path}.targetMultiplicity`, out);
  if (sm === null || tm === null) return null;
  return {
    name: rname,
    source,
    target,
    sourceMultiplicity: sm,
    targetMultiplicity: tm,
    lifecycle: String(rel.targetLifecycle ?? "independent"),
    inverse,
  };
}

export function relationships(
  mod: Obj,
  module: string,
  entities: EntityType[],
  names: Names,
  out: Violation[],
): Rel[] {
  const cols = new Map(entities.map((t) => [t.local, new Names(out)]));
  for (const t of entities) {
    const n = cols.get(t.local);
    if (n) n.seen = new Map(t.properties.map((p) => [p.name.toLowerCase(), p.name]));
  }
  const ctx: RelContext = { module, entities, cols, names, out };
  return list(mod.relationships)
    .map((raw, i) => readRelationship(raw, i, ctx))
    .filter((r): r is Rel => r !== null);
}
