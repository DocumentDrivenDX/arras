// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DataArea } from "../areas/DataArea";
import { EntityTable } from "../areas/EntityTable";
import { ModuleHeader } from "../console/ModuleHeader";
import { NARROW, NO_KEYBOARD, useHideKeyHints, useNarrow } from "../lib/useMediaQuery";
import { defined } from "./defined";
import { catalog, type FakeApi, seedCatalog, stage } from "./fake";
import { renderConsole, renderPart } from "./render";

/** A `matchMedia` where the listed queries match. */
function media(matching: string[]) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: matching.includes(query),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
}
const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const listPosts = () => api.posts(/\/graphql\/catalog$/).filter((r) => /List\(/.test(r.body.query));

function Probe() {
  return (
    <p data-testid="probe">
      {String(useNarrow())}/{String(useHideKeyHints())}
    </p>
  );
}

describe("narrow and touch detection", () => {
  it("is wide with keyboard hints where the page cannot ask (no matchMedia)", () => {
    window.matchMedia = undefined as unknown as typeof window.matchMedia;
    render(<Probe />);
    expect(screen.getByTestId("probe")).toHaveTextContent("false/false");
  });

  it("is narrow below md, which also hides the key hints", () => {
    media([NARROW, NO_KEYBOARD]);
    render(<Probe />);
    expect(screen.getByTestId("probe")).toHaveTextContent("true/true");
  });

  it("hides the key hints on a coarse pointer at any width, and is not narrow there", () => {
    media([NO_KEYBOARD]);
    render(<Probe />);
    expect(screen.getByTestId("probe")).toHaveTextContent("false/true");
  });

  it("the header's key hint and the table's follow it", async () => {
    const header = () => (
      <ModuleHeader module="catalog" area="entities" auditShown onArea={() => undefined} />
    );
    const { unmount } = render(header());
    expect(screen.getByTestId("key-hint")).toBeInTheDocument();
    unmount();
    media([NO_KEYBOARD]);
    render(header());
    expect(screen.queryByTestId("key-hint")).toBeNull();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    expect(screen.queryByTestId("table-key-hint")).toBeNull();
  });
});

describe("the module choice on a narrow screen", () => {
  it("is a select in the header in place of the rail, and choosing a module goes there", async () => {
    const user = userEvent.setup();
    api.modules = [catalog(), catalog({ name: "ledger" })];
    media([NARROW, NO_KEYBOARD]);
    renderConsole();
    const picker = await screen.findByRole("combobox", { name: "Module" });
    expect(picker).toHaveValue("catalog");
    expect(screen.getAllByRole("navigation", { name: "Modules" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^catalog/ })).toBeNull();
    await user.selectOptions(picker, "ledger");
    await screen.findByRole("heading", { level: 1, name: "ledger" });
  });

  it("is nothing for a single module, and the rail returns from md up", async () => {
    api.modules = [catalog()];
    media([NARROW, NO_KEYBOARD]);
    const first = renderConsole();
    await screen.findByRole("heading", { level: 1, name: "catalog" });
    expect(screen.queryByRole("navigation", { name: "Modules" })).toBeNull();
    first.unmount();
    media([]);
    renderConsole();
    const rail = await screen.findByRole("navigation", { name: "Modules" });
    expect(within(rail).getByRole("button", { name: /catalog/ })).toBeInTheDocument();
  });

  it("the Query tab keeps its whole label and the tabs scroll rather than shrink", async () => {
    media([NARROW, NO_KEYBOARD]);
    renderConsole();
    const query = await screen.findByRole("tab", { name: "Query" });
    expect(query.className).toContain("shrink-0");
    expect(query.className).toContain("whitespace-nowrap");
    expect(query.closest(".arras-cue")).not.toBeNull();
  });
});

function ui(onQuery?: (t: string) => void, onEntity?: (k: string | null) => void) {
  return (
    <DataArea
      module="catalog"
      type="catalog.UseCase"
      onType={() => undefined}
      onQuery={onQuery}
      onEntity={onEntity}
    />
  );
}

describe("Data: one pane at a time below md, both from md up", () => {
  it("opening an entity hides the table below md (shown from md) and puts a Back bar over the panel", async () => {
    const user = userEvent.setup();
    renderPart(ui());
    const tablePane = await screen.findByTestId("data-table-pane");
    expect(tablePane.className).not.toContain("hidden");
    expect(screen.queryByTestId("data-panel-pane")).toBeNull();
    await user.click(await screen.findByText("uc-2"));
    const panelPane = await screen.findByTestId("data-panel-pane");
    // The table pane is display:none below md and flex from md; the panel pane vanishes into the row from md.
    expect(tablePane.className).toContain("hidden");
    expect(tablePane.className).toContain("md:flex");
    expect(panelPane.className).toContain("md:contents");
    // The panel pane holds the Back bar (md:hidden) and the panel; the table is not inside it.
    const back = within(panelPane).getByRole("button", { name: /Back to list/ });
    expect(back.closest(".md\\:hidden")).not.toBeNull();
    expect(within(panelPane).getByTestId("entity-panel")).toBeInTheDocument();
    expect(within(panelPane).queryByTestId("entity-table")).toBeNull();
    expect(panelPane.parentElement).toBe(tablePane.parentElement);
  });

  it("Back returns to the list with the opened row focused, its page and filter intact", async () => {
    const user = userEvent.setup();
    const onEntity = vi.fn();
    renderPart(ui(undefined, onEntity));
    await user.type(await screen.findByLabelText("Filter name"), "Use case 2{Enter}");
    await user.click(await screen.findByText("uc-2"));
    await screen.findByTestId("data-panel-pane");
    await user.click(screen.getByRole("button", { name: /Back to list/ }));
    expect(onEntity).toHaveBeenLastCalledWith(null);
    await waitFor(() => expect(screen.queryByTestId("data-panel-pane")).toBeNull());
    expect(screen.getByTestId("data-table-pane").className).not.toContain("hidden");
    await waitFor(() => expect(screen.getByRole("button", { name: "uc-2" })).toHaveFocus());
    expect(screen.getByLabelText("Filter name")).toHaveValue("Use case 2");
  });
});

describe("Data: the table's cues, filters and sort", () => {
  it("the first column is the sticky key and the scroller sits in a cue wrapper", async () => {
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    const scroller = await screen.findByTestId("grid-scroll");
    expect(scroller.parentElement).toHaveClass("arras-cue", "arras-cue-table");
    // No cue until the box overflows: jsdom measures nothing, so neither edge shows.
    expect(scroller.parentElement).not.toHaveAttribute("data-cue-end");
    expect(scroller.parentElement).not.toHaveAttribute("data-cue-start");
  });

  it("a filter on a declared column that is not shown is offered under More filters", async () => {
    const user = userEvent.setup();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    // The relationship column is not shown by default; its filter is declared.
    const more = screen.getByTestId("hidden-filters");
    expect(more).toHaveTextContent("More filters (1");
    await user.type(within(more).getByLabelText("Filter addressedBy"), "sol-1{Enter}");
    await waitFor(() =>
      expect(defined(listPosts().at(-1), "last list").body.variables.filter).toEqual({
        addressedBy: "sol-1",
      }),
    );
    expect(more).toHaveTextContent("1 active");
    await user.click(screen.getByRole("button", { name: "Clear filter" }));
    await waitFor(() =>
      expect(defined(listPosts().at(-1), "last").body.variables.filter).toBeNull(),
    );
  });

  it("hiding a column moves its filter under More filters; an undeclared column never gets one", async () => {
    const user = userEvent.setup();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    await user.click(screen.getByText(/^Columns/));
    await user.click(screen.getByRole("checkbox", { name: /^name/ }));
    const more = screen.getByTestId("hidden-filters");
    expect(within(more).getByLabelText("Filter name")).toBeInTheDocument();
    expect(within(more).queryByLabelText("Filter workArea")).toBeNull();
    expect(screen.getAllByLabelText("Filter name")).toHaveLength(1);
  });

  it("headers sort this page with aria-sort, and a partial page says so", async () => {
    const user = userEvent.setup();
    api.rows["catalog.UseCase"] = Array.from({ length: 30 }, (_, i) => ({
      key: `uc-${String(i).padStart(2, "0")}`,
      type: "catalog.UseCase",
      code: `uc-${String(i).padStart(2, "0")}`,
      name: `Name ${(i * 7) % 30}`,
      workArea: null,
    }));
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-00");
    await user.selectOptions(screen.getByLabelText("Page size"), "25");
    await screen.findByText("uc-24");
    const nameHeader = screen.getByRole("columnheader", { name: /^name/ });
    expect(nameHeader).toHaveAttribute("aria-sort", "none");
    expect(nameHeader).toHaveAttribute("title", expect.stringContaining("sorts this page"));
    const firstKey = () =>
      within(screen.getAllByRole("row")[2] as HTMLElement).getAllByRole("cell")[0];
    expect(firstKey()).toHaveTextContent("uc-00");

    await user.click(within(nameHeader).getByRole("button"));
    expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    expect(firstKey()).toHaveTextContent("uc-00"); // "Name 0" is the least
    const note = screen.getByTestId("sort-note");
    expect(note).toHaveTextContent("Sorted by name ascending: this page only");
    expect(note).toHaveTextContent("other pages stay in key order");
    // The read itself is untouched: no order was asked of the server.
    expect(Object.keys(defined(listPosts().at(-1), "last").body.variables).sort()).toEqual([
      "afterKey",
      "consistency",
      "filter",
      "limit",
    ]);

    await user.click(within(nameHeader).getByRole("button"));
    expect(nameHeader).toHaveAttribute("aria-sort", "descending");
    expect(firstKey()).not.toHaveTextContent("uc-00");
    expect(screen.getByRole("columnheader", { name: /^code/ })).toHaveAttribute(
      "aria-sort",
      "none",
    );

    await user.click(within(nameHeader).getByRole("button"));
    expect(nameHeader).toHaveAttribute("aria-sort", "none");
    expect(screen.queryByTestId("sort-note")).toBeNull();
  });

  it("a page that is the whole result is sorted without the partial-page note", async () => {
    const user = userEvent.setup();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    await user.click(
      within(screen.getByRole("columnheader", { name: /^name/ })).getByRole("button"),
    );
    const note = screen.getByTestId("sort-note");
    expect(note).toHaveTextContent("this page only");
    expect(note).not.toHaveTextContent("other pages");
    await user.click(within(note).getByRole("button", { name: "Back to key order" }));
    expect(screen.queryByTestId("sort-note")).toBeNull();
  });
});

describe("Data: Query this type", () => {
  it("opens the Query area on the type, and shows nowhere it cannot", async () => {
    const user = userEvent.setup();
    const onQuery = vi.fn();
    const { unmount } = renderPart(ui(onQuery));
    await user.click(await screen.findByRole("button", { name: "Query this type" }));
    expect(onQuery).toHaveBeenCalledWith("catalog.UseCase");
    unmount();
    renderPart(ui());
    await screen.findByText("uc-1");
    expect(screen.queryByRole("button", { name: "Query this type" })).toBeNull();
  });

  it("in the console, opens the Query area with the type's starter statement", async () => {
    const user = userEvent.setup();
    renderConsole();
    await user.click(await screen.findByRole("tab", { name: "Entities" }));
    await user.click(await screen.findByRole("button", { name: "Query this type" }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Query" })).toHaveAttribute("aria-selected", "true"),
    );
    await waitFor(() =>
      expect((screen.getByTestId("query-input") as HTMLTextAreaElement).value).toMatch(
        /FROM "catalog"."UseCase"/,
      ),
    );
  });
});
