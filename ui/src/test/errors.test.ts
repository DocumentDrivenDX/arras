// SPDX-License-Identifier: MIT OR Apache-2.0
import { describe, expect, it } from "vitest";
import { ApiError, describeError, type ErrorKind } from "../api/errors";
import { defined } from "./defined";
import { wire } from "./fake";

// Every status x type x reason the two surfaces answer (CONTRACT-006, CONTRACT-009), with the kind the
// UI files it under and the words it shows. The bodies are the drift-guarded `wire` fixtures.
const rows: [string, ApiError, ErrorKind, string, RegExp][] = [
  [
    "401 token_expired (operate)",
    new ApiError(401, wire.tokenExpired()),
    "sign_in",
    "Sign in again",
    /token_expired/,
  ],
  [
    "401 no person (operate)",
    new ApiError(401, wire.signIn()),
    "sign_in",
    "Sign in again",
    /Sign in, then retry/,
  ],
  [
    "200 GraphQL token_expired",
    new ApiError(200, {
      type: "Refused",
      code: "REFUSED",
      reason: "token_expired",
      message: "memory refused catalog",
    }),
    "sign_in",
    "Sign in again",
    /token_expired/,
  ],
  [
    "403 Refused no_access",
    new ApiError(403, wire.refused()),
    "no_access",
    "No access",
    /\(no_access\)/,
  ],
  [
    "403 GraphQL REFUSED",
    new ApiError(403, { code: "REFUSED", message: "refused" }),
    "no_access",
    "No access",
    /no_access/,
  ],
  [
    "200 GraphQL REFUSED",
    new ApiError(200, { code: "REFUSED", message: "refused", reason: "no_access" }),
    "no_access",
    "No access",
    /no_access/,
  ],
  [
    "403 not offered",
    new ApiError(403, wire.notOffered()),
    "not_offered",
    "Not offered",
    /does not offer/,
  ],
  [
    "403 origin",
    new ApiError(403, { type: "Forbidden", message: "origin not allowed" }),
    "forbidden",
    "Request failed (403)",
    /origin not allowed/,
  ],
  ["404 operate", new ApiError(404, wire.notFound()), "not_found", "Not found", /cannot read it/],
  [
    "404 GraphQL",
    new ApiError(404, { code: "NOT_FOUND", message: "no such module" }),
    "not_found",
    "Not found",
    /cannot read it/,
  ],
  [
    "200 GraphQL NOT_FOUND",
    new ApiError(200, { code: "NOT_FOUND", message: "no such module" }),
    "not_found",
    "Not found",
    /cannot read it/,
  ],
  [
    "409 revision",
    new ApiError(409, wire.conflict()),
    "revision_conflict",
    "Conflict",
    /conflict \(revision\)/,
  ],
  [
    "409 other",
    new ApiError(409, { type: "Conflict", message: "conflict (version)", reason: "version" }),
    "conflict",
    "Conflict",
    /version/,
  ],
  [
    "409 NotYetCurrent",
    new ApiError(409, {
      type: "NotYetCurrent",
      message: "the replica has not reached that position",
    }),
    "conflict",
    "Conflict",
    /not reached/,
  ],
  [
    "400 Invalid",
    new ApiError(400, wire.invalid()),
    "invalid",
    "Invalid request",
    /inputs\.level: a value is required/,
  ],
  [
    "400 BadRequest",
    new ApiError(400, wire.badRequest()),
    "invalid",
    "Invalid request",
    /needs an offset/,
  ],
  [
    "422 PreconditionFailed",
    new ApiError(422, wire.precondition()),
    "precondition",
    "A precondition failed",
    /fresh: a use case with that code exists/,
  ],
  ["429", new ApiError(429, wire.tooMany(), 1), "rate_limited", "Too many requests", /retried/],
  ["501", new ApiError(501, wire.unsupported()), "unsupported", "Not supported", /not supported/],
  [
    "503 with backend",
    new ApiError(503, wire.unavailable("memory", "unreachable")),
    "unavailable",
    "Backend unavailable",
    /^memory is unavailable \(unreachable\)\.$/,
  ],
  [
    "503 without backend",
    new ApiError(503, { type: "Unavailable", message: "no backend" }),
    "unavailable",
    "Backend unavailable",
    /^A backend is unavailable\.$/,
  ],
  [
    "200 GraphQL UNAVAILABLE",
    new ApiError(200, {
      code: "UNAVAILABLE",
      backend: "memory_replica",
      reason: "migration_failed",
      message: "x",
    }),
    "unavailable",
    "Backend unavailable",
    /memory_replica is unavailable \(migration_failed\)/,
  ],
  [
    "0 network",
    new ApiError(0, { type: "Network", message: "fetch failed" }),
    "network",
    "Network error",
    /could not be reached \(fetch failed\)/,
  ],
  [
    "500",
    new ApiError(500, { type: "InternalError", message: "internal error" }),
    "other",
    "Request failed (500)",
    /internal error/,
  ],
  [
    "200 other GraphQL",
    new ApiError(200, { code: "COST_EXCEEDED", message: "too many fields" }),
    "other",
    "Request failed (200)",
    /too many fields/,
  ],
];

describe("errors: kind and words by status, type and reason (CONTRACT-009)", () => {
  it.each(rows)("%s", (_name, e, kind, title, detail) => {
    expect(e.kind).toBe(kind);
    const d = describeError(e);
    expect(d.title).toBe(title);
    expect(d.detail).toMatch(detail);
  });

  it("keeps the body's fields and the Retry-After", () => {
    const e = new ApiError(429, wire.tooMany(), 2);
    expect(e.retryAfter).toBe(2);
    const u = new ApiError(503, wire.unavailable("memory_replica", "access_denied"));
    expect([u.backend, u.reason, u.type]).toEqual([
      "memory_replica",
      "access_denied",
      "Unavailable",
    ]);
    const v = new ApiError(400, wire.invalid());
    expect(v.violations).toHaveLength(1);
    expect(
      defined(
        new ApiError(422, wire.precondition()).failures[0],
        "new ApiError(422, wire.precondition()).failures[0]",
      ).id,
    ).toBe("fresh");
    expect(new ApiError(418, {}).message).toBe("request failed (418)");
    expect(new ApiError(418, {}).type).toBe("Error");
  });

  it("a not-offered refusal is told apart from no access only by its missing reason", () => {
    expect(
      new ApiError(403, { type: "Refused", message: "not offered", reason: "no_access" }).kind,
    ).toBe("no_access");
    expect(new ApiError(403, { type: "Refused", message: "no access" }).kind).toBe("no_access");
  });

  it("describes something that is not an ApiError", () => {
    expect(describeError(new Error("boom"))).toEqual({
      title: "Something went wrong",
      detail: "boom",
    });
    expect(describeError("text")).toEqual({ title: "Something went wrong", detail: "text" });
  });
});
