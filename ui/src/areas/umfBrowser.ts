// SPDX-License-Identifier: MIT OR Apache-2.0
// What the console hands UMF's schema browser (`@documentdrivendx/umf-schema-browser`, its host
// contract 1.1: HOST_CONTRACT.md in the package) and how it reads what comes back: the catalog as
// entries, the selection grammar, annotations from the live registry, the theme from the console's
// own tokens. Pure functions, so each is tested without the frame.
import type { Annotation, Entry, Selection } from "@documentdrivendx/umf-schema-browser";
import type {
  BackendCapabilities,
  BackendStatus,
  ModuleInfo,
  SchemaCatalog,
  SchemaCatalogEntry,
} from "../api/types";

/** The catalog id of a module's registered document (CONTRACT-009). */
export const entryId = (module: string) => `arras:${module}`;

/** The one category the operator surface sets (`domain`), with the console's label for it. */
export const CATEGORIES = [{ id: "domain", label: "Registered modules" }];

/** The operator surface's catalog as the package's `Entry[]`: the fields it reads, nothing added. */
export function toEntries(catalog: SchemaCatalog): Entry[] {
  return catalog.entries.map((e: SchemaCatalogEntry) => ({
    id: e.id,
    title: e.title,
    category: "domain",
    path: e.path,
    text: e.text,
    format: e.format === "yaml" ? "yaml" : "json",
    description: e.description,
    schemaFormat: e.schemaFormat,
  }));
}

/** A definition key, `[moduleId, elementId]` as JSON (the contract's "Routing" section). */
export const definitionKey = (module: string, element: string) => JSON.stringify([module, element]);
/** A relationship key, `["relationship", moduleId, relationshipId]` as JSON. */
export const relationshipKey = (module: string, relationship: string) =>
  JSON.stringify(["relationship", module, relationship]);

function parseKey(key: string | undefined): string[] | undefined {
  if (!key) return undefined;
  try {
    const v: unknown = JSON.parse(key);
    return Array.isArray(v) && v.every((x) => typeof x === "string") ? (v as string[]) : undefined;
  } catch {
    return undefined;
  }
}

/** The registered document's record and relationship ids, by module (a JSON document only). */
export interface DocumentIds {
  /** UMF module id -> its record element ids. */
  records: Map<string, Set<string>>;
  /** UMF module id -> relationship name -> relationship id. */
  relationships: Map<string, Map<string, string>>;
}

interface RegisteredDoc {
  modules?: {
    id?: string;
    elements?: { id?: string; kind?: string }[];
    relationships?: { id?: string; name?: string }[];
  }[];
}

function parseDocument(e: Entry): RegisteredDoc | undefined {
  if (e.format !== "json" || typeof e.text !== "string") return undefined;
  try {
    return JSON.parse(e.text) as RegisteredDoc;
  } catch {
    return undefined;
  }
}

function addModuleIds(out: DocumentIds, m: NonNullable<RegisteredDoc["modules"]>[number]) {
  if (typeof m.id !== "string") return;
  const records = out.records.get(m.id) ?? new Set<string>();
  for (const el of m.elements ?? [])
    if (el.kind === "record" && typeof el.id === "string") records.add(el.id);
  out.records.set(m.id, records);
  const rels = out.relationships.get(m.id) ?? new Map<string, string>();
  for (const r of m.relationships ?? [])
    if (typeof r.id === "string") rels.set(typeof r.name === "string" ? r.name : r.id, r.id);
  out.relationships.set(m.id, rels);
}

export function documentIds(entries: Entry[]): DocumentIds {
  const out: DocumentIds = { records: new Map(), relationships: new Map() };
  for (const e of entries) {
    for (const m of parseDocument(e)?.modules ?? []) addModuleIds(out, m);
  }
  return out;
}

/** "catalog.UseCase" -> ["catalog", "UseCase"]: an Arras type is `<module>.<record>`. */
function split(typeName: string): [string, string] {
  const i = typeName.indexOf(".");
  return i < 0 ? ["", typeName] : [typeName.slice(0, i), typeName.slice(i + 1)];
}

/**
 * The entity type of `module` a selection names, mapped by name: a definition `[M, E]` in the
 * module's own entry is the type `M.E` when the module declares it. Anything else (a field, another
 * module's entry, a relationship) maps to nothing.
 */
export function typeForSelection(
  selection: Selection | null | undefined,
  module: ModuleInfo | undefined,
): string | undefined {
  if (!selection || !module || selection.schema !== entryId(module.name)) return undefined;
  const key = parseKey(selection.definition);
  if (key?.length !== 2) return undefined;
  const name = `${key[0]}.${key[1]}`;
  return module.entityTypes.some((t) => t.name === name) ? name : undefined;
}

/** The selection that opens the module's entry, with its entity type `<module>.<record>` selected when one is named. */
export function selectionFor(module: string, type?: string): Selection {
  const schema = entryId(module);
  if (!type) return { schema };
  const [moduleId, record] = split(type);
  return moduleId && record ? { schema, definition: definitionKey(moduleId, record) } : { schema };
}

/** "catalog › UseCase", "catalog › relationship solution-addresses", or the schema alone. */
export function describeSelection(
  selection: Selection,
  entries: Entry[],
): { schema: string; item?: string } {
  const schema = entries.find((e) => e.id === selection.schema)?.title ?? selection.schema;
  const def = parseKey(selection.definition);
  if (def && def.length === 2) return { schema, item: def[1] };
  const rel = parseKey(selection.relationship);
  if (rel && rel.length === 3 && rel[0] === "relationship")
    return { schema, item: `relationship ${rel[2]}` };
  if (selection.definition) return { schema, item: selection.definition };
  return { schema };
}

const backendsOf = (m: ModuleInfo) => [m.record, ...m.replicas.filter((r) => r !== m.record)];

/**
 * Host claims from the live registry for the browser's `annotations` (the contract: exact IDs to
 * `[{badge, tone, tooltip}]`). For each module in the catalog: on its entry, the record store, the
 * replicas and any backend the status reports unavailable; on each record that is an entity type,
 * one annotation per backend saying what it serves for it (`<backend> · mutable`, `<backend> · read-only`);
 * on each relationship, the backends whose capabilities follow it. Text only: the document is
 * unchanged.
 *
 * Tones, the same in both schemes: `positive` for the record store and a mutable backend, `neutral`
 * for a replica and a read-only one, `warning` for a backend that is unavailable or serves nothing
 * for the type, `info` for the backends a relationship follows. Package 1.1.2 draws every tone at
 * >= 4.5:1 in both schemes (measured in the frame: e2e/umf-explorer.spec.ts); its record map draws
 * them all in `--ink`, so there the badge's text carries the state. The map reserves a line for
 * each annotation, so a record carries one per backend, none over its property count.
 */
export function annotationsFor(
  modules: ModuleInfo[],
  status: BackendStatus[],
  entries: Entry[],
): Record<string, Annotation[]> {
  const ids = documentIds(entries);
  const listed = new Set(entries.map((e) => e.id));
  const down = new Map(
    status.filter((s) => !s.available).map((s) => [s.backend, s.reason ?? "unavailable"]),
  );
  const out: Record<string, Annotation[]> = {};
  for (const m of modules) {
    if (!listed.has(entryId(m.name))) continue;
    const backends = backendsOf(m);
    out[entryId(m.name)] = entryAnnotations(m, backends, down);
    Object.assign(out, recordAnnotations(m, backends, down, ids));
    Object.assign(out, relationshipAnnotations(m, backends, ids));
  }
  return out;
}

function entryAnnotations(
  m: ModuleInfo,
  backends: string[],
  down: Map<string, string>,
): Annotation[] {
  const entry: Annotation[] = [
    {
      badge: `record: ${m.record}`,
      tone: "positive",
      tooltip: `${m.record} is the system of record: it serves LATEST reads and holds the module's document`,
    },
    ...m.replicas.map(
      (r): Annotation => ({
        badge: `replica: ${r}`,
        tone: "neutral",
        tooltip: `${r} serves BULK reads from a replica`,
      }),
    ),
  ];
  for (const b of backends) {
    if (down.has(b))
      entry.push({
        badge: `${b} · unavailable`,
        tone: "warning",
        tooltip: `${b} is unavailable now (${down.get(b)})`,
      });
  }
  return entry;
}

function recordAnnotations(
  m: ModuleInfo,
  backends: string[],
  down: Map<string, string>,
  ids: DocumentIds,
): Record<string, Annotation[]> {
  const out: Record<string, Annotation[]> = {};
  for (const t of m.entityTypes) {
    const [mod, record] = split(t.name);
    if (!ids.records.get(mod)?.has(record)) continue;
    out[definitionKey(mod, record)] = backends.map((b) =>
      backendAnnotation(b, b === m.record ? "record store" : "replica", t.capabilities[b], down),
    );
  }
  return out;
}

function backendAnnotation(
  b: string,
  role: string,
  c: BackendCapabilities | undefined,
  down: Map<string, string>,
): Annotation {
  if (!c) {
    return down.has(b)
      ? {
          badge: `${b} · unavailable`,
          tone: "warning",
          tooltip: `${b} (${role}): unavailable now (${down.get(b)}), so it reports no capabilities`,
        }
      : {
          badge: `${b} · not served`,
          tone: "warning",
          tooltip: `${b} (${role}): reports no capabilities for this type`,
        };
  }
  const columns = (c.columns ?? []).join(", ") || "none";
  const access = c.mutable
    ? "mutable, applies this type's actions"
    : role === "replica"
      ? "read-only replica"
      : "read-only";
  return {
    badge: `${b} · ${c.mutable ? "mutable" : "read-only"}`,
    tone: c.mutable ? "positive" : "neutral",
    tooltip: `${b} (${role}): ${access}; latency ${c.latency_class ?? "not stated"}; filter columns: ${columns}; ${c.count ? "counts" : "no counts"}`,
  };
}

function relationshipAnnotations(
  m: ModuleInfo,
  backends: string[],
  ids: DocumentIds,
): Record<string, Annotation[]> {
  const out: Record<string, Annotation[]> = {};
  for (const r of m.relationships) {
    const [mod] = split(r.source[0] ?? "");
    const id = ids.relationships.get(mod || m.name)?.get(r.name);
    if (!id) continue;
    const sources = m.entityTypes.filter((t) => r.source.includes(t.name));
    const follows = backends.filter(
      (b) =>
        sources.length > 0 &&
        sources.every((t) => t.capabilities[b]?.relationships?.includes(r.name)),
    );
    out[relationshipKey(mod || m.name, id)] = [
      follows.length
        ? {
            badge: `follows: ${follows.join(", ")}`,
            tone: "info",
            tooltip: `Backends whose capabilities follow ${r.name} from ${r.source.join(", ")}`,
          }
        : {
            badge: "not followed",
            tone: "warning",
            tooltip: `No available backend reports ${r.name} among its capabilities`,
          },
    ];
  }
  return out;
}

/** The console's tokens -> the browser's theme variables (the contract's `themeVariables` keys). */
export const THEME_TOKENS: Record<string, string> = {
  "--paper": "--surface",
  "--ink": "--fg",
  "--muted": "--umf-muted",
  "--line": "--line",
  "--accent": "--accent",
};

/**
 * What an element says about the scheme itself: `data-appearance`, else an inline `color-scheme` that is one
 * scheme, with or without CSS's `only` keyword (`dark`, `dark only`); the two-value forms say none.
 */
function declaredScheme(e: Element): "light" | "dark" | undefined {
  const given = e.getAttribute("data-appearance");
  if (given === "light" || given === "dark") return given;
  const inline = (e as HTMLElement).style?.getPropertyValue("color-scheme").trim();
  const single = /^(light|dark)(?:\s+only)?$/.exec(inline ?? "");
  return single ? (single[1] as "light" | "dark") : undefined;
}

/**
 * The scheme the host shows an element in: the nearest ancestor (or the element itself) that says one, by
 * `data-appearance="light" | "dark"` (the host's `ThemeProvider` sets it) or by an inline `color-scheme`
 * (a `ThemeProvider` given only its `tokens` sets just that), else the element's computed `color-scheme`
 * (which the console's own tokens set), else the system's preference (also the answer where styles are not
 * computed). The console's stylesheet reads the same two markers, so its tokens and this agree.
 */
export function schemeOf(el: Element | null | undefined): "light" | "dark" {
  for (let a = el; a; a = a.parentElement) {
    const declared = declaredScheme(a);
    if (declared) return declared;
  }
  const view = el?.ownerDocument.defaultView ?? window;
  const cs = el ? view.getComputedStyle(el).colorScheme : "";
  if (cs === "dark" || cs === "light") return cs;
  return view.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * The browser's theme for the console's current scheme, read from the console's own tokens. The tokens are on
 * the console's root element (`.arras-root`), not on the page: `from` is an element inside it, or a document to
 * find it in; where there is none (a page that sets the tokens itself) the page's root element is read.
 */
export function hostTheme(from: Element | Document = document): {
  theme: "light" | "dark";
  themeVariables: Record<string, string>;
} {
  const doc = from instanceof Document ? from : from.ownerDocument;
  const root =
    (from instanceof Document ? from.querySelector(".arras-root") : from.closest(".arras-root")) ??
    doc.documentElement;
  const view = doc.defaultView;
  const style = view?.getComputedStyle(root);
  const themeVariables: Record<string, string> = {};
  for (const [umf, ours] of Object.entries(THEME_TOKENS)) {
    const v = style?.getPropertyValue(ours).trim();
    if (v) themeVariables[umf] = v;
  }
  const font = style?.fontFamily ?? "";
  if (font) themeVariables["--umf-font"] = font;
  return { theme: schemeOf(root), themeVariables };
}
