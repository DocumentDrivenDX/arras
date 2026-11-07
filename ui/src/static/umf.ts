// SPDX-License-Identifier: MIT OR Apache-2.0
// The reader for a UMF module document in the static read-only profile (CONTRACT-012): the subset
// `arras/umf.py` reads (UMF core 0.10.0 as CONTRACT-002 states it), so a document registers here only if
// the Python registry would register it. Actions are read for their name, description and inputs only
// and are not checked or run; vocabulary aliases and the duplicate-key check of the Python reader are
// not carried (both recorded in CONTRACT-012).

import { readDomains } from "./domain";
import {
  type Action,
  type Cardinality,
  type EntityType,
  type InputSpec,
  InvalidDocument,
  type ModuleModel,
  type Prop,
  SCALAR_FAMILIES,
  type Violation,
} from "./model";
import { checkName, doc, list, MODULE_NAME, Names, type Obj, obj, text } from "./umfCommon";
import { relationships } from "./umfRelations";
import { type DeclaredView, parseView, VOCABULARY } from "./view";

export const UMF_VERSION = "0.10.0";
const CARDINALITIES: Cardinality[] = ["one", "optional", "many"];
const ROOT_KEYS = new Set(["umf", "id", "vocabularies", "extensions", "modules"]);
const MODULE_KEYS = new Set([
  "id",
  "namespace",
  "extensions",
  "elements",
  "relationships",
  "actions",
]);
const VOCABULARIES = new Set(["umf.ddd", VOCABULARY]);
const RECORD_KINDS = new Set(["entity", "value-object"]);
function propertyType(
  pname: string,
  card: Cardinality,
  typ: Obj,
  at: string,
  kinds: Map<string, string>,
  out: Violation[],
): Prop | null {
  const tn = typ.name;
  if (typ.kind === "scalar") {
    if ((SCALAR_FAMILIES as readonly unknown[]).includes(tn))
      return { name: pname, type: String(tn), scalar: true, cardinality: card };
    out.push(doc(at, `scalar '${String(tn)}' is not a supported family`));
  } else if (typ.kind === "record" && typeof tn === "string") {
    if (kinds.get(tn) === "value-object")
      return { name: pname, type: tn, scalar: false, cardinality: card };
    out.push(doc(at, `'${tn}' is not a value object of this module`));
  } else out.push(doc(at, `unsupported type '${String(typ.kind)}'`));
  return null;
}

function properties(ddd: Obj, path: string, kinds: Map<string, string>, out: Violation[]): Prop[] {
  const props: Prop[] = [];
  const names = new Names(out);
  for (const [pname, raw] of Object.entries(obj(ddd.fields))) {
    const at = `${path}.${pname}`;
    const spec = obj(raw);
    const bad = checkName(pname, at);
    if (bad) out.push(bad);
    names.add(pname, at);
    const card = spec.cardinality as Cardinality;
    if (!CARDINALITIES.includes(card)) {
      out.push(doc(at, "cardinality must be one of ('one', 'optional', 'many')"));
      continue;
    }
    const prop = propertyType(pname, card, obj(spec.type), at, kinds, out);
    if (prop) props.push(prop);
  }
  return props;
}

function crossCheck(
  el: Obj,
  tname: string,
  props: Prop[],
  fields: Map<string, Obj>,
  path: string,
  out: Violation[],
): Set<string> {
  const members = new Set(list(el.members).map((m) => String(obj(m).element)));
  const claimed = new Set<string>();
  for (const p of props) {
    const fid = `${tname}.${p.name}`;
    const fel = fields.get(fid);
    if (!fel || !members.has(fid)) {
      out.push(doc(`${path}.${p.name}`, `no field element '${fid}' among the members`));
      continue;
    }
    claimed.add(fid);
    if (p.scalar && fel.scalarType !== p.type)
      out.push(doc(`${path}.${p.name}`, "the field element's scalar type differs"));
    if ((fel.nullability === "required") !== (p.cardinality === "one"))
      out.push(doc(`${path}.${p.name}`, "required-ness differs between the two forms"));
    if ((fel.cardinality === "many") !== (p.cardinality === "many"))
      out.push(doc(`${path}.${p.name}`, "the field element's cardinality differs"));
  }
  const declared = new Set(props.map((p) => `${tname}.${p.name}`));
  for (const extra of members)
    if (!declared.has(extra)) out.push(doc(path, `member '${extra}' has no field in the record`));
  return claimed;
}

function keyOf(
  el: Obj,
  module: string,
  tname: string,
  props: Prop[],
  fields: Map<string, Obj>,
  path: string,
  out: Violation[],
): string | null {
  const miss = (message: string): null => {
    out.push({ path, code: "missing_key", message });
    return null;
  };
  const primary = list(el.keys)
    .map(obj)
    .filter((k) => k.primary === true);
  if (primary.length !== 1) return miss("declare exactly one primary key");
  const members = list(primary[0]?.fields).map(obj);
  if (members.length !== 1) return miss("a key is exactly one field");
  const ref = String(members[0]?.element ?? "");
  const fname = ref.startsWith(`${tname}.`) ? ref.slice(tname.length + 1) : ref;
  if (members[0]?.module !== module || ref !== `${tname}.${fname}`)
    return miss("the key names a field of another record");
  const prop = props.find((p) => p.name === fname);
  const required = obj(fields.get(ref)).nullability === "required";
  if (prop?.type !== "string" || prop.cardinality !== "one" || !required)
    return miss("the key is a required string field");
  return fname;
}

function records(mod: Obj, module: string, names: Names, out: Violation[]): EntityType[] {
  const fields = new Map<string, Obj>();
  const recs: Obj[] = [];
  list(mod.elements)
    .map(obj)
    .forEach((el, i) => {
      const id = text(el.id, `elements[${i}].id`, "an element id", out);
      if (el.kind === "field" && id !== null) {
        if (fields.has(id)) out.push(doc(`elements.${id}`, `element '${id}' is declared twice`));
        fields.set(id, el);
      } else if (el.kind === "record" && id !== null) recs.push(el);
      else if (el.kind !== "field" && el.kind !== "record")
        out.push(doc(`elements[${i}]`, `unsupported element kind '${String(el.kind)}'`));
    });
  const dddOf = (el: Obj) => obj(obj(el.extensions)["umf.ddd"]);
  const kinds = new Map(recs.map((el) => [String(el.id), String(dddOf(el).kind)]));
  const entities: EntityType[] = [];
  const claimed = new Set<string>();
  for (const el of recs) {
    const tname = String(el.id);
    const path = `elements.${tname}`;
    const kind = kinds.get(tname) as string;
    if (!RECORD_KINDS.has(kind)) {
      out.push(doc(path, `unsupported record kind '${kind}'`));
      continue;
    }
    const entity = kind === "entity";
    const bad = checkName(tname, path, entity);
    if (bad) out.push(bad);
    names.add(tname, path);
    const props = properties(dddOf(el), path, kinds, out);
    for (const c of crossCheck(el, tname, props, fields, path, out)) claimed.add(c);
    if (entity) {
      const key = keyOf(el, module, tname, props, fields, path, out);
      entities.push({
        name: `${module}.${tname}`,
        local: tname,
        key: key ?? "",
        properties: props,
      });
    } else if (list(el.keys).length) out.push(doc(path, "a value object has no key"));
  }
  for (const fid of fields.keys())
    if (!claimed.has(fid)) out.push(doc(`elements.${fid}`, `field '${fid}' belongs to no record`));
  return entities;
}

function inputSpec(raw: unknown): InputSpec | null {
  const sd = obj(raw);
  const t = obj(sd.type);
  const kind = t.kind;
  const tname = kind === "ref" ? t.type : t.name;
  const card = sd.cardinality ?? "one";
  if (kind !== "scalar" && kind !== "record" && kind !== "ref") return null;
  if (!CARDINALITIES.includes(card as Cardinality)) return null;
  if (typeof tname !== "string" || typeof sd.name !== "string" || !sd.name) return null;
  return { name: sd.name, type: tname, kind, cardinality: card as Cardinality };
}

function actionOf(raw: unknown, module: string, out: Violation[]): Action | null {
  const r = obj(raw);
  if (typeof r.id !== "string" || !r.id) {
    out.push({ path: "actions", code: "invalid_action", message: "an action id is missing" });
    return null;
  }
  const inputSpecs: InputSpec[] = [];
  list(r.inputs).forEach((x, i) => {
    const s = inputSpec(x);
    if (s) inputSpecs.push(s);
    else
      out.push({
        path: `actions.${module}.${r.id}.inputs[${i}]`,
        code: "invalid_action",
        message: "an input has a name, a type and a cardinality",
      });
  });
  return { name: `${module}.${r.id}`, description: String(r.description ?? ""), inputSpecs };
}

function checkRoot(root: Obj, out: Violation[]): void {
  if (root.umf !== UMF_VERSION) out.push(doc("umf", `UMF core ${UMF_VERSION} is required`));
  for (const k of Object.keys(root))
    if (!ROOT_KEYS.has(k)) out.push(doc(k, `unsupported construct '${k}'`));
  const vocabularies = obj(root.vocabularies);
  for (const v of Object.keys(vocabularies))
    if (!VOCABULARIES.has(v)) out.push(doc(`vocabularies.${v}`, `unsupported vocabulary '${v}'`));
  if ("umf.ddd" in vocabularies && obj(vocabularies["umf.ddd"]).version !== "0.1.0")
    out.push(doc("vocabularies.umf.ddd.version", "umf.ddd vocabulary version 0.1.0 is required"));
}

export interface ParsedModule {
  module: ModuleModel;
  declared: DeclaredView;
}

/** Read one UMF module document; throws `InvalidDocument` listing every violation. */
export function parseModule(documentText: string): ParsedModule {
  let raw: unknown;
  try {
    raw = JSON.parse(documentText);
  } catch (e) {
    throw new InvalidDocument([
      doc("document", `not valid JSON: ${e instanceof Error ? e.message : String(e)}`),
    ]);
  }
  const root = obj(raw);
  const out: Violation[] = [];
  checkRoot(root, out);
  const modules = list(root.modules);
  if (modules.length !== 1) {
    out.push(doc("modules", `a document defines exactly one module, found ${modules.length}`));
    throw new InvalidDocument(out);
  }
  const mod = obj(modules[0]);
  for (const k of Object.keys(mod))
    if (!MODULE_KEYS.has(k)) out.push(doc(`modules[0].${k}`, `unsupported construct '${k}'`));
  let name = mod.id;
  if (typeof name !== "string" || !MODULE_NAME.test(name)) {
    out.push({
      path: "modules[0].id",
      code: "invalid_name",
      message: "a module id is [a-z][a-z0-9_]{0,40}",
    });
    name = String(name);
  }
  const moduleName = name as string;
  const allowed = new Set(
    [...VOCABULARIES].filter((v) => v in obj(root.vocabularies) || v === "umf.ddd"),
  );
  for (const ext of Object.keys(obj(mod.extensions)))
    if (!allowed.has(ext)) out.push(doc(`extensions.${ext}`, `unsupported extension '${ext}'`));
  const names = new Names(out);
  const entityTypes = records(mod, moduleName, names, out);
  const rels = relationships(mod, moduleName, entityTypes, names, out);
  const actions = list(mod.actions)
    .map((a) => actionOf(a, moduleName, out))
    .filter((a): a is Action => a !== null);
  const model: ModuleModel = {
    name: moduleName,
    domains: readDomains(root),
    entityTypes,
    relationships: rels,
    actions,
  };
  const { declared, faults } = parseView(root, model);
  out.push(...faults);
  if (out.length) throw new InvalidDocument(out);
  return { module: model, declared };
}
