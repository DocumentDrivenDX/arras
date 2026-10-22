// SPDX-License-Identifier: MIT OR Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import { createClient } from "../api/client";
import { ApiError } from "../api/errors";
import { encodeField } from "../lib/inputs";
import { defined } from "./defined";
import { err, type FakeApi, json, stage, validation, wire } from "./fake";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const make = (onUnauthorized = vi.fn()) => ({
  c: createClient({ operateBase: "/api/operate", consoleBase: "/api/console", onUnauthorized }),
  onUnauthorized,
});
const reject = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: unknown) => e as ApiError,
  );
const respond = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });

describe("client: an expired token in every form it arrives in", () => {
  let api: FakeApi;
  const meta = (r: { path: string }) => r.path.endsWith("/console/graphql");

  it("a 200 GraphQL answer whose error says token_expired is a sign-in and calls onUnauthorized", async () => {
    api = stage();
    api.on((r) => (meta(r) ? json(200, wire.gqlExpiredField()) : undefined));
    const { c, onUnauthorized } = make();
    const e = await reject(c.meta());
    expect(e).toBeInstanceOf(ApiError);
    expect(defined(e, "e").kind).toBe("sign_in");
    expect(defined(e, "e").reason).toBe("token_expired");
    expect(defined(e, "e").backend).toBe("memory");
    expect(onUnauthorized).toHaveBeenCalledTimes(1); // the meta read is two requests: one sign-in
  });

  it("a 401 GraphQL answer with the reason is a sign-in", async () => {
    api = stage();
    api.on((r) => (meta(r) ? json(401, wire.gqlExpired()) : undefined));
    const { c, onUnauthorized } = make();
    const e = await reject(c.meta());
    expect(defined(e, "e").kind).toBe("sign_in");
    expect(defined(e, "e").status).toBe(401);
    expect(defined(e, "e").reason).toBe("token_expired");
    expect(onUnauthorized).toHaveBeenCalledTimes(1); // the meta read is two requests: one sign-in
  });

  it("a 401 on a module path, and a 401 whose body has the per-field form, are sign-ins", async () => {
    api = stage();
    api.on((r) =>
      r.path.endsWith("/graphql/catalog")
        ? json(401, wire.gqlExpiredField("solutionList"))
        : undefined,
    );
    const { c, onUnauthorized } = make();
    const e = await reject(c.moduleQuery("catalog", "{ solutionList { items { key } } }"));
    expect(defined(e, "e").kind).toBe("sign_in");
    expect(defined(e, "e").backend).toBe("memory");
    api.handlers = [];
    api.on((r) => (r.path.endsWith("/graphql/catalog") ? json(401, wire.gqlExpired()) : undefined));
    expect(
      defined(
        await reject(c.moduleQuery("catalog", "{ solutionList { items { key } } }")),
        '(await reject(c.moduleQuery("catalog", "{ solutionList { items { key } } }")))',
      ).kind,
    ).toBe("sign_in");
    expect(onUnauthorized).toHaveBeenCalledTimes(2);
  });

  it("a module read refused for an expired token is a sign-in, even with partial data", async () => {
    api = stage();
    api.on((r) =>
      r.path.endsWith("/graphql/catalog")
        ? json(200, {
            data: { solutionList: { items: [] } },
            errors: [
              { message: "refused", extensions: { code: "REFUSED", reason: "token_expired" } },
            ],
          })
        : undefined,
    );
    const { c, onUnauthorized } = make();
    const e = await reject(c.moduleQuery("catalog", "{ solutionList { items { key } } }"));
    expect(defined(e, "e").kind).toBe("sign_in");
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("a 401 from the operator surface is a sign-in; a 401 for no person at all too", async () => {
    api = stage();
    api.on((r) =>
      r.path.endsWith("/validate")
        ? err(401, wire.tokenExpired())
        : r.path.endsWith("/changes")
          ? err(401, wire.signIn())
          : undefined,
    );
    const { c, onUnauthorized } = make();
    expect(
      defined(
        await reject(c.validate("catalog", "catalog.CorrectSolution", { inputs: {} })),
        '(await reject(c.validate("catalog", "catalog.CorrectSolution", { inputs: {} })))',
      ).kind,
    ).toBe("sign_in");
    expect(
      defined(
        await reject(c.changes({ module: "catalog" })),
        '(await reject(c.changes({ module: "catalog" })))',
      ).kind,
    ).toBe("sign_in");
    expect(onUnauthorized).toHaveBeenCalledTimes(2);
  });

  it("not found and no access stay distinct and do not ask for a sign-in", async () => {
    api = stage();
    api.on((r) =>
      r.path.endsWith("/graphql/catalog")
        ? json(200, {
            data: { solutionList: null },
            errors: [
              {
                message: "refused",
                extensions: { code: "REFUSED", reason: "no_access", backend: "memory" },
              },
            ],
          })
        : undefined,
    );
    api.on((r) => (r.path.endsWith("/validate") ? err(403, wire.refused()) : undefined));
    const { c, onUnauthorized } = make();
    const nf = await reject(c.moduleQuery("elsewhere", "{ xList { items { key } } }"));
    expect(defined(nf, "nf").kind).toBe("not_found");
    // A refused field inside a 200 is data with an error, not a thrown sign-in; the error keeps its reason.
    const r = await c.moduleQuery("catalog", "{ solutionList { items { key } } }");
    expect(r.errors[0]).toMatchObject({ code: "REFUSED", reason: "no_access", backend: "memory" });
    expect(
      defined(
        await reject(c.validate("catalog", "catalog.CorrectSolution", { inputs: {} })),
        '(await reject(c.validate("catalog", "catalog.CorrectSolution", { inputs: {} })))',
      ).kind,
    ).toBe("no_access");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("keeps extensions.reason, backend and path on GraphQL errors, and the revision", async () => {
    api = stage();
    api.on((r) =>
      r.path.endsWith("/graphql/catalog")
        ? json(200, wire.gqlUnavailable("solutionList"))
        : undefined,
    );
    const { c } = make();
    const r = await c.moduleQuery("catalog", "{ solutionList { items { key } } }");
    expect(r.errors).toEqual([
      {
        message: "memory unavailable (unreachable): memory cannot serve query",
        code: "UNAVAILABLE",
        reason: "unreachable",
        backend: "memory",
        path: ["solutionList"],
      },
    ]);
    expect(r.revision).toEqual({ memory: 1 });
  });

  it("the meta query with no data throws its first error with code, reason and backend", async () => {
    api = stage();
    api.on((r) =>
      meta(r)
        ? json(200, {
            data: null,
            errors: [
              {
                message: "down",
                extensions: { code: "UNAVAILABLE", backend: "memory", reason: "unreachable" },
              },
            ],
          })
        : undefined,
    );
    const { c } = make();
    const e = await reject(c.meta());
    expect(defined(e, "e").kind).toBe("unavailable");
    expect(defined(e, "e").backend).toBe("memory");
    api.handlers = [];
    api.on((r) => (meta(r) ? json(200, { data: null }) : undefined));
    expect(defined(await reject(c.meta()), "(await reject(c.meta()))").message).toBe("no data");
  });

  it("status() answers [] when the read has no data", async () => {
    api = stage();
    api.on((r) => (meta(r) ? json(200, { data: null, errors: [{ message: "x" }] }) : undefined));
    const { c } = make();
    expect(await c.status()).toEqual([]);
  });
});

describe("client: transport", () => {
  it("a network failure is a network error, not a server answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("fetch failed"))),
    );
    const { c } = make();
    const a = await reject(c.validate("catalog", "catalog.A", { inputs: {} }));
    expect(defined(a, "a").kind).toBe("network");
    expect(defined(a, "a").status).toBe(0);
    const b = await reject(c.meta());
    expect(defined(b, "b").kind).toBe("network");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject("not an error")),
    );
    expect(defined(await reject(c.version()), "(await reject(c.version()))").message).toBe(
      "network error",
    );
  });

  it("a non-JSON error body still answers by status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("oops", { status: 502 })),
    );
    const { c } = make();
    const e = await reject(c.loads({ module: "catalog" }));
    expect(defined(e, "e").status).toBe(502);
    expect(defined(e, "e").kind).toBe("other");
  });

  it("puts the action's short name and the module in the path, encoded, and the body in the POST", async () => {
    const api = stage();
    const { c } = make();
    api.on((r) => (r.path.includes("/actions/") ? json(200, validation()) : undefined));
    await c.validate("catalog", "catalog.CorrectSolution", { inputs: { a: 1 } });
    await c.batch("cat alog", "Other", { items: [] });
    expect(defined(api.log[0], "api.log[0]").path).toBe(
      "/api/operate/actions/catalog/CorrectSolution/validate",
    );
    expect(defined(api.log[1], "api.log[1]").url).toBe(
      "/api/operate/actions/cat%20alog/Other/batch",
    );
    expect(defined(api.log[0], "api.log[0]").headers["content-type"]).toBe("application/json");
    expect(defined(api.log[0], "api.log[0]").body).toEqual({ inputs: { a: 1 } });
  });

  it("trims trailing slashes from the bases", async () => {
    const api = stage();
    const c = createClient({
      operateBase: "http://h/api/operate//",
      consoleBase: "http://h/api/console/",
    });
    await c.version();
    await c.status();
    expect(api.log.map((r) => r.url)).toEqual([
      "http://h/api/operate/version",
      "http://h/api/console/graphql",
    ]);
    expect(defined(api.log[0], "api.log[0]").headers["content-type"]).toBeUndefined(); // a GET carries no body
  });

  it("reads count toward the bound of four in flight too", async () => {
    let live = 0;
    let peak = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        live++;
        peak = Math.max(peak, live);
        await new Promise((r) => setTimeout(r, 5));
        live--;
        return respond(200, { data: { status: [] } });
      }),
    );
    const { c } = make();
    await Promise.all([
      ...Array.from({ length: 6 }, () => c.status()),
      ...Array.from({ length: 6 }, () => c.loads({ module: "m" })),
    ]);
    expect(peak).toBe(4);
  });

  it("a 429 waits for Retry-After seconds, not less", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(429, { error: wire.tooMany() }, { "retry-after": "3" }))
      .mockResolvedValueOnce(respond(200, validation()));
    vi.stubGlobal("fetch", fetchMock);
    const { c } = make();
    const p = c.validate("catalog", "catalog.A", { inputs: {} });
    await vi.advanceTimersByTimeAsync(2900);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(200);
    await expect(p).resolves.toMatchObject({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a 429 without Retry-After waits one second", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(429, { error: wire.tooMany() }))
      .mockResolvedValueOnce(respond(200, validation()));
    vi.stubGlobal("fetch", fetchMock);
    const { c } = make();
    const p = c.validate("catalog", "catalog.A", { inputs: {} });
    await vi.advanceTimersByTimeAsync(900);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(200);
    await expect(p).resolves.toMatchObject({ ok: true });
  });

  it("gives up after three retries and reports the 429 with its Retry-After", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async () =>
      respond(429, { error: wire.tooMany() }, { "retry-after": "1" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { c } = make();
    const p = reject(c.invoke("catalog", "catalog.A", { inputs: {} }));
    await vi.advanceTimersByTimeAsync(5000);
    const e = await p;
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(defined(e, "e").kind).toBe("rate_limited");
    expect(defined(e, "e").retryAfter).toBe(1);
  });
});

describe("client: integers at the 2^53 boundary", () => {
  const spec = { name: "n", type: "integer", kind: "scalar" as const, cardinality: "one" as const };
  it.each([
    ["9007199254740991", 9007199254740991],
    ["-9007199254740991", -9007199254740991],
    ["9007199254740992", "9007199254740992"],
    ["-9007199254740992", "-9007199254740992"],
    ["9007199254740993", "9007199254740993"],
    ["+12", 12],
  ])("%s is sent as %o", async (text, wireValue) => {
    expect(encodeField(spec, text).value).toBe(wireValue);
    const api = stage();
    api.on((r) => (r.path.endsWith("/validate") ? json(200, validation()) : undefined));
    const { c } = make();
    await c.validate("m", "m.A", { inputs: { n: encodeField(spec, text).value } });
    // The JSON on the wire keeps every digit: a number within 53 bits, text beyond.
    expect(defined(api.log[0], "api.log[0]").body.inputs.n).toBe(wireValue);
  });
});
