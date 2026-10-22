// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ActionForm } from "../areas/ActionForm";
import { AuditView } from "../areas/AuditView";
import { entityHref, groupHref } from "../route";
import {
  type FakeApi,
  json,
  type Recorded,
  receipt,
  seedCatalog,
  stage,
  validation,
  wire,
} from "./fake";
import { renderConsole, renderPart } from "./render";

// Links out of the audit tables and the apply receipt (FEAT-010 OPR-05, OPR-18).
let api: FakeApi;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const verb = (v: string) => (r: Recorded) => r.method === "POST" && r.path.endsWith(`/${v}`);
const changes = verb("audit/changes");
const calls = () => api.log.filter(changes);
const serve = (items: unknown[]) =>
  api.on((r) => (changes(r) ? json(200, wire.page(items, null)) : undefined));

describe("Changes links", () => {
  it("a changed entity opens in Entities and in its History; the group opens its receipt", async () => {
    serve([
      wire.change({
        ops: [{ kind: "update", type: "catalog.Product", key: "lumen", version: 2 }],
      }),
    ]);
    renderPart(<AuditView module="catalog" />);
    const row = await screen.findByTestId("change-row");
    expect(row).toHaveTextContent("update Product lumen");
    expect(
      within(row).getByRole("link", { name: "Open Product lumen in Entities" }),
    ).toHaveAttribute("href", entityHref("catalog", "entities", "catalog.Product", "lumen"));
    expect(within(row).getByRole("link", { name: "Open Product lumen history" })).toHaveAttribute(
      "href",
      entityHref("catalog", "changes", "catalog.Product", "lumen"),
    );
    expect(within(row).getByRole("link", { name: "Open receipt for group g-4" })).toHaveAttribute(
      "href",
      groupHref("catalog", "g-4"),
    );
  });

  it("a deleted entity is text, not a link to nothing; link ops link both ends", async () => {
    serve([
      wire.change({
        ops: [
          { kind: "delete", type: "catalog.Product", key: "old" },
          {
            kind: "link",
            relationship: "addresses",
            source: { type: "catalog.Solution", key: "sol-1" },
            target: { type: "catalog.UseCase", key: "uc-1" },
          },
        ],
      }),
    ]);
    renderPart(<AuditView module="catalog" />);
    const row = await screen.findByTestId("change-row");
    expect(within(row).queryByRole("link", { name: "Open Product old in Entities" })).toBeNull();
    expect(row).toHaveTextContent("delete Product old");
    expect(
      within(row).getByRole("link", { name: "Open Solution sol-1 in Entities" }),
    ).toBeVisible();
    expect(within(row).getByRole("link", { name: "Open UseCase uc-1 in Entities" })).toBeVisible();
  });

  it("the entity's history is a chip; clearing it lists the module's changes", async () => {
    const user = userEvent.setup();
    serve([wire.change()]);
    renderPart(<AuditView module="catalog" entity={{ type: "catalog.Solution", key: "sol-1" }} />);
    const chip = await screen.findByTestId("history-chip");
    expect(chip).toHaveTextContent("History of Solution sol-1");
    // The tab is "Changes": History is the filter, not a mode.
    expect(screen.getByRole("tab", { name: "Changes" })).toBeVisible();
    expect(screen.queryByRole("tab", { name: "History" })).toBeNull();
    await user.click(within(chip).getByRole("button", { name: /Clear history filter/ }));
    await waitFor(() => expect(screen.queryByTestId("history-chip")).toBeNull());
    await waitFor(() => expect(calls().at(-1)?.body).toEqual({ module: "catalog", limit: 50 }));
    expect(screen.getByLabelText("Key")).toHaveValue("");
  });

  it("opens on a receipt when given a group", async () => {
    serve([wire.change()]);
    renderPart(<AuditView module="catalog" group="g-4" />);
    await screen.findByTestId("change-row");
    expect(screen.getByRole("tab", { name: "Receipt by group", selected: true })).toBeVisible();
    expect(screen.getByLabelText("Group id")).toHaveValue("g-4");
    expect(calls()[0]?.body).toMatchObject({ module: "catalog", group: "g-4" });
  });

  it("in the console a click on a group opens its receipt, and on an entity its Entities page", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/changes";
    serve([wire.change()]);
    renderConsole({ hashRouting: true });
    await user.click(await screen.findByRole("link", { name: "Open receipt for group g-4" }));
    expect(window.location.hash).toBe("#/catalog/changes?group=g-4");
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Receipt by group", selected: true })).toBeVisible(),
    );
    await user.click(await screen.findByRole("link", { name: "Open Solution sol-1 in Entities" }));
    expect(window.location.hash).toBe("#/catalog/entities/catalog.Solution/sol-1");
  });
});

describe("Receipt links", () => {
  async function apply(onInvoke = receipt()) {
    const user = userEvent.setup();
    api.on((r) => (verb("validate")(r) ? json(200, validation()) : undefined));
    api.on((r) => (verb("invoke")(r) ? json(200, onInvoke) : undefined));
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1" }}
      />,
    );
    await user.type(await screen.findByLabelText(/^level/), "partial");
    await user.tab();
    await screen.findByTestId("effects");
    await user.click(screen.getByTestId("confirm"));
    return { user, receiptEl: await screen.findByTestId("receipt") };
  }

  it("each changed entity opens in Data and History, and the group in Changes", async () => {
    const { receiptEl } = await apply();
    expect(
      within(receiptEl).getByRole("link", { name: "Open Solution sol-1 in Entities" }),
    ).toHaveAttribute("href", entityHref("catalog", "entities", "catalog.Solution", "sol-1"));
    expect(
      within(receiptEl).getByRole("link", { name: "Open Solution sol-1 history" }),
    ).toHaveAttribute("href", entityHref("catalog", "changes", "catalog.Solution", "sol-1"));
    expect(
      within(receiptEl).getByRole("link", { name: "View group g-4 in Changes" }),
    ).toHaveAttribute("href", groupHref("catalog", "g-4"));
    // Copy group id stays.
    expect(within(receiptEl).getByRole("button", { name: /Copy group id/ })).toBeVisible();
    expect(screen.getByRole("button", { name: "Run again" })).toBeVisible();
  });

  it("Edit and apply again returns to the form with the inputs kept and asks for nothing", async () => {
    const { user } = await apply();
    const before = api.log.length;
    await user.click(screen.getByRole("button", { name: "Edit and apply again" }));
    expect(screen.queryByTestId("receipt")).toBeNull();
    expect(screen.getByLabelText(/^level/)).toHaveValue("partial");
    expect(screen.getByLabelText(/^solution/)).toHaveValue("sol-1");
    expect(screen.getByLabelText(/^level/)).toBeEnabled();
    expect(api.log.length).toBe(before);
    // The next apply is a new change: a new idempotency key.
    await user.clear(screen.getByLabelText(/^level/));
    await user.type(screen.getByLabelText(/^level/), "full");
    await user.tab();
    await user.click(await screen.findByTestId("confirm"));
    await screen.findByTestId("receipt");
    const keys = api.log.filter(verb("invoke")).map((r) => r.body.idempotency_key);
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBe(keys[1]);
  });
});
