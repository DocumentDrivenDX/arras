// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page, test } from "@playwright/test";
import { ensureHub } from "./gb-fixtures";

// The route audit, whole stack (FR-74, SD-013): every page type is its address, so a refresh
// restores it, Back and Forward move through the entries that were pushed (and not the ones that
// were replaced), a link pasted for another person shows the one not-found page where she cannot
// read, and an address that names nothing leads to the module's entry. The table of addresses is in
// src/test/route-audit.test.ts; the cold renders on the dev host are in
// src/integration/route-audit.int.test.tsx.

const HUB_120 = "uc-hub-120";
const ORIGIN = "http://127.0.0.1:8123";

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureHub(request, HUB_120, 120);
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

const hashOf = (page: Page) => new URL(page.url()).hash;
/** Moves the address the way a link does: a new history entry. */
const push = (page: Page, hash: string) => page.evaluate((h) => window.location.assign(h), hash);

const h1 = (page: Page, name: string | RegExp) => page.getByRole("heading", { level: 1, name });

interface Screen {
  name: string;
  hash: string;
  shown: (p: Page) => Locator;
}

const EXPLORE: Screen[] = [
  { name: "the module entry", hash: "#/explore/catalog", shown: (p) => h1(p, /catalog/) },
  {
    name: "a type list",
    hash: "#/explore/catalog/UseCase",
    shown: (p) => p.getByRole("heading", { level: 2, name: "Use cases" }),
  },
  {
    name: "a type list at a position",
    hash: "#/explore/catalog/Solution?after=uc-hub-120-s009",
    shown: (p) => p.getByRole("link", { name: /Hub solution 010/ }),
  },
  {
    name: "an entity",
    hash: "#/explore/catalog/Solution/sol-1",
    shown: (p) => h1(p, "Pipeline extractor"),
  },
  {
    name: "an entity's History",
    hash: "#/explore/catalog/UseCase/uc-pipeline/history",
    shown: (p) => h1(p, "Pipeline mapping"),
  },
];

const OPERATE: Screen[] = [
  { name: "Model", hash: "#/operate/catalog/model", shown: (p) => p.getByTestId("schema") },
  {
    name: "Model with a type",
    hash: "#/operate/catalog/model/catalog.Solution",
    shown: (p) => p.getByTestId("type-catalog.Solution"),
  },
  {
    name: "Entities with a filter and a sort",
    hash: "#/operate/catalog/entities/catalog.Solution?f.code=sol-1&sort=name%3Adesc",
    shown: (p) => p.getByLabel("Filter code"),
  },
  {
    name: "an entity in Entities",
    hash: "#/operate/catalog/entities/catalog.Solution/sol-1",
    shown: (p) => p.getByTestId("entity-panel"),
  },
  {
    name: "Graph with a selection",
    hash: "#/operate/catalog/graph/catalog.Solution/sol-1",
    shown: (p) => p.getByRole("tab", { name: "Graph", selected: true }),
  },
  {
    name: "an action with a prefill",
    hash: "#/operate/catalog/actions/catalog.CorrectSolution?in.solution=sol-1",
    shown: (p) => p.getByRole("tab", { name: "Actions", selected: true }),
  },
  {
    name: "Changes for an entity",
    hash: "#/operate/catalog/changes/catalog.Solution/sol-1",
    shown: (p) => p.getByTestId("history-chip"),
  },
  {
    name: "the import loads",
    hash: "#/operate/catalog/changes?view=loads",
    shown: (p) => p.getByTestId("loads"),
  },
];

test.describe("a refresh restores each page type", () => {
  for (const s of [...EXPLORE, ...OPERATE]) {
    test(`${s.hash}: ${s.name}`, async ({ page }) => {
      await page.goto(`/${s.hash}`);
      await expect(s.shown(page)).toBeVisible();
      await page.reload();
      await expect(s.shown(page)).toBeVisible();
      expect(hashOf(page)).toBe(s.hash);
      expect(new URL(page.url()).search).toBe("");
    });
  }
});

test.describe("the earlier mode ids are aliases, replaced in the address", () => {
  const ALIASES = [
    { old: "#/browse/catalog", now: "#/explore/catalog" },
    { old: "#/admin/catalog/model", now: "#/operate/catalog/model" },
    {
      old: "#/admin/catalog/data/catalog.Solution",
      now: "#/operate/catalog/entities/catalog.Solution",
    },
  ];
  for (const a of ALIASES) {
    test(`${a.old} opens ${a.now} without a new history entry`, async ({ page }) => {
      await page.goto("/#/explore/catalog");
      await expect(h1(page, /catalog/)).toBeVisible();
      const entries = await page.evaluate(() => window.history.length);
      await page.evaluate((h) => {
        window.location.hash = h;
      }, a.old);
      await expect.poll(() => hashOf(page)).toBe(a.now);
      // the alias took the one entry the address change made; it did not add a second
      expect(await page.evaluate(() => window.history.length)).toBe(entries + 1);
    });
  }
});

test.describe("Back and Forward move through the pushed entries", () => {
  test("Explore: a link pushes, Show next replaces", async ({ page }) => {
    await page.goto("/#/explore/catalog");
    await expect(h1(page, /catalog/)).toBeVisible();
    await push(page, "#/explore/catalog/Solution");
    const rows = page.locator(".gb-hits .gb-t");
    await expect(rows).toHaveCount(50);
    const entries = await page.evaluate(() => window.history.length);
    await page.getByRole("button", { name: "Show next 50" }).click();
    await expect(rows).toHaveCount(100);
    await expect.poll(() => hashOf(page)).toMatch(/^#\/explore\/catalog\/Solution\?after=/);
    // the position replaced the entry: no new one
    expect(await page.evaluate(() => window.history.length)).toBe(entries);
    const positioned = hashOf(page);
    await page.getByRole("link", { name: /Pipeline extractor/ }).click();
    await expect(h1(page, "Pipeline extractor")).toBeVisible();
    await page.goBack();
    await expect.poll(() => hashOf(page)).toBe(positioned);
    // Back from the list goes to the entry in one step, not to the list before Show next
    await page.goBack();
    await expect.poll(() => hashOf(page)).toBe("#/explore/catalog");
    await expect(h1(page, /catalog/)).toBeVisible();
    await page.goForward();
    await expect.poll(() => hashOf(page)).toBe(positioned);
    await page.goForward();
    await expect(h1(page, "Pipeline extractor")).toBeVisible();
    expect(hashOf(page)).toBe("#/explore/catalog/Solution/sol-1");
  });

  test("Operate: Model, a table and an entity are three entries", async ({ page }) => {
    const model = "#/operate/catalog/model";
    const table = "#/operate/catalog/entities/catalog.Solution";
    const entity = `${table}/sol-1`;
    await page.goto(`/${model}`);
    await expect(page.getByTestId("schema")).toBeVisible();
    await push(page, table);
    await expect(page.getByLabel("Filter code")).toBeVisible();
    await push(page, entity);
    await expect(page.getByTestId("entity-panel")).toBeVisible();
    await page.goBack();
    await expect.poll(() => hashOf(page)).toBe(table);
    await expect(page.getByTestId("entity-panel")).toHaveCount(0);
    await page.goBack();
    await expect.poll(() => hashOf(page)).toBe(model);
    await expect(page.getByTestId("schema")).toBeVisible();
    await page.goForward();
    await page.goForward();
    await expect.poll(() => hashOf(page)).toBe(entity);
    await expect(page.getByTestId("entity-panel")).toBeVisible();
  });
});

test.describe("a pasted link opened as another person", () => {
  test("dave, who reads nothing, gets the not-available page, and the address says nothing more", async ({
    page,
  }) => {
    await as(page, "dave", "#/explore/catalog/Solution/sol-1");
    await expect(page.getByTestId("gb-state")).toContainText("Not available");
    await expect(page.getByText("Pipeline extractor")).toHaveCount(0);
    await expect(page).toHaveTitle("Arras");
    expect(hashOf(page)).toBe("#/explore/catalog/Solution/sol-1");
  });

  test("carol reads the same link where she may", async ({ page }) => {
    await as(page, "carol", "#/explore/catalog/Solution/sol-1");
    await expect(h1(page, "Pipeline extractor")).toBeVisible();
  });

  test("an Operate link opened as carol, who is not an operator, is the user's page", async ({
    page,
  }) => {
    await as(page, "carol", "#/operate/catalog/entities/catalog.Solution/sol-1");
    // the Explore entry: the chooser when other modules are registered (the run shares one server with
    // the console's specs), else the module
    await expect(page.getByTestId("gb")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^(catalog|Choose a module)$/);
    await expect(page.getByRole("group", { name: "Mode" })).toHaveCount(0);
    await expect(page.getByTestId("entity-panel")).toHaveCount(0);
  });
});

test.describe("an address that names nothing", () => {
  test("Explore: the not-available page leads to the module's entry", async ({ page }) => {
    await page.goto("/#/explore/catalog/Solution/no-such-solution");
    await expect(page.getByTestId("gb-state")).toContainText("Not available");
    await page.getByRole("button", { name: "Back to catalog" }).click();
    await expect.poll(() => hashOf(page)).toBe("#/explore/catalog");
    await expect(h1(page, /catalog/)).toBeVisible();
  });

  test("Explore: an address that does not parse is the same page, leading to the start", async ({
    page,
  }) => {
    await page.goto("/#/explore/catalog/Solution/sol-1/nope");
    await expect(page.getByTestId("gb-state")).toContainText("Not available");
  });

  test("Operate: the not-found page links to the module's Model", async ({ page }) => {
    await page.goto("/#/operate/catalog/entities/catalog.Solution/no-such-solution");
    const notFound = page.getByTestId("not-found");
    await expect(notFound).toContainText("Not found");
    await notFound.getByRole("link", { name: /Model of catalog/ }).click();
    await expect.poll(() => hashOf(page)).toBe("#/operate/catalog/model");
    await expect(page.getByTestId("schema")).toBeVisible();
  });
});

const NOT_FOUND: { name: string; hash: string; page: string }[] = [
  { name: "Explore", hash: "#/explore/catalog/Solution/no-such-solution", page: "gb-state" },
  {
    name: "Operate",
    hash: "#/operate/catalog/entities/catalog.Solution/no-such-solution",
    page: "not-found",
  },
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe on the not-found page, ${scheme}`, () => {
    test.use({ colorScheme: scheme, viewport: { width: 1440, height: 1200 } });
    for (const n of NOT_FOUND) {
      test(`${n.name} has no WCAG A/AA violations`, async ({ page }) => {
        await page.goto(`/${n.hash}`);
        await expect(page.getByTestId(n.page)).toBeVisible();
        const r = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        expect(r.passes.length).toBeGreaterThan(10);
        const found = r.violations.map((v) => ({
          id: v.id,
          help: v.help,
          nodes: v.nodes.slice(0, 5).map((x) => x.target.join(" ")),
        }));
        expect(found, JSON.stringify(found, null, 2)).toEqual([]);
        const review = r.incomplete.flatMap((v) =>
          v.nodes
            .filter((x) => !(v.id === "color-contrast" && /^<(text|kbd)\b/.test(x.html)))
            .map((x) => `${v.id}: ${x.html.slice(0, 140)}`),
        );
        expect(review, review.join("\n")).toEqual([]);
      });
    }
  });
}
