// SPDX-License-Identifier: MIT OR Apache-2.0
// The closed vocabulary `arras.view` 0.1.0 for the static read-only profile (CONTRACT-010 A and B, CONTRACT-012):
// its names, limits, and the types for what a document declares and what a view resolves to. A port of the
// constants and dataclasses of `arras/view.py`.
export const VOCABULARY = "arras.view";
export const VERSION = "0.1.0";

export const ICONS = [
  "box",
  "package",
  "puzzle",
  "file-text",
  "folder",
  "user",
  "users",
  "building",
  "tag",
  "flag",
  "alert",
  "check-circle",
  "clock",
  "calendar",
  "link",
  "globe",
  "wrench",
  "scale",
  "book",
  "chart",
  "shield",
  "star",
  "bolt",
  "circle",
] as const;
export const TONES = ["slate", "blue", "teal", "green", "amber", "red", "violet", "rose"] as const;
export const FORMATS = [
  "text",
  "prose",
  "code",
  "link",
  "badge",
  "tags",
  "date",
  "datetime",
  "number",
  "boolean",
  "json",
] as const;

export const MODULE_TERMS = ["title", "description"];
export const RECORD_TERMS = [
  "label",
  "pluralLabel",
  "icon",
  "tone",
  "title",
  "summary",
  "sections",
  "search",
];
export const FIELD_TERMS = ["label", "format", "hideWhenEmpty", "tones"];
export const RELATIONSHIP_TERMS = ["label", "inverseLabel", "hideWhenEmpty", "order"];
export const SECTION_TERMS = ["label", "properties", "collapsed"];
export const RELATIONSHIP_ONLY = ["inverseLabel", "order"];

export const MAX_MODULE_TITLE = 80;
export const MAX_MODULE_DESCRIPTION = 280;
export const MAX_LABEL = 60;
export const MAX_TEMPLATE = 200;
export const MAX_SECTIONS = 8;
export const MAX_SECTION_PROPERTIES = 24;
export const MAX_SEARCH = 8;
export const MAX_TONES = 24;
export const MAX_RECORD_BYTES = 16 * 1024;
export const MAX_DOCUMENT_BYTES = 128 * 1024;

export const TITLE_NAMES = ["name", "title", "label"];
export const SUMMARY_NAMES = ["summary", "description", "statement", "problem", "notes"];
export const SEARCH_TAIL = ["description", "statement", "problem", "notes"];
export const PROSE = new Set(
  "summary description statement problem notes prompt workflow caveat rationale".split(" "),
);
export const BADGE = new Set("status state kind level".split(" "));
export const LINK_SUFFIXES = ["url", "uri", "link"];

export type Obj = Record<string, unknown>;
export const isObj = (v: unknown): v is Obj =>
  typeof v === "object" && v !== null && !Array.isArray(v);
export const obj = (v: unknown): Obj => (isObj(v) ? v : {});
export const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
export const chars = (s: string) => Array.from(s).length;

// -- declared and resolved views ---------------------------------------------------------------

export interface DeclaredSection {
  label: string;
  properties: string[];
  collapsed: boolean;
}
export interface RecordTerms {
  label?: string;
  pluralLabel?: string;
  icon?: string;
  tone?: string;
  title?: string;
  summary?: string;
  sections?: DeclaredSection[];
  search?: string[];
}
export interface FieldTerms {
  label?: string;
  format?: string;
  hideWhenEmpty?: boolean;
  tones?: Record<string, string>;
}
export interface RelationshipTerms {
  label?: string;
  inverseLabel?: string;
  hideWhenEmpty?: boolean;
  order?: number;
}
export interface DeclaredView {
  title?: string;
  description?: string;
  records: Map<string, RecordTerms>;
  fields: Map<string, FieldTerms>;
  relationships: Map<string, RelationshipTerms>;
}
export const emptyView = (): DeclaredView => ({
  records: new Map(),
  fields: new Map(),
  relationships: new Map(),
});
export const fieldKey = (type: string, prop: string) => `${type}\u0000${prop}`;

export interface ResolvedView {
  declared: boolean;
  label: string;
  pluralLabel: string;
  icon: string;
  tone: string;
  title: string;
  summary: string | null;
  sections: { label: string; properties: string[]; collapsed: boolean }[];
  search: string[];
  fields: {
    property: string;
    label: string;
    format: string;
    hideWhenEmpty: boolean;
    tones: Record<string, string> | null;
  }[];
  relationships: { field: string; label: string; hideWhenEmpty: boolean; order: number }[];
}
export interface ResolvedModule {
  module: { title: string; description: string | null };
  types: Map<string, ResolvedView>;
}
