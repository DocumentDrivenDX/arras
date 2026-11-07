// SPDX-License-Identifier: MIT OR Apache-2.0
// Reading a document's `arras.view` terms for the static read-only profile (CONTRACT-010 A): where a term may
// be, the size bounds, and `parseView`. A port of `parse_view` and its readers in `arras/view.py`.
import { entityTypeOf, type ModuleModel, propertyOf, type Violation } from "./model";
import { Checker } from "./viewCheck";
import {
  type DeclaredView,
  emptyView,
  type FieldTerms,
  fieldKey,
  list,
  MAX_DOCUMENT_BYTES,
  MAX_RECORD_BYTES,
  type Obj,
  obj,
  type RecordTerms,
  type RelationshipTerms,
  VERSION,
  VOCABULARY,
} from "./viewTerms";

const size = (...parts: unknown[]): number =>
  new TextEncoder().encode(JSON.stringify(parts)).length;
const extOf = (carrier: unknown, vocabulary: string): unknown =>
  obj(obj(carrier).extensions)[vocabulary];
const hasView = (carrier: unknown, vocabulary: string): boolean =>
  vocabulary in obj(obj(carrier).extensions);

type ElementTerms = { records: Map<string, RecordTerms>; fields: Map<string, FieldTerms> };

function readRecord(c: Checker, el: Obj, path: string, vocabulary: string, out: ElementTerms) {
  const id = String(el.id ?? "");
  const t = entityTypeOf(c.mod, id);
  if (!t) c.fault(path, "view_unknown_term", "only an entity record has a view");
  else out.records.set(id, c.recordTerms(extOf(el, vocabulary), path, t));
}

function readField(c: Checker, el: Obj, path: string, vocabulary: string, out: ElementTerms) {
  const id = String(el.id ?? "");
  const dot = id.indexOf(".");
  const typeName = dot < 0 ? id : id.slice(0, dot);
  const prop = dot < 0 ? "" : id.slice(dot + 1);
  const t = entityTypeOf(c.mod, typeName);
  const p = t ? propertyOf(t, prop) : undefined;
  if (!p) c.fault(path, "view_unknown_term", "only the field of an entity record has a view");
  else out.fields.set(fieldKey(typeName, prop), c.fieldTerms(extOf(el, vocabulary), path, p));
}

function readElement(c: Checker, raw: unknown, i: number, vocabulary: string, out: ElementTerms) {
  const el = obj(raw);
  if (!hasView(el, vocabulary)) return;
  const path = `modules[0].elements[${i}].extensions.${vocabulary}`;
  if (el.kind === "record") readRecord(c, el, path, vocabulary, out);
  else if (el.kind === "field") readField(c, el, path, vocabulary, out);
  else c.fault(path, "view_unknown_term", "only a record or a field has a view");
}

function readElements(c: Checker, elements: unknown[], vocabulary: string): ElementTerms {
  const out: ElementTerms = { records: new Map(), fields: new Map() };
  elements.forEach((raw, i) => {
    readElement(c, raw, i, vocabulary, out);
  });
  checkRecordSizes(c, elements, vocabulary);
  return out;
}

function checkRecordSizes(c: Checker, elements: unknown[], vocabulary: string): void {
  const sizes = new Map<string, number>();
  const first = new Map<string, number>();
  elements.forEach((raw, i) => {
    const el = obj(raw);
    const id = String(el.id ?? "");
    const owner = el.kind === "field" ? (id.split(".")[0] ?? "") : id;
    if (!hasView(el, vocabulary)) return;
    sizes.set(owner, (sizes.get(owner) ?? 0) + size(extOf(el, vocabulary)));
    if (!first.has(owner)) first.set(owner, i);
  });
  for (const [owner, n] of sizes)
    if (n > MAX_RECORD_BYTES)
      c.fault(
        `modules[0].elements[${first.get(owner)}].extensions.${vocabulary}`,
        "view_too_large",
        `${owner}'s view is at most 16 KiB`,
      );
}

function readRelationships(c: Checker, rels: unknown[], vocabulary: string) {
  const out = new Map<string, RelationshipTerms>();
  rels.forEach((raw, i) => {
    const rel = obj(raw);
    if (!hasView(rel, vocabulary)) return;
    const path = `modules[0].relationships[${i}].extensions.${vocabulary}`;
    if (size(extOf(rel, vocabulary)) > MAX_RECORD_BYTES)
      c.fault(path, "view_too_large", "a relationship's view is at most 16 KiB");
    out.set(
      String(rel.name ?? ""),
      c.relationshipTerms(extOf(rel, vocabulary), path, Boolean(rel.inverse)),
    );
  });
  return out;
}

function readModule(c: Checker, root: Obj, module: Obj, vocabulary: string): DeclaredView {
  if (hasView(root, vocabulary))
    c.fault(`extensions.${vocabulary}`, "view_unknown_term", "a view belongs to a module");
  let head: { title?: string; description?: string } = {};
  if (hasView(module, vocabulary))
    head = c.moduleTerms(extOf(module, vocabulary), `modules[0].extensions.${vocabulary}`);
  list(module.actions).forEach((a, i) => {
    if (hasView(a, vocabulary))
      c.fault(
        `modules[0].actions[${i}].extensions.${vocabulary}`,
        "view_unknown_term",
        "an action has no view",
      );
  });
  const { records, fields } = readElements(c, list(module.elements), vocabulary);
  const relationships = readRelationships(c, list(module.relationships), vocabulary);
  return { ...head, records, fields, relationships };
}

/**
 * Check and read the document's `arras.view` terms against the module's types. The terms are examined
 * only when the document declares the vocabulary; a version this release does not support is the one
 * fault then. (Vocabulary aliases are not read by the static profile: CONTRACT-012.)
 */
export function parseView(
  root: Obj,
  mod: ModuleModel,
): { declared: DeclaredView; faults: Violation[] } {
  const module = obj(list(root.modules)[0]);
  if (!(VOCABULARY in obj(root.vocabularies))) return { declared: emptyView(), faults: [] };
  if (obj(obj(root.vocabularies)[VOCABULARY]).version !== VERSION)
    return {
      declared: emptyView(),
      faults: [
        {
          path: `vocabularies.${VOCABULARY}.version`,
          code: "view_unsupported_version",
          message: `view vocabulary ${VERSION} is supported`,
        },
      ],
    };
  const c = new Checker(mod);
  const declared = readModule(c, root, module, VOCABULARY);
  const total = size(
    declared.title,
    declared.description,
    list(module.elements).map((e) => extOf(e, VOCABULARY)),
    list(module.relationships).map((r) => extOf(r, VOCABULARY)),
  );
  if (total > MAX_DOCUMENT_BYTES)
    c.fault(
      `modules[0].extensions.${VOCABULARY}`,
      "view_too_large",
      "a document's views are at most 128 KiB",
    );
  return { declared, faults: c.out };
}
