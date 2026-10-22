// SPDX-License-Identifier: MIT OR Apache-2.0
// Captures screenshots of the console for design review: node e2e/shots.mjs <outdir> [baseURL]
import { chromium } from "@playwright/test";

const out = process.argv[2] ?? "shots";
const base = process.argv[3] ?? "http://127.0.0.1:8123";
const b = await chromium.launch();
const mk = async (opts = {}) =>
  (await b.newContext({ viewport: { width: 1440, height: 900 }, ...opts })).newPage();
const p = await mk();
const shot = async (n, page = p) => {
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/${n}.png` });
};
await p.goto(`${base}/#/catalog/model`);
await p.waitForSelector("text=catalog");
await shot("01-schema");
await p.goto(`${base}/#/catalog/graph`);
await p.waitForSelector("[data-testid=node]");
await shot("02-graph");
await p.getByRole("button", { name: /Solution Pipeline risk scorer/ }).click();
await shot("03-graph-selected");
await p.getByRole("button", { name: /CorrectSolution/ }).click();
await p.getByLabel(/^level/).fill("full");
await p.getByLabel(/^level/).blur();
await p.waitForSelector("[data-testid=impact-graph]");
await shot("04-actions-impact");
await p.getByTestId("confirm").click();
await p.getByTestId("receipt").waitFor();
await shot("05-applied");
await p.getByRole("button", { name: "View in graph" }).click();
await p.waitForSelector("[data-testid=changed-banner]");
await shot("06-graph-changed");
// create a solution, retire a use case
await p.goto(`${base}/#/catalog/actions/catalog.AddSolution`);
await p.getByLabel(/^code/).fill("sol-demo");
await p.getByLabel(/^name/).fill("Demo solution");
await p.getByLabel(/^useCase/).fill("uc-dependency-study");
await p.getByLabel(/^useCase/).blur();
await p.waitForSelector("[data-testid=impact-graph]");
await shot("07-impact-create");
await p.goto(`${base}/#/catalog/actions/catalog.RetireUseCase`);
await p.getByLabel(/^useCase/).fill("uc-pipeline-review");
await p.getByLabel(/^useCase/).blur();
await p.waitForSelector("[data-testid=impact-graph]");
await shot("08-impact-delete");
await p.goto(`${base}/#/catalog/entities`);
await p.waitForSelector("table");
await shot("09-data");
await p.getByText("uc-capacity-check").first().click();
await shot("10-data-entity");
await p.goto(`${base}/#/catalog/changes`);
await shot("11-audit");
const d = await mk({ colorScheme: "dark" });
await d.goto(`${base}/#/catalog/graph`);
await d.waitForSelector("[data-testid=node]");
await shot("12-dark-graph", d);
await d.goto(`${base}/#/catalog/model`);
await shot("13-dark-schema", d);
const n = await (await b.newContext({ viewport: { width: 900, height: 800 } })).newPage();
await n.goto(`${base}/#/catalog/graph`);
await n.waitForSelector("[data-testid=node]");
await shot("14-narrow-graph", n);
await n.goto(`${base}/#/catalog/actions/catalog.AddSolution`);
await shot("15-narrow-actions", n);
await b.close();
