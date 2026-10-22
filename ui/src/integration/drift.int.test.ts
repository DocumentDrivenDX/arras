// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import {
  buildEntityQuery,
  buildFollowQuery,
  buildListQuery,
  columnsFor,
  defaultColumns,
} from "../api/gql";
import { buildGraphQuery } from "../lib/graph";
import { defined } from "../test/defined";
import { FakeApi, type Recorded, seedCatalog, validation, wire } from "../test/fake";
import { asBob, call, control, gql, unique, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";
import { type CompareOpts, schemaErrors, shapeDiff } from "./shapes";

// The drift guard: the unit tier's fetch double (src/test/fake.ts) against the real dev host. For every
// call the fake models, the real call is made and the two answers must have the same key structure
// (keys at every level, JSON types, nulls, array element shapes); every operator-surface body, real
// and fake, must satisfy ui/openapi.json. A failure here means the fake (or the server) moved: fix
// the fake to what the server answers, or report the server.
withDevHost();

const doc = JSON.parse(readFileSync(resolve(REPO_ROOT, "ui/openapi.json"), "utf8")) as Record<
  string,
  unknown
>;
const META_QUERY = `{ modules { name record replicas providers revision entityTypes { name key properties { name type required cardinality } capabilities } relationships { name source target sourceMultiplicity targetMultiplicity lifecycle inverse } actions { name description inputSpecs { name type kind cardinality } preconditions effects } } status { backend available reason position lag } }`;
const VIEWS_QUERY = `{ modules { name revision entityTypes { name view { declared label pluralLabel icon tone title summary sections { label properties collapsed } search fields { property label format hideWhenEmpty tones } relationships { field label hideWhenEmpty order } } } } }`;
const STATUS_QUERY = `{ status { backend available reason position lag } }`;

interface MetaReply {
  data: { modules: { actions: { name: string }[]; entityTypes: unknown[] }[] };
}

const fake = new FakeApi();
seedCatalog(fake);
const fakeGql = (query: string, variables: Record<string, unknown> = {}, module?: string) => {
  const rec: Recorded = {
    method: "POST",
    url: "",
    path: `/api/console/graphql${module ? `/${module}` : ""}`,
    headers: {},
    body: JSON.parse(JSON.stringify({ query, variables })),
  };
  return fake.route(rec);
};
const m = defined(fake.modules[0], "the fake's first module");
const solution = defined(
  m.entityTypes.find((t) => t.name === "catalog.Solution"),
  "the Solution type",
);
const useCase = defined(
  m.entityTypes.find((t) => t.name === "catalog.UseCase"),
  "the UseCase type",
);

/** Optional properties and the like, null in some rows and text in others, on either side. */
const ROWS: CompareOpts = { nullable: [".coverageLevel", ".workArea", ".lag", ".target"] };
const META: CompareOpts = {
  nullable: [
    ".lag",
    ".alias",
    ".type",
    ".ref_type",
    ".key",
    ".source",
    ".target",
    ".over",
    ".inverse",
  ],
  open: [".properties", ".args", ".capabilities"],
};

function responseSchema(path: string, method: string, status: number) {
  const p = (
    doc.paths as Record<
      string,
      Record<
        string,
        {
          responses: Record<
            string,
            { content?: Record<string, { schema: Record<string, unknown> }> }
          >;
        }
      >
    >
  )[path];
  return p?.[method]?.responses[String(status)]?.content?.["application/json"]?.schema;
}

const covered: string[] = [];
afterAll(() => {
  // Every `wire` fixture is either compared with the real server or named here as unreachable.
  const unreachable = ["notOffered", "unsupported", "load", "page", "gqlExpiredField"];
  const fixtures = Object.keys(wire).filter((k) => !unreachable.includes(k));
  expect(fixtures.filter((k) => !covered.includes(k))).toEqual([]);
});

function same(
  name: string,
  real: { status: number; body: unknown },
  fakeReply: { status?: number; body?: unknown },
  opts: CompareOpts = {},
  api?: { path: string; method?: string },
) {
  covered.push(name);
  expect({ name, status: real.status }).toEqual({ name, status: fakeReply.status ?? 200 });
  expect(
    shapeDiff(real.body, fakeReply.body, opts),
    `${name}: real ${JSON.stringify(real.body).slice(0, 400)}`,
  ).toEqual([]);
  if (api) {
    const schema = responseSchema(api.path, api.method ?? "post", real.status);
    const documented = defined(
      schema,
      `${name}: openapi.json documents ${api.path} ${real.status}`,
    );
    expect(schemaErrors(real.body, documented, doc), `${name} (real) against openapi.json`).toEqual(
      [],
    );
    expect(
      schemaErrors(fakeReply.body, documented, doc),
      `${name} (fake) against openapi.json`,
    ).toEqual([]);
  }
}
const op = (status: number, body: unknown) => ({ status, body });
const ACTION = "/actions/{module}/{action}";

describe("drift guard: the fake answers what the real server answers", () => {
  it("GET /version", async () => {
    same(
      "version",
      await call("/api/operate/version"),
      op(200, wire.version()),
      {},
      { path: "/version", method: "get" },
    );
  });

  it("GET /explorer/schema-catalog.json", async () => {
    same(
      "schemaCatalog",
      await call("/api/operate/explorer/schema-catalog.json"),
      op(200, wire.schemaCatalog()),
      {},
      { path: "/explorer/schema-catalog.json", method: "get" },
    );
  });

  it("the meta query (modules, status)", async () => {
    same("meta", await gql(META_QUERY), fakeGql(META_QUERY), META);
    same("status", await gql(STATUS_QUERY), fakeGql(STATUS_QUERY), META);
    // The fake's CorrectSolution is the real declaration, field for field.
    const real = (await gql<MetaReply>(META_QUERY)).body.data.modules[0]?.actions.find(
      (a) => a.name === "catalog.CorrectSolution",
    );
    expect(m.actions.find((a) => a.name === "catalog.CorrectSolution")).toEqual(real);
    // the views are the second request of the meta read (VIEWS_QUERY); this read's types carry none
    expect(m.entityTypes.map(({ view: _v, ...t }) => t)).toEqual(
      (await gql<MetaReply>(META_QUERY)).body.data.modules[0]?.entityTypes,
    );
    same("views", await gql(VIEWS_QUERY), fakeGql(VIEWS_QUERY), META);
  });

  it("a module's list, graph, by-key and follow queries", async () => {
    for (const t of [solution, useCase]) {
      const cols = columnsFor(m, t);
      const shown = cols.filter((c) => defaultColumns(cols).includes(c.id) || c.kind === "rel");
      const list = buildListQuery(t.name, shown);
      const vars = { filter: null, limit: 25, consistency: "LATEST" };
      same("list", await gql(list, vars, "alice", "catalog"), fakeGql(list, vars, "catalog"), ROWS);
      const bulk = { ...vars, consistency: "BULK" };
      same(
        "list BULK",
        await gql(list, bulk, "alice", "catalog"),
        fakeGql(list, bulk, "catalog"),
        ROWS,
      );
      const graph = buildGraphQuery(m, t);
      same(
        "graph",
        await gql(graph, { limit: 100, consistency: "LATEST" }, "alice", "catalog"),
        fakeGql(graph, { limit: 100, consistency: "LATEST" }, "catalog"),
        ROWS,
      );
    }
    const one = buildEntityQuery(m, solution);
    same(
      "by key",
      await gql(one, { key: "sol-1", consistency: "LATEST" }, "alice", "catalog"),
      fakeGql(one, { key: "sol-1", consistency: "LATEST" }, "catalog"),
      ROWS,
    );
    same(
      "by key, absent",
      await gql(one, { key: "nope" }, "alice", "catalog"),
      fakeGql(one, { key: "nope" }, "catalog"),
      ROWS,
    );
    const follow = buildFollowQuery(m, solution, "addresses");
    same(
      "follow",
      await gql(follow, { key: "sol-1" }, "alice", "catalog"),
      fakeGql(follow, { key: "sol-1" }, "catalog"),
      ROWS,
    );
  });

  it("validate: valid, invalid inputs, a failed precondition", async () => {
    const v = (inputs: Record<string, unknown>) =>
      call("/api/operate/actions/catalog/CorrectSolution/validate", {
        inputs,
        expected_revision: { memory: 1 },
      });
    same(
      "validation",
      await v({ solution: "sol-1", level: "x" }),
      op(200, wire.validation()),
      {},
      { path: `${ACTION}/validate` },
    );
    same(
      "invalidValidation",
      await v({ solution: "sol-1" }),
      op(200, wire.invalidValidation()),
      {},
      { path: `${ACTION}/validate` },
    );
    same(
      "validation, failed precondition",
      await v({ solution: "nope", level: "x" }),
      op(200, validation({ ok: false, failures: [{ id: "exists", reason: "no such solution" }] })),
      {},
      { path: `${ACTION}/validate` },
    );
  });

  it("invoke: a receipt, and the same key again (a replay)", async () => {
    const key = unique("drift");
    const body = { inputs: { solution: "sol-1", level: "drift" }, idempotency_key: key };
    same(
      "receipt",
      await call("/api/operate/actions/catalog/CorrectSolution/invoke", body),
      op(200, wire.receipt()),
      {},
      { path: `${ACTION}/invoke` },
    );
    const replay = await call<{ replayed: boolean }>(
      "/api/operate/actions/catalog/CorrectSolution/invoke",
      body,
    );
    expect(replay.body.replayed).toBe(true);
    same(
      "receipt, replayed",
      replay,
      op(200, wire.receipt({ replayed: true })),
      {},
      { path: `${ACTION}/invoke` },
    );
  });

  it("batch: an independent batch with a refusal", async () => {
    const real = await call("/api/operate/actions/catalog/AddUseCase/batch", {
      items: [
        { code: unique("drift"), name: "D" },
        { code: "uc-pipeline", name: "dup" },
      ],
    });
    same("batch", real, op(200, wire.batch()), {}, { path: `${ACTION}/batch` });
    // The refusal is the error body without the library's `_type` tags (operate._untag).
    expect(JSON.stringify(real.body)).not.toContain("_type");
  });

  it("audit: a page of changes, an empty page of loads", async () => {
    same(
      "change",
      await call("/api/operate/audit/changes", { module: "catalog", limit: 2 }),
      op(200, wire.page([wire.change(), wire.change({ group: "g-3" })], "2")),
      {},
      { path: "/audit/changes" },
    );
    same(
      "loads page",
      await call("/api/operate/audit/loads", { module: "catalog" }),
      op(200, wire.page([wire.load()])),
      {},
      { path: "/audit/loads" },
    );
    // No load can be made on the dev host; the fake's Load is checked against openapi.json alone.
    expect(
      schemaErrors(
        wire.page([wire.load()]),
        defined(responseSchema("/audit/loads", "post", 200), "the /audit/loads 200 schema"),
        doc,
      ),
    ).toEqual([]);
    expect(
      schemaErrors(
        { error: wire.notOffered() },
        defined(responseSchema(`${ACTION}/invoke`, "post", 403), "the invoke 403 schema"),
        doc,
      ),
    ).toEqual([]);
    expect(
      schemaErrors(
        { error: wire.unsupported() },
        defined(responseSchema("/audit/changes", "post", 501), "the /audit/changes 501 schema"),
        doc,
      ),
    ).toEqual([]);
  });

  it("POST /query: a grid and every error the fake models", async () => {
    const q = (body: Record<string, unknown>, who: Parameters<typeof call>[2] = "alice") =>
      call("/api/operate/query", { module: "catalog", ...body }, who);
    // The fake's solutions get a value for the optional property too: a row has a member only for a property that has a value.
    const qfake = new FakeApi();
    seedCatalog(qfake);
    qfake.rows["catalog.Solution"] = [
      ...defined(qfake.rows["catalog.Solution"], "the fake's solutions"),
      {
        ...defined(qfake.rows["catalog.Solution"]?.[0], "a solution"),
        key: "sol-2",
        code: "sol-2",
        coverageLevel: "full",
      },
    ];
    const fakeQ = (body: Record<string, unknown>) =>
      qfake.route({
        method: "POST",
        url: "",
        path: "/api/operate/query",
        headers: {},
        body: { module: "catalog", ...body } as unknown as Recorded["body"],
      });
    const sql = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100";
    const API = { path: "/query" };
    // Rows have different values on each side but the same shape: columns, row objects, truncated, freshness (lower-case consistency), revision.
    same("queryResult", await q({ sql, limit: 2 }), fakeQ({ sql, limit: 2 }), {}, API);
    same(
      "queryResult bulk",
      await q({ sql, limit: 2, consistency: "bulk" }),
      fakeQ({ sql, limit: 2, consistency: "bulk" }),
      {},
      API,
    );
    const all = "SELECT s.* FROM catalog.Solution s ORDER BY s.code LIMIT 100";
    same(
      "queryResult x.*",
      await q({ sql: all }),
      fakeQ({ sql: all }),
      { nullable: [".coverageLevel"] },
      API,
    );
    same(
      "invalidQuery",
      await q({ sql: "DELETE FROM catalog.UseCase" }),
      op(400, { error: wire.invalidQuery() }),
      {},
      API,
    );
    same(
      "unknownModule",
      await q({ sql }, { name: "nil", role: "none" }),
      op(404, { error: wire.unknownModule() }),
      {},
      API,
    );
    // a page is the statement's own: a cursor is refused, and a page without its order and LIMIT is unsupported
    expect((await q({ sql, after: "c1.x" })).status).toBe(fakeQ({ sql, after: "c1.x" }).status);
    const unordered = "SELECT u.code FROM catalog.UseCase u";
    expect((await q({ sql: unordered })).status).toBe(501);
    expect(fakeQ({ sql: unordered }).status).toBe(501);
    expect((await q({ sql, module: undefined })).status).toBe(400);
    same(
      "unsupportedQuery",
      await q({
        sql: "SELECT u.code FROM catalog.UseCase u WHERE u.workArea = 'x' ORDER BY u.code LIMIT 5",
      }),
      op(501, { error: wire.unsupportedQuery() }),
      { open: [".supported"] },
      API,
    );
    same(
      "badRequest (query)",
      await q({ sql: "  " }),
      op(400, { error: wire.badRequest("sql is a string") }),
      {},
      API,
    );
    // The fake refuses what the server refuses, with the same statuses.
    for (const body of [
      { sql: "   " },
      { sql, limit: 0 },
      { sql, limit: 101 },
      { sql, consistency: "eventually" },
      { sql: "x".repeat(4001) },
    ]) {
      expect((await q(body)).status, JSON.stringify(body).slice(0, 60)).toBe(fakeQ(body).status);
    }
    const nope = "SELECT u.code FROM catalog.Nope u ORDER BY u.code LIMIT 5";
    expect((await q({ sql: nope })).status).toBe(fakeQ({ sql: nope }).status);
    expect(
      schemaErrors(
        { error: wire.unavailable() },
        defined(responseSchema("/query", "post", 503), "the 503 schema"),
        doc,
      ),
    ).toEqual([]);
  });

  it("every error the fake models", async () => {
    const act = (
      a: string,
      v: string,
      inputs: Record<string, unknown>,
      who: Parameters<typeof call>[2] = "alice",
      extra = {},
    ) => call(`/api/operate/actions/catalog/${a}/${v}`, { inputs, ...extra }, who);
    same(
      "invalid",
      await act("CorrectSolution", "invoke", { solution: "sol-1" }),
      op(400, { error: wire.invalid() }),
      {},
      { path: `${ACTION}/invoke` },
    );
    same(
      "badRequest",
      await call("/api/operate/audit/changes", { module: "catalog", since: "2026-10-09T14:02:11" }),
      op(400, { error: wire.badRequest() }),
      {},
      { path: "/audit/changes" },
    );
    // An operator the backend lets read but not write (bob, with the rest revoked: carol is no operator).
    await asBob(["read"], async () => {
      same(
        "refused",
        await act("CorrectSolution", "validate", { solution: "sol-1", level: "x" }, "bob"),
        op(403, { error: wire.refused() }),
        {},
        { path: `${ACTION}/validate` },
      );
      same(
        "refused (changes)",
        await call("/api/operate/audit/changes", { module: "catalog" }, "bob"),
        op(403, { error: wire.refused("changes") }),
        {},
        { path: "/audit/changes" },
      );
    });
    same(
      "notFound",
      await act("Nope", "validate", {}),
      op(404, { error: wire.notFound() }),
      {},
      { path: `${ACTION}/validate` },
    );
    same(
      "conflict",
      await act("CorrectSolution", "invoke", { solution: "sol-1", level: "x" }, "alice", {
        expected_revision: { memory: 99 },
      }),
      op(409, { error: wire.conflict() }),
      {},
      { path: `${ACTION}/invoke` },
    );
    same(
      "precondition",
      await act("AddUseCase", "invoke", { code: "uc-pipeline", name: "dup" }),
      op(422, { error: wire.precondition() }),
      {},
      { path: `${ACTION}/invoke` },
    );
    same(
      "signIn",
      await act("CorrectSolution", "validate", {}, "nobody"),
      op(401, { error: wire.signIn() }),
      {},
      { path: `${ACTION}/validate` },
    );
    same(
      "gqlSignIn",
      await gql("{ modules { name } }", undefined, "nobody"),
      op(401, wire.gqlSignIn()),
    );
    same(
      "gqlNotFound",
      await gql("{ solutionList { items { key } } }", undefined, "dave", "catalog"),
      op(404, wire.gqlNotFound()),
    );

    await control({ op: "expire", user: "bob" });
    try {
      same(
        "tokenExpired",
        await act("CorrectSolution", "validate", { solution: "sol-1", level: "x" }, "bob"),
        op(401, { error: wire.tokenExpired() }),
        {},
        { path: `${ACTION}/validate` },
      );
      const meta = await gql("{ modules { name } }", undefined, "bob");
      same("gqlExpired", meta, op(401, wire.gqlExpired()));
      same(
        "gqlExpired (module path)",
        await gql("{ solutionList { items { key } } }", undefined, "bob", "catalog"),
        op(401, wire.gqlExpired()),
      );
    } finally {
      await control({ op: "restore", user: "bob" });
    }

    await control({ op: "outage", backend: "memory", reason: "unreachable" });
    try {
      same(
        "unavailable",
        await act("CorrectSolution", "validate", { solution: "sol-1", level: "x" }),
        op(503, { error: wire.unavailable() }),
        {},
        { path: `${ACTION}/validate` },
      );
      same(
        "gqlUnavailable",
        await gql("{ solutionList { items { key } } }", undefined, "alice", "catalog"),
        op(200, wire.gqlUnavailable("solutionList")),
      );
    } finally {
      await control({ op: "outage", backend: "memory", reason: null });
    }
  });

  it("429: the body and Retry-After of a burst past four in flight", async () => {
    const answers = await Promise.all(
      Array.from({ length: 12 }, () => call("/api/operate/audit/changes", { module: "catalog" })),
    );
    const limited = answers.find((a) => a.status === 429);
    const burst = defined(limited, "a burst of 12 raw calls answered 429 at least once");
    same("tooMany", burst, op(429, { error: wire.tooMany() }), {}, { path: "/audit/changes" });
    expect(burst.headers.get("retry-after")).toBe("1");
  });
});
