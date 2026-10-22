// SPDX-License-Identifier: MIT OR Apache-2.0
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { APPLY_KEYS, invalidateAfterApply } from "../kit";

// One invalidation scheme for both modes (SD-013 D6): an applied action makes every family of reads
// that can show it stale, whichever mode ran it.
describe("invalidateAfterApply", () => {
  it("marks the browser's, the console's and the search reads stale and leaves the registry alone", async () => {
    const qc = new QueryClient();
    const keys: unknown[][] = [
      ["gb", "node", "catalog", "Solution", "s-1"],
      ["gb", "search", "k"],
      ["list", "catalog", "Solution"],
      ["graph", "catalog"],
      ["entity", "catalog", "Solution", "s-1"],
      ["status"],
      ["audit", "catalog"],
      ["meta"],
    ];
    for (const key of keys) qc.setQueryData(key, 1);
    await invalidateAfterApply(qc);
    const stale = (key: unknown[]) => qc.getQueryState(key)?.isInvalidated;
    for (const key of keys.slice(0, -1)) expect(stale(key), key.join("/")).toBe(true);
    expect(stale(["meta"])).toBe(false);
    expect(APPLY_KEYS).toContain("gb");
  });
});
