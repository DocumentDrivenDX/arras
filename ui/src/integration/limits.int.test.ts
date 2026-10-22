// SPDX-License-Identifier: MIT OR Apache-2.0
import { afterEach, describe, expect, it, vi } from "vitest";
import { defined } from "../test/defined";
import { call, client, server, withDevHost } from "./harness";

// CONTRACT-009's bound of four requests in flight per person, provoked for real: the server's 429 and
// the client's backoff. The fetch spy passes every call through to the dev host; it only counts.
withDevHost();
afterEach(() => vi.restoreAllMocks());

const changes = (n: number) => Array.from({ length: n }, () => ({ module: "catalog", limit: 50 }));

describe("in-flight bound and 429 (CONTRACT-009)", () => {
  it("a burst of raw calls past four in flight is answered 429 with Retry-After", async () => {
    const answers = await Promise.all(
      changes(12).map((b) => call("/api/operate/audit/changes", b)),
    );
    const limited = answers.filter((a) => a.status === 429);
    const one = defined(limited[0], "a 429 answer");
    expect(limited.length).toBeGreaterThan(0);
    expect(one.headers.get("retry-after")).toBe("1");
    expect(one.body).toEqual({
      error: { type: "TooManyRequests", message: "too many requests" },
    });
  });

  it("one client never has more than four in flight, so it is never refused", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    const c = client("alice");
    const pages = await Promise.all(changes(16).map((q) => c.changes(q)));
    expect(pages).toHaveLength(16);
    const statuses = await Promise.all(
      spy.mock.results.map(async (r) => ((await r.value) as Response).status),
    );
    expect(statuses.filter((s) => s === 429)).toHaveLength(0);
  });

  it("two consoles of one person exceed the bound: the 429s are retried after Retry-After and every call succeeds", async (ctx) => {
    for (let burst = 0; burst < 5; burst++) {
      vi.restoreAllMocks();
      const spy = vi.spyOn(globalThis, "fetch");
      const a = client("bob");
      const b = client("bob");
      const started = Date.now();
      const pages = await Promise.all([
        ...changes(8).map((q) => a.changes(q)),
        ...changes(8).map((q) => b.changes(q)),
      ]);
      expect(pages.every((p) => Array.isArray(p.items))).toBe(true);
      const statuses = await Promise.all(
        spy.mock.results.map(async (r) => ((await r.value) as Response).status),
      );
      const limited = statuses.filter((s) => s === 429).length;
      if (limited === 0) continue; // the two never overlapped past four this time: burst again
      expect(spy.mock.calls.length).toBe(16 + limited); // each 429 was sent again, and nothing else
      expect(statuses.filter((s) => s === 200)).toHaveLength(16);
      expect(Date.now() - started).toBeGreaterThanOrEqual(1000); // after waiting Retry-After (1 s)
      expect(String(defined(spy.mock.calls[0], "the first fetch")[0])).toBe(
        `${server().base}/api/operate/audit/changes`,
      );
      return;
    }
    ctx.skip(
      "five bursts never overlapped past four in flight; the backoff is covered in src/test/client.test.ts",
    );
  });
});
