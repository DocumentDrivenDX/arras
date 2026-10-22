// SPDX-License-Identifier: MIT OR Apache-2.0
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Request, test } from "@playwright/test";
import { ORIGIN } from "./acceptance";
import { ensureUseCase } from "./gb-fixtures";

// An entity's History panel in the Graph Browser (FR-69), whole stack: the built UI served by the
// dev host, read as the sandbox's people. alice is an operator (edit offer, journal grant); carol is not.

const CODE = "uc-history-e2e";
const ENTITY = `#/explore/catalog/UseCase/${CODE}`;
const HISTORY = `${ENTITY}/history`;

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: ORIGIN });
  await ensureUseCase(request, CODE, "History e2e use case", "history");
  await request.dispose();
});

async function as(page: Page, person: string, hash: string) {
  await page.goto(`/${hash}`);
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

/** The operate calls the page makes, as "METHOD path". */
function recordOperate(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (r: Request) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/operate")) seen.push(`${r.method()} ${u.pathname}`);
  });
  return seen;
}

test.describe("an entity's history", () => {
  test("History opens the panel at the history address, a refresh restores it and Back closes it", async ({
    page,
  }) => {
    await as(page, "alice", ENTITY);
    await page.getByRole("button", { name: "History" }).click();
    await expect(page).toHaveURL(new RegExp(`${CODE}/history$`));
    const panel = page.getByTestId("gb-history");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("gb-change").first()).toContainText("alice");
    await page.reload();
    await page.getByLabel("Person").selectOption("alice");
    await expect(page.getByTestId("gb-history")).toBeVisible();
    await expect(page.getByTestId("gb-history").getByTestId("gb-change").first()).toBeVisible();
    await page.goBack();
    await expect(page.getByTestId("gb-history")).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`${CODE}$`));
  });

  test("a change's group links to Operate's receipt view and Back returns to the History panel", async ({
    page,
  }) => {
    await as(page, "alice", HISTORY);
    const group = page.getByTestId("gb-change").first().locator(".gb-hist-group");
    const id = (await group.textContent()) ?? "";
    expect(id).not.toBe("");
    await expect(group).toHaveAttribute("href", `#/operate/catalog/changes?group=${id}`);
    await group.click();
    await expect(page).toHaveURL(new RegExp(`#/operate/catalog/changes\\?group=${id}$`));
    await expect(page.getByTestId("gb-history")).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`${CODE}/history$`));
    await expect(page.getByTestId("gb-history")).toBeVisible();
  });

  test("the recorder shows only `changes` added to the browser's calls, and none for carol", async ({
    page,
  }) => {
    await as(page, "carol", ENTITY);
    const carol = recordOperate(page);
    await page.goto(`/${HISTORY}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "History e2e use case" }),
    ).toBeVisible();
    await expect(page.getByTestId("gb-history")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "History" })).toHaveCount(0);
    // The viewer was read before the recorder attached; opening the history address adds no call.
    expect(carol).toEqual([]);

    await as(page, "alice", ENTITY);
    const alice = recordOperate(page);
    await page.goto(`/${HISTORY}`);
    await expect(page.getByTestId("gb-change").first()).toBeVisible();
    expect(new Set(alice)).toEqual(new Set(["POST /api/operate/audit/changes"]));
  });

  test("at 390px the panel is the one pane and has a way back", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await as(page, "alice", HISTORY);
    await expect(page.getByTestId("gb-history")).toBeVisible();
    await expect(page.locator("article.gb-card")).toBeHidden();
    await page.getByRole("button", { name: /^Back to / }).click();
    await expect(page.locator("article.gb-card")).toBeVisible();
    await expect(page.getByTestId("gb-history")).toHaveCount(0);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme, viewport: { width: 1280, height: 1600 } });
    test("the history panel has no WCAG A/AA violation", async ({ page }) => {
      await as(page, "alice", HISTORY);
      await expect(page.getByTestId("gb-change").first()).toBeVisible();
      const r = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const found = r.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
      }));
      expect(found, JSON.stringify(found, null, 2)).toEqual([]);
      const review = r.incomplete.flatMap((v) =>
        v.nodes
          .filter((n) => !(v.id === "color-contrast" && /^<text\b/.test(n.html)))
          .map((n) => `${v.id}: ${n.html.slice(0, 140)}`),
      );
      expect(review, review.join("\n")).toEqual([]);
    });
  });
}
