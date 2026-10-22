// SPDX-License-Identifier: MIT OR Apache-2.0
// Wire types for CONTRACT-009 (operate) and CONTRACT-006 (console GraphQL). Written by hand from
// ui/openapi.json and src/arras/operate/; the build does not need Python.

export const SUPPORTED_OPERATE_VERSION = 2;

export interface Versions {
  contracts: { interface: number; actions: number; console: number; operate: number };
}

/** One module's registered UMF document in the viewer's catalog (CONTRACT-009, GET explorer/schema-catalog.json). */
export interface SchemaCatalogEntry {
  /** `arras:<module>` */
  id: string;
  title: string;
  category: string;
  path: string;
  /** The document exactly as registered. */
  text: string;
  format: string;
  description: string;
  /** `umf` for a registered document; `json-schema` for a note entry that says why it is not shown. */
  schemaFormat: string;
}

/** The modules this viewer may read, each with its registered document; never entity data. */
export interface SchemaCatalog {
  version: number;
  entries: SchemaCatalogEntry[];
}

/** The module's revision as received: an object keyed by backend name (`{memory: 3}`); sent back unchanged. */
export type Revision = Record<string, number | null>;

export interface InputSpec {
  name: string;
  type: string;
  kind: "scalar" | "record" | "ref";
  cardinality: "one" | "optional" | "many";
}
export interface PropertyInfo {
  name: string;
  type: string;
  required: boolean;
  cardinality: string;
}
export interface BackendCapabilities {
  read?: boolean;
  columns?: string[];
  relationships?: string[];
  count?: boolean;
  mutable?: boolean;
  latency_class?: string;
  /** CONTRACT-010: the text match this backend serves for the type. */
  search?: "none" | "substring";
  searchable?: string[];
}
export interface EntityTypeInfo {
  name: string;
  key: string;
  properties: PropertyInfo[];
  capabilities: Record<string, BackendCapabilities>;
  /** The resolved view (CONTRACT-010); every meta read carries it. */
  view?: TypeView;
}
export interface RelationshipInfo {
  name: string;
  source: string[];
  target: string[];
  sourceMultiplicity: string;
  targetMultiplicity: string;
  lifecycle: string;
  inverse: string | null;
}
export interface PreconditionDecl {
  id: string;
  reason: string;
  op?: string;
  args?: unknown;
}
export interface EffectDecl {
  op: string;
  type?: string | null;
  alias?: string | null;
  [k: string]: unknown;
}
export interface ActionInfo {
  name: string;
  description: string;
  inputSpecs: InputSpec[];
  preconditions: PreconditionDecl[];
  effects: EffectDecl[];
}
export interface ModuleInfo {
  name: string;
  /** The reader that is the system of record: it serves LATEST and holds the document. */
  record: string;
  replicas: string[];
  /** Action name to the backend that runs it; an action not listed runs on the record store. */
  providers: Record<string, string>;
  revision: Revision;
  entityTypes: EntityTypeInfo[];
  relationships: RelationshipInfo[];
  actions: ActionInfo[];
  view?: ModuleView;
}
export interface BackendStatus {
  backend: string;
  available: boolean;
  reason: string | null;
  position: string | null;
  lag: string | null;
}
export interface MetaData {
  modules: ModuleInfo[];
  status: BackendStatus[];
}

export type Consistency = "LATEST" | "BULK";
export interface Freshness {
  backend: string;
  asOf: string;
  at: string;
  consistency: string;
}
export interface Ref {
  module: string;
  type: string;
  key: string;
  target?: Record<string, unknown> | null;
}

// -- CONTRACT-009 ---------------------------------------------------------------------------

export interface Violation {
  path: string;
  code: string;
  message: string;
}
export interface Failure {
  id: string;
  reason: string;
}
export interface EntityRef {
  type: string;
  key: string;
  generated?: boolean;
}
export type Effect =
  | { kind: "create"; ref: EntityRef; properties: Record<string, unknown> }
  | { kind: "update"; ref: EntityRef; set: Record<string, unknown>; unset: string[] }
  | { kind: "delete"; ref: EntityRef }
  | { kind: "link" | "unlink"; relationship: string; source: EntityRef; target: EntityRef };
export interface Receipt {
  action: string;
  refs: { type: string; key: string; version: number }[];
  created: number;
  updated: number;
  deleted: number;
  linked: number;
  unlinked: number;
  token: string | null;
  group: string | null;
  replayed: boolean;
}
export interface Validation {
  ok: boolean;
  violations: Violation[];
  failures: Failure[];
  effects: Effect[];
  replay: Receipt | null;
  freshness: Freshness | null;
}
export interface ErrorBody {
  type: string;
  message: string;
  reason?: string;
  backend?: string;
  operation?: string;
  violations?: Violation[];
  failures?: Failure[];
  [k: string]: unknown;
}
export type BatchItem = { index: number; receipt: Receipt } | { index: number; refusal: ErrorBody };
export interface BatchReceipt {
  action: string;
  atomic: boolean;
  items: BatchItem[];
  succeeded: number;
  failed: number;
  token: string | null;
}
export interface ActionRequest {
  inputs: Record<string, unknown>;
  idempotency_key?: string;
  expected_revision?: Revision;
}
export interface BatchRequest {
  items: Record<string, unknown>[];
  atomic?: boolean;
  stop_on_error?: boolean;
  idempotency_key?: string;
  expected_revision?: Revision;
}
export interface ChangeOp {
  kind: string;
  type?: string;
  key?: string;
  version?: number;
  relationship?: string;
  source?: { type: string; key: string };
  target?: { type: string; key: string };
}
export interface Change {
  group: string;
  at: string;
  by: string;
  action: string;
  module: string;
  ops: ChangeOp[];
  backend: string;
}
export interface Load {
  load_id: string;
  initiated_by: string;
  at: string;
  module: string;
  created: number;
  skipped: number;
  rejected: number;
  /** The counts are of the chunks a backend could show, not of the whole load. */
  partial?: boolean;
}
export interface Page<T> {
  items: T[];
  nextCursor: string | null;
  truncated: boolean;
  freshness: Freshness | null;
}
export interface ChangesQuery {
  module?: string;
  type?: string;
  key?: string;
  by?: string;
  action?: string;
  group?: string;
  since?: string;
  until?: string;
  limit?: number;
  after?: string;
  /** Whose journal: a backend that applies the module's actions (default: its record store). */
  provider?: string;
}

// -- CONTRACT-009 `POST /query` (one Weft statement over a named module, CONTRACT-001) ------------------

/** The bound on the text, in characters; the server answers 400 for more. */
export const QUERY_MAX_CHARS = 4000;
/** The most rows one page of an answer holds. */
export const QUERY_MAX_LIMIT = 100;
export type QueryConsistency = "latest" | "bulk";
export interface QueryColumn {
  name: string;
  /** False for a column holding a list (the keys of a relationship's far end). */
  scalar: boolean;
  /** `string`, `integer`, `decimal`, `boolean`, `timestamp`, or `keys` for a relationship. */
  type: string;
}
/** The body of `POST /query`. The text travels here and nowhere else: never a URL, a log or storage. */
export interface QueryRequest {
  /** The module the statement reads (CONTRACT-001): its types are the only ones it may name. */
  module: string;
  /** One read-only Weft statement; a page is its own (`ORDER BY` the key, `LIMIT`, a keyset predicate). */
  sql: string;
  params?: Record<string, unknown>;
  consistency?: QueryConsistency;
  at_least?: string;
  /** 1 to 100 (default 50): Arras's cap; `truncated` says it cut the rows. */
  limit?: number;
}
/** A grid: one column per selected column, a row an object by column name with JSON values (a decimal, timestamp or 64-bit integer as text). */
export interface QueryResult {
  columns: QueryColumn[];
  rows: Record<string, unknown>[];
  truncated: boolean;
  /** Its `consistency` is lower case (`latest`, `bulk`), unlike the GraphQL reads'. */
  freshness: Freshness | null;
  revision: Revision;
}

// -- CONTRACT-011 (schema administration surface) ---------------------------------------------

/** The schema surface's contract version this console speaks; import is offered only for this one. */
export const SUPPORTED_SCHEMA_VERSION = 1;

export interface SchemaVersions {
  contracts: { schema: number };
}
/** The values CONTRACT-011 gives `SchemaChange.kind` and `.element`; the drift guard checks a real plan against them. */
export const SCHEMA_CHANGE_KINDS = ["added", "changed", "retired"] as const;
export const SCHEMA_CHANGE_ELEMENTS = ["type", "property", "relationship", "action"] as const;
export type SchemaChangeKind = (typeof SCHEMA_CHANGE_KINDS)[number];
export type SchemaChangeElement = (typeof SCHEMA_CHANGE_ELEMENTS)[number];
/** One element a registration would add, change or retire; `detail` carries no record value. */
export interface SchemaChange {
  kind: SchemaChangeKind;
  element: SchemaChangeElement;
  /** Module-qualified, for example `catalog.Solution.notes`. */
  name: string;
  detail: string;
}
/** What `POST validate` answers: what a registration would change and what would refuse it, nothing applied. */
export interface SchemaPlan {
  module: string;
  ok: boolean;
  violations: Violation[];
  /** False when the document's derived rows equal those in force. */
  changed: boolean;
  /** The module's current revision; null for a module the record store does not yet hold. */
  revision: Revision | null;
  changes: SchemaChange[];
  report: string[];
}
/** What `POST register` answers. */
export interface RegistryResult {
  module: string;
  revision: Revision | null;
  changed: boolean;
  report: string[];
}
export interface SchemaRequest {
  /** The UMF text, at most 1 MiB. */
  document: string;
  unknown_endpoint?: "reject" | "provisional";
  /** The `revision` a plan answered with: a store that has moved on answers 409. */
  expected_revision?: Revision;
}

// -- CONTRACT-010: the resolved view, the viewer's modes and the search read -------------------

export interface ModuleView {
  title: string;
  description: string | null;
}
export interface ViewSection {
  label: string;
  properties: string[];
  collapsed: boolean;
}
export interface FieldView {
  property: string;
  label: string;
  format: string;
  hideWhenEmpty: boolean;
  tones: Record<string, string> | null;
}
export interface RelationshipView {
  field: string;
  label: string;
  hideWhenEmpty: boolean;
  order: number;
}
export interface TypeView {
  declared: boolean;
  label: string;
  /** The type where it names a collection (a list, a chip, a card, a crumb). */
  pluralLabel: string;
  icon: string;
  tone: string;
  title: string;
  summary: string | null;
  sections: ViewSection[];
  search: string[];
  fields: FieldView[];
  relationships: RelationshipView[];
}

/** `GET {operate}/viewer`: who the host says is asking and which modes it offers. */
export interface Viewer {
  user: string;
  modes: ("user" | "admin")[];
}

export interface SearchSegment {
  text: string;
  mark: boolean;
}
export interface SearchHit {
  type: string;
  key: string;
  score: number;
  label: string;
  excerpt: SearchSegment[] | null;
  matched: string[];
  entity: Record<string, unknown>;
}
export interface SearchCount {
  type: string;
  count: number;
  atLeast: boolean;
}
export interface NotSearched {
  type: string;
  reason: "no_searchable_property" | "no_capability" | "unavailable" | "over_budget" | string;
  backend: string | null;
}
export interface SearchPage {
  text: string;
  hits: SearchHit[];
  counts: SearchCount[];
  notSearched: NotSearched[];
  truncated: boolean;
  freshness: Freshness[];
}

/** One page of `POST /export` (CONTRACT-009): records of the shapes `import_records` takes. */
export interface ExportPage {
  items: Record<string, unknown>[];
  nextCursor: string | null;
  /** Types the viewer could not be given; a page with any is not the whole graph. */
  omitted: string[];
  freshness: Freshness | null;
}
