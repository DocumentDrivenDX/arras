// SPDX-License-Identifier: MIT OR Apache-2.0
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { AREA_LABELS } from "../src/lib/vocabulary";
import { defined } from "../src/test/defined";
import { asBob } from "./gb-fixtures";

// More whole-stack flows on the dev host (playwright.config.ts starts it with the demo catalog).
// The sandbox has no reset and the server is shared by every test of the run, so each test makes
// its own entities (unique codes) and mends what it breaks through the control endpoint.
// A 409 revision conflict cannot be provoked honestly through the UI (nothing in the UI or the dev
// host changes a module's revision); it is covered by src/integration/actions.int.test.tsx.

const uid = (p: string) =>
  `${p}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;

async function control(
  request: APIRequestContext,
  baseURL: string | undefined,
  data: Record<string, unknown>,
) {
  const r = await request.post("/api/dev/control", {
    data,
    headers: { origin: defined(baseURL, "baseURL") },
  });
  expect(r.status(), await r.text()).toBe(200);
}

async function as(page: Page, person: string, hash = "#/catalog/model") {
  await page.goto(`/${hash}`);
  await page.reload(); // a hash change alone does not reload: start a fresh console
  await page.getByLabel("Person").selectOption(person);
  await expect(page.getByLabel("Person")).toHaveValue(person);
}

test("validation: the browser's and the server's answers at the fields, and no invoke offered", async ({
  page,
}) => {
  await as(page, "alice", "#/catalog/actions/catalog.AddUseCase");
  // A required field left empty is caught before any request.
  await page.getByLabel(/^code/).fill(uid("uc"));
  await page.getByLabel(/^name/).focus();
  await page.getByLabel(/^name/).blur();
  await expect(page.getByTestId("err-name")).toHaveText("Expected a value (required)");
  await expect(page.getByTestId("confirm")).toBeDisabled();
  // A duplicate code is refused by the module's precondition, with its reason.
  await page.getByLabel(/^code/).fill("uc-pipeline");
  await page.getByLabel(/^name/).fill("Duplicate");
  await page.getByTestId("validate").click();
  await expect(page.getByTestId("precondition-fresh")).toContainText(
    "a use case with that code exists",
  );
  await expect(page.getByTestId("not-valid")).toBeVisible();
  await expect(page.getByTestId("confirm")).toBeDisabled();
});

test("batch: an atomic batch with a failing item applies nothing; independent applies the rest", async ({
  page,
}) => {
  await as(page, "alice", "#/catalog/actions/catalog.AddUseCase");
  await page.getByRole("tab", { name: "Batch" }).click();
  const a = uid("ba");
  const b = uid("bb");
  const items = JSON.stringify([
    { code: a, name: "Batch A" },
    { code: "uc-pipeline", name: "dup" },
    { code: b, name: "Batch B" },
  ]);
  await page.getByLabel("Items").fill(items);
  await expect(page.getByText("3 items")).toBeVisible();
  await page.getByLabel(/Atomic/).check();
  await page.getByRole("button", { name: /Review batch/ }).click();
  await page.getByRole("button", { name: /Confirm and apply batch/ }).click();
  await expect(page.getByText("A precondition failed")).toBeVisible();
  await expect(page.getByTestId("batch-result")).toHaveCount(0);

  await page.getByLabel(/Atomic/).uncheck();
  await page.getByRole("button", { name: /Review batch/ }).click();
  await page.getByRole("button", { name: /Confirm and apply batch/ }).click();
  const result = page.getByTestId("batch-result");
  await expect(result).toContainText("2 applied");
  await expect(result).toContainText("1 refused");
  await expect(page.getByTestId("batch-refusal-1")).toContainText(
    "fresh: a use case with that code exists",
  );
  await expect(page.getByTestId("batch-item-0")).toContainText(a);
  await expect(page.getByTestId("batch-item-2")).toContainText(b);

  // The atomic attempt left nothing: the table has b once and a once (from the independent run).
  await page.goto("/#/catalog/entities/catalog.UseCase");
  await page.getByLabel("Filter code").fill(a);
  await page.getByLabel("Filter code").press("Enter");
  await expect(page.getByTestId("page-info")).toContainText("1 rows");
});

test("audit: history, person and action filters, a receipt by group, and loads", async ({
  page,
}) => {
  const code = uid("au");
  await as(page, "bob", "#/catalog/actions/catalog.AddUseCase");
  await page.getByLabel(/^code/).fill(code);
  await page.getByLabel(/^name/).fill("Audited");
  await page.getByLabel(/^name/).blur();
  await page.getByTestId("confirm").click();
  const receipt = page.getByTestId("receipt");
  await expect(receipt).toContainText("Applied");
  const group = defined(
    defined(
      /group (g-\d+)/.exec((await receipt.textContent()) ?? ""),
      '/group (g-\\d+)/.exec((await receipt.textContent()) ?? "")',
    )[1],
    'defined(/group (g-\\d+)/.exec((await receipt.textContent()) ?? ""), "/group (g-\\\\d+)/.exec((await receipt.textContent()) ?? \\"\\")")[1]',
  );

  await page.getByRole("tab", { name: "Changes" }).click();
  await expect(page.getByTestId("change-row").first()).toBeVisible();
  await page.getByLabel("Person").last().fill("bob");
  await page.getByLabel("Action").selectOption("catalog.AddUseCase");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("change-row").first()).toContainText(code);
  for (const row of await page.getByTestId("change-row").all())
    await expect(row.locator("td").nth(1)).toHaveText("bob");

  // History of the entity
  await page.getByLabel("Type").selectOption("catalog.UseCase");
  await page.getByLabel("Key").fill(code);
  await page.getByLabel("Person").last().fill("");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("change-row")).toHaveCount(1);

  await page.getByRole("tab", { name: "Receipt by group" }).click();
  await page.getByLabel("Group id").fill(group);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("change-row")).toHaveCount(1);
  await expect(page.getByTestId("change-row")).toContainText(group);

  await page.getByRole("tab", { name: "Import loads" }).click();
  await expect(page.getByText("No loads recorded for this module")).toBeVisible();
});

test("an expired token: the console asks to sign in again, and works once the token is restored", async ({
  page,
  request,
  baseURL,
}) => {
  await as(page, "bob", "#/catalog/actions/catalog.CorrectSolution");
  await expect(page.getByLabel(/^solution/)).toBeVisible();
  await control(request, baseURL, { op: "expire", user: "bob" });
  try {
    await page.getByLabel(/^solution/).fill("sol-1");
    await page.getByLabel(/^level/).fill("full");
    await page.getByTestId("validate").click();
    await expect(page.getByRole("alert").filter({ hasText: "Sign in again" })).toBeVisible();
    await expect(page.getByTestId("confirm")).toBeDisabled();
    // A fresh load says the same, before any module is shown.
    await page.reload();
    await page.getByLabel("Person").selectOption("bob");
    await expect(page.getByRole("alert").filter({ hasText: "Sign in again" })).toBeVisible();
  } finally {
    await control(request, baseURL, { op: "restore", user: "bob" });
  }
  await page.reload();
  await page.getByLabel("Person").selectOption("bob");
  await expect(page.getByRole("button", { name: /^catalog/ })).toBeVisible();
});

test("an outage names the backend, and the console recovers when it is mended", async ({
  page,
  request,
  baseURL,
}) => {
  await as(page, "alice", "#/catalog/entities/catalog.Solution");
  await expect(page.getByText("sol-1", { exact: true })).toBeVisible();
  await control(request, baseURL, { op: "outage", backend: "memory", reason: "unreachable" });
  try {
    await as(page, "alice", "#/catalog/actions/catalog.CorrectSolution");
    await page.getByLabel(/^solution/).fill("sol-1");
    await page.getByLabel(/^level/).fill("full");
    await page.getByTestId("validate").click();
    const alert = page.getByRole("alert").filter({ hasText: "Backend unavailable" });
    await expect(alert).toContainText("memory is unavailable (unreachable)");
    await as(page, "alice", "#/catalog/entities/catalog.Solution");
    await expect(page.getByRole("alert").filter({ hasText: "UNAVAILABLE" })).toContainText(
      "memory unavailable (unreachable)",
    );
    await expect(page.getByTestId("freshness")).toHaveCount(0); // no page was read, so no freshness is claimed
  } finally {
    await control(request, baseURL, { op: "outage", backend: "memory", reason: null });
  }
  // The table said "retry"; it offers it, and the record store answers again.
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("sol-1", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "UNAVAILABLE" })).toHaveCount(0);
  await expect(page.getByTestId("freshness")).toContainText("record: memory");
});

test("personas: bob applies a change attributed to bob; root, the administrator, is refused the console", async ({
  page,
}) => {
  const code = uid("bob");
  await as(page, "bob", "#/catalog/actions/catalog.AddUseCase");
  await page.getByLabel(/^code/).fill(code);
  await page.getByLabel(/^name/).fill("By bob");
  await page.getByLabel(/^name/).blur();
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("receipt")).toContainText("Applied");
  await as(page, "bob", "#/catalog/entities/catalog.UseCase");
  await page.getByLabel("Filter code").fill(code);
  await page.getByLabel("Filter code").press("Enter");
  await page.getByText(code, { exact: true }).click();
  await expect(page.getByTestId("entity-panel").getByTestId("entity-created-by")).toHaveText("bob");
  await expect(page.getByTestId("entity-panel").getByTestId("entity-updated-by")).toHaveText("bob");

  // root registers modules and is refused every user operation (`describe` included): no access, with
  // the reason, not "request failed".
  await page.getByLabel("Person").selectOption("root");
  const alert = page.getByRole("alert").filter({ hasText: "No access" });
  await expect(alert).toContainText("no_access");
  await expect(page.getByRole("navigation", { name: "Modules" })).toHaveCount(0);
});

test("the person picker starts a fresh console: what alice may do, a read-only operator is refused, a reader is not offered the console", async ({
  page,
  request,
}) => {
  await as(page, "alice", "#/operate/catalog/actions/catalog.CorrectSolution");
  await page.getByLabel(/^solution/).fill("sol-1");
  await page.getByLabel(/^level/).fill("partial");
  await page.getByLabel(/^level/).blur();
  await expect(page.getByTestId("confirm")).toBeEnabled();
  // carol and dave are not operators (CONTRACT-010): the console is not offered, the Graph Browser is
  await page.getByLabel("Person").selectOption("carol");
  await expect(page.getByTestId("gb")).toBeVisible();
  await expect(page.getByTestId("console-header")).toHaveCount(0);
  await asBob(request, ["read"], async () => {
    await page.getByLabel("Person").selectOption("bob");
    await expect(page.getByLabel(/^level/)).toHaveValue("");
    await page.getByLabel(/^solution/).fill("sol-1");
    await page.getByLabel(/^level/).fill("partial");
    await page.getByTestId("validate").click();
    await expect(page.getByText(/The provider refused you/)).toBeVisible();
  });
  await page.getByLabel("Person").selectOption("alice");
  await expect(page.getByRole("button", { name: /^catalog/ })).toBeVisible();
  // No person or input ever reaches the URL or browser storage.
  expect(page.url()).not.toMatch(/alice|carol|dave|bob|sol-1|partial/);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
});

test("a legacy address opens the new area and is rewritten in place: schema is Model, data is Entities, audit is Changes", async ({
  page,
}) => {
  await page.goto("/#/catalog/schema");
  await page.reload();
  await expect(page.getByRole("tab", { name: "Model", selected: true })).toBeVisible();
  await expect.poll(() => new URL(page.url()).hash).toBe("#/operate/catalog/model");
  const depth = await page.evaluate(() => window.history.length);
  await page.goto("/#/operate/catalog/data/catalog.UseCase");
  await page.reload();
  await expect(page.getByRole("tab", { name: "Entities", selected: true })).toBeVisible();
  await expect
    .poll(() => new URL(page.url()).hash)
    .toBe("#/operate/catalog/entities/catalog.UseCase");
  await page.goto("/#/operate/catalog/audit/catalog.Solution/sol-1");
  await page.reload();
  await expect(
    page
      .getByRole("tablist", { name: "Areas" })
      .getByRole("tab", { name: "Changes", selected: true }),
  ).toBeVisible();
  await expect
    .poll(() => new URL(page.url()).hash)
    .toBe("#/operate/catalog/changes/catalog.Solution/sol-1");
  // The rewrite replaced the entry: Back from the rewritten address does not return to the alias.
  expect(await page.evaluate(() => window.history.length)).toBeGreaterThanOrEqual(depth);
});

test("keyboard: areas by number, the table by arrows and Enter, the filter by /, the graph by arrows", async ({
  page,
}) => {
  await as(page, "alice", "#/catalog/model");
  await page.locator("body").press("3"); // Data
  await expect(page.getByRole("tab", { name: "Entities", selected: true })).toBeVisible();
  const grid = page.getByRole("table", { name: "catalog.UseCase table" });
  await expect(grid.locator("button[data-row-stop]").first()).toBeVisible({ timeout: 15_000 });
  await expect(grid.getByText("uc-pipeline", { exact: true })).toBeVisible({ timeout: 15_000 });
  const rowButtons = grid.locator("button[data-row-stop]");
  await rowButtons.first().focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("ArrowDown");
  const focused = await page.locator("tr.focused td").first().textContent();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("entity-panel")).toContainText(defined(focused, "focused"));
  await rowButtons.first().focus();
  await page.keyboard.press("/");
  await expect(page.getByLabel("Filter code")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(rowButtons.nth(1)).toBeFocused();

  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("2"); // Graph
  const first = page.getByTestId("node").first();
  await expect(first).toBeVisible();
  await page.locator("button.arras-node-hit[tabindex='0']").focus();
  const start = await page.evaluate(() => document.activeElement?.getAttribute("data-node-id"));
  await page.keyboard.press("ArrowDown");
  const next = await page.evaluate(() => document.activeElement?.getAttribute("data-node-id"));
  expect(next).not.toBe(start);
  await page.keyboard.press("ArrowRight");
  const across = await page.evaluate(() => document.activeElement?.getAttribute("data-node-id"));
  expect(across?.split(":")[0]).not.toBe(next?.split(":")[0]); // another lane (type)
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("entity-panel")).toContainText(
    defined(across, "across").slice(defined(across, "across").indexOf(":") + 1),
  );
});

test("a name with markup is shown as text in the table, the panel and the graph (no script runs)", async ({
  page,
}) => {
  const code = uid("xss");
  const evil = `<img src=x onerror="window.__xss=1">`;
  await as(page, "alice", "#/catalog/actions/catalog.AddUseCase");
  await page.getByLabel(/^code/).fill(code);
  await page.getByLabel(/^name/).fill(evil);
  await page.getByLabel(/^name/).blur();
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("receipt")).toContainText("Applied");
  await page.goto("/#/catalog/entities/catalog.UseCase");
  await page.getByLabel("Filter code").fill(code);
  await page.getByLabel("Filter code").press("Enter");
  await expect(page.getByText(evil, { exact: true })).toBeVisible();
  await page.getByText(code, { exact: true }).click();
  await expect(page.getByTestId("entity-panel").getByTestId("prop-name")).toHaveText(evil);
  await page.getByRole("tab", { name: "Graph" }).click();
  await page.getByLabel("Filter entities").fill(code);
  await expect(
    page.locator(`[data-testid="node"][data-node-id="catalog.UseCase:${code}"]`),
  ).toContainText("<img");
  expect(
    await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
  ).toBeUndefined();
  expect(await page.locator("main img").count()).toBe(0);
});

for (const scheme of ["light", "dark"] as const) {
  for (const width of [900, 375]) {
    test(`${width}px, ${scheme}: no sideways page scroll and the key controls reachable`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.emulateMedia({ colorScheme: scheme });
      for (const area of ["model", "graph", "entities", "actions", "changes"] as const) {
        await page.goto(`/#/catalog/${area}`);
        await expect(
          page
            .getByRole("tablist", { name: "Areas" })
            .getByRole("tab", { name: AREA_LABELS[area], selected: true }),
        ).toBeVisible();
        const sideways = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(sideways, `${area} at ${width}px`).toBeLessThanOrEqual(0);
      }
      // UMF source: the schema browser's iframe fits the page; it scrolls inside its own frame.
      await page.goto("/#/catalog/model");
      await page.getByRole("button", { name: "UMF source" }).click();
      const umf = page.locator('iframe[title="UMF schema browser"]');
      await expect(
        page.frameLocator('iframe[title="UMF schema browser"]').locator("#inspector"),
      ).toContainText("Use Case", { timeout: 20_000 });
      const frameBox = defined(await umf.boundingBox(), "(await umf.boundingBox())");
      expect(frameBox.x + frameBox.width, `UMF source frame at ${width}px`).toBeLessThanOrEqual(
        width,
      );
      expect(frameBox.height).toBeGreaterThanOrEqual(600);
      const inner = await umf.evaluate((f: HTMLIFrameElement) => {
        const root = f.contentDocument?.documentElement;
        if (!root) throw new Error("the frame has no document");
        return root.scrollWidth - root.clientWidth;
      });
      expect(inner, `inside the UMF frame at ${width}px`).toBeLessThanOrEqual(0);
      expect(
        await umf.evaluate(
          (f: HTMLIFrameElement) => f.contentDocument?.documentElement.dataset.theme,
        ),
        "the frame follows the scheme",
      ).toBe(scheme);
      await expect(page.getByRole("button", { name: "Refresh badges" })).toBeInViewport();
      const wide = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(wide, `UMF source at ${width}px`).toBeLessThanOrEqual(0);
      expect(
        await page.evaluate(
          () => getComputedStyle(document.querySelector(".arras-root") as Element).colorScheme,
        ),
      ).toBe(scheme);
      // The person picker, the module and area tabs, and an action's controls are on screen and usable.
      await page.goto("/#/catalog/actions/catalog.CorrectSolution");
      await expect(page.getByLabel("Person")).toBeInViewport();
      // The module: a rail button from 768px; below it the module picker (or just the title for one module).
      await expect(
        width >= 768
          ? page.getByRole("button", { name: /^catalog/ })
          : page.getByRole("heading", { level: 1, name: "catalog" }),
      ).toBeInViewport();
      await page.getByLabel(/^solution/).fill("sol-1");
      await page.getByLabel(/^level/).fill("partial");
      await page.getByTestId("validate").scrollIntoViewIfNeeded();
      await page.getByTestId("validate").click();
      await page.getByTestId("confirm").scrollIntoViewIfNeeded();
      await expect(page.getByTestId("confirm")).toBeInViewport();
      await expect(page.getByTestId("confirm")).toBeEnabled();
      await page.getByRole("tab", { name: "Entities" }).click();
      await page.getByText("uc-pipeline", { exact: true }).click();
      await page.getByTestId("entity-panel").scrollIntoViewIfNeeded();
      await expect(page.getByRole("button", { name: "Close entity panel" })).toBeInViewport();
    });
  }
}
