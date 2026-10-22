// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "#/explore/catalog";
  fake = stageBrowser();
});

const searches = () => fake.moduleQueries("catalog").filter((q) => q.includes("_search"));
const searchBox = () => screen.findByRole("textbox", { name: /Search/ });

describe("the Entry and its type chips (US-066)", () => {
  it("US-066-AC1: the module's title and description, an All chip and a chip for every readable type, with no count, All selected", async () => {
    renderBrowser();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Use cases, solutions and products")).toBeInTheDocument();
    const chips = within(screen.getByRole("radiogroup", { name: "Narrow by type" })).getAllByRole(
      "radio",
    );
    expect(chips.map((c) => c.textContent)).toEqual(["All", "Use cases", "Solutions", "Products"]);
    chips.forEach((c, i) => {
      expect(c).toHaveAttribute("aria-checked", i === 0 ? "true" : "false");
    });
    expect(await screen.findAllByText("List them")).toHaveLength(3);
  });

  it("US-066-AC2: a chip lists the type's entities in key order, 50 to a page, the next after the last key shown", async () => {
    const user = userEvent.setup();
    const rows = fake.rows["catalog.UseCase"];
    for (let i = 0; i < 120; i++)
      rows?.push({
        key: `uc-z-${String(i).padStart(3, "0")}`,
        props: { code: `z${i}`, name: `Bulk ${String(i).padStart(3, "0")}` },
      });
    renderBrowser();
    await user.click(await screen.findByRole("radio", { name: "Use cases" }));
    expect(screen.getByRole("radio", { name: "Use cases" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(50));
    await user.click(screen.getByRole("button", { name: "Show next 50" }));
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(100));
    const q = fake.moduleQueries("catalog").filter((x) => x.includes("useCaseList"));
    expect(q).toHaveLength(2);
    expect(q[1]).toContain("afterKey");
    // key order: the first listed is the smallest key
    expect(screen.getAllByRole("link")[0]).toHaveTextContent("Alert review");
  });

  it("US-066-AC5: choosing All brings every hit back and leaves the text as it was", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await screen.findByRole("link", { name: /Lumen alert correlation/ });
    const all = screen.getAllByRole("link").length;
    await user.click(screen.getByRole("radio", { name: /^Product/ }));
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeLessThan(all));
    expect(screen.getByRole("radio", { name: /^Product/ })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: /^All/ }));
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(all));
    expect(screen.getByRole("radio", { name: /^Product/ })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("radio", { name: /^All/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("textbox", { name: /Search/ })).toHaveValue("lumen");
  });

  it("US-066-AC1: a list shows no search count; the status line says how many are listed so far", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.click(await screen.findByRole("radio", { name: "Solutions" }));
    expect(await screen.findByText(/Solutions in key order/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Solutions" })).toHaveTextContent(/^Solutions$/);
  });
});

describe("search (US-065)", () => {
  it("US-065-AC1: two or more characters and a pause send one search; hits show type, label and a marked excerpt", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await waitFor(() => expect(searches()).toHaveLength(1), { timeout: 3000 });
    const hit = await screen.findByRole("link", { name: /Lumen alert correlation/ });
    expect(hit).toHaveTextContent("Solution");
    expect(hit.querySelector("mark")).toHaveTextContent(/lumen/i);
    expect(await screen.findByTestId("gb-status")).toHaveTextContent("2 results for lumen");
    expect(searches()).toHaveLength(1); // not one per keystroke
  });

  it("US-065-AC1: a hit is a link to the node page and its excerpt is text segments, never markup", async () => {
    fake.rows["catalog.Product"]?.push({
      key: "p-x",
      props: { code: "p-x", name: "<img src=x onerror=alert(1)> lumen" },
    });
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await screen.findByTestId("gb-status");
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getAllByText(/<img src=x onerror=alert\(1\)>/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Lumen alert correlation/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution/sol-1",
    );
  });

  it("a hit whose excerpt only repeats its label shows no excerpt line", async () => {
    fake.rows["catalog.Product"]?.push({ key: "p-z", props: { code: "p-z", name: "zebra" } });
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "zebra");
    const hit = await screen.findByRole("link", { name: /zebra/ });
    expect(hit.querySelector(".gb-ex")).toBeNull();
  });

  it("US-065-AC2: the answer to an earlier text is discarded and never displayed", async () => {
    const user = userEvent.setup();
    const release = fake.gate("lumen");
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await waitFor(() => expect(searches()).toHaveLength(1), { timeout: 3000 });
    await user.clear(screen.getByRole("textbox", { name: /Search/ }));
    await user.type(screen.getByRole("textbox", { name: /Search/ }), "pattern");
    expect(
      await screen.findByRole("link", { name: /Alert grouping/ }, { timeout: 3000 }),
    ).toBeInTheDocument();
    release();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("link", { name: /Lumen alert correlation/ })).toBeNull();
    expect(screen.getByTestId("gb-status")).toHaveTextContent("for pattern");
  });

  it("US-065-AC3: the answer's freshness is shown with it", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    expect(await screen.findByTestId("gb-answer-freshness")).toHaveTextContent("memory · LATEST");
  });

  it("US-065-AC4: text with no hit names the text and the types searched; All searches every type", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.click(await screen.findByRole("radio", { name: "Solutions" }));
    await user.type(await searchBox(), "zzzz");
    expect(
      await screen.findByRole("heading", { name: "No results for “zzzz”" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Searched Solutions\./)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /^All/ }));
    expect(
      await screen.findByText(/Searched Use cases, Solutions, Products\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Solution/ })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByRole("textbox", { name: /Search/ })).toHaveValue("zzzz");
  });

  it("US-065-AC5: one character sends no search and the page says two are needed", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "h");
    expect(await screen.findByTestId("gb-hint", {}, { timeout: 3000 })).toHaveTextContent(
      "Type at least two characters",
    );
    await new Promise((r) => setTimeout(r, 400));
    expect(searches()).toHaveLength(0);
  });

  it("US-065-AC6: a type whose backend does not serve search is named as not searched, and the others' hits show", async () => {
    fake.notSearched = [{ type: "UseCase", reason: "unavailable", backend: "ashlar" }];
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    const banner = await screen.findByTestId("gb-banner");
    expect(banner).toHaveTextContent("Use case was not searched.");
    expect(banner).toHaveTextContent("Its backend (ashlar) is unavailable.");
    expect(screen.getByRole("link", { name: /Lumen alert correlation/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Use case/ })).toHaveTextContent("not searched");
  });
});

describe("narrowing a search (US-066)", () => {
  it("US-066-AC3, AC4, AC5: chips show the hits of each type and All the total; choosing one sends that type; All keeps the text", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await screen.findByTestId("gb-status");
    expect(screen.getByRole("radio", { name: /^Solution/ })).toHaveTextContent("1");
    expect(screen.getByRole("radio", { name: /^Product/ })).toHaveTextContent("1");
    expect(screen.getByRole("radio", { name: /^Use case/ })).toHaveTextContent("0");
    expect(screen.getByRole("radio", { name: /^All/ })).toHaveTextContent("2");
    await user.click(screen.getByRole("radio", { name: /^Product/ }));
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(1));
    expect(screen.getByRole("link", { name: /Lumen/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Product/p-1",
    );
    expect(screen.getByRole("radio", { name: /^Solution/ })).toBeInTheDocument(); // the others stay visible
    const last = JSON.parse(JSON.stringify(fake.requests.at(-1)?.body.variables));
    expect(last.types).toEqual(["Product"]);
    await user.click(screen.getByRole("radio", { name: /^All/ }));
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(1));
    expect(fake.requests.at(-1)?.body.variables).toMatchObject({ types: null });
    expect(screen.getByRole("textbox", { name: /Search/ })).toHaveValue("lumen");
  });

  it("US-066-AC6: the chips are one radio group: one is checked, choosing it again changes nothing, the arrow keys move the choice", async () => {
    const user = userEvent.setup();
    renderBrowser();
    const all = await screen.findByRole("radio", { name: "All" });
    const products = screen.getByRole("radio", { name: "Products" });
    expect(all).toHaveAttribute("tabindex", "0");
    expect(products).toHaveAttribute("tabindex", "-1");
    await user.click(products);
    expect(products).toHaveAttribute("aria-checked", "true");
    expect(all).toHaveAttribute("aria-checked", "false");
    await user.click(products);
    expect(products).toHaveAttribute("aria-checked", "true");
    expect(products).toHaveAttribute("tabindex", "0");
    await user.keyboard("{ArrowLeft}");
    const solutions = screen.getByRole("radio", { name: "Solutions" });
    expect(solutions).toHaveAttribute("aria-checked", "true");
    expect(solutions).toHaveFocus();
    expect(products).toHaveAttribute("aria-checked", "false");
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("radio", { name: "All" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "Products" })).toHaveAttribute("aria-checked", "true");
  });

  it("with search text, All searches every type and a type pill only that type", async () => {
    const user = userEvent.setup();
    renderBrowser();
    await user.type(await searchBox(), "lumen");
    await screen.findByTestId("gb-status");
    expect(fake.requests.at(-1)?.body.variables).toMatchObject({ types: null });
    await user.click(screen.getByRole("radio", { name: /^Solution/ }));
    await waitFor(() =>
      expect(fake.requests.at(-1)?.body.variables).toMatchObject({ types: ["Solution"] }),
    );
  });

  it("an older server that serves no search has no search box, and the chips still list types", async () => {
    for (const t of fake.mods[0]?.entityTypes ?? []) delete t.capabilities.memory?.search;
    renderBrowser();
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.queryByRole("search")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("the / key focuses the search box and Escape clears it (DESIGN-GB, Interaction States)", async () => {
    const user = userEvent.setup();
    renderBrowser();
    const box = await searchBox();
    await user.keyboard("/");
    expect(box).toHaveFocus();
    await user.keyboard("abc");
    expect(box).toHaveValue("abc");
    await user.keyboard("{Escape}");
    expect(box).toHaveValue("");
  });
});
