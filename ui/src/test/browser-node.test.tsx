// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { crossLinks } from "../shell/links";
import { addHub, type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const open = (hash: string) => {
  window.location.hash = hash;
  return renderBrowser();
};
const solution = "#/explore/catalog/Solution/sol-1";

/** A relationship group's card, by its title. */
const groupOf = async (name: RegExp) =>
  (await screen.findByRole("heading", { level: 3, name })).closest("section") as HTMLElement;

describe("a node page (US-067)", () => {
  it("US-067-AC1: the title, summary, badges and sections follow the resolved view", async () => {
    open(solution);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Groups alerts against recent deploys.")).toBeInTheDocument();
    expect(screen.getByText("Solution", { selector: ".gb-eyebrow" })).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.slice(0, 3)).toEqual(["Delivery", "How it works", "Facts"]);
  });

  it("a property shown as a header badge is not repeated in the sections, and a section left empty is not drawn", async () => {
    open(solution);
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.getByTitle("Delivery").querySelector(".gb-badge")).toHaveTextContent("Embedded");
    expect(screen.queryByTestId("prop-deliveryMode")).toBeNull();
    expect(screen.getByTestId("prop-audience")).toBeInTheDocument();
  });

  it("a section whose only property is a header badge is not drawn", async () => {
    const type = fake.mods[0]?.entityTypes.find((t) => t.name === "catalog.Solution");
    if (type?.view)
      type.view = {
        ...type.view,
        sections: [
          { label: "Delivery", properties: ["deliveryMode"], collapsed: false },
          ...type.view.sections.slice(1),
        ],
      };
    open(solution);
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByRole("heading", { level: 3, name: "Delivery" })).toBeNull();
    expect(screen.getByRole("heading", { level: 3, name: "Facts" })).toBeInTheDocument();
  });

  it("a tag value that repeats is shown each time", async () => {
    fake.rows["catalog.Solution"]?.[0] &&
      Object.assign(fake.rows["catalog.Solution"][0].props, { tags: ["ai", "ai", "logs"] });
    open(solution);
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(within(screen.getByTestId("prop-tags")).getAllByText(/logs|ai/)).toHaveLength(3);
  });

  it("US-067-AC2: each property is formatted by its format: badge, link, prose, datetime, number, boolean, tags, json", async () => {
    const user = userEvent.setup();
    open(solution);
    const badge = (await screen.findByTitle("Delivery")).querySelector(".gb-badge");
    expect(badge).toHaveTextContent("Embedded");
    const link = within(screen.getByTestId("prop-launchUrl")).getByRole("link");
    expect(link).toHaveAttribute("href", "https://praxis.example/solutions/s-017");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByTestId("prop-workflow").textContent).toContain(
      "Upload a draft.\nLumen compares each pattern.",
    );
    expect(screen.getByTestId("prop-cost")).toHaveTextContent(/^\d{1,3}([,. ]\d{3})*[.,]50$/);
    expect(screen.getByTestId("prop-active")).toHaveTextContent("Yes");
    expect(within(screen.getByTestId("prop-tags")).getAllByText(/logs|ai/)).toHaveLength(2);
    const built = screen.getByTestId("prop-builtAt");
    expect(built.querySelector("time")).toHaveAttribute("dateTime", "2026-10-09T14:12:08-04:00");
    expect(within(built).queryByText("2026-10-09T14:12:08-04:00")).toBeNull();
    await user.click(within(built).getByRole("button", { name: "Show stored value of Built" }));
    expect(within(built).getByText("2026-10-09T14:12:08-04:00")).toBeInTheDocument();
    const json = screen.getByTestId("prop-config").querySelector("details");
    expect(json).not.toHaveAttribute("open");
    expect(json?.textContent).toContain('"retries": 2');
  });

  it("US-067-AC3: a property with no value shows Not set, unless the view hides it when empty", async () => {
    open(solution);
    expect(await screen.findByTestId("prop-caveat")).toHaveTextContent("Not set");
    // sol-2 has no audience: Not set; a hidden-when-empty relationship group (Notes) is absent for it
    expect(screen.getByRole("heading", { level: 3, name: /^Notes/ })).toBeInTheDocument();
  });

  it("US-067-AC3: a collapsed section is a closed disclosure and an uncollapsed one is open", async () => {
    open(solution);
    await screen.findByTestId("prop-workflow");
    const how = screen.getByText("How it works").closest("details");
    expect(how).not.toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Delivery" }).closest("details")).toBeNull();
  });

  it("US-067-AC4, AC5: attribution and freshness are in the card's footer", async () => {
    open(solution);
    expect(await screen.findByTestId("gb-attribution")).toHaveTextContent("Last changed by alice");
    const fresh = screen.getByTestId("gb-freshness");
    expect(fresh).toHaveTextContent("memory · current as of");
    expect(fresh).toHaveTextContent("LATEST");
  });

  it("US-067-AC5: an answer from a replica that is behind is marked", async () => {
    fake.api.status = fake.api.status.map((s) => ({
      ...s,
      lag: s.backend === "memory" ? "4.0" : s.lag,
    }));
    open(solution);
    const fresh = await screen.findByTestId("gb-freshness");
    expect(fresh).toHaveTextContent("behind by 4");
    expect(fresh).toHaveAttribute("data-stale", "true");
    expect(fresh).toHaveAttribute("role", "status");
  });

  it("US-067-AC6: an absent key and an entity the viewer may not read are the same page", async () => {
    open("#/explore/catalog/Solution/ghost");
    const absent = (await screen.findByTestId("gb-state")).textContent;
    fake.hidden.add("catalog.Solution:sol-2");
    window.location.hash = "#/explore/catalog/Solution/sol-2";
    await waitFor(() => expect(screen.getByTestId("gb-state")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("gb-state").textContent).toBe(absent));
    expect(absent).toContain("Not available");
    expect(absent).toContain("This page does not exist or you cannot read it.");
    expect(absent).not.toMatch(/ghost|sol-2|Solution/);
  });

  it("US-071-AC3: a malformed fragment, an unknown module and an unknown type are the same page too", async () => {
    // The page says the same whatever the cause; only its way on differs (the module's entry, else the start).
    const said = async () => {
      const state = await screen.findByTestId("gb-state");
      return state.querySelector("h1")?.textContent + (state.querySelector("p")?.textContent ?? "");
    };
    const { unmount } = open("#/explore/catalog/Solution/ghost");
    const expected = await said();
    unmount();
    for (const bad of [
      "#/explore/nowhere/Solution/sol-1",
      "#/explore/catalog/Ghost/x",
      "#/explore/%E0%A4%A",
      "#/explore/a/b/c/d",
    ]) {
      const r = open(bad);
      expect(await said()).toBe(expected);
      r.unmount();
    }
  });
});

describe("relationships (US-068)", () => {
  it("US-068-AC1, AC2: each relationship is a group titled by its label with a count, and each neighbour is a link", async () => {
    open(solution);
    const addresses = await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ });
    expect(addresses).toHaveTextContent("3");
    const group = addresses.closest("section") as HTMLElement;
    const links = await within(group).findAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      expect.stringContaining("Alert review"),
      expect.stringContaining("Runbook check"),
      expect.stringContaining("Log extraction"),
    ]);
    expect(links[0]).toHaveAttribute("href", "#/explore/catalog/UseCase/uc-1");
    expect(links[0]).toHaveTextContent("Use case · uc-1");
    expect(screen.getByRole("heading", { level: 3, name: /Provided by/ })).toBeInTheDocument();
  });

  it("US-068-AC2: activating a neighbour opens its page, and its inverse links back (US-068-AC6)", async () => {
    const user = userEvent.setup();
    open(solution);
    await user.click(
      await within(await groupOf(/Addresses use cases/)).findByRole("link", {
        name: /Alert review/,
      }),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Alert review" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/UseCase/uc-1");
    const back = await screen.findByRole("heading", { level: 3, name: /Addressed by/ });
    expect(
      await within(back.closest("section") as HTMLElement).findByRole("link", {
        name: /Lumen alert correlation/,
      }),
    ).toBeInTheDocument();
  });

  it("US-068-AC4: a related entity of another module opens in that module's page, read on its own endpoint", async () => {
    open(solution);
    const link = await within(await groupOf(/Notes/)).findByRole("link", {
      name: /A note elsewhere/,
    });
    expect(link).toHaveAttribute("href", "#/explore/other/Note/n-1");
    expect(fake.moduleQueries("other").some((q) => q.includes("note(key"))).toBe(true);
  });

  it("US-068-AC5: a neighbour the viewer may not read is a Not available row that is not a link and carries no key", async () => {
    fake.hidden.add("catalog.UseCase:uc-2");
    open(solution);
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    await within(group).findByRole("link", { name: /Alert review/ });
    const na = await within(group).findByText("Not available");
    const row = na.closest("li") as HTMLElement;
    expect(within(row).queryByRole("link")).toBeNull();
    expect(row.textContent).toBe("Not available");
    expect(group.textContent).toContain("3"); // still counted
  });

  it("US-068-AC7: a neighbour whose label read fails for cost shows its key and a retry, never Not available", async () => {
    const user = userEvent.setup();
    fake.failing.set("catalog.UseCase:uc-2", "COST_EXCEEDED");
    open(solution);
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    const retry = await within(group).findByRole("button", { name: "Retry" });
    expect(retry.closest("li")).toHaveTextContent("uc-2");
    expect(within(group).queryByText("Not available")).toBeNull();
    fake.failing.clear();
    await user.click(retry);
    expect(await within(group).findByRole("link", { name: /Runbook check/ })).toBeInTheDocument();
    expect(within(group).queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("US-068-AC3: a group of 100 keys says 100 or more, labels 20, and Show more labels the next 20 of the keys read", async () => {
    const user = userEvent.setup();
    addHub(fake, 120);
    open("#/explore/catalog/Solution/sol-hub");
    const h = await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ });
    expect(h).toHaveTextContent("100 or more");
    const group = h.closest("section") as HTMLElement;
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(20));
    expect(within(group).getByRole("button", { name: "Show more (20 of 80+)" })).toBeVisible();
    await user.click(within(group).getByRole("button", { name: /Show more/ }));
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(40));
    // no request carries more than 20 targets
    for (const q of fake.moduleQueries("catalog"))
      expect((q.match(/\$k\d+: String!/g) ?? []).length).toBeLessThanOrEqual(20);
  });

  it("US-068-AC3: beyond the 100 keys a further control reads more through the inverse relationship, a page after the last key", async () => {
    const user = userEvent.setup();
    addHub(fake, 120);
    open("#/explore/catalog/Solution/sol-hub");
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    for (let i = 0; i < 4; i++) {
      await user.click(await within(group).findByRole("button", { name: /Show more \(/ }));
    }
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(100));
    await user.click(await within(group).findByRole("button", { name: "Show more" }));
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(120));
    const reads = fake.moduleQueries("catalog").filter((q) => q.includes("useCaseList"));
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.every((q) => q.includes("afterKey"))).toBe(true);
  });

  it("US-068-AC3: with no inverse the group says it shows the first 100", async () => {
    fake.mods[0]?.relationships.forEach((r) => {
      if (r.name === "addresses") r.inverse = null;
    });
    addHub(fake, 120);
    open("#/explore/catalog/Solution/sol-hub");
    const group = (
      await screen.findByRole("heading", { level: 3, name: /Addresses use cases/ })
    ).closest("section") as HTMLElement;
    const user = userEvent.setup();
    for (let i = 0; i < 4; i++)
      await user.click(await within(group).findByRole("button", { name: /Show more \(/ }));
    expect(await within(group).findByText("Showing the first 100.")).toBeInTheDocument();
  });

  it("the page request reads no target, and label requests stay inside the limits", async () => {
    open(solution);
    await within(await groupOf(/Addresses use cases/)).findByRole("link", {
      name: /Alert review/,
    });
    const queries = fake.moduleQueries();
    expect(queries.length).toBeGreaterThan(1);
    expect(queries[0]).not.toContain("target");
    expect(queries[0]).toContain("addresses { module type key }");
  });

  it("the previous page's relationships are not shown for the next page while it loads", async () => {
    const user = userEvent.setup();
    open(solution);
    await user.click(
      await within(await groupOf(/Addresses use cases/)).findByRole("link", {
        name: /Alert review/,
      }),
    );
    await screen.findByRole("heading", { level: 1, name: "Alert review" });
    expect(screen.queryByTestId("prop-deliveryMode")).toBeNull();
    await act(async () => undefined);
  });
});

describe("links into Operate, handed in by the shell (FR-71)", () => {
  const links = crossLinks({ hash: true, openOperate: () => {}, openExplore: () => {} });

  it("alice's node page offers Open in Operate: Entities, History and Actions with the entity prefilled", async () => {
    window.location.hash = solution;
    renderBrowser({ links });
    const nav = within(await screen.findByTestId("gb-open-in-operate"));
    expect(nav.getByRole("link", { name: /Entities of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/entities/catalog.Solution/sol-1",
    );
    expect(nav.getByRole("link", { name: /History of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/changes/catalog.Solution/sol-1",
    );
    expect(nav.getByRole("link", { name: /Actions of/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/^#\/operate\/catalog\/actions\/catalog\.\w+\?in\.solution=sol-1$/),
    );
    expect(nav.getByText("Open in Operate")).toBeInTheDocument();
  });

  it("a modified click keeps the anchor and does not switch the mode in place", async () => {
    window.location.hash = solution;
    renderBrowser({ links });
    const link = await within(await screen.findByTestId("gb-open-in-operate")).findByRole("link", {
      name: /History of/,
    });
    // Seen after the component's handler; the listener stops jsdom following the anchor itself.
    let prevented: boolean | undefined;
    const seen = (e: Event) => {
      prevented = e.defaultPrevented;
      e.preventDefault();
    };
    document.addEventListener("click", seen);
    fireEvent.click(link, { ctrlKey: true });
    document.removeEventListener("click", seen);
    expect(prevented).toBe(false);
    expect(window.location.hash).toBe(solution);
  });

  it("a type's list has Model", async () => {
    window.location.hash = "#/explore/catalog/Solution";
    renderBrowser({ links });
    expect(await screen.findByRole("link", { name: /Model of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/model/catalog.Solution",
    );
  });

  it("carol's pages carry no link into Operate and no word of it", async () => {
    window.location.hash = solution;
    const { container, unmount } = renderBrowser();
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(screen.queryByTestId("gb-open-in-operate")).toBeNull();
    expect(container.innerHTML).not.toMatch(/operate/i);
    unmount();
    window.location.hash = "#/explore/catalog/Solution";
    const list = renderBrowser();
    await screen.findByRole("heading", { level: 2, name: /Solutions/ });
    expect(screen.queryByRole("link", { name: /Model/ })).toBeNull();
    expect(list.container.innerHTML).not.toMatch(/operate/i);
  });
});
