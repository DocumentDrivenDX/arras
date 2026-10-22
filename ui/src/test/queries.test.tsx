// SPDX-License-Identifier: MIT OR Apache-2.0
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasProvider } from "../api/context";
import { useAuditProbe, useMeta, useModule, useRefresh, useStatus } from "../api/queries";
import { encodeField } from "../lib/inputs";
import { defined } from "./defined";
import { err, type FakeApi, json, stage, wire } from "./fake";
import { qc } from "./render";

let api: FakeApi;
beforeEach(() => {
  api = stage();
});
const wrapper = ({ children }: { children: ReactNode }) => (
  <ArrasProvider queryClient={qc()}>{children}</ArrasProvider>
);
const probe = async (reply: ReturnType<typeof json> | (() => never)) => {
  api.on((r) =>
    r.path.endsWith("/audit/changes") ? (typeof reply === "function" ? reply() : reply) : undefined,
  );
  const { result } = renderHook(() => useAuditProbe("catalog"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  return result.current.data;
};

describe("useAuditProbe: is the audit served for this module?", () => {
  it.each([
    ["a page", json(200, wire.page([])), "ok"],
    ["501", err(501, wire.unsupported()), "unsupported"],
    ["403 no access", err(403, wire.refused("changes")), "refused"],
    ["403 not offered", err(403, wire.notOffered()), "refused"],
    ["401", err(401, wire.tokenExpired()), "sign_in"],
    ["503", err(503, wire.unavailable()), "error"],
  ] as const)("%s answers %s", async (_n, reply, want) => {
    expect(await probe(reply)).toBe(want);
    expect(
      defined(api.posts(/audit\/changes$/)[0], "api.posts(/audit\\/changes$/)[0]").body,
    ).toEqual({ module: "catalog", limit: 1 });
  });

  it("a dropped connection is an error, not a hidden area", async () => {
    expect(
      await probe(() => {
        throw new TypeError("fetch failed");
      }),
    ).toBe("error");
  });

  it("does not ask without a module", async () => {
    const { result } = renderHook(() => useAuditProbe(undefined), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(api.log).toHaveLength(0);
  });
});

describe("module, status and refresh hooks", () => {
  it("useModule finds the module by name and nothing without one", async () => {
    const { result } = renderHook(
      () => ({ a: useModule("catalog"), b: useModule(undefined), c: useModule("nope") }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.a.module?.name).toBe("catalog"));
    expect(result.current.b.module).toBeUndefined();
    expect(result.current.c.module).toBeUndefined();
  });

  it("useStatus reads the backends; useRefresh reads everything again", async () => {
    const { result } = renderHook(() => ({ s: useStatus(), refresh: useRefresh() }), { wrapper });
    await waitFor(() =>
      expect(result.current.s.data?.map((x) => x.backend)).toEqual(["memory", "memory_replica"]),
    );
    const before = api.log.length;
    await result.current.refresh();
    await waitFor(() => expect(api.log.length).toBeGreaterThan(before));
  });
});

describe("inputs: records", () => {
  const rec = (cardinality: "one" | "many") => ({
    name: "r",
    type: "Terms",
    kind: "record" as const,
    cardinality,
  });
  it("a many record is a JSON array of objects, nothing else", () => {
    expect(encodeField(rec("many"), '[{"a":1},{"b":2}]').value).toEqual([{ a: 1 }, { b: 2 }]);
    expect(encodeField(rec("many"), "[1, 2]").error).toBe("a JSON array of objects");
    expect(encodeField(rec("many"), "[[]]").error).toBe("a JSON array of objects");
    expect(encodeField(rec("many"), '{"a":1}').error).toBe("a JSON array of objects");
    expect(encodeField(rec("many"), "[").error).toBe("valid JSON");
    expect(encodeField(rec("many"), ['[{"a":', "1}]"]).value).toEqual([{ a: 1 }]);
  });
  it("one record is an object; null and a list are not", () => {
    expect(encodeField(rec("one"), "null").error).toBe("a JSON object");
    expect(encodeField(rec("one"), "[]").error).toBe("a JSON object");
    expect(encodeField(rec("one"), "{").error).toBe("valid JSON");
  });
  it("a ref is its key, trimmed; an unknown scalar type is passed as typed; a many list may come as lines", () => {
    expect(
      encodeField({ name: "s", type: "Solution", kind: "ref", cardinality: "one" }, " sol-1 ")
        .value,
    ).toBe("sol-1");
    expect(
      encodeField({ name: "x", type: "geometry", kind: "scalar", cardinality: "one" }, " p ").value,
    ).toBe(" p ");
    expect(
      encodeField({ name: "t", type: "boolean", kind: "scalar", cardinality: "many" }, [
        "true",
        "",
        "false",
      ]).value,
    ).toEqual([true, false]);
    expect(
      encodeField({ name: "t", type: "string", kind: "scalar", cardinality: "one" }, ["a", "b"])
        .value,
    ).toBe("a");
    expect(
      encodeField({ name: "t", type: "string", kind: "scalar", cardinality: "optional" }, []).value,
    ).toBeUndefined();
  });
});

describe("useMeta: the one shared read signs the viewer in once", () => {
  it("an expired token on both of its requests calls onUnauthorized once, and the read fails as a sign-in", async () => {
    api.on((r) => (r.path.endsWith("/console/graphql") ? err(401, wire.gqlExpired()) : undefined));
    const onUnauthorized = vi.fn();
    const signed = ({ children }: { children: ReactNode }) => (
      <ArrasProvider queryClient={qc()} onUnauthorized={onUnauthorized}>
        {children}
      </ArrasProvider>
    );
    const { result } = renderHook(() => useMeta(), { wrapper: signed });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.kind).toBe("sign_in");
    expect(api.posts(/\/console\/graphql$/)).toHaveLength(2);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
