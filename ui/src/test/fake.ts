// SPDX-License-Identifier: MIT OR Apache-2.0
// A fetch double that answers with the wire shapes of src/arras/operate/ (CONTRACT-009) and the
// console GraphQL surface (CONTRACT-006). It is tied to the real server by the drift guard
// (src/integration/drift.int.test.ts): every shape exported in `wire` below, and what `FakeApi`
// answers for the meta, list, by-key and follow queries, is compared key for key with the real dev
// host's answer to the same call. Change a shape here only together with that test.

import { vi } from "vitest";
import type {
  BackendStatus,
  BatchReceipt,
  Change,
  EffectDecl,
  EntityTypeInfo,
  ErrorBody,
  Load,
  MetaData,
  ModuleInfo,
  Page,
  QueryColumn,
  QueryResult,
  Receipt,
  RegistryResult,
  SchemaCatalog,
  SchemaPlan,
  SchemaVersions,
  TypeView,
  Validation,
} from "../api/types";
import { defined } from "./defined";

/** The variables of a recorded GraphQL request (a given call carries only some of them). */
interface GqlVars {
  filter: Record<string, string>;
  limit: number;
  /** A list's next page: the entities after this key (CONTRACT-006). */
  afterKey: string;
  consistency: string;
  key: string;
}

/** A recorded request body: the fields the tests read from any wire call (a given call carries only some). */
interface Body extends GqlVars {
  query: string;
  variables: GqlVars;
  inputs: Record<string, unknown>;
  items: unknown[];
  atomic: boolean;
  expected_revision: unknown;
  idempotency_key: string;
  /** The journal's own cursor (`changes` and `loads`). */
  after: string;
  provider: string;
  group: string;
  by: string;
  module: string;
  action: string;
  since: string;
  until: string;
  type: string;
  key: string;
  sql: string;
  at_least: string;
  params: Record<string, unknown>;
  document: string;
  unknown_endpoint: string;
}

export interface Recorded {
  method: string;
  url: string;
  path: string;
  headers: Record<string, string>;
  body: Body;
}
type Reply = { status?: number; body?: unknown; headers?: Record<string, string> };
export type Handler = (req: Recorded) => Reply | undefined | Promise<Reply | undefined>;

export const json = (
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Reply => ({ status, body, headers });
export const err = (
  status: number,
  error: Record<string, unknown>,
  headers: Record<string, string> = {},
) => json(status, { error }, headers);

export const REV = { memory: 1 } as const;

/** A resolved view (CONTRACT-010 B) as the meta read answers it; the browser's double builds its views the same way. */
export const view = (
  over: Partial<TypeView> & Pick<TypeView, "label" | "icon" | "tone" | "title">,
): TypeView => ({
  declared: true,
  pluralLabel: `${over.label}s`,
  summary: null,
  sections: [],
  search: [],
  fields: [],
  relationships: [],
  ...over,
});

const cap = (mutable: boolean, rel: string, extra: string) => ({
  read: true,
  columns: ["code", "name"],
  relationships: [rel],
  count: true,
  mutable,
  latency_class: mutable ? "interactive" : "batch",
  search: "substring" as const,
  searchable: ["code", "name", extra],
});

/** A declared effect as the meta query answers it: every field present, null when unused. */
export const decl = (over: Partial<EffectDecl>): EffectDecl => ({
  op: "update",
  alias: null,
  type: null,
  ref_type: null,
  key: null,
  source: null,
  target: null,
  properties: {},
  unset: [],
  over: null,
  body: [],
  ...over,
});

export function catalog(overrides: Partial<ModuleInfo> = {}): ModuleInfo {
  return {
    name: "catalog",
    record: "memory",
    replicas: ["memory_replica"],
    providers: {},
    revision: { ...REV },
    entityTypes: [
      {
        name: "catalog.UseCase",
        key: "code",
        properties: [
          { name: "code", type: "string", required: true, cardinality: "one" },
          { name: "name", type: "string", required: true, cardinality: "one" },
          { name: "workArea", type: "string", required: false, cardinality: "optional" },
        ],
        capabilities: {
          memory: cap(true, "addressedBy", "workArea"),
          memory_replica: cap(false, "addressedBy", "workArea"),
        },
        view: view({ label: "Use case", icon: "book", tone: "violet", title: "{name}" }),
      },
      {
        name: "catalog.Solution",
        key: "code",
        properties: [
          { name: "code", type: "string", required: true, cardinality: "one" },
          { name: "name", type: "string", required: true, cardinality: "one" },
          { name: "coverageLevel", type: "string", required: false, cardinality: "optional" },
        ],
        capabilities: {
          memory: cap(true, "addresses", "coverageLevel"),
          memory_replica: cap(false, "addresses", "coverageLevel"),
        },
        view: view({ label: "Solution", icon: "puzzle", tone: "blue", title: "{name}" }),
      },
    ],
    relationships: [
      {
        name: "addresses",
        source: ["catalog.Solution"],
        target: ["catalog.UseCase"],
        sourceMultiplicity: "0..*",
        targetMultiplicity: "0..*",
        lifecycle: "independent",
        inverse: "addressedBy",
      },
    ],
    actions: [
      {
        name: "catalog.CorrectSolution",
        description: "Correct a solution's coverage level",
        inputSpecs: [
          { name: "solution", type: "Solution", kind: "ref", cardinality: "one" },
          { name: "level", type: "string", kind: "scalar", cardinality: "one" },
        ],
        preconditions: [
          {
            id: "exists",
            reason: "no such solution",
            op: "exists",
            args: { ref: { name: "solution" } },
          },
        ],
        effects: [
          decl({
            op: "update",
            ref_type: "Solution",
            key: { name: "solution" },
            properties: { coverageLevel: { name: "level" } },
          }),
        ],
      },
      {
        name: "catalog.Typed",
        description: "Every input type",
        inputSpecs: [
          { name: "count", type: "integer", kind: "scalar", cardinality: "one" },
          { name: "amount", type: "decimal", kind: "scalar", cardinality: "optional" },
          { name: "active", type: "boolean", kind: "scalar", cardinality: "optional" },
          { name: "when", type: "timestamp", kind: "scalar", cardinality: "optional" },
          { name: "tags", type: "string", kind: "scalar", cardinality: "many" },
          { name: "useCases", type: "UseCase", kind: "ref", cardinality: "many" },
          { name: "terms", type: "Terms", kind: "record", cardinality: "optional" },
        ],
        preconditions: [],
        effects: [],
      },
    ],
    ...overrides,
  };
}

export const STATUS = [
  { backend: "memory", available: true, reason: null, position: "fake:3", lag: null },
  { backend: "memory_replica", available: true, reason: null, position: "fake:3", lag: "0.0" },
];

export const FRESH = {
  backend: "memory",
  asOf: "fake:3",
  at: "2026-10-10T02:47:09+00:00",
  consistency: "LATEST",
};

export const receipt = (over: Partial<Receipt> = {}): Receipt => ({
  action: "catalog.CorrectSolution",
  refs: [{ type: "catalog.Solution", key: "sol-1", version: 2 }],
  created: 0,
  updated: 1,
  deleted: 0,
  linked: 0,
  unlinked: 0,
  token: "fake:4",
  group: "g-4",
  replayed: false,
  ...over,
});

export const validation = (over: Partial<Validation> = {}): Validation => ({
  ok: true,
  violations: [],
  failures: [],
  effects: [
    {
      kind: "update",
      ref: { type: "catalog.Solution", key: "sol-1", generated: false },
      set: { coverageLevel: "partial" },
      unset: [],
    },
  ],
  replay: null,
  freshness: { ...FRESH, consistency: "latest" },
  ...over,
});

const page = <T>(items: T[], nextCursor: string | null = null): Page<T> => ({
  items,
  nextCursor,
  truncated: false,
  freshness: { ...FRESH, consistency: "latest" },
});

/**
 * The bodies the real server answers, one per call and error. The unit tests answer with these and
 * the drift guard checks each against the dev host. Error bodies are the `error` member's contents.
 */
export const wire = {
  version: () => ({ contracts: { interface: 2, actions: 1, console: 2, operate: 2 } }),
  /** GET explorer/schema-catalog.json: each module the viewer reads, its document as registered. */
  schemaCatalog: (): SchemaCatalog => ({
    version: 1,
    entries: [
      {
        id: "arras:catalog",
        title: "catalog",
        category: "domain",
        path: "catalog.umf.json",
        text: '{\n  "umf": "1.0",\n  "module": "catalog"\n}\n',
        format: "json",
        description:
          "Registered at revision memory 1; record store memory; replicas memory_replica.",
        schemaFormat: "umf",
      },
    ],
  }),
  validation,
  /** validate of incomplete inputs: 200, not ok, a violation, no effects and no freshness. */
  invalidValidation: (): Validation => ({
    ok: false,
    violations: [{ path: "inputs.level", code: "required", message: "a value is required" }],
    failures: [],
    effects: [],
    replay: null,
    freshness: null,
  }),
  receipt,
  /** POST /query: a grid. `freshness.consistency` is lower case here (unlike the GraphQL reads'). */
  queryResult: (over: Partial<QueryResult> = {}): QueryResult => ({
    columns: [
      { name: "code", scalar: true, type: "string" },
      { name: "name", scalar: true, type: "string" },
    ],
    rows: [
      { code: "uc-pipeline", name: "Pipeline mapping" },
      { code: "uc-alerts", name: "Alert review" },
    ],
    truncated: false,
    freshness: { ...FRESH, consistency: "latest" },
    revision: { ...REV },
    ...over,
  }),
  batch: (over: Partial<BatchReceipt> = {}): BatchReceipt => ({
    action: "catalog.AddUseCase",
    atomic: false,
    items: [
      {
        index: 0,
        receipt: receipt({
          action: "catalog.AddUseCase",
          refs: [{ type: "catalog.UseCase", key: "b-1", version: 1 }],
          created: 1,
          updated: 0,
        }),
      },
      { index: 1, refusal: wire.precondition() },
    ],
    succeeded: 1,
    failed: 1,
    token: "fake:5",
    ...over,
  }),
  change: (over: Partial<Change> = {}): Change => ({
    group: "g-4",
    at: "2026-10-09T14:02:11+00:00",
    by: "ana",
    action: "catalog.CorrectSolution",
    module: "catalog",
    ops: [{ kind: "update", type: "catalog.Solution", key: "sol-1", version: 2 }],
    backend: "memory",
    ...over,
  }),
  load: (over: Partial<Load> = {}): Load => ({
    load_id: "ld-1",
    initiated_by: "root",
    at: "2026-10-01T10:00:00+00:00",
    module: "catalog",
    created: 5,
    skipped: 1,
    rejected: 0,
    ...over,
  }),
  page,
  // -- error bodies (the contents of `{error: ...}`)
  invalid: (): ErrorBody => ({
    type: "Invalid",
    message: "invalid request",
    violations: [{ path: "inputs.level", code: "required", message: "a value is required" }],
  }),
  badRequest: (message = "since needs an offset (RFC 3339)"): ErrorBody => ({
    type: "BadRequest",
    message,
  }),
  refused: (operation = "apply"): ErrorBody => ({
    type: "Refused",
    message: "no access",
    backend: "memory",
    operation,
    reason: "no_access",
  }),
  /** A host's authorize_action said no (CONTRACT-009): no reason, no backend. */
  notOffered: (): ErrorBody => ({ type: "Refused", message: "not offered" }),
  notFound: (): ErrorBody => ({ type: "NotFound", message: "no such module or action" }),
  conflict: (): ErrorBody => ({
    type: "Conflict",
    message: "conflict (revision)",
    reason: "revision",
  }),
  precondition: (): ErrorBody => ({
    type: "PreconditionFailed",
    message: "a precondition failed",
    failures: [{ id: "fresh", reason: "a use case with that code exists" }],
  }),
  /** A query that does not parse or names something it may not: 400, every violation listed (the text is never echoed). */
  invalidQuery: (): ErrorBody => ({
    type: "Invalid",
    message: "invalid request",
    violations: [{ path: "sql", code: "syntax", message: "expected '.', found 'FROM'" }],
  }),
  /** A module the viewer cannot read, or none such: 404 with the violation of an unknown module. */
  unknownModule: (name = "catalog"): ErrorBody => ({
    type: "Invalid",
    message: "invalid request",
    violations: [{ path: "sql", code: "unknown_type", message: `no module '${name}'` }],
  }),

  /** A construct the backend does not serve: 501 naming it and the supported shapes. */
  unsupportedQuery: (): ErrorBody => ({
    type: "Unsupported",
    message: "not supported",
    construct: "filter workArea (optional string)",
    supported: [
      "a filter is on a required, single-valued string, integer, decimal or boolean",
      "SELECT alias.* FROM module.Type alias [WHERE alias.field = literal AND ...]",
    ],
  }),
  unavailable: (backend = "memory", reason = "unreachable"): ErrorBody => ({
    type: "Unavailable",
    message: `${backend} is unavailable (${reason})`,
    backend,
    reason,
  }),
  /** 501 from `changes` on a module whose record store keeps no journal. Not reachable in the sandbox
   * (no module whose record store keeps no journal); written from serialize.error_body and checked against openapi.json. */
  unsupported: (): ErrorBody => ({
    type: "Unsupported",
    message: "not supported",
    construct: "changes",
    supported: ["a journal"],
  }),
  tokenExpired: (operation = "catalog"): ErrorBody => ({
    type: "Refused",
    message: "sign in again",
    backend: "memory",
    operation,
    reason: "token_expired",
  }),
  /** No person at all (principal_for_request answered None). */
  signIn: (): ErrorBody => ({ type: "Refused", message: "sign in" }),
  tooMany: (): ErrorBody => ({ type: "TooManyRequests", message: "too many requests" }),
  // -- GraphQL bodies (whole responses)
  gqlNotFound: () => ({
    errors: [{ message: "no such module", extensions: { code: "NOT_FOUND" } }],
  }),
  gqlSignIn: () => ({ errors: [{ message: "sign in", extensions: { code: "REFUSED" } }] }),
  /** An expired token on either GraphQL path: 401 with the reason (CONTRACT-006). */
  gqlExpired: () => ({
    errors: [
      { message: "sign in again", extensions: { code: "REFUSED", reason: "token_expired" } },
    ],
  }),
  /** The same refusal reported on a field inside a 200 (what the server answered before the 401 fix,
   * and what a field refused mid-query looks like); the client treats it as a sign-in too. */
  gqlExpiredField: (field = "modules") => ({
    data: null,
    errors: [
      {
        message: "memory refused catalog",
        extensions: { code: "REFUSED", backend: "memory", reason: "token_expired" },
        path: [field],
        locations: [{ line: 1, column: 3 }],
      },
    ],
    extensions: {},
  }),
  gqlUnavailable: (field: string) => ({
    data: { [field]: null },
    errors: [
      {
        message: "memory unavailable (unreachable): memory cannot serve query",
        extensions: { code: "UNAVAILABLE", backend: "memory", reason: "unreachable" },
        path: [field],
        locations: [{ line: 1, column: 3 }],
      },
    ],
    extensions: { revision: { ...REV } },
  }),
};

/**
 * The schema administration surface's bodies (CONTRACT-011), one per call and error, as the dev host answers
 * them. Kept apart from `wire` so the operate drift guard is unchanged; `schema-drift.int.test.ts` compares
 * each with the real dev host and `schemaWire`'s own list must be covered there.
 */
export const schemaWire = {
  version: (): SchemaVersions => ({ contracts: { schema: 1 } }),
  /** A compatible edit: one optional property added to a type. */
  plan: (over: Partial<SchemaPlan> = {}): SchemaPlan => ({
    module: "catalog",
    ok: true,
    violations: [],
    changed: true,
    revision: { ...REV },
    changes: [
      {
        kind: "added",
        element: "property",
        name: "catalog.UseCase.notes",
        detail: "optional string",
      },
    ],
    report: [],
    ...over,
  }),
  /** A document equal in meaning to the one in force. */
  planUnchanged: (): SchemaPlan => schemaWire.plan({ changed: false, changes: [] }),
  /** A required property while records exist: an answer (200) with `ok: false`, naming the rule and the count. */
  planIncompatible: (): SchemaPlan =>
    schemaWire.plan({
      ok: false,
      violations: [
        {
          path: "types.catalog.UseCase.notes",
          code: "incompatible_change",
          message: "cannot add a required property while 14 records exist",
        },
      ],
      changes: [
        {
          kind: "added",
          element: "property",
          name: "catalog.UseCase.notes",
          detail: "required string",
        },
        { kind: "changed", element: "action", name: "catalog.AddUseCase", detail: "" },
      ],
    }),
  registryResult: (over: Partial<RegistryResult> = {}): RegistryResult => ({
    module: "catalog",
    revision: { memory: 2 },
    changed: true,
    report: ["accepted", "replicas learn of it through their feed"],
    ...over,
  }),
  // -- error bodies (the contents of `{error: ...}`)
  /** The backend's refusal: the viewer holds no `schema` grant. */
  refused: (): ErrorBody => ({
    type: "Refused",
    message: "no access",
    backend: "memory",
    operation: "validate_register",
    reason: "no_access",
  }),
  /** The host's `authorize_schema` said no: no backend, no reason. */
  notAuthorized: (): ErrorBody => ({ type: "Refused", message: "no access" }),
  /** A document that does not parse (400), every violation listed. */
  invalidDocument: (): ErrorBody => ({
    type: "Invalid",
    message: "invalid request",
    violations: [
      {
        path: "document",
        code: "invalid_document",
        message: "not valid JSON: Expecting value: line 1 column 1 (char 0)",
      },
    ],
  }),
  /** `register` of an incompatible document, or a name or placement the host refuses (400 with the violations). */
  incompatible: (): ErrorBody => ({
    type: "Invalid",
    message: "invalid request",
    violations: [
      {
        path: "types.catalog.UseCase.notes",
        code: "incompatible_change",
        message: "cannot add a required property while 14 records exist",
      },
    ],
  }),
  /** The record store has moved on since the plan (409). */
  conflict: (): ErrorBody => ({
    type: "Conflict",
    message: "conflict (revision)",
    reason: "revision",
  }),
  badRequest: (message = "document is a string"): ErrorBody => ({ type: "BadRequest", message }),
  tokenExpired: (): ErrorBody => ({
    type: "Refused",
    message: "sign in again",
    backend: "memory",
    operation: "validate_register",
    reason: "token_expired",
  }),
};

/** The dev host's own endpoints (`GET /api/people`, `POST /api/dev/control`); compared with the real host in `schema-drift.int.test.ts`. */
export const devWire = {
  people: () => ({
    people: ["alice", "bob", "carol", "dave", "root"],
    roles: ["none", "viewer", "editor", "schema author", "auditor", "maintainer"],
    default: "alice",
  }),
  control: () => ({ ok: true }),
};

// -- the fake's `POST /query`, in small parts ----------------------------------------------------------

const invalidQuery = (path: string, code: string, message: string): ErrorBody => ({
  type: "Invalid",
  message: "invalid request",
  violations: [{ path, code, message }],
});

/** The request's own bounds (CONTRACT-009): a string of at most 4,000 characters, `limit` 1 to 100, `consistency`. */
function checkQueryBody(b: Record<string, unknown>): Reply | undefined {
  if ("after" in b)
    return err(
      400,
      wire.badRequest("a page is the statement's own (ORDER BY, LIMIT, a keyset): no after"),
    );
  if (typeof b.module !== "string" || b.module === "")
    return err(400, wire.badRequest("module is the module the statement reads"));
  if (typeof b.sql !== "string" || b.sql.trim() === "")
    return err(400, wire.badRequest("sql is a string"));
  if (Array.from(b.sql).length > 4000)
    return err(400, wire.badRequest("sql is at most 4000 characters"));
  const limit = b.limit;
  if (
    limit !== undefined &&
    !(Number.isInteger(limit) && Number(limit) >= 1 && Number(limit) <= 100)
  ) {
    return err(400, invalidQuery("limit", "bound", "limit is an integer from 1 to 100"));
  }
  if (b.consistency !== undefined && b.consistency !== "latest" && b.consistency !== "bulk") {
    return err(400, invalidQuery("consistency", "value", "latest or bulk"));
  }
  return undefined;
}

/** A name, bare or a Weft quoted identifier (the console's templates quote every name). */
const ID = '"[A-Za-z_]\\w*"|[A-Za-z_]\\w*';
const SELECT_SHAPE = new RegExp(
  `^\\s*SELECT\\s+(.+?)\\s+FROM\\s+(${ID})\\.(${ID})\\s+(?:AS\\s+)?([A-Za-z_]\\w*)(?:\\s+ORDER\\s+BY\\s+([A-Za-z_]\\w*)\\.(${ID})(?:\\s+ASC)?\\s+LIMIT\\s+(\\d+))?\\s*;?\\s*$`,
  "is",
);
const unquote = (s: string | undefined) => s?.replace(/^"(.*)"$/, "$1");

/** The shapes the tests use: a projection of one type, in key order with a LIMIT (an entity page). */
function parseSelect(sql: string) {
  const m = SELECT_SHAPE.exec(sql);
  if (!m) return undefined;
  return {
    projection: m[1] ?? "",
    module: unquote(m[2]) ?? "",
    short: unquote(m[3]) ?? "",
    alias: m[4] ?? "",
    order: unquote(m[6]),
    limit: m[7] === undefined ? undefined : Number(m[7]),
  };
}

/** The columns named, or `star`; undefined for a projection the fake does not read. */
function resolveProjection(projection: string, alias: string) {
  const names: string[] = [];
  let star = false;
  const one = new RegExp(`^${alias}\\.(\\*|\\w+|"\\w+")$`);
  for (const part of projection.split(",").map((x) => x.trim())) {
    const c = one.exec(part);
    if (!c) return undefined;
    if (c[1] === "*") star = true;
    else names.push(unquote(c[1]) ?? "");
  }
  return { names, star };
}

/** An unknown column is 400; a column that is not a required scalar is 501 (use `alias.*`). */
function checkNames(type: EntityTypeInfo, short: string, names: string[]): Reply | undefined {
  for (const n of names) {
    const p = type.properties.find((x) => x.name === n);
    if (!p)
      return err(400, invalidQuery(`sql.${n}`, "unknown_field", `${short} has no property '${n}'`));
  }
  return undefined;
}

/** `alias.*` is every declared property and the facts the backend appends (CONTRACT-001). */
const QUERY_META = [
  ["_version", "integer"],
  ["_created_by", "string"],
  ["_updated_by", "string"],
  ["_original_author", "string"],
  ["_created_at", "timestamp"],
  ["_updated_at", "timestamp"],
  ["_original_at", "timestamp"],
  ["_load_id", "string"],
] as const;
const ATTRIBUTION: Record<string, string> = {
  _created_by: "createdBy",
  _updated_by: "updatedBy",
  _created_at: "createdAt",
  _updated_at: "updatedAt",
};

function queryColumns(
  type: EntityTypeInfo,
  proj: { names: string[]; star: boolean },
): QueryColumn[] {
  const scalar = (name: string): QueryColumn => ({
    name,
    scalar: true,
    type: type.properties.find((p) => p.name === name)?.type ?? "string",
  });
  if (!proj.star) return proj.names.map(scalar);
  return [
    ...type.properties.map((p) => scalar(p.name)),
    ...QUERY_META.map(([name, t]) => ({ name, scalar: true, type: t })),
  ];
}

function queryValue(row: Record<string, unknown>, name: string): unknown {
  if (name === "_version") return 1;
  if (name in ATTRIBUTION) return row[ATTRIBUTION[name] ?? ""];
  if (name.startsWith("_")) return null;
  const v = row[name];
  return Array.isArray(v) ? (v as { key: string }[]).map((x) => x.key) : v;
}

/** A property with no value has no member in the row (its column is still listed); the `_original_*` facts are null. */
function queryRow(row: Record<string, unknown>, columns: QueryColumn[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const c of columns) {
    const v = queryValue(row, c.name);
    if (v !== undefined && v !== null) out[c.name] = v;
    else if (c.name.startsWith("_")) out[c.name] = null;
  }
  return out;
}

export class FakeApi {
  log: Recorded[] = [];
  modules: ModuleInfo[] = [catalog()];
  versions = { interface: 2, actions: 1, console: 2, operate: 2 };
  status: BackendStatus[] = STATUS;
  /** Does the host mount the schema surface? When false `GET /api/schema/version` is a 404, as when it is not mounted. */
  schemaMounted = true;
  handlers: Handler[] = [];
  /** Rows by type name: a list answers pages of these. */
  rows: Record<string, Record<string, unknown>[]> = {};
  /** Targets by `type:key` for follow queries. */
  targets: Record<string, Record<string, unknown>> = {};

  on(h: Handler) {
    this.handlers.unshift(h);
    return this;
  }

  posts(pattern: RegExp) {
    return this.log.filter((r) => r.method === "POST" && pattern.test(r.path));
  }

  install() {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const path = new URL(url, "http://x").pathname;
        const headers: Record<string, string> = {};
        new Headers(init?.headers).forEach((v, k) => {
          headers[k] = v;
        });
        const rec: Recorded = {
          method: init?.method ?? "GET",
          url,
          path,
          headers,
          body: JSON.parse(init?.body ? String(init.body) : "{}"),
        };
        this.log.push(rec);
        let reply: Reply | undefined;
        for (const h of this.handlers) {
          reply = await h(rec);
          if (reply) break;
        }
        reply ??= this.route(rec);
        const status = reply.status ?? 200;
        return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
          status,
          headers: { "content-type": "application/json", ...reply.headers },
        });
      }),
    );
    return this;
  }

  /** The meta read: the registry (a type's view is answered by the second request), and the views for `declared`. */
  meta(query = ""): MetaData {
    if (query.includes("declared"))
      return {
        modules: this.modules.map((x) => ({
          name: x.name,
          revision: x.revision,
          entityTypes: x.entityTypes.map((t) => ({ name: t.name, view: t.view })),
        })),
      } as unknown as MetaData;
    return {
      modules: this.modules.map((x) => ({
        ...x,
        entityTypes: x.entityTypes.map(({ view: _v, ...t }) => t),
      })),
      status: this.status,
    };
  }

  route(r: Recorded): Reply {
    if (r.path.includes("/api/schema/")) return this.schemaRoute(r);
    if (r.method === "GET" && r.path.endsWith("/viewer"))
      return json(200, { user: "alice", modes: ["user", "admin"] });
    if (r.method === "GET" && r.path === "/api/people") return json(200, devWire.people());
    if (r.method === "POST" && r.path === "/api/dev/control") return json(200, devWire.control());
    if (r.method === "GET" && r.path.endsWith("/version"))
      return json(200, { contracts: this.versions });
    const graphql = this.graphqlRoute(r);
    if (graphql) return graphql;
    if (r.method === "POST" && r.path.endsWith("/operate/query")) return this.queryRoute(r);
    if (/\/audit\/(changes|loads)$/.test(r.path)) return json(200, page([]));
    if (r.method === "GET" && r.path.endsWith("/explorer/schema-catalog.json"))
      return json(200, wire.schemaCatalog());
    return err(404, { type: "NotFound", message: "not found" });
  }

  private graphqlRoute(r: Recorded): Reply | undefined {
    if (r.path.endsWith("/console/graphql")) {
      const q: string = r.body.query;
      if (q.includes("modules")) return json(200, { data: this.meta(q), extensions: {} });
      return json(200, { data: { status: this.status }, extensions: {} });
    }
    const m = /\/graphql\/([^/]+)$/.exec(r.path);
    if (!m) return undefined;
    // An unknown module and one the viewer may not read answer alike (CONTRACT-006): 404.
    const name = decodeURIComponent(defined(m[1], "m[1]"));
    if (!this.modules.some((x) => x.name === name)) return json(404, wire.gqlNotFound());
    return json(200, this.gql(name, r.body.query, r.body.variables ?? {}));
  }

  /**
   * `POST /query` for the shapes the tests use: `SELECT alias.col, ... | alias.* FROM module.Type alias ORDER BY
   * alias.key LIMIT n` over `rows`, for the named module. Statuses and bodies are the server's (CONTRACT-009): 400
   * for a bad request or an unparsable statement, 404 for an unknown module, 501 for an optional column, a type
   * or module outside the named one, or a page without its order and LIMIT. A test answers anything else (401,
   * 403, 409, 503) with `on`.
   */
  queryRoute(r: Recorded): Reply {
    const b: Record<string, unknown> = { ...r.body };
    const bad = checkQueryBody(b);
    if (bad) return bad;
    const sql = String(b.sql);
    const sel = parseSelect(sql);
    if (!sel) return err(400, wire.invalidQuery());
    const mod = this.modules.find((x) => x.name === b.module);
    if (!mod) return err(404, wire.unknownModule(String(b.module)));
    if (sel.module !== mod.name) return err(501, wire.unsupportedQuery()); // outside the module
    const type = mod.entityTypes.find((t) => t.name === `${sel.module}.${sel.short}`);
    if (!type) return err(501, wire.unsupportedQuery()); // a type the backend does not hold
    if (sel.limit === undefined || sel.order !== type.key) return err(501, wire.unsupportedQuery());
    const proj = resolveProjection(sel.projection, sel.alias);
    if (!proj) return err(400, wire.invalidQuery());
    const fault = checkNames(type, sel.short, proj.names);
    if (fault) return fault;
    const all = (this.rows[type.name] ?? []).slice(0, sel.limit);
    const limit = typeof b.limit === "number" ? b.limit : 50;
    const columns = queryColumns(type, proj);
    const bulk = b.consistency === "bulk";
    return json(
      200,
      wire.queryResult({
        columns,
        rows: all.slice(0, limit).map((row) => queryRow(row, columns)),
        truncated: all.length > limit, // the cap cut the rows
        freshness: {
          ...FRESH,
          backend: bulk ? "memory_replica" : "memory",
          consistency: bulk ? "bulk" : "latest",
        },
      }),
    );
  }

  /** The schema surface: a plan or a result by default; a test answers anything else with `on`. */
  schemaRoute(r: Recorded): Reply {
    if (!this.schemaMounted) return err(404, { type: "NotFound", message: "not found" });
    if (r.method === "GET" && r.path.endsWith("/version")) return json(200, schemaWire.version());
    if (r.method === "POST" && r.path.endsWith("/validate")) return json(200, schemaWire.plan());
    if (r.method === "POST" && r.path.endsWith("/register"))
      return json(200, schemaWire.registryResult());
    return err(404, { type: "NotFound", message: "not found" });
  }

  private list(typeName: string, vars: Partial<GqlVars>) {
    const all = (this.rows[typeName] ?? [])
      .filter((row) => Object.entries(vars.filter ?? {}).every(([k, v]) => String(row[k]) === v))
      .filter((row) => vars.afterKey == null || String(row.key) > vars.afterKey);
    const limit = vars.limit ?? 50;
    const bulk = vars.consistency === "BULK";
    return {
      items: all.slice(0, limit),
      truncated: all.length > limit, // the limit cut the result, as the server says

      freshness: {
        ...FRESH,
        backend: bulk ? "memory_replica" : "memory",
        consistency: vars.consistency ?? "LATEST",
      },
    };
  }

  /**
   * `_search` answered in full (CONTRACT-010 C): every hit with its score, label, matched properties and
   * entity, a count per searched type, the types not searched, `truncated` at the limit and freshness.
   * A row matches when every word is in one of its type's searchable properties.
   */
  searchAnswer(moduleName: string, vars: Partial<GqlVars>) {
    const v = vars as { text?: string; types?: string[] | null; limit?: number };
    const words = (v.text ?? "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    const has = (row: Record<string, unknown>, p: string, w: string) =>
      String(row[p] ?? "")
        .toLowerCase()
        .includes(w);
    const hits: Record<string, unknown>[] = [];
    const counts: { type: string; count: number; atLeast: boolean }[] = [];
    for (const t of this.modules.find((m) => m.name === moduleName)?.entityTypes ?? []) {
      const short = t.name.slice(t.name.lastIndexOf(".") + 1);
      if (v.types && !v.types.includes(short)) continue;
      const props = Object.values(t.capabilities)[0]?.searchable ?? [];
      const found = (this.rows[t.name] ?? []).filter((row) =>
        words.every((w) => props.some((p) => has(row, p, w))),
      );
      counts.push({ type: short, count: found.length, atLeast: false });
      for (const row of found)
        hits.push({
          type: short,
          key: row.key,
          score: 1,
          label: String(row.name ?? row.key),
          excerpt: null,
          matched: props.filter((p) => words.some((w) => has(row, p, w))),
          entity: { ...row, type: short },
        });
    }
    const limit = v.limit ?? 50;
    return {
      data: {
        _search: {
          text: words.join(" "),
          hits: hits.slice(0, limit),
          counts,
          notSearched: [],
          truncated: hits.length > limit,
          freshness: [FRESH],
        },
      },
      extensions: { revision: { ...REV } },
    };
  }

  gql(moduleName: string, query: string, vars: Partial<GqlVars>) {
    if (query.includes("_search(")) return this.searchAnswer(moduleName, vars);
    // Aliased by-key reads (`t0: solution(key: $k0) { name }`), as a label request makes them.
    const aliased = [...query.matchAll(/(\w+)\s*:\s*(\w+)\(key:\s*\$(\w+)\)\s*\{([^}]*)\}/g)];
    if (aliased.length > 0) {
      const data: Record<string, unknown> = {};
      for (const [, alias, field, variable, body] of aliased) {
        const typeName = `catalog.${defined(field, "field").charAt(0).toUpperCase()}${defined(field, "field").slice(1)}`;
        const key = (vars as Record<string, unknown>)[defined(variable, "variable")];
        const row = (this.rows[typeName] ?? []).find((x) => x.key === key) ?? null;
        const sel = (body ?? "")
          .split(/\s+/)
          .filter(Boolean)
          .map((name) => ({ name }));
        data[defined(alias, "alias")] = project(row, sel);
      }
      return { data, extensions: { revision: { ...REV } } };
    }
    // Answer only what the query selects, as the real server does: parse the selection and project.
    const [root] = parseSelection(query.slice(query.indexOf("{")));
    if (!root)
      return {
        data: null,
        errors: [{ message: "empty query", extensions: { code: "BAD_QUERY" } }],
      };
    const typeOf = (field: string) => `catalog.${field.charAt(0).toUpperCase()}${field.slice(1)}`;
    const withTargets = (row: Record<string, unknown>) =>
      Object.fromEntries(
        Object.entries(row).map(([k, v]) => [
          k,
          Array.isArray(v) &&
          v.every((x) => x && typeof x === "object" && "key" in x && "module" in x)
            ? v.map((ref: { type: string; key: string }) => ({
                ...ref,
                target: this.targets[`${ref.type}:${ref.key}`] ?? null,
              }))
            : v,
        ]),
      );
    let value: unknown;
    if (root.name.endsWith("List")) {
      value = this.list(typeOf(root.name.slice(0, -4)), vars);
    } else {
      const row = (this.rows[typeOf(root.name)] ?? []).find((x) => x.key === vars.key) ?? null;
      value = row && { ...withTargets(row), freshness: FRESH };
    }
    return {
      data: { [root.name]: project(value, root.children ?? []) },
      extensions: { revision: { ...REV } },
    };
  }
}

interface Sel {
  name: string;
  children?: Sel[];
}

/** A GraphQL selection set as a tree; arguments are skipped and inline fragments merged into the parent. */
export function parseSelection(text: string): Sel[] {
  const tokens = text.replace(/\([^)]*\)/g, " ").match(/\.\.\.|[{}]|[A-Za-z_][A-Za-z0-9_]*/g) ?? [];
  let i = 0;
  const block = (): Sel[] => {
    const out: Sel[] = [];
    i++; // {
    while (i < tokens.length && tokens[i] !== "}") {
      if (tokens[i] === "...") {
        i += 3; // ... on Type
        out.push(...block());
        continue;
      }
      const node: Sel = { name: defined(tokens[i++], "tokens[i++]") };
      if (tokens[i] === "{") node.children = block();
      out.push(node);
    }
    i++; // }
    return out;
  };
  return tokens[0] === "{" ? block() : [];
}

function project(value: unknown, sel: Sel[]): unknown {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) return value.map((v) => project(v, sel));
  const obj = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const f of sel)
    out[f.name] = f.children ? project(obj[f.name], f.children) : (obj[f.name] ?? null);
  return out;
}

export function stage(): FakeApi {
  return new FakeApi().install();
}

export const attribution = (by = "alice") => ({
  version: "1",
  createdBy: by,
  createdAt: "2026-10-10T02:47:09+00:00",
  updatedBy: by,
  updatedAt: "2026-10-10T02:47:09+00:00",
});

export function seedCatalog(api: FakeApi, n = 3) {
  api.rows["catalog.UseCase"] = Array.from({ length: n }, (_, i) => ({
    key: `uc-${i + 1}`,
    type: "catalog.UseCase",
    code: `uc-${i + 1}`,
    name: `Use case ${i + 1}`,
    workArea: "data",
    addressedBy: [{ module: "catalog", type: "catalog.Solution", key: "sol-1" }],
    ...attribution(),
  }));
  api.rows["catalog.Solution"] = [
    {
      key: "sol-1",
      type: "catalog.Solution",
      code: "sol-1",
      name: "Pipeline extractor",
      coverageLevel: null,
      addresses: [{ module: "catalog", type: "catalog.UseCase", key: "uc-1" }],
      ...attribution("ana"),
    },
  ];
  api.targets["catalog.UseCase:uc-1"] = {
    key: "uc-1",
    type: "catalog.UseCase",
    ...attribution(),
    name: "Use case 1",
    workArea: "data",
    addressedBy: [{ module: "catalog", type: "catalog.Solution", key: "sol-1" }],
  };
}
