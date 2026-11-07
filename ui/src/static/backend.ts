// SPDX-License-Identifier: MIT OR Apache-2.0
// The static read-only backend (ADR-031, CONTRACT-012): an `ArrasClient` that answers from a UMF module
// document and an `arras.graph` file held in memory, with no server. Every read the Graph Browser makes
// is served here; every write, the journal and the SQL surface answer a 501 that says the graph is
// published read-only.
import {
  type ArrasClient,
  type GraphQLResult,
  META_QUERY,
  mergeViews,
  type SchemaApi,
  STATUS_QUERY,
  VIEWS_QUERY,
  type ViewsData,
} from "../api/client";
import { ApiError } from "../api/errors";
import { parseGraphFile } from "../api/graphFile";
import type { ExportPage, MetaData, SchemaCatalog, Versions, Viewer } from "../api/types";
import { SUPPORTED_OPERATE_VERSION } from "../api/types";
import { Refusal, run } from "./execute";
import { BACKEND, Store } from "./store";
import { byCodePoint } from "./text";
import { parseModule } from "./umf";
import { resolve } from "./view";

export const EXPORT_PAGE = 500;
export const READ_ONLY =
  "this graph is published read-only: it is read from files, and nothing can be changed in it";

/** The first 16 hex digits of a digest of `text`: SHA-256 where the browser offers it, else FNV-1a (64-bit). */
export async function digestOf(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const subtle = globalThis.crypto?.subtle;
  if (subtle) {
    const d = new Uint8Array(await subtle.digest("SHA-256", bytes));
    return Array.from(d.slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  let h = 0xcbf29ce484222325n;
  for (const b of bytes) h = ((h ^ BigInt(b)) * 0x100000001b3n) & 0xffffffffffffffffn;
  return h.toString(16).padStart(16, "0");
}

/** Load a store from a module document and a graph file; throws `InvalidDocument` or `GraphLoadError`. */
export async function loadStore(moduleText: string, graphText: string, now?: Date): Promise<Store> {
  const { module, declared } = parseModule(moduleText);
  const graph = parseGraphFile(graphText);
  return new Store(module, resolve(module, declared), graph, await digestOf(graphText), now);
}

const unsupported = (construct: string, message: string): ApiError =>
  new ApiError(501, { type: "Unsupported", message, construct, supported: ["reads"] });

// -- export ---------------------------------------------------------------------------------

type Place = [number, ...string[]];
const b64url = (s: string) =>
  btoa(String.fromCharCode(...new TextEncoder().encode(s)))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");

function badCursor(): ApiError {
  return new ApiError(400, {
    type: "Invalid",
    message: "after: cursor: not a cursor of this export",
    violations: [{ path: "after", code: "cursor", message: "not a cursor of this export" }],
  });
}

function placeOf(rec: Record<string, unknown>, module: string): Place {
  return "type" in rec
    ? [0, `${module}.${String(rec.type)}`, String(rec.key)]
    : [1, String(rec.relationship), String(rec.source), String(rec.target)];
}

function resumePlace(after: string): Place {
  try {
    if (after.length > 1024) throw new Error("long");
    const padded =
      after.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (after.length % 4)) % 4);
    const order: unknown = JSON.parse(
      new TextDecoder().decode(Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))),
    );
    if (!Array.isArray(order) || (order[0] !== 0 && order[0] !== 1)) throw new Error("shape");
    const parts = order.slice(1);
    if (parts.length !== (order[0] === 0 ? 2 : 3) || !parts.every((x) => typeof x === "string"))
      throw new Error("shape");
    return order as Place;
  } catch {
    throw badCursor();
  }
}

function exportPage(store: Store, req: { after?: string; limit?: number }): ExportPage {
  const limit = req.limit ?? EXPORT_PAGE;
  if (!Number.isInteger(limit) || limit < 1 || limit > EXPORT_PAGE)
    throw new ApiError(400, {
      type: "Invalid",
      message: `limit: bound: limit is an integer from 1 to ${EXPORT_PAGE}`,
      violations: [
        { path: "limit", code: "bound", message: `limit is an integer from 1 to ${EXPORT_PAGE}` },
      ],
    });
  const mod = store.module;
  const table: [Map<string, number>, Map<string, number>] = [
    new Map(mod.entityTypes.map((t, i) => [t.name, i])),
    new Map(mod.relationships.map((r, i) => [r.name, i])),
  ];
  const rankOf = (p: Place): (number | string)[] => {
    const at = (table[p[0]] as Map<string, number>).get(p[1] as string);
    if (at === undefined) throw badCursor();
    return [p[0], at, ...p.slice(2)];
  };
  const before = (a: (number | string)[], b: (number | string)[]): number => {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const x = a[i] as number | string;
      const y = b[i] as number | string;
      const c =
        typeof x === "number" && typeof y === "number" ? x - y : byCodePoint(String(x), String(y));
      if (c !== 0) return c;
    }
    return 0;
  };
  let from = 0;
  if (req.after !== undefined) {
    const resume = rankOf(resumePlace(req.after));
    from = store.records.findIndex((r) => before(rankOf(placeOf(r, mod.name)), resume) > 0);
    if (from < 0) from = store.records.length;
  }
  const items = store.records.slice(from, from + limit);
  const last = items[items.length - 1];
  const more = from + items.length < store.records.length;
  return {
    items,
    nextCursor: more && last ? b64url(JSON.stringify(placeOf(last, mod.name))) : null,
    omitted: [],
    freshness: { backend: BACKEND, asOf: store.asOf, at: store.at, consistency: "latest" },
  };
}

// -- the client -----------------------------------------------------------------------------

const clientError = (r: Refusal) => new ApiError(r.status, { message: r.message, code: r.code });

/** The `ArrasClient` over a loaded store: reads only, no network. */
export function createStaticClient(store: Store, documentText?: string): ArrasClient {
  const gql = <T>(query: string): T => {
    const r = run(store, null, { query });
    if (!r.data) throw new ApiError(200, { message: "no data" });
    return r.data as T;
  };
  const refuse = (what: string) => (): Promise<never> =>
    Promise.reject(unsupported(what, READ_ONLY));
  return {
    config: { operateBase: "", consoleBase: "" },
    version: async (): Promise<Versions> => ({
      contracts: { interface: 2, actions: 2, console: 2, operate: SUPPORTED_OPERATE_VERSION },
    }),
    viewer: async (): Promise<Viewer> => ({ user: "public", modes: ["user"] }),
    meta: async (): Promise<MetaData> =>
      mergeViews(gql<MetaData>(META_QUERY), gql<ViewsData>(VIEWS_QUERY)),
    status: async () => gql<Pick<MetaData, "status">>(STATUS_QUERY).status,
    moduleQuery: async <T>(
      module: string,
      query: string,
      variables?: Record<string, unknown>,
    ): Promise<GraphQLResult<T>> => {
      try {
        const r = run(store, module, { query, variables });
        return {
          data: (r.data ?? null) as T | null,
          errors: (r.errors ?? []).map((e) => ({
            message: e.message,
            code: e.extensions.code as string | undefined,
            reason: e.extensions.reason as string | undefined,
            backend: e.extensions.backend as string | undefined,
            path: e.path,
          })),
          revision: r.extensions.revision,
        };
      } catch (e) {
        throw e instanceof Refusal ? clientError(e) : e;
      }
    },
    validate: refuse("writes"),
    invoke: refuse("writes"),
    batch: refuse("writes"),
    changes: refuse("the audit journal"),
    loads: refuse("the audit journal"),
    query: refuse("SQL queries"),
    export: async (req) => exportPage(store, req),
    schemaCatalog: async (): Promise<SchemaCatalog> => ({
      version: 1,
      entries: documentText
        ? [
            {
              id: `arras:${store.module.name}`,
              title: store.resolved.module.title,
              category: "domain",
              path: `${store.module.name}.umf.json`,
              text: documentText,
              format: "json",
              description: store.resolved.module.description ?? "",
              schemaFormat: "umf",
            },
          ]
        : [],
    }),
  };
}

/** The schema surface of a host that has none: never offered, so the interface shows no import. */
export function staticSchemaApi(): SchemaApi {
  const no = (): Promise<never> => Promise.reject(unsupported("schema administration", READ_ONLY));
  return { schemaBase: "", offered: async () => false, validate: no, register: no };
}
