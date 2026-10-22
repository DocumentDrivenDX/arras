// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { defined } from "../src/test/defined";

// Schema import and export, and the sandbox toolbar (OPR-12 to OPR-15), whole stack: the built console on
// the real dev host, under its strict Content-Security-Policy (`default-src 'none'; ... connect-src 'self'`).
// The export is a Blob behind an object URL saved by an `<a download>`: this proves the policy admits it
// (any CSP violation or page error fails). This file runs against a dev host of its own (playwright.config.ts)
// because it registers a revision of `catalog`.

const AUTHOR = { name: "ana", role: "schema author" };

/** Every CSP violation and page error in the page, as text. */
function watch(page: Page): string[] {
  const seen: string[] = [];
  page.on("console", (m) => {
    // A refused or unavailable answer is logged by the browser as "Failed to load resource": expected here.
    if (
      /Content Security Policy|CSP violation/.test(m.text()) ||
      (m.type() === "error" && !/Failed to load resource/.test(m.text()))
    )
      seen.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => seen.push(`pageerror: ${e.message}`));
  void page.exposeFunction("reportCsp", (text: string) =>
    seen.push(`console: CSP violation: ${text}`),
  );
  void page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) =>
      (window as unknown as { reportCsp: (text: string) => void }).reportCsp(
        `${e.violatedDirective} ${e.blockedURI} ${e.sourceFile}:${e.lineNumber}`,
      ),
    );
  });
  return seen;
}

async function asCustom(page: Page, name: string, role: string) {
  await page.goto("/#/catalog/model");
  await page.getByLabel("Person").selectOption({ label: "Custom name and role…" });
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Role").selectOption(role);
  await page.getByRole("button", { name: "Use", exact: true }).click();
  await expect(page.getByRole("button", { name: "Import" })).toBeVisible();
}

/** The registered document of catalog, as the viewer's catalog holds it. */
async function registered(page: Page, who = AUTHOR): Promise<string> {
  const r = await page.request.get("/api/operate/explorer/schema-catalog.json", {
    headers: { "x-arras-user": who.name, "x-arras-role": who.role },
  });
  const entries = (await r.json()).entries as { id: string; text: string }[];
  return defined(
    entries.find((e) => e.id === "arras:catalog"),
    "the catalog entry",
  ).text;
}

/** The document with one more optional property (tests/test_schema_library.py `with_property`). */
function withOptional(text: string, name: string): string {
  const d = JSON.parse(text);
  const els = d.modules[0].elements;
  const rec = els.find((e: { id: string }) => e.id === "UseCase");
  rec.members.push({ module: "catalog", element: `UseCase.${name}` });
  rec.extensions["umf.ddd"].fields[name] = {
    type: { kind: "scalar", name: "string" },
    cardinality: "optional",
  };
  els.push({
    id: `UseCase.${name}`,
    kind: "field",
    nullability: "absent-allowed",
    cardinality: "one",
    scalarType: "string",
    extensions: {},
  });
  return JSON.stringify(d);
}

const upload = (page: Page, text: string, name = "catalog.umf.json") =>
  page
    .getByLabel("UMF document", { exact: true })
    .setInputFiles({ name, mimeType: "application/json", buffer: Buffer.from(text) });

test("a viewer is refused by the backend: the reason is shown and Apply is disabled", async ({
  page,
}) => {
  const seen = watch(page);
  await asCustom(page, "zed", "viewer");
  await page.getByRole("button", { name: "Import" }).click();
  await upload(page, await registered(page, { name: "zed", role: "viewer" }));
  await page.getByRole("button", { name: "Validate" }).click();
  const why = page.getByTestId("schema-refused");
  await expect(why).toContainText("No access");
  await expect(why).toContainText("no_access");
  await expect(page.getByRole("button", { name: "Apply" })).toBeDisabled();
  await expect(page.getByLabel("UMF document", { exact: true })).toBeDisabled();
  expect(seen).toEqual([]);
});

test("a schema author previews and applies an optional property, exports it, and validating the export says nothing would change", async ({
  page,
}) => {
  const seen = watch(page);
  await asCustom(page, AUTHOR.name, AUTHOR.role);
  const doc = withOptional(await registered(page), "e2eNote");

  await page.getByRole("button", { name: "Import" }).click();
  await upload(page, doc);
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByTestId("plan-property")).toContainText("catalog.UseCase.e2eNote");
  await expect(page.getByTestId("current-document")).toHaveValue(/"module"/);
  expect(await registered(page)).not.toContain("e2eNote"); // validating applied nothing

  // an axe pass over the import view with a plan, and over the open sandbox controls
  const scan = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(scan.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html).join(" | ")}`)).toEqual(
    [],
  );

  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("schema-applied")).toContainText("Registered catalog");
  expect(await registered(page)).toBe(doc);
  await page.getByRole("button", { name: "Live registry" }).click();
  await expect(page.getByTestId("type-catalog.UseCase")).toContainText("e2eNote");

  // Export: a Blob download under the strict CSP, byte for byte as registered
  const [one] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export", exact: true }).click(),
  ]);
  expect(one.suggestedFilename()).toBe("catalog.umf.json");
  const exported = readFileSync(await one.path(), "utf8");
  expect(exported).toBe(doc);
  const [all] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export all" }).click(),
  ]);
  expect(all.suggestedFilename()).toBe("arras-schema-catalog.json");
  const file = JSON.parse(readFileSync(await all.path(), "utf8"));
  expect(file.version).toBe(1);
  expect(file.entries.map((e: { id: string; text: string }) => [e.id, e.text])).toContainEqual([
    "arras:catalog",
    doc,
  ]);

  // The export loaded back changes nothing
  await page.getByRole("button", { name: "Import" }).click();
  await upload(page, exported);
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByTestId("plan-unchanged")).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply" })).toBeDisabled();

  // nothing is kept in the browser, and no person or document is in the URL
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  expect(page.url()).not.toContain(AUTHOR.name);
  expect(seen).toEqual([]);
});

test("the sandbox toolbar breaks and mends a backend, and an invalid name is refused in the browser", async ({
  page,
}) => {
  const seen = watch(page);
  await page.goto("/#/catalog/model");
  await expect(page.getByText("dev host: no sign-in")).toBeVisible();
  await page.getByText("Sandbox", { exact: true }).click();
  // The sandbox badge says the backend is down; the page may also show its own notice.
  const badge = page.getByTestId("sandbox-controls").getByText("unavailable (unreachable)");
  await page.getByRole("button", { name: "Outage memory", exact: true }).click();
  await expect(badge).toBeVisible();
  await page.getByRole("button", { name: "Mend memory", exact: true }).click();
  await expect(badge).toHaveCount(0);

  await page.getByLabel("Person").selectOption({ label: "Custom name and role…" });
  const control = page
    .waitForRequest((r) => r.url().includes("/api/dev/control"), { timeout: 1000 })
    .then(
      () => true,
      () => false,
    );
  await page.getByLabel("Name").fill("Not Allowed");
  await page.getByRole("button", { name: "Use", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "lower-case" })).toBeVisible();
  expect(await control).toBe(false);
  expect(seen).toEqual([]);
});
