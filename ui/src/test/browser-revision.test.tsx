// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { qc, renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const metaReads = () =>
  fake.requests.filter((r) => r.method === "POST" && /\/api\/console\/graphql$/.test(r.path));
const viewReads = () => metaReads().filter((r) => r.body.query.includes("declared"));

describe("the registry moves under an open page (US-070-AC8)", () => {
  it("US-070-AC8: a REVISION_CHANGED from a read refreshes the meta read, and the page reads again under the new view without leaving its place", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser();
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    const link = await within(group).findByRole("link", { name: /Alert review/ });
    const before = metaReads().length;
    // The next read finds the registry on its next revision, whose view calls a use case a scenario.
    fake.expireNext = (mods) => {
      for (const m of mods) {
        m.revision = { memory: 2 };
        for (const t of m.entityTypes)
          if (t.name === "catalog.UseCase" && t.view) t.view = { ...t.view, label: "Scenario" };
      }
    };
    await user.click(link);
    expect(await screen.findByRole("heading", { level: 1, name: "Alert review" })).toBeVisible();
    expect(await screen.findByText("Scenario", { selector: ".gb-eyebrow" })).toBeVisible();
    expect(metaReads().length).toBeGreaterThan(before);
    expect(window.location.hash).toBe("#/explore/catalog/UseCase/uc-1");
  });

  it("US-070-AC8: a node that stays open keeps showing its content while it is read under the new revision", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    const client = qc();
    renderBrowser({ queryClient: client });
    const title = "Lumen alert correlation (S-017)";
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeVisible();
    let sawSkeleton = false;
    const watch = new MutationObserver(() => {
      if (!screen.queryByRole("heading", { level: 1, name: title })) sawSkeleton = true;
    });
    watch.observe(document.body, { childList: true, subtree: true });
    for (const m of fake.mods) m.revision = { memory: 3 };
    await client.invalidateQueries({ queryKey: ["meta"] });
    await waitFor(() => expect(viewReads().length).toBeGreaterThan(1));
    await new Promise((r) => setTimeout(r, 50));
    watch.disconnect();
    expect(sawSkeleton).toBe(false);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeVisible();
  });
});

describe("the two-request meta read is one revision (CONTRACT-010 B)", () => {
  it("reads the pair again when the registry moved between the two requests, and shows the second", async () => {
    let calls = 0;
    fake.api.on((r) => {
      if (r.method !== "POST" || !/\/api\/console\/graphql$/.test(r.path)) return undefined;
      if (!r.body.query.includes("declared")) return undefined;
      calls++;
      const reply = fake.answer(null, r.body.query);
      // The first views read answers from an older revision.
      if (calls === 1)
        for (const m of (reply.body as { data: { modules: { revision: unknown }[] } }).data.modules)
          m.revision = { memory: 0 };
      return { status: reply.status, body: reply.body };
    });
    window.location.hash = "#/explore/catalog";
    renderBrowser();
    expect(await screen.findByText("Use cases, solutions and products")).toBeVisible();
    expect(calls).toBe(2);
  });

  it("a second disagreement is not shown as a registry: the browser offers a retry", async () => {
    fake.api.on((r) => {
      if (r.method !== "POST" || !/\/api\/console\/graphql$/.test(r.path)) return undefined;
      if (!r.body.query.includes("declared")) return undefined;
      const reply = fake.answer(null, r.body.query);
      for (const m of (reply.body as { data: { modules: { revision: unknown }[] } }).data.modules)
        m.revision = { memory: 0 };
      return { status: reply.status, body: reply.body };
    });
    window.location.hash = "#/explore/catalog";
    renderBrowser();
    expect(await screen.findByText("Something went wrong")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });
});
