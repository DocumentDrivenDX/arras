// SPDX-License-Identifier: MIT OR Apache-2.0
// Defaults and resolution for the static read-only profile (CONTRACT-010 B): a declaration merged with the
// defaults a type's name and properties give. A port of the resolution half of `arras/view.py`.
import { type EntityType, type ModuleModel, type Prop, propertyOf } from "./model";
import { evaluate, placeholders, pyStrip } from "./viewTemplate";
import {
  BADGE,
  type DeclaredSection,
  type DeclaredView,
  emptyView,
  type FieldTerms,
  fieldKey,
  LINK_SUFFIXES,
  MAX_SEARCH,
  PROSE,
  type RelationshipTerms,
  type ResolvedModule,
  type ResolvedView,
  SEARCH_TAIL,
  SUMMARY_NAMES,
  TITLE_NAMES,
  TONES,
} from "./viewTerms";

export const titleOf = (view: ResolvedView, row: Record<string, unknown>, key: string): string =>
  pyStrip(evaluate(view.title, row)) || key;

// -- words and defaults ------------------------------------------------------------------------

const WORDS = /[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+[0-9]*|[A-Z]+[0-9]*|[0-9]+/g;
const isUpper = (w: string) => w === w.toUpperCase() && w !== w.toLowerCase();

/** `UseCase` is `Use case`, `workArea` is `Work area`, `HTTPServer` is `HTTP server`. */
export function splitWords(name: string): string {
  const words = name.replaceAll("_", " ").replaceAll("-", " ").match(WORDS);
  if (!words) return name;
  const out = words.map((w) => (w.length > 1 && isUpper(w) ? w : w.toLowerCase()));
  out[0] = (out[0] ?? "").slice(0, 1).toUpperCase() + (out[0] ?? "").slice(1);
  return out.join(" ");
}

/** A label in the plural, by English rules; only the last word changes. */
export function pluralize(label: string): string {
  const at = label.lastIndexOf(" ");
  const head = at < 0 ? "" : label.slice(0, at + 1);
  const last = at < 0 ? label : label.slice(at + 1);
  const lower = last.toLowerCase();
  let plural: string;
  if (lower.length > 1 && lower.endsWith("y") && !"aeiou".includes(lower.charAt(lower.length - 2)))
    plural = `${last.slice(0, -1)}ies`;
  else if (["s", "x", "z", "ch", "sh"].some((e) => lower.endsWith(e))) plural = `${last}es`;
  else plural = `${last}s`;
  return head + plural;
}

const SCALAR_FORMAT: Record<string, string> = {
  timestamp: "datetime",
  integer: "number",
  decimal: "number",
  boolean: "boolean",
  binary: "binary",
};

function stringFormat(name: string): string {
  if (LINK_SUFFIXES.some((s) => name.toLowerCase().endsWith(s))) return "link";
  if (PROSE.has(name)) return "prose";
  return BADGE.has(name) ? "badge" : "text";
}

/** The format a property shows in when none is declared (CONTRACT-010, Defaults). */
export function defaultFormat(p: Prop): string {
  if (!p.scalar) return "json";
  if (p.cardinality === "many") return p.type === "string" ? "tags" : "json";
  if (p.type === "string") return stringFormat(p.name);
  return SCALAR_FORMAT[p.type] ?? "json";
}

const SUITS: Record<string, string[]> = {
  string: ["text", "prose", "code", "link", "badge", "markdown"],
  timestamp: ["date", "datetime"],
  integer: ["number"],
  decimal: ["number"],
  boolean: ["boolean"],
};

/** Whether `fmt` can show the property's type. */
export function formatSuits(p: Prop, fmt: string): boolean {
  if (!p.scalar) return fmt === "json";
  if (p.cardinality === "many") return p.type === "string" ? fmt === "tags" : fmt === "json";
  return (SUITS[p.type] ?? []).includes(fmt);
}

/** A single-valued string: what a search can match. */
export const isSearchableType = (p: Prop): boolean =>
  p.scalar && p.type === "string" && p.cardinality !== "many";

const nonKey = (t: EntityType) => t.properties.filter((p) => p.name !== t.key);

function defaultTitle(t: EntityType): string {
  for (const n of TITLE_NAMES) {
    const p = propertyOf(t, n);
    if (p && p.name !== t.key) return `{${n}}`;
  }
  const first = nonKey(t).find(isSearchableType);
  return `{${first ? first.name : t.key}}`;
}

function defaultSummary(t: EntityType, title: string): string | null {
  const used = placeholders(title);
  for (const n of SUMMARY_NAMES)
    if (propertyOf(t, n) && !used.includes(n) && n !== t.key) return `{${n}}`;
  return null;
}

function defaultSearch(t: EntityType, title: string, summary: string | null): string[] {
  const chosen: string[] = [];
  const add = (name: string) => {
    const p = propertyOf(t, name);
    if (p && isSearchableType(p) && !chosen.includes(name)) chosen.push(name);
  };
  for (const n of placeholders(title)) add(n);
  add(t.key);
  for (const n of placeholders(summary ?? "")) add(n);
  for (const n of SEARCH_TAIL) add(n);
  return chosen.slice(0, MAX_SEARCH);
}

function resolveSections(t: EntityType, declared: DeclaredSection[] | undefined, used: string[]) {
  if (declared === undefined) {
    const rest = nonKey(t)
      .map((p) => p.name)
      .filter((n) => !used.includes(n));
    return rest.length ? [{ label: "Details", properties: rest, collapsed: false }] : [];
  }
  const placed = new Set(declared.flatMap((s) => s.properties));
  const out = declared.map((s) => ({
    label: s.label,
    properties: s.properties,
    collapsed: s.collapsed,
  }));
  const more = nonKey(t)
    .map((p) => p.name)
    .filter((n) => !placed.has(n) && !used.includes(n));
  if (more.length) out.push({ label: "More", properties: more, collapsed: false });
  return out;
}

function fieldView(t: string, p: Prop, terms: Map<string, FieldTerms>): ResolvedView["fields"][0] {
  const ft = terms.get(fieldKey(t, p.name)) ?? {};
  const format = ft.format || defaultFormat(p);
  const tones = ft.tones !== undefined && format === "badge" ? { ...ft.tones } : null;
  return {
    property: p.name,
    label: ft.label || splitWords(p.name),
    format,
    hideWhenEmpty: ft.hideWhenEmpty === true,
    tones,
  };
}

function relationshipViews(
  m: ModuleModel,
  t: EntityType,
  terms: Map<string, RelationshipTerms>,
): ResolvedView["relationships"] {
  const out: ResolvedView["relationships"] = [];
  for (const r of m.relationships) {
    const rt = terms.get(r.name) ?? {};
    const order = rt.order ?? 50;
    const hideWhenEmpty = rt.hideWhenEmpty === true;
    if (r.source.includes(t.name))
      out.push({ field: r.name, label: rt.label || splitWords(r.name), hideWhenEmpty, order });
    if (r.inverse && r.target.includes(t.name))
      out.push({
        field: r.inverse,
        label: rt.inverseLabel || splitWords(r.inverse),
        hideWhenEmpty,
        order,
      });
  }
  return out;
}

function resolveType(
  m: ModuleModel,
  t: EntityType,
  position: number,
  d: DeclaredView,
): ResolvedView {
  const rt = d.records.get(t.local) ?? {};
  const title = rt.title ?? defaultTitle(t);
  const summary = rt.summary ?? defaultSummary(t, title);
  const used = [...placeholders(title), ...placeholders(summary ?? "")];
  const search = rt.search ?? defaultSearch(t, title, summary);
  const declared =
    Object.keys(rt).length > 0 ||
    [...d.fields.keys()].some((k) => k.startsWith(`${t.local}\u0000`));
  const label = rt.label || splitWords(t.local);
  return {
    declared,
    label,
    pluralLabel: rt.pluralLabel || pluralize(label),
    icon: rt.icon || "circle",
    tone: rt.tone || (TONES[position % TONES.length] as string),
    title,
    summary,
    sections: resolveSections(t, rt.sections, used),
    search: [...search],
    fields: t.properties.map((p) => fieldView(t.local, p, d.fields)),
    relationships: relationshipViews(m, t, d.relationships),
  };
}

/** The module's resolved view: every type's declared terms merged with the defaults. */
export function resolve(m: ModuleModel, declared: DeclaredView = emptyView()): ResolvedModule {
  const types = new Map<string, ResolvedView>();
  m.entityTypes.forEach((t, i) => {
    types.set(t.local, resolveType(m, t, i, declared));
  });
  return {
    module: { title: declared.title || m.name, description: declared.description ?? null },
    types,
  };
}
