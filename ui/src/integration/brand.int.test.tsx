// SPDX-License-Identifier: MIT OR Apache-2.0
import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_BRAND, readBrandMeta } from "../lib/brand";
import { server, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";

// The page the real dev host serves carries the brand's title and the meta tag the app reads
// (SD-013, Branding). It needs the built UI (`npm run build`): the host serves `ui/dist`. A missing
// build fails the test; it is never skipped, so the meta path is always checked.
withDevHost();

describe("the served page's brand", () => {
  it("has the built UI to serve (run `npm run build` first)", () => {
    expect(existsSync(join(REPO_ROOT, "ui/dist/index.html"))).toBe(true);
  });

  it("carries the default brand's meta tag, which readBrandMeta reads, and its title", async () => {
    const res = await fetch(`${server().base}/`);
    expect(res.status).toBe(200);
    const doc = new DOMParser().parseFromString(await res.text(), "text/html");
    const meta = doc.querySelector('meta[name="arras-brand"]');
    expect(meta).not.toBeNull();
    expect(JSON.parse(meta?.getAttribute("content") ?? "null")).toEqual({
      name: DEFAULT_BRAND.name,
    });
    expect(readBrandMeta(doc)).toEqual(DEFAULT_BRAND);
    expect(doc.title).toBe(DEFAULT_BRAND.name);
  });
});
