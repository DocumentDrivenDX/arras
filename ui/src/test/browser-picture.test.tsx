// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addHub, type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = "";
});

const open = (hash = "#/explore/catalog/Solution/sol-1") => {
  window.location.hash = hash;
  return renderBrowser();
};
const picture = async () => screen.findByRole("group", { name: /^Neighbourhood of/ });
const nodes = async () => {
  const p = await picture();
  await waitFor(() => expect(within(p).getAllByRole("link").length).toBeGreaterThan(0));
  return within(p).getAllByRole("link");
};

describe("the neighbourhood picture (US-069)", () => {
  it("US-069-AC1, AC6: the picture is a labelled group, not an image, and its name says the lists have the same links", async () => {
    open();
    const p = await picture();
    expect(p).toHaveAccessibleName(
      "Neighbourhood of Lumen alert correlation (S-017): 5 neighbours. The lists have the same links.",
    );
    expect(screen.queryByRole("img")).toBeNull();
    const all = await nodes();
    expect(all).toHaveLength(5);
    // each node's name: type, title, relationship
    expect(all.map((n) => n.getAttribute("aria-label"))).toContain(
      "Use case, Alert review, Addresses use cases",
    );
    expect(all.map((n) => n.getAttribute("aria-label"))).toContain("Note, A note elsewhere, Notes");
  });

  it("US-069-AC1: every neighbour is drawn once, with its own type's tone, and the footer counts them", async () => {
    open();
    await waitFor(() =>
      expect(screen.getByTestId("gb-picture-count")).toHaveTextContent("5 of 5 neighbours shown"),
    );
    const tones = (await nodes()).map((n) => [...n.classList].find((c) => c.startsWith("gb-t-")));
    expect(tones.sort()).toEqual([
      "gb-t-amber",
      "gb-t-teal",
      "gb-t-violet",
      "gb-t-violet",
      "gb-t-violet",
    ]);
  });

  it("US-069-AC6: the picture is one Tab stop and the arrow keys move between its nodes group by group", async () => {
    const user = userEvent.setup();
    open();
    const all = await nodes();
    expect(all.filter((n) => n.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(all.filter((n) => n.getAttribute("tabindex") === "-1")).toHaveLength(4);
    const first = all[0] as HTMLElement;
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(all[1]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(all[2]).toHaveFocus();
    await user.keyboard("{End}");
    expect(all[4]).toHaveFocus();
    await user.keyboard("{Home}");
    expect(all[0]).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(all[0]).toHaveFocus();
    // the focused node is the one Tab stop now
    expect(all[0]).toHaveAttribute("tabindex", "0");
    expect(all[1]).toHaveAttribute("tabindex", "-1");
  });

  it("US-069-AC4: selecting a node by pointer opens its page and the picture re-centres on it", async () => {
    const user = userEvent.setup();
    open();
    const target = (await nodes()).find((n) =>
      /Alert review/.test(n.getAttribute("aria-label") ?? ""),
    );
    await user.click(target as Element);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Alert review" }),
    ).toBeInTheDocument();
    expect(await picture()).toHaveAccessibleName(/^Neighbourhood of Alert review: 1 neighbour\./);
    expect(window.location.hash).toBe("#/explore/catalog/UseCase/uc-1");
  });

  it("US-069-AC4: selecting a node by keyboard (Enter) opens its page", async () => {
    const user = userEvent.setup();
    open();
    const all = await nodes();
    const target = all.find((n) => /Lumen/.test(n.getAttribute("aria-label") ?? "")) as HTMLElement;
    target.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: "Lumen" })).toBeInTheDocument();
  });

  it("US-069-AC5: hover and focus show the label, the type and the joining relationship", async () => {
    const user = userEvent.setup();
    open();
    const all = await nodes();
    const target = all.find((n) =>
      /Runbook check/.test(n.getAttribute("aria-label") ?? ""),
    ) as HTMLElement;
    await user.hover(target);
    const card = await screen.findByTestId("gb-hover");
    expect(card).toHaveTextContent("Runbook check");
    expect(card).toHaveTextContent("Use case");
    expect(card).toHaveTextContent("Addresses use cases");
    await user.unhover(target);
    expect(screen.queryByTestId("gb-hover")).toBeNull();
    target.focus();
    expect(await screen.findByTestId("gb-hover")).toHaveTextContent("Runbook check");
  });

  it("US-069-AC3: more neighbours than the bound draw 40, say how many are left out, and the list still has every one", async () => {
    addHub(fake, 120);
    open("#/explore/catalog/Solution/sol-hub");
    await waitFor(
      () =>
        expect(screen.getByTestId("gb-picture-count")).toHaveTextContent(
          "40 of 100+ neighbours shown",
        ),
      { timeout: 8000 },
    );
    const p = await picture();
    expect(p.querySelectorAll("a")).toHaveLength(40);
    expect(within(p).getByText("ADDRESSES USE CASES · +60 or more")).toBeInTheDocument();
    const list = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    expect(list).toHaveTextContent("100 or more");
  });

  it("US-069-AC1: an entity with no relationships shows a compact No relationships card, not a picture", async () => {
    fake.rows["catalog.UseCase"]?.push({
      key: "uc-lone",
      props: { code: "uc-lone", name: "Lonely" },
    });
    open("#/explore/catalog/UseCase/uc-lone");
    expect(await screen.findByText("No relationships")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /^Neighbourhood of/ })).toBeNull();
  });

  it("in a narrow window the picture is behind a button and the lists are the only view until it is pressed", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q.includes("max-width: 419px"),
      media: q,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    open();
    const button = await screen.findByRole("button", { name: "Show neighbourhood picture" });
    expect(screen.queryByRole("group", { name: /^Neighbourhood of/ })).toBeNull();
    await user.click(button);
    expect(await picture()).toBeInTheDocument();
  });

  it("US-069-AC7: nothing animates unless the reader allows motion", () => {
    const css = readFileSync(join(import.meta.dirname, "../browser/browser.css"), "utf8");
    const header = "@media (prefers-reduced-motion: no-preference)";
    // remove every such block by counting braces, then no animation may be left outside
    let outside = css;
    for (let at = outside.indexOf(header); at >= 0; at = outside.indexOf(header)) {
      let depth = 0;
      let end = outside.indexOf("{", at);
      do {
        if (outside[end] === "{") depth++;
        if (outside[end] === "}") depth--;
        end++;
      } while (depth > 0);
      outside = outside.slice(0, at) + outside.slice(end);
    }
    expect(css).toContain(header);
    expect(css).toMatch(/animation\s*:/);
    expect(outside).not.toMatch(/animation\s*:/);
  });
});
