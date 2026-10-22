// SPDX-License-Identifier: MIT OR Apache-2.0
import { expect, test } from "@playwright/test";
import { asBob } from "./gb-fixtures";

// The primary operator workflow through the real UI against the dev host (FEAT-010, ADR-021):
// find a type, follow a relationship, run a declared correction, read the attributed change.
// The dev host seeds the sandbox: catalog with UseCase uc-pipeline and uc-alerts, Solution sol-1.
// People: root, alice (read/write/journal), carol (read only), bob (read/write/journal), dave (no access).

test("a builder corrects a solution and finds the change attributed to her", async ({ page }) => {
  await page.goto("/#/operate");
  await expect(page.getByRole("button", { name: /^catalog/ })).toBeVisible();

  // Pick the person (dev host only).
  await page.getByLabel("Person").selectOption("alice");
  await page.getByRole("button", { name: /^catalog/ }).click();

  // Open the UseCase table.
  await page.getByRole("tab", { name: "Entities" }).click();
  await page.getByRole("tab", { name: "UseCase" }).click();
  await expect(page.getByRole("cell", { name: "uc-pipeline", exact: true })).toBeVisible();
  await expect(page.getByTestId("freshness")).toContainText("LATEST");

  // Open the Solution and follow its relationship to the use case it addresses.
  await page.getByRole("tab", { name: "Solution" }).click();
  await page.getByRole("cell", { name: "sol-1" }).click();
  const panel = page.getByTestId("entity-panel");
  await expect(panel.getByTestId("entity-version")).toBeVisible();
  await panel.getByRole("button", { name: "uc-pipeline" }).click();
  await expect(panel).toContainText("UseCase");
  await expect(panel.getByTestId("prop-name")).toHaveText("Pipeline mapping");
  await panel.getByRole("button", { name: /back/ }).click();

  // Open the action from the entity: the ref input is prefilled.
  await panel.getByRole("button", { name: /CorrectSolution/ }).click();
  const solution = page.getByLabel(/^solution/);
  await expect(solution).toHaveValue("sol-1");
  await page.getByLabel(/^level/).fill("partial");
  await page.getByLabel(/^level/).blur();

  // Validate shows the effects; nothing has changed yet.
  await expect(page.getByTestId("effects")).toContainText('set coverageLevel="partial"');

  // Confirm explicitly, then read the receipt.
  await page.getByTestId("confirm").click();
  const receipt = page.getByTestId("receipt");
  await expect(receipt).toContainText("Applied");
  await expect(receipt).toContainText("sol-1");
  await expect(receipt).toContainText(/group g-\d+/);

  // The entity now shows the change, attributed to alice.
  await page.getByRole("tab", { name: "Entities" }).click();
  await page.getByRole("tab", { name: "Solution" }).click();
  await page.getByRole("cell", { name: "sol-1" }).click();
  await expect(page.getByTestId("entity-panel").getByTestId("prop-coverageLevel")).toHaveText(
    "partial",
  );
  await expect(page.getByTestId("entity-panel").getByTestId("entity-updated-by")).toHaveText(
    "alice",
  );

  // History, when the backend serves it, names the person and the action.
  await page.getByTestId("entity-panel").getByRole("button", { name: "History" }).click();
  const rows = page.getByTestId("change-row");
  await expect(rows.first()).toContainText("alice");
  await expect(rows.first()).toContainText("catalog.CorrectSolution");
});

// The sandbox's operators are alice, bob and root (CONTRACT-010); carol and dave are not, and the console is
// operator-only, so a read-only person and one with no access are bob with part of his access revoked.
test("a read-only operator is refused by the provider and sees the reason", async ({
  page,
  request,
}) => {
  await asBob(request, ["read"], async () => {
    await page.goto("/#/operate/catalog/actions/catalog.CorrectSolution");
    await page.getByLabel("Person").selectOption("bob");
    await page.getByLabel(/^solution/).fill("sol-1");
    await page.getByLabel(/^level/).fill("full");
    await page.getByTestId("validate").click();
    await expect(page.getByText(/The provider refused you/)).toBeVisible();
    await expect(page.getByTestId("confirm")).toHaveCount(0);
  });
});

test("an operator with no access to catalog sees no module", async ({ page, request }) => {
  await asBob(request, [], async () => {
    await page.goto("/#/operate/catalog/model");
    await page.getByLabel("Person").selectOption("bob");
    await expect(page.getByTestId("no-modules")).toBeVisible();
  });
});

// The graph, its impact preview and the receipt, on the dev host's demo catalog (14 use cases across
// 3 work areas, 11 solutions each addressing one use case).
test("an administrator sees the graph, previews a change on it, applies it and finds it highlighted", async ({
  page,
}) => {
  await page.goto("/#/operate");
  await page.getByLabel("Person").selectOption("alice");
  await page.getByRole("tab", { name: "Graph" }).click();

  // The graph itself: typed lanes with the demo entities and their links.
  const nodes = page.getByTestId("node");
  await expect(nodes.first()).toBeVisible();
  expect(await nodes.count()).toBeGreaterThanOrEqual(25);
  expect(await page.getByTestId("edge").count()).toBeGreaterThanOrEqual(11);
  await expect(page.getByTestId("freshness")).toContainText("LATEST");
  await page.getByLabel("Filter entities").fill("capacity");
  await expect(page.locator("[data-testid=node][data-dimmed=true]").first()).toBeVisible();
  await page.getByLabel("Filter entities").fill("");

  // Select an entity; the panel opens beside the graph.
  await page.getByRole("button", { name: /Solution Pipeline risk scorer/ }).click();
  const panel = page.getByTestId("entity-panel");
  await expect(panel.getByTestId("prop-name")).toHaveText("Pipeline risk scorer");

  // Run an action from it; the form is prefilled and the impact view starts empty.
  await panel.getByRole("button", { name: /CorrectSolution/ }).click();
  await expect(page.getByLabel(/^solution/)).toHaveValue("sol-pipeline-risk");
  await expect(page.getByTestId("impact-empty")).toBeVisible();
  await page.getByLabel(/^level/).fill("full");
  await page.getByLabel(/^level/).blur();

  // The preview draws the updated entity with before and after; nothing is applied yet.
  const impact = page.getByTestId("impact");
  await expect(impact).toHaveAttribute("data-state", "preview");
  await expect(impact.locator("[data-testid=node][data-status=updated]")).toHaveCount(1);
  await expect(page.getByTestId("impact-changes")).toContainText('"partial"');
  await expect(page.getByTestId("impact-changes")).toContainText('"full"');
  await expect(page.getByTestId("impact-summary")).toContainText("Updates 1 Solution");

  // Confirm, read the receipt, and the same view stays in its applied state.
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("receipt")).toContainText("Applied");
  await expect(impact).toHaveAttribute("data-state", "applied");
  await expect(page.getByTestId("next-steps")).toBeVisible();

  // Jump to the graph: the changed entity is outlined under a dismissible banner.
  await page.getByRole("button", { name: "View in graph" }).click();
  await expect(page.getByTestId("changed-banner")).toContainText(/Changed by group g-\d+/);
  await expect(page.locator("[data-testid=node][data-changed=true]")).toHaveCount(1);
  await expect(page.locator("[data-testid=node][data-changed=true]")).toContainText(
    "Pipeline risk scorer",
  );
  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page.getByTestId("changed-banner")).toHaveCount(0);
});

test("the impact of a delete shows the use case struck through and its links removed", async ({
  page,
}) => {
  await page.goto("/#/catalog/actions/catalog.RetireUseCase");
  await page.getByLabel(/^useCase/).fill("uc-capacity-check");
  await page.getByLabel(/^useCase/).blur();
  const impact = page.getByTestId("impact");
  await expect(impact.locator("[data-testid=node][data-status=deleted]")).toHaveCount(1);
  await expect(impact.locator("[data-testid=edge][data-status=removed]")).toHaveCount(1);
  await expect(page.getByTestId("impact-summary")).toContainText("Deletes 1 UseCase");
  // Reviewing applies nothing: the use case is still in the graph.
  await page.goto("/#/catalog/graph");
  await expect(page.getByRole("button", { name: /UseCase Capacity check/ })).toBeVisible();
});
