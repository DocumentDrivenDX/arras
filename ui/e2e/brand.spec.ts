// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

// The brand (SD-013, Branding): the dev host's page carries the default name in the top bar and in the
// document title, in both modes, and the top bar passes axe in both schemes.

const MODES = [
  { name: "explore", hash: "#/explore/catalog", bar: "banner" },
  { name: "operate", hash: "#/operate/catalog/model", bar: "banner" },
] as const;

test("the served page carries the brand meta tag the app reads", async ({ page }) => {
  await page.goto("/");
  const content = await page.locator('meta[name="arras-brand"]').getAttribute("content");
  expect(JSON.parse(content ?? "null")).toEqual({ name: "Arras" });
});

const CUSTOM = { name: "Example Ledger", title: "Example Ledger Console" };

/** Serves the page with a custom brand in place of the default one in its meta tag. */
async function serveCustomBrand(page: Page, brand: object = CUSTOM) {
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const meta = `<meta name="arras-brand" content='${JSON.stringify(brand)}'>`;
    const html = (await response.text()).replace(/<meta name="arras-brand"[^>]*>/, "");
    await route.fulfill({ response, body: html.replace("</head>", `${meta}</head>`) });
  });
}

test("operate: a custom brand is in the console header and ends the document title", async ({
  page,
}) => {
  await serveCustomBrand(page);
  await page.goto("/#/operate/catalog/model");
  const header = page.getByTestId("console-header");
  await expect(header).toContainText(CUSTOM.name);
  await expect(header).not.toContainText("Arras");
  await expect.poll(() => page.title()).toMatch(/Example Ledger Console$/);
});

/** Every Content-Security-Policy violation the page logs (a blocked image is one). */
function watchCsp(page: Page): string[] {
  const found: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy|CSP violation/i.test(m.text())) found.push(m.text());
  });
  page.on("pageerror", (e) => found.push(String(e)));
  return found;
}

/** Whether an image (an `<img>`, or an inline SVG which cannot be blocked) has loaded. */
const isDecoded = (el: Element): boolean =>
  !(el instanceof HTMLImageElement) || (el.complete && el.naturalWidth > 0);

for (const m of MODES) {
  for (const scheme of ["light", "dark"] as const) {
    test(`${m.name}: logo "theme" renders the theme's mark in the top bar, ${scheme}`, async ({
      page,
    }) => {
      const violations = watchCsp(page);
      await page.emulateMedia({ colorScheme: scheme });
      await serveCustomBrand(page, { ...CUSTOM, logo: "theme" });
      await page.goto(`/${m.hash}`);
      const bar = page.getByRole(m.bar).first();
      await expect(bar.getByRole("img", { name: CUSTOM.name })).toBeVisible();
      await expect
        .poll(() => bar.getByRole("img", { name: CUSTOM.name }).evaluate(isDecoded))
        .toBe(true);
      expect(violations, violations.join("\n")).toEqual([]);
      await expect(bar).toContainText(CUSTOM.name);
      const r = await new AxeBuilder({ page })
        .include("header")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const found = r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }));
      expect(found, JSON.stringify(found)).toEqual([]);
    });
  }
}

for (const m of MODES) {
  test(`${m.name}: the default name is in the top bar and the document title`, async ({ page }) => {
    await page.goto(`/${m.hash}`);
    const bar =
      m.name === "operate" ? page.getByTestId("console-header") : page.getByRole(m.bar).first();
    await expect(bar).toContainText("Arras");
    await expect.poll(() => page.title()).toMatch(/Arras$/);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`${m.name}: the top bar has no WCAG A/AA violations, ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(`/${m.hash}`);
      const bar = page.getByRole(m.bar).first();
      await expect(bar).toContainText("Arras");
      const r = await new AxeBuilder({ page })
        .include("header")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(r.passes.length).toBeGreaterThan(0);
      const found = r.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }));
      expect(found, JSON.stringify(found)).toEqual([]);
      const review = r.incomplete.map((v) => v.id);
      expect(review).toEqual([]);
    });
  }
}
