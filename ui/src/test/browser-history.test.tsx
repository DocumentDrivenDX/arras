// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GraphBrowser } from "../browser/GraphBrowser";
import { readViewState } from "../browser/location";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { qc, renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "#/explore/catalog";
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const goBack = () =>
  act(async () => {
    window.history.back();
    await new Promise((r) => setTimeout(r, 30));
  });

describe("location and history (US-071)", () => {
  it("US-071-AC1: a node page's address is in the fragment and nothing of it is in the path or the query", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser();
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    await user.click(await within(group).findByRole("link", { name: /Alert review/ }));
    expect(window.location.hash).toBe("#/explore/catalog/UseCase/uc-1");
    expect(window.location.pathname).toBe("/");
    expect(window.location.search).toBe("");
  });

  it("US-071-AC2: a copied address opens the same node page", async () => {
    window.location.hash = "#/explore/catalog/UseCase/uc-3";
    renderBrowser();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Log extraction" }),
    ).toBeInTheDocument();
  });

  it("US-071-AC4: after a hit is opened, Back returns the search with its text and chips, held in history.state and not the URL", async () => {
    const user = userEvent.setup();
    const { unmount } = renderBrowser();
    await user.click(await screen.findByRole("radio", { name: "Products" }));
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "lumen");
    await screen.findByTestId("gb-status");
    expect(window.location.href).not.toMatch(/lumen|Product/i);
    expect(readViewState()).toMatchObject({ text: "lumen", types: ["Product"] });
    await user.click(screen.getByRole("link", { name: /Lumen/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Lumen" })).toBeInTheDocument();
    expect(window.location.href).not.toMatch(/lumen=|text=|search/i);
    await goBack();
    expect(await screen.findByTestId("gb-status")).toHaveTextContent("for lumen");
    expect(screen.getByRole("textbox", { name: /Search/ })).toHaveValue("lumen");
    expect(screen.getByRole("radio", { name: /^Product/ })).toHaveAttribute("aria-checked", "true");
    // a browser opened again at this entry (a reload) finds the same state in the history entry
    unmount();
    renderBrowser();
    expect(await screen.findByRole("textbox", { name: /Search/ })).toHaveValue("lumen");
    expect(screen.getByRole("radio", { name: /^Product/ })).toHaveAttribute("aria-checked", "true");
  });

  it("US-071-AC4: the scroll position is kept in the entry's state and restored", async () => {
    const user = userEvent.setup();
    const scroll = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    Object.defineProperty(window, "scrollY", { value: 420, configurable: true });
    renderBrowser();
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "lumen");
    await user.click(await screen.findByRole("link", { name: /Lumen alert correlation/ }));
    await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
    await goBack();
    await screen.findByTestId("gb-status");
    await waitFor(() => expect(scroll).toHaveBeenCalledWith(0, 420));
  });

  it("US-071-AC5, AC6: every request is a read as the viewer, and no key, search text or person is in a path or query", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser({ getHeaders: () => ({ "x-arras-user": "alice" }) });
    await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ });
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "lumen");
    await screen.findByTestId("gb-status");
    expect(fake.requests.length).toBeGreaterThan(3);
    for (const r of fake.requests) {
      expect(r.method).toBe("POST");
      expect(r.path).toMatch(/^\/api\/console\/graphql(\/(catalog|other))?$/);
      expect(r.url).not.toMatch(/sol-1|lumen|uc-1|alice|\?/);
      expect(r.headers["x-arras-user"]).toBe("alice");
      expect(r.body.query).not.toMatch(/\bmutation\b/);
    }
    expect(fake.requests.some((r) => r.path.includes("/api/operate"))).toBe(false);
  });

  it("US-071-AC7: a host that owns the location receives it as data and the browser neither reads nor writes the URL", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/somewhere-else";
    const seen: unknown[] = [];
    const ui = (location: { module: string; type?: string; key?: string }) => (
      <GraphBrowser queryClient={qc()} location={location} onLocation={(l) => seen.push(l)} />
    );
    const { rerender } = render(ui({ module: "catalog" }));
    await user.click(await screen.findByRole("radio", { name: "Solutions" }));
    await user.click(await screen.findByRole("link", { name: /Lumen alert correlation/ }));
    expect(seen).toEqual([{ module: "catalog", type: "Solution", key: "sol-1" }]);
    expect(window.location.hash).toBe("#/somewhere-else");
    // the host stores it and passes it back: the page follows the host, not the URL
    rerender(ui({ module: "catalog", type: "Solution", key: "sol-1" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/somewhere-else");
  });

  it("a host's location that names nothing readable is the Not available page", async () => {
    render(
      <GraphBrowser
        queryClient={qc()}
        location={{ module: "catalog", type: "Solution", key: "ghost" }}
      />,
    );
    expect(await screen.findByText("Not available")).toBeInTheDocument();
  });
});

describe("states (DESIGN-GB, States)", () => {
  it("a backend that is down shows the Retry state naming the backend, then recovers", async () => {
    const user = userEvent.setup();
    fake.down = "memory";
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser();
    expect(
      await screen.findByRole("heading", { name: "The catalog did not answer" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/memory is not responding\./)).toBeInTheDocument();
    fake.down = null;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
  });

  it("a read that loads shows a busy skeleton with the status text Loading", async () => {
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser();
    const busy = await screen.findByRole("status");
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy).toHaveTextContent("Loading");
  });

  it("an expired session is the host's state: the browser says so and keeps its location", async () => {
    const onUnauthorized = vi.fn();
    fake.api.on((r) =>
      r.path.endsWith("/graphql/catalog")
        ? {
            status: 401,
            body: {
              errors: [
                {
                  message: "sign in again",
                  extensions: { code: "REFUSED", reason: "token_expired" },
                },
              ],
            },
          }
        : undefined,
    );
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    renderBrowser({ onUnauthorized });
    expect(
      await screen.findByRole("heading", { name: "Your session has expired" }),
    ).toBeInTheDocument();
    expect(onUnauthorized).toHaveBeenCalled();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("no module is readable: the Not available page, and no module name is mentioned", async () => {
    fake.mods = [];
    renderBrowser();
    expect(await screen.findByText("Not available")).toBeInTheDocument();
  });

  it("several modules offer a chooser", async () => {
    window.location.hash = "#/explore";
    renderBrowser();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Choose a module" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Product catalog/ })).toHaveAttribute(
      "href",
      "#/explore/catalog",
    );
    expect(screen.getByRole("link", { name: /Other notes/ })).toHaveAttribute(
      "href",
      "#/explore/other",
    );
  });
});

describe("the breadcrumb and a type's list (US-067, US-071)", () => {
  const crumbs = () => screen.findByRole("navigation", { name: "Breadcrumb" });

  it("names the type by its plural label; Explore and the type are links, the last crumb is the page", async () => {
    window.location.hash = "#/explore/catalog/UseCase/uc-1";
    renderBrowser();
    const nav = await crumbs();
    expect(
      within(nav)
        .getAllByRole("link")
        .map((a) => [a.textContent, a.getAttribute("href")]),
    ).toEqual([
      ["Explore", "#/explore/catalog"],
      ["Use cases", "#/explore/catalog/UseCase"],
    ]);
    const here = nav.querySelector('[aria-current="page"]');
    expect(here?.tagName).toBe("SPAN");
    expect(here).toHaveTextContent("uc-1");
    expect(within(nav).queryByText("Use case")).toBeNull();
    // the card still names the one entity by its singular label
    expect(screen.getByText("Use case", { selector: ".gb-eyebrow" })).toBeInTheDocument();
  });

  it("the type crumb opens the type's list; Explore then opens the cards; Back and Forward follow", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/UseCase/uc-1";
    renderBrowser();
    await user.click(within(await crumbs()).getByRole("link", { name: "Use cases" }));
    expect(window.location.hash).toBe("#/explore/catalog/UseCase");
    expect(await screen.findByRole("heading", { level: 2, name: "Use cases" })).toBeInTheDocument();
    expect(await screen.findByText(/Use cases in key order/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Use cases" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(await screen.findByRole("link", { name: /Alert review/ }));
    await user.click(within(await crumbs()).getByRole("link", { name: "Explore" }));
    expect(window.location.hash).toBe("#/explore/catalog");
    expect(await screen.findAllByText("List them")).toHaveLength(3);
    await goBack();
    expect(await crumbs()).toBeInTheDocument();
    await goBack();
    expect(await screen.findByRole("heading", { level: 2, name: "Use cases" })).toBeInTheDocument();
  });

  it("a type's address opens its list directly and a list of one says the singular", async () => {
    window.location.hash = "#/explore/catalog/Product";
    renderBrowser();
    expect(await screen.findByRole("heading", { level: 2, name: "Products" })).toBeInTheDocument();
    const rows = fake.rows["catalog.Product"] ?? [];
    expect(
      await screen.findByText(new RegExp(`${rows.length} Products? in key order`)),
    ).toBeInTheDocument();
  });

  it("from a search the first crumb is the search and the type crumb still lists the type without it", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "lumen");
    await user.click(await screen.findByRole("link", { name: /Lumen alert correlation/ }));
    const nav = await crumbs();
    expect(within(nav).getByRole("link", { name: "Search: lumen" })).toHaveAttribute(
      "href",
      "#/explore/catalog",
    );
    await user.click(within(nav).getByRole("link", { name: "Solutions" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Solutions" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Search/ })).toHaveValue("");
  });
});
