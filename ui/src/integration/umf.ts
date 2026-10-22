// SPDX-License-Identifier: MIT OR Apache-2.0
// UMF documents for the integration tests: the module in force, read as the dev host serves it, and edited
// the way tests/test_schema_library.py `with_property` does (a required property is also set by the actions
// that create the type, or the document would not be valid).

import { defined } from "../test/defined";
import { call, type Who } from "./harness";

/** The registered document of `catalog`, exactly as the viewer's schema catalog holds it. */
export async function registered(who: Who = "alice", module = "catalog"): Promise<string> {
  const r = await call("/api/operate/explorer/schema-catalog.json", undefined, who);
  const e = (r.body as { entries: { id: string; text: string }[] }).entries.find(
    (x) => x.id === `arras:${module}`,
  );
  if (!e)
    throw new Error(`no catalog entry for ${module}: ${JSON.stringify(r.body).slice(0, 200)}`);
  return e.text;
}

/** The parts of a registered UMF document `withProperty` reads and edits. */
interface UmfElement {
  id: string;
  members?: { module: string; element: string }[];
  extensions: Record<string, { fields: Record<string, unknown> }>;
  [key: string]: unknown;
}
interface UmfDocument {
  modules: {
    elements: UmfElement[];
    actions: { effects: { op: string; type?: string; properties: Record<string, unknown> }[] }[];
  }[];
}

export function withProperty(
  text: string,
  name: string,
  opts: { required: boolean; type?: string },
): string {
  const type = opts.type ?? "UseCase";
  const d = JSON.parse(text) as UmfDocument;
  const mod = defined(d.modules[0], "the module");
  const els = mod.elements;
  const rec = defined(
    els.find((e) => e.id === type),
    `element ${type}`,
  );
  defined(rec.members, `members of ${type}`).push({
    module: "catalog",
    element: `${type}.${name}`,
  });
  defined(rec.extensions["umf.ddd"], "umf.ddd").fields[name] = {
    type: { kind: "scalar", name: "string" },
    cardinality: opts.required ? "one" : "optional",
  };
  els.push({
    id: `${type}.${name}`,
    kind: "field",
    nullability: opts.required ? "required" : "absent-allowed",
    cardinality: "one",
    scalarType: "string",
    extensions: {},
  });
  if (opts.required) {
    for (const a of mod.actions)
      for (const e of a.effects)
        if (e.op === "create" && e.type === type) e.properties[name] = { literal: "n/a" };
  }
  return JSON.stringify(d);
}
