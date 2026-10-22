// SPDX-License-Identifier: MIT OR Apache-2.0
import { expect, type Page, test } from "@playwright/test";
import { defined } from "../src/test/defined";

// The Query area (OPR-16, OPR-17; US-077, US-078) through the real UI against the dev host: a query is run
// with the keyboard, read as a grid, run again from the history, and nothing is kept in the browser.
// The dev host's sandbox: catalog with 14 use cases and 11 solutions (other specs on the shared host may add use cases); alice reads and writes; a made-up person with role viewer reads only (carol and dave are not operators).

const CODES = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 50";
const posts = (page: Page) => {
  const seen: { url: string; body: string }[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/operate/query"))
      seen.push({ url: r.url(), body: r.postData() ?? "" });
  });
  return seen;
};
const history = (page: Page) => page.getByTestId("query-history").getByTestId("history-entry");

test("a builder runs a query from the keyboard, reads the grid, and reuses it from the history", async ({
  page,
}) => {
  const sent = posts(page);
  await page.goto("/#/catalog/model");
  await page.getByLabel("Person").selectOption("alice");
  await page.getByRole("tab", { name: "Query" }).click();
  await expect(page).toHaveURL(/#\/operate\/catalog\/query$/);

  const editor = page.getByLabel("Query (Weft SQL, read-only)");
  await expect(editor).toHaveAttribute("spellcheck", "false");
  await editor.fill(CODES);
  await expect(page.getByTestId("query-chars")).toContainText(`${CODES.length} / 4,000`);
  await editor.press("Control+Enter");

  const grid = page.getByRole("table");
  await expect(grid.getByRole("cell", { name: /^uc-pipeline(?: Open .*)?$/ })).toBeVisible();
  await expect(grid.getByRole("columnheader")).toHaveText(["code", "name"]);
  await expect(page.getByTestId("query-count-rows")).toHaveText(/^\d+ rows$/);
  await expect(page.getByTestId("freshness")).toContainText("LATEST");
  await expect(page.getByTestId("freshness")).toContainText("record: memory");
  await expect(page.getByTestId("query-info")).toContainText(/revision memory \d+/);
  expect(sent).toHaveLength(1);
  expect(sent[0]?.url).not.toContain("SELECT");
  expect(JSON.parse(defined(sent[0], "the first request").body)).toEqual({
    module: "catalog",
    sql: CODES,
    consistency: "latest",
    limit: 100,
  });

  // BULK is read from the replica.
  await page.getByRole("button", { name: "BULK" }).click();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByTestId("freshness")).toContainText("replica: memory_replica");
  await expect(history(page)).toHaveCount(2);
  await expect(history(page).first()).toContainText("BULK");
  await expect(history(page).first()).toContainText(/\d+ rows/);
  await expect(history(page).last()).toContainText("LATEST");

  // Choosing an entry puts it back in the editor without running it; Run again runs it now.
  await editor.fill("SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 50");
  await history(page)
    .last()
    .getByTitle(/without running it/)
    .click();
  await expect(editor).toHaveValue(CODES);
  await expect(page.getByRole("button", { name: "LATEST", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(sent).toHaveLength(2);
  await history(page)
    .first()
    .getByRole("button", { name: /Run again/ })
    .click();
  await expect.poll(() => sent.length).toBe(3);
  expect(JSON.parse(defined(sent[2], "the third request").body).consistency).toBe("bulk");
  await expect(history(page)).toHaveCount(2); // the same query again in a row is listed once

  // The history survives another tab, and the draft with it.
  await page.getByRole("tab", { name: "Entities" }).click();
  await page.getByRole("tab", { name: "Query" }).click();
  await expect(history(page)).toHaveCount(2);

  // Another person (a made-up viewer): the console is mounted afresh and the history is empty.
  await page.getByLabel("Person").selectOption({ label: "Custom name and role…" });
  await page.getByLabel("Name").fill("vic");
  await page.getByLabel("Role").selectOption("viewer");
  await page.getByRole("button", { name: "Use", exact: true }).click();
  await expect(page.getByTestId("query-history-empty")).toBeVisible();
  await expect(editor).toHaveValue("");

  // Nothing is kept in the browser and no URL holds the text.
  await editor.fill(CODES);
  await editor.press("Meta+Enter");
  await expect(grid.getByRole("cell", { name: /^uc-pipeline(?: Open .*)?$/ })).toBeVisible();
  const kept = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    cookie: document.cookie,
    databases: indexedDB.databases ? (await indexedDB.databases()).length : 0,
    href: location.href,
  }));
  expect(kept).toMatchObject({ local: 0, session: 0, cookie: "", databases: 0 });
  expect(decodeURIComponent(kept.href)).not.toContain("SELECT");
  await page.getByRole("button", { name: "Clear history" }).click();
  await expect(page.getByTestId("query-history-empty")).toBeVisible();
});

test("a query that does not parse lists its violations, and one over 4,000 characters is stopped", async ({
  page,
}) => {
  await page.goto("/#/catalog/query");
  await page.getByLabel("Person").selectOption("alice");
  const editor = page.getByLabel("Query (Weft SQL, read-only)");
  await editor.fill("DELETE FROM catalog.UseCase");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const e = page.getByTestId("query-error");
  await expect(e).toContainText("Invalid request");
  await expect(e.getByRole("listitem").first()).toContainText("syntax");
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(history(page).first()).toContainText("Invalid request (400)");
  await editor.fill("x".repeat(4001));
  await expect(page.getByRole("button", { name: "Run", exact: true })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await expect(page.getByTestId("query-too-long")).toBeVisible();
});

test("the grid fits at least 30 rows on a 1080p screen without scrolling the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/catalog/query");
  await page.getByLabel("Person").selectOption("alice");
  const editor = page.getByLabel("Query (Weft SQL, read-only)");
  await editor.fill("SELECT s.code, s.name FROM catalog.Solution s ORDER BY s.code LIMIT 50");
  await editor.press("Control+Enter");
  const row = page.getByTestId("query-row").first();
  await expect(row).toBeVisible();
  const m = await page.evaluate(() => {
    const scroller = document.querySelector('[data-testid="query-scroll"]') as HTMLElement;
    const tr = document.querySelector('[data-testid="query-row"]') as HTMLElement;
    const th = scroller.querySelector("thead") as HTMLElement;
    return {
      rows:
        (scroller.clientHeight - th.getBoundingClientRect().height) /
        tr.getBoundingClientRect().height,
      pageScroll: document.documentElement.scrollHeight - window.innerHeight,
    };
  });
  expect(m.rows).toBeGreaterThanOrEqual(30);
  expect(m.pageScroll).toBeLessThanOrEqual(0);
});

test("the type panel puts a query for a type in the editor", async ({ page }) => {
  await page.goto("/#/catalog/query");
  await page.getByLabel("Person").selectOption("alice");
  await page.getByTestId("query-types").getByText("What can I query?").click();
  await expect(page.getByTestId("query-type")).toHaveCount(2);
  await page
    .getByTestId("query-type")
    .first()
    .getByRole("button", { name: "catalog.UseCase", exact: true })
    .click();
  await expect(page.getByLabel("Query (Weft SQL, read-only)")).toHaveValue(
    'SELECT x."code", x."name" FROM "catalog"."UseCase" x ORDER BY x."code" LIMIT 101',
  );
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("cell", { name: /^uc-pipeline(?: Open .*)?$/ })).toBeVisible();
});
