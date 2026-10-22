// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Change } from "../api/types";
import { crossLinks } from "../shell/links";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { wire } from "./fake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  window.location.hash = "#/explore/catalog/Solution/sol-1";
});
afterEach(() => {
  window.location.hash = "";
});

const SOL = "catalog.Solution";
const update = (group: string, over: Partial<Change> = {}) =>
  wire.change({
    group,
    ops: [{ kind: "update", type: SOL, key: "sol-1", version: 2 }],
    ...over,
  });

const changeCalls = () => fake.requests.filter((r) => r.path.endsWith("/audit/changes"));
const goBack = () =>
  act(async () => {
    window.history.back();
    await new Promise((r) => setTimeout(r, 30));
  });

describe("an entity's history panel (FR-69)", () => {
  it("opens at the history address, with who, when, the action and what the change touched", async () => {
    const user = userEvent.setup();
    fake.journal = [
      update("g-2"),
      wire.change({
        group: "g-1",
        by: "bob",
        ops: [
          {
            kind: "link",
            relationship: "addresses",
            source: { type: SOL, key: "sol-1" },
            target: { type: "catalog.UseCase", key: "uc-1" },
          },
        ],
      }),
    ];
    renderBrowser({ canEdit: true });
    await user.click(await screen.findByRole("button", { name: "History" }));
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1/history");
    const rows = await screen.findAllByTestId("gb-change");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("ana");
    expect(rows[0]).toHaveTextContent("2026-10-09 14:02:11 UTC");
    expect(rows[0]).toHaveTextContent("CorrectSolution");
    const second = rows[1] as HTMLElement;
    expect(second).toHaveTextContent("bob");
    // Either end of a link counts, and a readable entity is a link by its title.
    expect(await within(second).findByRole("link", { name: /Alert review/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/UseCase/uc-1",
    );
    expect(await within(second).findByRole("link", { name: /Lumen/ })).toBeInTheDocument();
    expect(defined(changeCalls()[0]).body).toEqual({ type: SOL, key: "sol-1", limit: 20 });
    expect(changeCalls()[0]?.url).not.toContain("sol-1");
  });

  it("shows an unreadable touched entity as not available, without its key", async () => {
    fake.hidden.add("catalog.UseCase:uc-9");
    fake.rows["catalog.UseCase"]?.push({ key: "uc-9", props: { code: "uc-9", name: "Secret" } });
    fake.journal = [
      wire.change({
        ops: [
          {
            kind: "link",
            relationship: "addresses",
            source: { type: SOL, key: "sol-1" },
            target: { type: "catalog.UseCase", key: "uc-9" },
          },
        ],
      }),
    ];
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: true });
    const row = await screen.findByTestId("gb-change");
    await within(row).findByText("Not available");
    expect(row).not.toHaveTextContent("uc-9");
    expect(row).not.toHaveTextContent("Secret");
  });

  it("pages by twenty with Show more, by the contract's cursor", async () => {
    const user = userEvent.setup();
    fake.journal = Array.from({ length: 25 }, (_, i) => update(`g-${i}`));
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: true });
    await waitFor(() => expect(screen.getAllByTestId("gb-change")).toHaveLength(20));
    await user.click(screen.getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByTestId("gb-change")).toHaveLength(25));
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
    expect(defined(changeCalls().at(-1)).body).toMatchObject({ limit: 20, after: "20" });
  });

  it("answers a missing journal grant and a backend with no journal in a sentence each", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    fake.changesStatus = 403;
    const first = renderBrowser({ canEdit: true });
    expect(await screen.findByText(/do not have access to the history/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    first.unmount();
    fake.changesStatus = 501;
    renderBrowser({ canEdit: true });
    expect(await screen.findByText(/keeps no history of changes/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("round trips through the address: a fresh load shows it open and Back closes it", async () => {
    const user = userEvent.setup();
    fake.journal = [update("g-1")];
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    const { unmount } = renderBrowser({ canEdit: true });
    expect(await screen.findByTestId("gb-history")).toBeInTheDocument();
    unmount();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser({ canEdit: true });
    await user.click(await screen.findByRole("button", { name: "History" }));
    await screen.findByTestId("gb-history");
    await goBack();
    await waitFor(() => expect(screen.queryByTestId("gb-history")).toBeNull());
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
    expect(screen.getByRole("button", { name: "History" })).toBeInTheDocument();
  });

  it("its own back control returns to the entity without leaving a loop behind", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser({ canEdit: true });
    await user.click(await screen.findByRole("button", { name: "History" }));
    await screen.findByTestId("gb-history");
    await user.click(screen.getByRole("button", { name: /^Back to / }));
    await waitFor(() => expect(screen.queryByTestId("gb-history")).toBeNull());
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
    await goBack();
    expect(window.location.hash).not.toMatch(/\/history$/);
    expect(screen.queryByTestId("gb-history")).toBeNull();
  });

  it("closes a freshly loaded history address by replacing it with the entity", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: true });
    await user.click(await screen.findByRole("button", { name: /^Back to / }));
    await waitFor(() => expect(screen.queryByTestId("gb-history")).toBeNull());
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
    await goBack();
    expect(window.location.hash).not.toMatch(/\/history$/);
  });

  it("shows a change's group as plain text while the shell offers no link, and builds no address itself", async () => {
    fake.journal = [update("g-7")];
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: true });
    await screen.findByTestId("gb-change");
    expect(screen.getByText("g-7").tagName).toBe("SPAN");
  });

  it("links a change's group to Operate's receipt view where the shell hands over the primitive", async () => {
    fake.journal = [update("g-7")];
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    const links = crossLinks({ hash: true, openOperate: () => {}, openExplore: () => {} });
    renderBrowser({ canEdit: true, links });
    await screen.findByTestId("gb-change");
    expect(screen.getByRole("link", { name: "g-7" })).toHaveAttribute(
      "href",
      "#/operate/catalog/changes?group=g-7",
    );
  });

  it("draws the group as a button that goes where the host owns the location", async () => {
    fake.journal = [update("g-7")];
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    const opened: unknown[] = [];
    const links = crossLinks({
      hash: false,
      openOperate: (r) => opened.push(r),
      openExplore: () => {},
    });
    renderBrowser({ canEdit: true, links });
    await screen.findByTestId("gb-change");
    await userEvent.setup().click(screen.getByRole("button", { name: "g-7" }));
    expect(opened).toEqual([{ module: "catalog", area: "changes", group: "g-7" }]);
  });

  it("shows a placeholder, not 'Not available', while a touched entity's label is loading", async () => {
    fake.journal = [
      wire.change({
        ops: [
          {
            kind: "link",
            relationship: "addresses",
            source: { type: SOL, key: "sol-1" },
            target: { type: "catalog.UseCase", key: "uc-1" },
          },
        ],
      }),
    ];
    const release = fake.holdLabels();
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: true });
    const row = await screen.findByTestId("gb-change");
    expect(row).not.toHaveTextContent("Not available");
    expect(row).toHaveTextContent("Loading");
    release();
    expect(await within(row).findByRole("link", { name: /Alert review/ })).toBeInTheDocument();
  });

  it("offers a viewer who may not edit no History control, and a pasted history address shows the entity alone", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1/history";
    renderBrowser({ canEdit: false });
    expect(await screen.findByRole("heading", { level: 1, name: /Lumen/ })).toBeInTheDocument();
    expect(screen.queryByTestId("gb-history")).toBeNull();
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
    expect(changeCalls()).toHaveLength(0);
  });
});

function defined<T>(v: T | undefined): T {
  if (v === undefined) throw new Error("expected a value");
  return v;
}
