// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { entity, firstLink, loadGraph, nameOf } from "./graph";

// The Graph Browser as a static read-only host (ADR-031, CONTRACT-012): the built page, a module document and a
// graph file served as plain files, no API. These are the read flows of e2e/browser.spec.ts and e2e/a11y.spec.ts
// run over the example catalog and pizza modules. The editing, history, operator and identity specs of that suite
// need a person and a writable store, which this host does not have (the profile refuses them: static-refusals).

const catalog = loadGraph("catalog", "catalog.graph.json");
const pizza = loadGraph("pizza", "pizza.graph.json");

const chip = (page: Page, type: string) =>
  page
    .getByRole("radiogroup", { name: "Narrow by type" })
    .getByRole("radio", { name: new RegExp(`^${type}`) });
const group = (page: Page, name: RegExp) =>
  page.getByRole("heading", { level: 3, name }).locator("xpath=ancestor::section[1]");

/** Every request the page makes and every console error, from the first navigation. */
function watch(page: Page) {
  const requests: Request[] = [];
  const problems: string[] = [];
  page.on("request", (r) => requests.push(r));
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
  return { requests, problems };
}

test.describe("the catalog, read as files", () => {
  test("opens, reads the module and its graph as GETs of its own files, and nothing else", async ({
    page,
  }) => {
    const seen = watch(page);
    await page.goto("/catalog/#/explore/catalog");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Product catalog");
    await expect(page.getByText(/static · /).first()).toBeVisible();
    expect(seen.problems).toEqual([]);
    const origin = new URL(page.url()).origin;
    for (const r of seen.requests) {
      expect(r.method(), r.url()).toBe("GET");
      expect(new URL(r.url()).origin, r.url()).toBe(origin);
      expect(r.url()).not.toMatch(/\/api\//);
    }
    const names = seen.requests.map((r) => new URL(r.url()).pathname);
    expect(names).toContain("/catalog/arras-static.json");
    expect(names).toContain("/catalog/catalog.umf.json");
    expect(names).toContain("/catalog/catalog.graph.json");
  });

  test("open a type and a node, follow a relationship, use the picture, and go Back", async ({
    page,
  }) => {
    const link = firstLink(catalog, "addresses");
    const solution = entity(catalog, "Solution", String(link.source));
    const useCase = entity(catalog, "UseCase", String(link.target));
    await page.goto("/catalog/#/explore/catalog");
    await chip(page, "Solutions").click();
    await expect(chip(page, "Solutions")).toHaveAttribute("aria-checked", "true");
    await page
      .getByRole("link", { name: new RegExp(nameOf(solution)) })
      .first()
      .click();
    await expect(page.getByRole("heading", { level: 1, name: nameOf(solution) })).toBeVisible();
    expect(new URL(page.url()).hash).toBe(`#/explore/catalog/Solution/${solution.key}`);
    expect(new URL(page.url()).search).toBe("");
    await group(page, /^Addresses/)
      .getByRole("link", { name: new RegExp(nameOf(useCase)) })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: nameOf(useCase) })).toBeVisible();
    await expect(
      group(page, /Addressed by/).getByRole("link", { name: new RegExp(nameOf(solution)) }),
    ).toBeVisible();
    await page
      .getByRole("group", { name: /^Neighbourhood of/ })
      .getByRole("link", { name: new RegExp(nameOf(solution)) })
      .first()
      .click();
    await expect(page.getByRole("heading", { level: 1, name: nameOf(solution) })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: nameOf(useCase) })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: nameOf(solution) })).toBeVisible();
  });

  test("search ranks, marks the match, narrows by type and reports counts", async ({ page }) => {
    await page.goto("/catalog/#/explore/catalog");
    const box = page
      .getByRole("searchbox")
      .or(page.getByLabel(/^Search/))
      .first();
    await box.fill("runbook");
    const hits = page.locator("a.gb-hit");
    await expect(hits.first()).toBeVisible();
    expect(await hits.count()).toBeGreaterThan(1);
    await expect(page.locator("mark").first()).toBeVisible();
    await box.fill("zzzzqqq");
    await expect(
      page.getByText(/no match|nothing|No results|found nothing/i).first(),
    ).toBeVisible();
  });

  test("offers no way to change anything and no operator mode", async ({ page }) => {
    const solution = entity(catalog, "Solution", String(firstLink(catalog, "addresses").source));
    await page.goto(`/catalog/#/explore/catalog/Solution/${solution.key}`);
    await expect(page.getByRole("heading", { level: 1, name: nameOf(solution) })).toBeVisible();
    for (const name of [/^Edit/, /^New /, /Retire/, /^Actions/, /Export/, /^Operate/]) {
      await expect(page.getByRole("button", { name })).toHaveCount(0);
      await expect(page.getByRole("link", { name })).toHaveCount(0);
    }
    await page.goto("/catalog/#/operate/catalog");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Product catalog");
    await expect(page.getByTestId("operate")).toHaveCount(0);
  });

  test('a node that is not in the graph is "Not available", as an unreadable one is on the server', async ({
    page,
  }) => {
    await page.goto("/catalog/#/explore/catalog/Solution/no-such-key");
    await expect(page.getByRole("heading", { level: 1, name: "Not available" })).toBeVisible();
  });
});

test.describe("pizza, read as files", () => {
  test("a many-to-many relationship, a badge with declared tones, a decimal and a boolean", async ({
    page,
  }) => {
    const margherita = entity(pizza, "Pizza", "margherita");
    await page.goto(`/pizza/#/explore/pizza/Pizza/${margherita.key}`);
    await expect(page.getByRole("heading", { level: 1, name: nameOf(margherita) })).toBeVisible();
    const toppings = pizza.filter(
      (r) => r.relationship === "hasTopping" && r.source === "margherita",
    );
    expect(toppings.length).toBeGreaterThan(1);
    const links = group(page, /^Toppings/).getByRole("link");
    await expect(links).toHaveCount(toppings.length);
    await links.first().click();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(
      group(page, /On pizzas/)
        .getByRole("link")
        .first(),
    ).toBeVisible();
  });
});

const SCHEMES = ["light", "dark"] as const;
const PAGES = [
  ["entry", "/catalog/#/explore/catalog"],
  ["a type list", "/catalog/#/explore/catalog/Solution"],
  ["a node", `/catalog/#/explore/catalog/UseCase/${firstLink(catalog, "addresses").target}`],
  ["pizza node", "/pizza/#/explore/pizza/Pizza/margherita"],
] as const;

test.describe("accessibility (WCAG 2.1 A and AA, axe-core)", () => {
  for (const scheme of SCHEMES)
    for (const [name, url] of PAGES)
      test(`${name}, ${scheme}`, async ({ page }) => {
        await page.setViewportSize({ width: 1280, height: 1600 });
        await page.emulateMedia({ colorScheme: scheme });
        await page.goto(url);
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        const r = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const review = r.incomplete.filter(
          (i) =>
            !(
              i.id === "color-contrast" &&
              i.nodes.every(
                (n) =>
                  /^<(text|kbd)\b/.test(n.html) ||
                  /only non-text characters/.test(JSON.stringify(n.any)),
              )
            ),
        );
        expect(
          r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
        ).toEqual([]);
        expect(review.map((i) => i.id)).toEqual([]);
      });
});
