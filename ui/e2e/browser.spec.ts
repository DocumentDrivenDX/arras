// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { ORIGIN } from "./acceptance";
import { control, ensureHub } from "./gb-fixtures";

// The Graph Browser whole stack (FEAT-011): the built UI served by the dev host, read as the
// sandbox's people. alice, bob and root are operators; carol and dave are not; dave reads nothing.
// The hub fixtures are made once through the operate surface as alice (e2e/gb-fixtures.ts).

const HUB_25 = "uc-hub-25";
const HUB_120 = "uc-hub-120";

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureHub(request, HUB_25, 25);
  await ensureHub(request, HUB_120, 120);
  await request.dispose();
});

async function as(page: Page, person: string, hash = "#/explore/catalog") {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

interface Seen {
  method: string;
  url: string;
  headers: Record<string, string>;
}

/** Every request the page makes, with its full headers. */
function record(page: Page): Seen[] {
  const seen: Seen[] = [];
  const pending: Promise<void>[] = [];
  page.on("request", (r: Request) => {
    pending.push(
      r.allHeaders().then((headers) => {
        seen.push({ method: r.method(), url: r.url(), headers });
      }),
    );
  });
  Object.defineProperty(seen, "settled", { value: () => Promise.all(pending) });
  return seen;
}
const settled = (seen: Seen[]) =>
  (seen as unknown as { settled: () => Promise<unknown> }).settled();

/** A type chip (a radio; "All" is the first): the type cards on the Entry have the same names. */
const chip = (page: Page, type: string) =>
  page
    .getByRole("radiogroup", { name: "Narrow by type" })
    .getByRole("radio", { name: new RegExp(`^${type}`) });

const group = (page: Page, name: RegExp) =>
  page.getByRole("heading", { level: 3, name }).locator("xpath=ancestor::section[1]");

test.describe("the reader's primary workflow (US-066 to US-069, US-071)", () => {
  test("open the module, a type and a node, follow a relationship, use the picture, and go Back", async ({
    page,
  }) => {
    const seen = record(page);
    await as(page, "carol");
    await settled(seen);
    const afterPicker = seen.length; // what was asked before the person was chosen is alice's, the default
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("catalog");
    // a chip lists the type
    await chip(page, "Solution").click();
    await expect(chip(page, "Solution")).toHaveAttribute("aria-checked", "true");
    await page.getByRole("link", { name: /Pipeline extractor/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/explore/catalog/Solution/sol-1");
    expect(new URL(page.url()).pathname).toBe("/");
    expect(new URL(page.url()).search).toBe("");
    // follow the relationship to the use case
    const addresses = group(page, /^Addresses/);
    await addresses.getByRole("link", { name: /Pipeline mapping/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/explore/catalog/UseCase/uc-pipeline");
    // the inverse links back; use the picture to go there
    await expect(
      group(page, /Addressed by/).getByRole("link", { name: /Pipeline extractor/ }),
    ).toBeVisible();
    await page
      .getByRole("group", { name: /^Neighbourhood of/ })
      .getByRole("link", { name: /Pipeline extractor/ })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    // Back, Back
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    await page.goBack();
    await expect(chip(page, "Solution")).toHaveAttribute("aria-checked", "true");
    await settled(seen);
    // every API request: a read as carol, nothing of the node in a path or query
    const api = seen.filter((s) => /\/api\/(console|operate)/.test(s.url));
    expect(api.length).toBeGreaterThan(5);
    for (const s of api) {
      expect(["alice", "carol"], s.url).toContain(s.headers["x-arras-user"]);
      if (seen.indexOf(s) >= afterPicker) expect(s.headers["x-arras-user"], s.url).toBe("carol");
      expect(["GET", "POST"]).toContain(s.method);
      expect(s.url).not.toMatch(/sol-1|uc-pipeline|Pipeline|\?/);
      expect(s.headers.referer ?? "").not.toMatch(/sol-1|uc-pipeline|#/);
    }
    expect(seen.map((s) => s.method).filter((m) => !["GET", "POST"].includes(m))).toEqual([]);
    const operate = api
      .filter((s) => s.url.includes("/api/operate"))
      .map((s) => new URL(s.url).pathname);
    expect(new Set(operate)).toEqual(new Set(["/api/operate/viewer"]));
  });

  test("the breadcrumb: Explore and the type's plural name are links, the page is plain text; they walk back to the list and the entry", async ({
    page,
  }) => {
    await as(page, "carol", "#/explore/catalog/UseCase/uc-pipeline");
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    const crumbs = page.getByRole("navigation", { name: "Breadcrumb" });
    await expect(crumbs).toContainText("Explore›Use cases›uc-pipeline");
    await expect(crumbs.getByRole("link")).toHaveText(["Explore", "Use cases"]);
    await expect(crumbs.locator("[aria-current=page]")).toHaveText("uc-pipeline");
    await expect(crumbs.locator("a[aria-current]")).toHaveCount(0);
    // a keyboard reaches the type crumb, shows where it is, and Enter follows it
    const type = crumbs.getByRole("link", { name: "Use cases" });
    await type.focus();
    await expect(type).toBeFocused();
    expect(await type.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
    await page.keyboard.press("Enter");
    expect(new URL(page.url()).hash).toBe("#/explore/catalog/UseCase");
    await expect(page.getByRole("heading", { level: 2, name: "Use cases" })).toBeVisible();
    await expect(chip(page, "Use cases")).toHaveAttribute("aria-checked", "true");
    await page.locator("a.gb-hit", { hasText: "Pipeline mapping" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    await crumbs.getByRole("link", { name: "Explore" }).click();
    expect(new URL(page.url()).hash).toBe("#/explore/catalog");
    await expect(page.locator(".gb-type-card-t")).toContainText(["Use cases", "Solutions"]);
    await page.goBack();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    await page.goBack();
    await expect(page.getByRole("heading", { level: 2, name: "Use cases" })).toBeVisible();
    await page.goForward();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    const r = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(r.violations).toEqual([]);
  });

  test("search by text narrows by type, and the search comes back with Back, never in the URL", async ({
    page,
  }) => {
    const seen = record(page);
    await as(page, "carol");
    const box = page.getByRole("textbox", { name: /Search/ });
    await box.fill("pipeline");
    await expect(page.getByTestId("gb-status")).toContainText("results for pipeline");
    await expect(page.getByTestId("gb-answer-freshness")).toContainText("memory");
    await chip(page, "Solution").click();
    await expect(page.locator("a.gb-hit").first()).toContainText("Solution");
    await page.locator("a.gb-hit", { hasText: "Pipeline extractor" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText(
      "Search: pipeline",
    );
    expect(page.url()).not.toMatch(/pipeline/i);
    await page.goBack();
    await expect(page.getByRole("textbox", { name: /Search/ })).toHaveValue("pipeline");
    await expect(chip(page, "Solution")).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("gb-status")).toContainText("results for pipeline");
    await settled(seen);
    for (const s of seen.filter((x) => /\/api\/(console|operate)/.test(x.url))) {
      expect(s.url).not.toMatch(/pipeline/i);
      expect(s.headers.referer ?? "").not.toMatch(/pipeline|#/i);
    }
  });

  test("no hit and a single character are stated, not guessed", async ({ page }) => {
    await as(page, "carol");
    const box = page.getByRole("textbox", { name: /Search/ });
    await box.fill("zzzzqqq");
    await expect(page.getByRole("heading", { name: "No results for “zzzzqqq”" })).toBeVisible();
    await box.fill("z");
    await expect(page.getByTestId("gb-hint")).toContainText("at least two characters");
  });

  test("a type that is not searched is named, and the others still answer", async ({
    page,
    request,
  }) => {
    await control(request, {
      op: "search",
      backend: "memory",
      type: "catalog.UseCase",
      mode: "none",
    });
    try {
      await as(page, "carol");
      await page.getByRole("textbox", { name: /Search/ }).fill("pipeline");
      await expect(page.getByTestId("gb-banner")).toContainText("Use case was not searched.");
      await expect(chip(page, "Use case")).toContainText("not searched");
      await expect(page.locator("a.gb-hit", { hasText: "Pipeline extractor" })).toBeVisible();
    } finally {
      await control(request, {
        op: "search",
        backend: "memory",
        type: "catalog.UseCase",
        mode: null,
      });
    }
  });
});

test.describe("the type chips are a single choice (US-066)", () => {
  test("All is selected first; choosing a chip deselects the rest; arrows move the choice; focus differs from selected", async ({
    page,
  }) => {
    await as(page, "carol");
    await expect(chip(page, "All")).toHaveAttribute("aria-checked", "true");
    await expect(page.locator(".gb-type-card-t")).toContainText(["Use cases", "Solutions"]);
    await chip(page, "Solution").click();
    await expect(chip(page, "Solution")).toHaveAttribute("aria-checked", "true");
    await expect(chip(page, "All")).toHaveAttribute("aria-checked", "false");
    await expect(page.getByRole("radiogroup").getByRole("radio", { checked: true })).toHaveCount(1);
    await page.keyboard.press("ArrowLeft");
    await expect(chip(page, "Use cases")).toHaveAttribute("aria-checked", "true");
    await expect(chip(page, "Use cases")).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(chip(page, "All")).toBeFocused();
    await expect(chip(page, "All")).toHaveAttribute("aria-checked", "true");
    // a focused chip beside the selected one: the ring is its own, outside the selected border
    const ring = await chip(page, "All").evaluate((el) => getComputedStyle(el).outlineOffset);
    expect(ring).toBe("3px");
    await expect(page.getByText("List them")).toHaveCount(2);
    await page.getByRole("textbox", { name: /Search/ }).fill("pipeline");
    await expect(page.getByTestId("gb-status")).toContainText("results for pipeline");
    await expect(chip(page, "All")).toContainText(/\d/);
    const r = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(r.violations).toEqual([]);
  });
});

test.describe("modes (US-072)", () => {
  test("alice is offered Explore and Operate, opens in Explore, carries the entity to Operate and gets his page back", async ({
    page,
  }) => {
    await as(page, "alice", "#/explore/catalog/Solution/sol-1");
    const mode = page.getByRole("group", { name: "Mode" });
    await expect(mode.getByRole("button", { name: "Explore" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(mode.getByRole("button", { name: "Operate" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await mode.getByRole("button", { name: "Operate" }).click();
    await expect(page.getByTestId("console-header")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/operate/catalog/entities/catalog.Solution/sol-1");
    await expect(page.getByRole("tab", { name: "Entities" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByRole("tab", { name: "Solution" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page
      .getByRole("group", { name: "Mode" })
      .getByRole("button", { name: "Explore" })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  test("the console's earlier fragment form opens Operate for an operator and the Explore entry for a reader", async ({
    page,
  }) => {
    await as(page, "alice", "#/catalog/entities/catalog.UseCase");
    await expect(page.getByTestId("console-header")).toBeVisible();
    await expect
      .poll(() => new URL(page.url()).hash)
      .toBe("#/operate/catalog/entities/catalog.UseCase");
    await as(page, "carol", "#/operate/catalog/entities/catalog.UseCase");
    // the Explore entry: the chooser when other modules are registered (the run shares one server), else the module
    await expect(page.getByTestId("gb")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^(catalog|Choose a module)$/);
    await expect(page.getByTestId("console-header")).toHaveCount(0);
  });

  test("carol has no switch and nothing in the page, or in the requests, refers to Operate", async ({
    page,
  }) => {
    const seen = record(page);
    await as(page, "carol", "#/explore/catalog/Solution/sol-1");
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Mode" })).toHaveCount(0);
    const html = await page.locator("body").innerHTML();
    expect(html).not.toMatch(/operate/i);
    await settled(seen);
    const operate = seen
      .filter((s) => s.url.includes("/api/operate"))
      .map((s) => `${s.method} ${new URL(s.url).pathname}`);
    expect(new Set(operate)).toEqual(new Set(["GET /api/operate/viewer"]));
  });

  test("the switch is reachable by keyboard and its state is aria-pressed", async ({ page }) => {
    await as(page, "alice");
    const mode = page.getByRole("group", { name: "Mode" });
    await mode.getByRole("button", { name: "Explore" }).focus();
    await page.keyboard.press("Tab");
    await expect(mode.getByRole("button", { name: "Operate" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("console-header")).toBeVisible();
    await expect(
      page.getByRole("group", { name: "Mode" }).getByRole("button", { name: "Operate" }),
    ).toHaveAttribute("aria-pressed", "true");
    await page
      .getByRole("group", { name: "Mode" })
      .getByRole("button", { name: "Explore" })
      .focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("heading", { level: 1, name: "catalog" })).toBeVisible();
  });

  test("US-072-AC5: every operate endpoint refuses carol with 403 REFUSED not_operator, and the viewer's modes answer user only", async ({
    request,
  }) => {
    const carol = { "x-arras-user": "carol", origin: ORIGIN };
    const refusal = { error: "REFUSED", reason: "not_operator" };
    for (const path of [
      "/audit/changes",
      "/audit/loads",
      "/actions/catalog/AddUseCase/validate",
      "/actions/catalog/AddUseCase/invoke",
      "/actions/catalog/AddUseCase/batch",
    ]) {
      const r = await request.post(`/api/operate${path}`, {
        data: { module: "catalog", inputs: {}, items: [] },
        headers: carol,
      });
      expect([path, r.status(), await r.json()]).toEqual([path, 403, refusal]);
    }
    const catalog = await request.get("/api/operate/explorer/schema-catalog.json", {
      headers: carol,
    });
    expect([catalog.status(), await catalog.json()]).toEqual([403, refusal]);
    const viewer = await request.get("/api/operate/viewer", { headers: carol });
    expect(await viewer.json()).toEqual({ user: "carol", modes: ["user"] });
    expect((await request.get("/api/operate/version", { headers: carol })).status()).toBe(200);
    const alice = await request.get("/api/operate/viewer", {
      headers: { "x-arras-user": "alice" },
    });
    expect(await alice.json()).toEqual({ user: "alice", modes: ["user", "admin"] });
  });
});

test.describe("not available (US-067-AC6, US-068-AC5, US-071-AC3)", () => {
  const na = (page: Page) => page.getByTestId("gb-state");

  // The page says the same whatever the cause; only its way on differs (the module's entry, else the start).
  const said = (page: Page) => na(page).locator("h1, p").allInnerTexts();

  test("a missing key, a malformed location and a reader who reads nothing all show the same page", async ({
    page,
  }) => {
    await as(page, "carol", "#/explore/catalog/Solution/no-such-solution");
    await expect(na(page)).toContainText("Not available");
    const missing = await said(page);
    expect(missing.join(" ")).not.toMatch(/no-such|Solution|catalog/);
    await expect(na(page).getByRole("button")).toHaveText("Back to catalog");
    await page.goto("/#/explore/catalog/Solution/%E0%A4%A");
    await expect(na(page)).toBeVisible();
    expect(await said(page)).toEqual(missing);
    await as(page, "dave", "#/explore/catalog/Solution/sol-1");
    await expect(na(page)).toBeVisible();
    expect(await said(page)).toEqual(missing);
    await as(page, "dave", "#/explore/catalog");
    await expect(na(page)).toBeVisible();
    expect(await said(page)).toEqual(missing);
  });
});

test.describe("keyboard-only paths (US-069-AC6, US-072-AC8)", () => {
  async function tabTo(page: Page, css: string, max = 60) {
    for (let i = 0; i < max; i++) {
      await page.keyboard.press("Tab");
      if (await page.evaluate((c) => document.activeElement?.matches(c) ?? false, css)) return;
    }
    throw new Error(`never reached ${css} by Tab`);
  }

  test("/ finds the search, Escape clears it, Tab reaches a hit, Enter opens it", async ({
    page,
  }) => {
    await as(page, "carol");
    await page.locator("body").click({ position: { x: 5, y: 300 } });
    await page.keyboard.press("/");
    await expect(page.getByRole("textbox", { name: /Search/ })).toBeFocused();
    await page.keyboard.type("pipeline");
    await expect(page.getByTestId("gb-status")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("textbox", { name: /Search/ })).toHaveValue("");
    await page.keyboard.type("extractor");
    await expect(page.locator("a.gb-hit", { hasText: "Pipeline extractor" })).toBeVisible();
    await tabTo(page, "a.gb-hit");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(new URL(page.url()).hash).toMatch(/^#\/explore\/catalog\/\w+\//);
  });

  test("the picture is one Tab stop, the arrows move between its nodes and Enter opens a node", async ({
    page,
  }) => {
    await as(page, "carol", `#/explore/catalog/UseCase/${HUB_25}`);
    const nodes = page.locator("a.gb-node");
    await expect(nodes).toHaveCount(25);
    await tabTo(page, "a.gb-node");
    const first = await page.evaluate(() => document.activeElement?.getAttribute("aria-label"));
    expect(first).toMatch(/^Solution, Hub solution 000, Addressed by/);
    await page.keyboard.press("ArrowDown");
    expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toMatch(
      /Hub solution 001/,
    );
    await page.keyboard.press("End");
    expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toMatch(
      /Hub solution 024/,
    );
    await page.keyboard.press("Home");
    // one Tab stop: the next Tab leaves the picture
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.matches("a.gb-node"))).toBe(false);
    expect(
      await nodes.evaluateAll(
        (els) => els.filter((e) => e.getAttribute("tabindex") === "0").length,
      ),
    ).toBe(1);
    await page.keyboard.press("Shift+Tab");
    await expect(nodes.first()).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Hub solution 000" })).toBeVisible();
  });

  test("hover and focus show a card with the label, type and relationship", async ({ page }) => {
    await as(page, "carol", "#/explore/catalog/Solution/sol-1");
    const node = page.locator("a.gb-node").first();
    await node.focus();
    await expect(page.getByTestId("gb-hover")).toContainText("Addresses");
    await page.locator("a.gb-node").nth(0).blur();
    await node.hover();
    await expect(page.getByTestId("gb-hover")).toBeVisible();
  });
});

test.describe("a hub (US-068-AC3, US-069-AC3)", () => {
  test("25 neighbours: 20 labelled, show more for the rest, and the picture draws all 25", async ({
    page,
  }) => {
    const seen = record(page);
    await as(page, "carol", `#/explore/catalog/UseCase/${HUB_25}`);
    const list = group(page, /Addressed by/);
    await expect(list.getByRole("link")).toHaveCount(20);
    await expect(list).toContainText("25");
    await expect(page.getByTestId("gb-picture-count")).toHaveText("25 of 25 neighbours shown");
    await expect(page.locator("a.gb-node")).toHaveCount(25);
    await list.getByRole("button", { name: /Show more/ }).click();
    await expect(list.getByRole("link")).toHaveCount(25);
    await settled(seen);
    expect(seen.length).toBeGreaterThan(3);
  });

  test("120 neighbours: the picture draws 40 round-robin and says so, the list says 100 or more and reads further through the inverse", async ({
    page,
  }) => {
    const bodies: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().includes("/graphql/catalog"))
        bodies.push(r.postData() ?? "");
    });
    await as(page, "carol", `#/explore/catalog/UseCase/${HUB_120}`);
    const list = group(page, /Addressed by/);
    await expect(list).toContainText("100 or more");
    await expect(list.getByRole("link")).toHaveCount(20);
    await expect(page.getByTestId("gb-picture-count")).toHaveText("40 of 100+ neighbours shown");
    await expect(page.locator("a.gb-node")).toHaveCount(40);
    await expect(page.getByRole("group", { name: /^Neighbourhood of/ })).toContainText(
      "ADDRESSED BY · +60 or more",
    );
    for (let n = 40; n <= 100; n += 20) {
      await list.getByRole("button", { name: /Show more \(/ }).click();
      await expect(list.getByRole("link")).toHaveCount(n);
    }
    await list.getByRole("button", { name: "Show more" }).click(); // the inverse, after the last key
    await expect(list.getByRole("link")).toHaveCount(120);
    // no label request carried more than 20 targets or 50 selections
    for (const b of bodies) {
      const q = (JSON.parse(b) as { query: string }).query;
      expect((q.match(/\$k\d+: String!/g) ?? []).length).toBeLessThanOrEqual(20);
    }
    expect(bodies.length).toBeGreaterThan(3);
  });
});

test.describe("states", () => {
  test("a backend that is down shows the Retry state, and mending it brings the page back", async ({
    page,
    request,
  }) => {
    await as(page, "carol", "#/explore/catalog/Solution/sol-1");
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline extractor" })).toBeVisible();
    await control(request, { op: "outage", backend: "memory", reason: "unreachable" });
    try {
      await page.goto("/#/explore/catalog/Solution/sol-extract");
      await page.reload();
      await page.getByLabel("Person").selectOption("carol");
      await expect(page.getByRole("heading", { name: "The catalog did not answer" })).toBeVisible();
      await expect(page.getByText(/memory is not responding/)).toBeVisible();
    } finally {
      await control(request, { op: "outage", backend: "memory", reason: null });
    }
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pattern extractor" })).toBeVisible();
  });
});

/**
 * axe cannot compute the background of SVG `<text>` (the picture's captions and labels sit on an SVG
 * rect), so it reports their contrast as "needs review". They use the same tokens as the HTML text
 * (`--fg`, `--fg-muted` on `--surface` or the tone's `--soft`), whose pairs are checked at design time
 * (DESIGN-GB, Tokens). Anything else axe cannot decide fails this test.
 */
const ALLOW_REVIEW = (id: string, html: string) => id === "color-contrast" && /^<text\b/.test(html);

const SCREENS: { name: string; person: string; hash: string; ready: (p: Page) => Promise<void> }[] =
  [
    {
      name: "entry",
      person: "carol",
      hash: "#/explore/catalog",
      ready: (p) => expect(p.getByRole("heading", { level: 1, name: "catalog" })).toBeVisible(),
    },
    {
      name: "type list",
      person: "carol",
      hash: "#/explore/catalog/Solution",
      ready: (p) => expect(p.locator("a.gb-hit").first()).toBeVisible(),
    },
    {
      name: "results",
      person: "carol",
      hash: "#/explore/catalog",
      ready: async (p) => {
        await p.getByRole("textbox", { name: /Search/ }).fill("pipeline");
        await expect(p.getByTestId("gb-status")).toBeVisible();
      },
    },
    {
      name: "no results",
      person: "carol",
      hash: "#/explore/catalog",
      ready: async (p) => {
        await p.getByRole("textbox", { name: /Search/ }).fill("zzzzqqq");
        await expect(p.getByRole("heading", { name: /No results for/ })).toBeVisible();
      },
    },
    {
      name: "node page",
      person: "carol",
      hash: "#/explore/catalog/Solution/sol-1",
      ready: (p) => expect(p.locator("a.gb-node").first()).toBeVisible(),
    },
    {
      name: "node page with a hub",
      person: "carol",
      hash: `#/explore/catalog/UseCase/${HUB_120}`,
      ready: (p) => expect(p.locator("a.gb-node")).toHaveCount(40),
    },
    {
      name: "not available",
      person: "carol",
      hash: "#/explore/catalog/Solution/ghost",
      ready: (p) => expect(p.getByTestId("gb-state")).toBeVisible(),
    },
    {
      name: "operator's top bar with the mode switch",
      person: "alice",
      hash: "#/explore/catalog/Solution/sol-1",
      ready: (p) => expect(p.getByRole("group", { name: "Mode" })).toBeVisible(),
    },
  ];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme, viewport: { width: 1280, height: 2400 } });
    for (const s of SCREENS) {
      test(`${s.name}: no WCAG A/AA violation`, async ({ page }) => {
        await page.goto(`/${s.hash}`);
        await page.getByLabel("Person").selectOption(s.person);
        await s.ready(page);
        expect(
          await page.evaluate(
            () => getComputedStyle(document.querySelector(".arras-root") as Element).colorScheme,
          ),
        ).toBe(scheme);
        const r = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        expect(r.passes.length).toBeGreaterThan(10);
        const found = r.violations.map((v) => ({
          id: v.id,
          help: v.help,
          nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
        }));
        expect(found, JSON.stringify(found, null, 2)).toEqual([]);
        const review = r.incomplete.flatMap((v) =>
          v.nodes
            .filter((n) => !ALLOW_REVIEW(v.id, n.html))
            .map(
              (n) => `${v.id}: ${n.html.slice(0, 140)} (${n.any.map((c) => c.message).join("; ")})`,
            ),
        );
        expect(review, review.join("\n")).toEqual([]);
      });
    }
  });
}

test.describe("Explore state in the address (FR-74)", () => {
  test("a list's position is in its address: a refresh at a ?after= address restores the positioned list", async ({
    page,
  }) => {
    await as(page, "carol", "#/explore/catalog/Solution?after=uc-hub-120-s009");
    const rows = page.locator(".gb-hits .gb-t");
    await expect(rows.first()).toHaveText(/Hub solution 010/);
    await expect(rows).toHaveCount(50);
    const entries = await page.evaluate(() => window.history.length);
    await page.getByRole("button", { name: "Show next 50" }).click();
    await expect(rows).toHaveCount(100);
    // Show next moved the position in place: the same history entry, the new start in the address
    await expect
      .poll(() => new URL(page.url()).hash)
      .toBe("#/explore/catalog/Solution?after=uc-hub-120-s059");
    expect(await page.evaluate(() => window.history.length)).toBe(entries);
    await page.reload();
    await expect(rows.first()).toHaveText(/Hub solution 060/);
    await expect(rows).toHaveCount(50);
  });

  test("a pasted /history address, read as carol, shows the entity's page", async ({ page }) => {
    await as(page, "carol", "#/explore/catalog/UseCase/uc-pipeline/history");
    await expect(page.getByRole("heading", { level: 1, name: "Pipeline mapping" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/explore/catalog/UseCase/uc-pipeline/history");
    await expect(page).toHaveTitle("Pipeline mapping · Use cases · catalog · Arras");
  });
});
