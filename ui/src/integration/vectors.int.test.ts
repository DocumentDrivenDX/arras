// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { checkScalar } from "../lib/inputs";
import { call, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";

// The shared input vectors sent to the real server. The sandbox module declares no action with typed
// inputs (tests/typed_module.py is reachable from pytest, not from the dev host), so timestamps are
// checked through the one typed field the operator surface takes from a person: the audit's
// `since`/`until`, which the server reads as it reads a timestamp input (fromisoformat, offset
// required). Integers, decimals, binary and booleans are checked against the server's conversion by
// tests/test_inputs_vectors.py, and against the UI by src/test/inputs.vectors.test.ts.
withDevHost();

const { vectors } = JSON.parse(
  readFileSync(resolve(REPO_ROOT, "tests/vectors/inputs.json"), "utf8"),
) as {
  vectors: { type: string; value: string; ok: boolean }[];
};
const stamps = vectors.filter((v) => v.type === "timestamp");

describe("timestamps: the form and the server agree on every shared vector", () => {
  it.each(stamps.map((v) => [v.value, v.ok] as const))("%j ok=%s", async (value, ok) => {
    const ui = checkScalar("timestamp", value).error === undefined;
    expect(ui).toBe(ok);
    for (const field of ["since", "until"]) {
      const r = await call<{ error: { type: string } }>("/api/operate/audit/changes", {
        module: "catalog",
        [field]: value,
        limit: 1,
      });
      expect({ field, status: r.status }).toEqual({ field, status: ok ? 200 : 400 });
      if (!ok) expect(r.body.error.type).toBe("BadRequest");
    }
  });

  it("every timestamp the form accepts is one the server accepts", async () => {
    const accepted = stamps.filter((v) => checkScalar("timestamp", v.value).error === undefined);
    expect(accepted.length).toBeGreaterThan(3);
    // One at a time: a burst of raw calls past four in flight is answered 429 (see limits.int.test.ts).
    const statuses: number[] = [];
    for (const v of accepted)
      statuses.push(
        (await call("/api/operate/audit/changes", { module: "catalog", since: v.value, limit: 1 }))
          .status,
      );
    expect(statuses).toEqual(accepted.map(() => 200));
  });
});
