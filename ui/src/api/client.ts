// SPDX-License-Identifier: MIT OR Apache-2.0
import { ApiError } from "./errors";
import { parseRecords } from "./losslessJson";
import type {
  ActionRequest,
  BatchReceipt,
  BatchRequest,
  Change,
  ChangesQuery,
  ExportPage,
  Load,
  MetaData,
  Page,
  QueryRequest,
  QueryResult,
  Receipt,
  RegistryResult,
  Revision,
  SchemaCatalog,
  SchemaPlan,
  SchemaRequest,
  SchemaVersions,
  TypeView,
  Validation,
  Versions,
  Viewer,
} from "./types";
import { SUPPORTED_SCHEMA_VERSION } from "./types";

export interface ClientConfig {
  operateBase: string;
  consoleBase: string;
  /** A host's own auth headers. Nothing is stored here; it is called for every request. */
  getHeaders?: () => Record<string, string>;
  /** Called on a 401 so the host can sign the viewer in again. */
  onUnauthorized?: () => void;
  /** Called when a module read answers `REVISION_CHANGED`: the registry moved under the page. */
  onRevisionChanged?: () => void;
}

export interface GraphQLError {
  message: string;
  code?: string;
  /** `extensions.reason`, for example `token_expired` or `unreachable`. */
  reason?: string;
  /** `extensions.backend`, the backend that refused or was unavailable. */
  backend?: string;
  path?: (string | number)[];
}

export interface GraphQLResult<T> {
  data: T | null;
  errors: GraphQLError[];
  revision?: Record<string, number | null>;
}

const MAX_IN_FLIGHT = 4; // CONTRACT-009: more than four per person answers 429
const MAX_RETRIES = 3;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const networkError = (e: unknown) =>
  new ApiError(0, { type: "Network", message: e instanceof Error ? e.message : "network error" });
const trim = (s: string) => s.replace(/\/+$/, "");

export interface ArrasClient {
  config: ClientConfig;
  version(): Promise<Versions>;
  /**
   * The one meta read both modes make: the registry (types, relationships, actions, status) with the
   * module's view and each type's resolved view (CONTRACT-010 B), in as many requests as the field limit needs.
   */
  meta(): Promise<MetaData>;
  status(): Promise<MetaData["status"]>;
  /** One GraphQL request against a module's schema. Variables travel in the body, never the URL. */
  moduleQuery<T>(
    module: string,
    query: string,
    variables?: Record<string, unknown>,
  ): Promise<GraphQLResult<T>>;
  validate(module: string, action: string, req: ActionRequest): Promise<Validation>;
  invoke(module: string, action: string, req: ActionRequest): Promise<Receipt>;
  batch(module: string, action: string, req: BatchRequest): Promise<BatchReceipt>;
  changes(q: ChangesQuery): Promise<Page<Change>>;
  loads(q: {
    module: string;
    limit?: number;
    after?: string;
    provider?: string;
  }): Promise<Page<Load>>;
  /**
   * `POST /query` (OPR-16): a read-only Weft statement over a named module, run as the viewer. The text is in
   * the POST body only; this client puts it in no URL, log, error message or storage.
   */
  query(req: QueryRequest): Promise<QueryResult>;
  /** `POST /export`: one page of a module's graph as records, read as the viewer (CONTRACT-009). */
  export(req: { module: string; after?: string; limit?: number }): Promise<ExportPage>;
  /** Who the host says is asking and the modes it offers (CONTRACT-010). */
  viewer(): Promise<Viewer>;
  /** The viewer's catalog of registered UMF documents, for UMF's schema browser (OPR-11). */
  schemaCatalog(): Promise<SchemaCatalog>;
}

// A request selects at most 50 fields (CONTRACT-006), so the meta read is two: the registry's modules,
// types, relationships, actions and status, and each type's resolved view (CONTRACT-010 B).
const META_QUERY = `{ modules { name record replicas providers revision view { title description } entityTypes { name key properties { name type required cardinality } capabilities } relationships { name source target sourceMultiplicity targetMultiplicity lifecycle inverse } actions { name description inputSpecs { name type kind cardinality } preconditions effects } } status { backend available reason position lag } }`;
const VIEW_FIELDS = `declared label pluralLabel icon tone title summary sections { label properties collapsed } search fields { property label format hideWhenEmpty tones } relationships { field label hideWhenEmpty order }`;
const VIEWS_QUERY = `{ modules { name revision entityTypes { name view { ${VIEW_FIELDS} } } } }`;
const STATUS_QUERY = `{ status { backend available reason position lag } }`;

async function sendJson(
  config: ClientConfig,
  url: string,
  init: { method: string; body?: unknown },
): Promise<Response> {
  const headers: Record<string, string> = { accept: "application/json", ...config.getHeaders?.() };
  if (init.body !== undefined) headers["content-type"] = "application/json";
  return fetch(url, {
    method: init.method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

/** A response's JSON, its integers kept exactly when `lossless` (the graph file's records, in `items`). */
const readBody = async (res: Response, lossless: boolean): Promise<unknown> =>
  lossless ? parseRecords(await res.text(), "items") : res.json();

/** A GraphQL error as an error body: its code, reason and backend kept. */
function gqlBody(e: GraphQLError, status: number): Record<string, unknown> {
  const body: Record<string, unknown> = {
    message: e.message,
    code: e.code,
    reason: e.reason,
    backend: e.backend,
  };
  if (status === 403 || status === 401 || e.code === "REFUSED") body.type = "Refused";
  return body;
}

/** Tell the host to sign the viewer in again, whatever form the expiry arrived in. */
function signalSignIn(config: ClientConfig, err: ApiError): ApiError {
  if (err.kind === "sign_in") config.onUnauthorized?.();
  return err;
}

/** A failed response as an `ApiError` (the contract's `error` member, or a GraphQL error), signalled. */
async function failResponse(config: ClientConfig, res: Response): Promise<never> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* no body */
  }
  const retry = Number(res.headers.get("retry-after"));
  const p = payload as {
    error?: Record<string, unknown> | string;
    errors?: {
      message?: string;
      extensions?: { code?: string; reason?: string; backend?: string };
    }[];
  } | null;
  let body: Record<string, unknown> = {};
  // The operator refusal (CONTRACT-010, the Graph Browser's) carries `error` as a plain code beside a `reason`.
  if (typeof p?.error === "string")
    body = { type: "Refused", message: p.error, reason: (payload as { reason?: string }).reason };
  else if (p?.error) body = p.error;
  else if (p?.errors?.[0]) {
    const e = p.errors[0];
    body = gqlBody(
      {
        message: e.message ?? "",
        code: e.extensions?.code,
        reason: e.extensions?.reason,
        backend: e.extensions?.backend,
      },
      res.status,
    );
  }
  throw signalSignIn(
    config,
    new ApiError(res.status, body, Number.isFinite(retry) ? retry : undefined),
  );
}
interface ViewsData {
  modules: {
    name: string;
    revision: Revision;
    entityTypes: { name: string; view: TypeView }[];
  }[];
}

/** Do the registry read and the views read describe the same revision of every module? */
function sameRevisions(meta: MetaData, views: ViewsData): boolean {
  const at = new Map(views.modules.map((m) => [m.name, JSON.stringify(m.revision)]));
  return meta.modules.every((m) => at.get(m.name) === JSON.stringify(m.revision));
}

/** The views read beside the registry, attached to the types they describe. */
function mergeViews(meta: MetaData, views: ViewsData): MetaData {
  const viewOf = (module: string, type: string) =>
    views.modules.find((m) => m.name === module)?.entityTypes.find((t) => t.name === type)?.view;
  return {
    ...meta,
    modules: meta.modules.map((m) => ({
      ...m,
      entityTypes: m.entityTypes.map((t) => ({ ...t, view: viewOf(m.name, t.name) })),
    })),
  };
}

const REVISION_CHANGED = "REVISION_CHANGED";

export function createClient(config: ClientConfig): ArrasClient {
  const operate = trim(config.operateBase);
  const consoleBase = trim(config.consoleBase);
  let inFlight = 0;
  const waiters: (() => void)[] = [];

  async function acquire() {
    while (inFlight >= MAX_IN_FLIGHT) await new Promise<void>((r) => waiters.push(r));
    inFlight++;
  }
  function release() {
    inFlight--;
    waiters.shift()?.();
  }

  const send = (url: string, init: { method: string; body?: unknown }) =>
    sendJson(config, url, init);
  const fail = (res: Response) => failResponse(config, res);

  async function sendOrThrow(
    url: string,
    init: { method: string; body?: unknown },
  ): Promise<Response> {
    try {
      return await send(url, init);
    } catch (e) {
      throw networkError(e);
    }
  }

  async function operateCall<T>(
    path: string,
    method: "GET" | "POST",
    body?: unknown,
    lossless = false,
  ): Promise<T> {
    await acquire();
    try {
      for (let attempt = 0; ; attempt++) {
        const res = await sendOrThrow(`${operate}${path}`, { method, body });
        if (res.status === 429 && attempt < MAX_RETRIES) {
          const secs = Number(res.headers.get("retry-after"));
          await sleep((Number.isFinite(secs) && secs > 0 ? secs : 1) * 1000);
          continue;
        }
        if (!res.ok) return await fail(res);
        // A body that carries stored integers is read without rounding them (the graph file).
        return (await readBody(res, lossless)) as T;
      }
    } finally {
      release();
    }
  }

  async function graphql<T>(
    path: string,
    query: string,
    variables?: Record<string, unknown>,
    cfg: ClientConfig = config,
  ): Promise<GraphQLResult<T>> {
    let res: Response;
    await acquire(); // reads share the bound of four in flight: the graph reads one list per type
    try {
      try {
        res = await send(`${consoleBase}${path}`, { method: "POST", body: { query, variables } });
      } catch (e) {
        throw networkError(e);
      }
      if (!res.ok) return await failResponse(cfg, res);
      const r = await readGraphql<T>(res);
      // An expired token can arrive as a 200 whose error says so (CONTRACT-006 executes the query and
      // reports the refusal per field): it is a sign-in, never "no data" or "not found".
      const expired = r.errors.find((e) => e.reason === "token_expired");
      if (expired) throw signalSignIn(cfg, new ApiError(res.status, gqlBody(expired, res.status)));
      return r;
    } finally {
      release();
    }
  }

  async function readGraphql<T>(res: Response): Promise<GraphQLResult<T>> {
    const j = (await res.json()) as {
      data?: T | null;
      errors?: {
        message: string;
        extensions?: { code?: string; reason?: string; backend?: string };
        path?: (string | number)[];
      }[];
      extensions?: { revision?: Record<string, number | null> };
    };
    return {
      data: j.data ?? null,
      errors: (j.errors ?? []).map((e) => ({
        message: e.message,
        code: e.extensions?.code,
        reason: e.extensions?.reason,
        backend: e.extensions?.backend,
        path: e.path,
      })),
      revision: j.extensions?.revision,
    };
  }

  // The path takes the action's short name; a declared action is named `module.Short`.
  const verb = (module: string, action: string, v: string) => {
    const short = action.startsWith(`${module}.`) ? action.slice(module.length + 1) : action;
    return `/actions/${encodeURIComponent(module)}/${encodeURIComponent(short)}/${v}`;
  };

  async function graphqlData<T>(query: string, cfg: ClientConfig = config): Promise<T> {
    const r = await graphql<T>("/graphql", query, undefined, cfg);
    if (!r.data) {
      const e = r.errors[0];
      throw new ApiError(200, e ? gqlBody(e, 200) : { message: "no data" });
    }
    return r.data;
  }

  return {
    config,
    version: () => operateCall<Versions>("/version", "GET"),
    viewer: () => operateCall<Viewer>("/viewer", "GET"),
    async meta() {
      // Two requests (the field limit), each selecting the revision: if the registry moved between
      // them the pair is read once more, and a second disagreement is REVISION_CHANGED.
      // The pair is one read to the host: an expired token asks it to sign the viewer in once, not once
      // per request.
      let signed = false;
      const cfg: ClientConfig = {
        ...config,
        onUnauthorized: () => {
          if (signed) return;
          signed = true;
          config.onUnauthorized?.();
        },
      };
      for (let attempt = 0; attempt < 2; attempt++) {
        const [meta, views] = await Promise.all([
          graphqlData<MetaData>(META_QUERY, cfg),
          graphqlData<ViewsData>(VIEWS_QUERY, cfg),
        ]);
        if (sameRevisions(meta, views)) return mergeViews(meta, views);
      }
      throw new ApiError(200, {
        message: "the registry changed while it was read; read it again",
        code: "REVISION_CHANGED",
      });
    },
    async status() {
      const r = await graphql<Pick<MetaData, "status">>("/graphql", STATUS_QUERY);
      return r.data?.status ?? [];
    },
    async moduleQuery<T>(module: string, query: string, variables?: Record<string, unknown>) {
      try {
        const r = await graphql<T>(`/graphql/${encodeURIComponent(module)}`, query, variables);
        if (r.errors.some((e) => e.code === REVISION_CHANGED)) config.onRevisionChanged?.();
        return r;
      } catch (e) {
        if (e instanceof ApiError && e.code === REVISION_CHANGED) config.onRevisionChanged?.();
        throw e;
      }
    },
    validate: (m, a, req) => operateCall<Validation>(verb(m, a, "validate"), "POST", req),
    invoke: (m, a, req) => operateCall<Receipt>(verb(m, a, "invoke"), "POST", req),
    batch: (m, a, req) => operateCall<BatchReceipt>(verb(m, a, "batch"), "POST", req),
    changes: (q) => operateCall<Page<Change>>("/audit/changes", "POST", q),
    loads: (q) => operateCall<Page<Load>>("/audit/loads", "POST", q),
    query: (req) => operateCall<QueryResult>("/query", "POST", req),
    export: (req) => operateCall<ExportPage>("/export", "POST", req, true),
    schemaCatalog: () => operateCall<SchemaCatalog>("/explorer/schema-catalog.json", "GET"),
  };
}

/** The default mount of the schema administration surface (CONTRACT-011). */
export const DEFAULT_SCHEMA_BASE = "/api/schema";

export interface SchemaApi {
  schemaBase: string;
  /**
   * Is the schema surface mounted, at a version this console speaks? A 404, a network failure or
   * any other answer means the host did not mount it, so the console offers no import.
   */
  offered(): Promise<boolean>;
  /** `POST validate`: a plan for the document; nothing is applied. */
  validate(document: string): Promise<SchemaPlan>;
  /** `POST register`: apply the document, as the viewer, if the store is still at `expected`. */
  register(document: string, expected?: Revision | null): Promise<RegistryResult>;
}

/**
 * The schema surface's client (CONTRACT-011): the console's only write besides a declared action
 * (OPR-08, OPR-13). It shares the console's headers and sign-in signal, holds no credential, and
 * sends the document in a POST body, never a URL. Whether the viewer may register is the backend's
 * answer (403 `no access`), which the caller shows; nothing here decides it.
 */
export function createSchemaApi(config: ClientConfig & { schemaBase?: string }): SchemaApi {
  const schemaBase = trim(config.schemaBase ?? DEFAULT_SCHEMA_BASE);
  async function post<T>(verb: "validate" | "register", body: SchemaRequest): Promise<T> {
    let res: Response;
    try {
      res = await sendJson(config, `${schemaBase}/${verb}`, { method: "POST", body });
    } catch (e) {
      throw networkError(e);
    }
    if (!res.ok) return await failResponse(config, res);
    return (await res.json()) as T;
  }
  return {
    schemaBase,
    async offered() {
      try {
        const res = await sendJson(config, `${schemaBase}/version`, { method: "GET" });
        if (!res.ok) return false;
        const v = (await res.json()) as Partial<SchemaVersions> | null;
        return v?.contracts?.schema === SUPPORTED_SCHEMA_VERSION;
      } catch {
        return false;
      }
    },
    validate: (document) => post<SchemaPlan>("validate", { document }),
    register: (document, expected) =>
      post<RegistryResult>(
        "register",
        expected ? { document, expected_revision: expected } : { document },
      ),
  };
}
