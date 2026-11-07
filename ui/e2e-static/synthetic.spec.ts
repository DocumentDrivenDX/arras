// SPDX-License-Identifier: MIT OR Apache-2.0
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The static host over a synthetic graph (tools/gen_synthetic_graph.py): 1,000 documents of up to 8 KB, 24 topics,
// one hub with 1,000 edges, about 6,000 records. It measures load, search and the hub's paging in Chromium and
// writes them to test-results/arras-static/metrics.json (ADR-031 records them). The bounds asserted are loose;
// the numbers are what the report cites.

const metrics: Record<string, unknown> = {};
test.afterAll(() => {
  mkdirSync("test-results/arras-static", { recursive: true });
  writeFileSync("test-results/arras-static/metrics.json", `${JSON.stringify(metrics, null, 2)}\n`);
});

const group = (page: Page, name: RegExp) =>
  page.getByRole("heading", { level: 3, name }).locator("xpath=ancestor::section[1]");

/** The staged site's files, as stored and gzipped (what a static host serves to a browser that accepts it). */
function fileSizes(dir: string): Record<string, { bytes: number; gzipBytes: number }> {
  const out: Record<string, { bytes: number; gzipBytes: number }> = {};
  for (const name of readdirSync(dir, { recursive: true, encoding: "utf8" })) {
    const path = `${dir}/${name}`;
    if (statSync(path).isFile())
      out[name] = { bytes: statSync(path).size, gzipBytes: gzipSync(readFileSync(path)).length };
  }
  return out;
}

async function heapMb(page: Page): Promise<number> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("HeapProfiler.collectGarbage");
  const { usedSize } = (await cdp.send("Runtime.getHeapUsage")) as { usedSize: number };
  return Math.round(usedSize / 1048576);
}

test("loads a thousand-node graph and answers a search and the hub's pages", async ({ page }) => {
  test.setTimeout(120_000);
  const t0 = Date.now();
  await page.goto("/synthetic/#/explore/synthetic");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Synthetic atlas");
  await expect(page.locator(".gb-type-card-t").first()).toBeVisible();
  metrics.loadToEntryMs = Date.now() - t0;
  metrics.files = fileSizes(".static-sites/synthetic");
  const navigation = await page.evaluate(() => {
    const n = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    return {
      domContentLoadedMs: Math.round(n.domContentLoadedEventEnd),
      loadMs: Math.round(n.loadEventEnd),
    };
  });
  Object.assign(metrics, navigation);
  metrics.heapAfterLoadMb = await heapMb(page);

  // search: one word and two words, to the first hit
  const box = page
    .getByRole("searchbox")
    .or(page.getByLabel(/^Search/))
    .first();
  let t = Date.now();
  await box.fill("needle07");
  await expect(page.locator("a.gb-hit").first()).toBeVisible();
  metrics.searchOneWordMs = Date.now() - t; // includes the 250 ms pause before a search is asked
  const hits = await page.locator("a.gb-hit").count();
  expect(hits).toBeGreaterThan(5);
  t = Date.now();
  await box.fill("needle07 pipeline");
  await expect(page.locator("a.gb-hit").first()).toBeVisible();
  metrics.searchTwoWordsMs = Date.now() - t;

  // the hub: every one of its 1,000 edges reached through the interface
  t = Date.now();
  await page.goto("/synthetic/#/explore/synthetic/Topic/hub");
  await expect(page.getByRole("heading", { level: 1, name: "Hub" })).toBeVisible();
  const list = group(page, /Covered by/);
  await expect(list).toContainText("100 or more");
  metrics.hubOpenMs = Date.now() - t;
  t = Date.now();
  let clicks = 0;
  for (;;) {
    const more = list.getByRole("button", { name: /Show more/ });
    if ((await more.count()) === 0) break;
    const before = await list.getByRole("link").count();
    await more.first().click();
    await expect
      .poll(() => list.getByRole("link").count(), { timeout: 20_000 })
      .toBeGreaterThan(before);
    clicks += 1;
    if (clicks > 200) throw new Error("the hub did not end");
  }
  metrics.hubAllEdgesMs = Date.now() - t;
  metrics.hubShowMoreClicks = clicks;
  await expect(list.getByRole("link")).toHaveCount(1000);
  metrics.heapAfterHubMb = await heapMb(page);
});

test("a Markdown body is drawn as elements, and the page is accessible", async ({ page }) => {
  await page.goto("/synthetic/#/explore/synthetic/Doc/doc-0001");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Document 0001");
  const body = page.locator(".gb-md");
  await expect(body.locator("h5")).toHaveText("Summary");
  await expect(body.locator("li strong")).toHaveText("Point");
  await expect(body.locator("table th").first()).toHaveText("Criterion");
  expect(await body.locator("script, img, iframe").count()).toBe(0);
  const r = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(r.violations.map((v) => v.id)).toEqual([]);
});
