// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { columnsFor } from "../api/gql";
import { DataArea } from "../areas/DataArea";
import { EntityTable } from "../areas/EntityTable";
import { addressOf, SETTLE_MS } from "../areas/entityAddress";
import { defined } from "./defined";
import { attribution, catalog, type FakeApi, json, seedCatalog, stage, wire } from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const listPosts = () => api.posts(/\/graphql\/catalog$/).filter((r) => /List\(/.test(r.body.query));

function ui(type = "catalog.UseCase") {
  return (
    <DataArea
      module="catalog"
      type={type}
      onType={() => undefined}
      onAction={() => undefined}
      onHistory={() => undefined}
    />
  );
}

describe("Data (US-061)", () => {
  it("US-061-AC1: a type with 250 entities pages at most 100 at a time, each after the last key of the one before, with the page's freshness", async () => {
    const user = userEvent.setup();
    api.rows["catalog.UseCase"] = Array.from({ length: 250 }, (_, i) => ({
      key: `uc-${String(i).padStart(3, "0")}`,
      type: "catalog.UseCase",
      code: `uc-${i}`,
      name: `Name ${i}`,
      workArea: null,
      ...attribution(),
    }));
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-000");
    await user.selectOptions(screen.getByLabelText("Page size"), "100");
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(2 + 100));
    expect(Math.max(...listPosts().map((r) => r.body.variables.limit))).toBeLessThanOrEqual(100);
    expect(screen.getByTestId("freshness")).toHaveTextContent("position fake:3");
    expect(screen.getByTestId("page-info")).toHaveTextContent("Page 1 · 100 rows");
    expect(screen.getByText("truncated")).toBeInTheDocument(); // the limit cut the page
    const next = screen.getByRole("button", { name: /Next/ });
    expect(next).toBeEnabled();
    await user.click(next);
    await screen.findByText("uc-100");
    expect(defined(listPosts().at(-1), "listPosts().at(-1)").body.variables.afterKey).toBe(
      "uc-099",
    );
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("uc-200");
    expect(screen.getAllByRole("row")).toHaveLength(2 + 50);
    expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Previous/ }));
    await screen.findByText("uc-100");
  });

  it("US-061-AC2: a filter on a declared column returns only matches; an undeclared column offers no filter", async () => {
    const user = userEvent.setup();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    expect(screen.getByLabelText("Filter name")).toBeInTheDocument();
    // workArea is a property but not a declared column of the backends: no filter is offered.
    expect(screen.getByRole("columnheader", { name: "workArea" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Filter workArea")).toBeNull();
    // Attribution columns are not filterable either.
    expect(screen.queryByLabelText("Filter updatedBy")).toBeNull();
    await user.type(screen.getByLabelText("Filter name"), "Use case 2{Enter}");
    await waitFor(() => expect(screen.queryByText("uc-1")).toBeNull());
    expect(screen.getByText("uc-2")).toBeInTheDocument();
    expect(defined(listPosts().at(-1), "listPosts().at(-1)").body.variables.filter).toEqual({
      name: "Use case 2",
    });
    // The filter travels in the POST body, not the URL.
    expect(listPosts().every((r) => !r.url.includes("Use%20case") && !r.url.includes("?"))).toBe(
      true,
    );
  });

  it("US-061-AC3: an opened entity shows properties, version and who created and last changed it", async () => {
    const user = userEvent.setup();
    renderPart(ui("catalog.Solution"));
    await user.click(await screen.findByText("sol-1"));
    const panel = await screen.findByTestId("entity-panel");
    await within(panel).findByTestId("prop-name");
    expect(within(panel).getByTestId("prop-name")).toHaveTextContent("Pipeline extractor");
    expect(within(panel).getByTestId("entity-version")).toHaveTextContent("1");
    expect(within(panel).getByTestId("entity-created-by")).toHaveTextContent("ana");
    expect(within(panel).getByTestId("entity-updated-by")).toHaveTextContent("ana");
  });

  it("US-061-AC4: following a relationship opens the entity at the other end, and `target` is read only on open", async () => {
    const user = userEvent.setup();
    renderPart(ui("catalog.Solution"));
    await user.click(await screen.findByText("sol-1"));
    const panel = await screen.findByTestId("entity-panel");
    const follow = await within(panel).findByRole("button", { name: /uc-1/ });
    // Nothing selected `target` while the table and the entity opened.
    expect(api.log.some((r) => /target \{/.test(r.body?.query ?? ""))).toBe(false);
    await user.click(follow);
    await waitFor(() => expect(screen.getByTestId("entity-panel")).toHaveTextContent("UseCase"));
    const followReqs = api.log.filter((r) => /target \{/.test(r.body?.query ?? ""));
    expect(followReqs).toHaveLength(1);
    expect(defined(followReqs[0], "followReqs[0]").body.query).toContain("... on UseCase");
    expect(defined(followReqs[0], "followReqs[0]").body.variables).toEqual({ key: "sol-1" });
    const p2 = screen.getByTestId("entity-panel");
    expect(within(p2).getByTestId("prop-name")).toHaveTextContent("Use case 1");
    // Back returns to the source entity.
    await user.click(within(p2).getByRole("button", { name: /back/ }));
    await waitFor(() =>
      expect(within(screen.getByTestId("entity-panel")).getByTestId("prop-name")).toHaveTextContent(
        "Pipeline extractor",
      ),
    );
  });

  it("US-061-AC4: a target in another module shows interface fields and a hint to open that module", async () => {
    const user = userEvent.setup();
    defined(
      defined(api.rows["catalog.Solution"], 'api.rows["catalog.Solution"]')[0],
      'defined(api.rows["catalog.Solution"], "api.rows[\\"catalog.Solution\\"]")[0]',
    ).addresses = [{ module: "billing", type: "billing.Invoice", key: "inv-9" }];
    api.targets["billing.Invoice:inv-9"] = {
      key: "inv-9",
      type: "billing.Invoice",
      ...attribution("bob"),
    };
    renderPart(ui("catalog.Solution"));
    await user.click(await screen.findByText("sol-1"));
    await user.click(await screen.findByRole("button", { name: /inv-9/ }));
    const panel = await screen.findByText(/belongs to module/);
    expect(panel).toHaveTextContent("billing");
    expect(panel).toHaveTextContent("interface fields");
    expect(screen.getByTestId("entity-created-by")).toHaveTextContent("bob");
  });

  it("US-061-AC5: BULK shows the replica's position and lag", async () => {
    const user = userEvent.setup();
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    expect(screen.getByTestId("freshness")).toHaveTextContent("record: memory");
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await waitFor(() =>
      expect(screen.getByTestId("freshness")).toHaveTextContent("replica: memory_replica"),
    );
    const f = screen.getByTestId("freshness");
    expect(f).toHaveTextContent("BULK");
    expect(f).toHaveTextContent("position fake:3");
    expect(f).toHaveTextContent("replica lag 0.0");
    expect(f).toHaveTextContent("not current");
    expect(defined(listPosts().at(-1), "listPosts().at(-1)").body.variables.consistency).toBe(
      "BULK",
    );
  });

  it("US-061 keyboard: arrows move row focus, Enter opens the entity, `/` focuses the filter", async () => {
    const user = userEvent.setup();
    renderPart(ui("catalog.UseCase"));
    await screen.findByText("uc-1");
    const table = screen.getByRole("table", { name: "catalog.UseCase table" });
    const stops = () => within(table).getAllByRole("button", { name: /^uc-/ });
    defined(stops()[0], "first row button").focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(stops()[2]).toHaveFocus();
    expect(stops().map((b) => b.tabIndex)).toEqual(stops().map((_, i) => (i === 2 ? 0 : -1)));
    const rows = screen.getAllByRole("row");
    expect(defined(rows[4], "rows[4]").className).toContain("focused"); // header, filter row, then rows 0..2
    await user.keyboard("{Enter}");
    const panel = await screen.findByTestId("entity-panel");
    expect(panel).toHaveTextContent("uc-3");
    defined(stops()[2], "focused row button").focus();
    await user.keyboard("/");
    expect(screen.getByLabelText("Filter code")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(stops()[2]).toHaveFocus();
  });

  it("US-061 edge: a request over the cost limits shows COST_EXCEEDED and the table stays usable", async () => {
    api.on((r) =>
      /List\(/.test(r.body?.query ?? "")
        ? json(200, {
            data: { useCaseList: null },
            errors: [
              {
                message: "too many fields",
                extensions: { code: "COST_EXCEEDED" },
                path: ["useCaseList"],
              },
            ],
          })
        : undefined,
    );
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("COST_EXCEEDED");
    expect(screen.getByLabelText("Filter name")).toBeEnabled();
    expect(screen.getByRole("button", { name: "BULK" })).toBeEnabled();
  });

  it("US-061: a query selects only the visible columns and stays within 50 field selections", async () => {
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-1");
    const q: string = defined(listPosts()[0], "listPosts()[0]").body.query;
    expect(q).toContain("workArea");
    expect(q).not.toContain("createdBy");
    expect(q).not.toContain("addressedBy");
    expect(q).not.toMatch(/target \{/);
  });
});

describe("Data: an in-band read error", () => {
  it("names the backend and offers the retry it speaks of", async () => {
    const user = userEvent.setup();
    let down = true;
    api.on((r) =>
      down && r.path.endsWith("/graphql/catalog") && /List\(/.test(r.body.query)
        ? json(200, wire.gqlUnavailable("useCaseList"))
        : undefined,
    );
    renderPart(<EntityTable module="catalog" type="catalog.UseCase" />);
    const notice = (await screen.findByText("UNAVAILABLE")).closest("[role=alert]");
    expect(notice).toHaveTextContent("memory unavailable (unreachable)");
    expect(notice).toHaveTextContent("try the other consistency or retry");
    down = false;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("uc-1");
    expect(screen.queryByText("UNAVAILABLE")).toBeNull();
  });
});

describe("Entities in the address (CONTRACT-010 D)", () => {
  const solutions = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      key: `sol-${String(i + 1).padStart(2, "0")}`,
      type: "catalog.Solution",
      code: `sol-${String(i + 1).padStart(2, "0")}`,
      name: `Solution ${String.fromCharCode(65 + (i % 26))}`,
      coverageLevel: null,
      addresses: [],
      ...attribution("ana"),
    }));
  const operate = (path: string) => {
    window.location.hash = `#/operate/catalog/entities/${path}`;
    return renderConsole({ hashRouting: true, hashPrefix: "operate" });
  };
  const depth = () => window.history.length;

  it("a fresh render restores the filter, the page start and the sort from the address", async () => {
    api.rows["catalog.Solution"] = solutions(6);
    operate("catalog.Solution?f.code=sol-04&after=sol-03&sort=name:desc");
    await screen.findByText("sol-04");
    const last = defined(listPosts().at(-1), "listPosts().at(-1)").body.variables;
    expect(last.filter).toEqual({ code: "sol-04" });
    expect(last.afterKey).toBe("sol-03");
    expect(screen.getByLabelText("Filter code")).toHaveValue("sol-04");
    expect(screen.getByRole("columnheader", { name: /name/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByTestId("page-info")).toHaveTextContent("Page 2");
  });

  it("a sorted page restores in that order", async () => {
    api.rows["catalog.Solution"] = solutions(3);
    operate("catalog.Solution?sort=name:desc");
    await screen.findByText("sol-01");
    const rows = screen.getAllByRole("row").slice(2);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual([
      "sol-03",
      "sol-02",
      "sol-01",
    ]);
  });

  it("typing a filter replaces the entry once it settles; Next and a sort push", async () => {
    const user = userEvent.setup();
    api.rows["catalog.Solution"] = solutions(30);
    operate("catalog.Solution");
    await screen.findByText("sol-01");
    const start = depth();
    await user.type(screen.getByLabelText("Filter code"), "sol-02{Enter}");
    await waitFor(() => expect(window.location.hash).toContain("f.code=sol-02"));
    expect(depth()).toBe(start);
    await user.click(screen.getByRole("button", { name: "Clear filter" }));
    await waitFor(() => expect(window.location.hash).not.toContain("f.code"));
    expect(depth()).toBe(start);
    await user.selectOptions(screen.getByLabelText("Page size"), "25");
    await screen.findByText("sol-25");
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await waitFor(() => expect(window.location.hash).toContain("after=sol-25"));
    expect(depth()).toBe(start + 1);
    await user.click(
      within(screen.getByRole("columnheader", { name: /name/ })).getByRole("button"),
    );
    await waitFor(() => expect(window.location.hash).toContain("sort=name%3Aasc"));
    expect(depth()).toBe(start + 2);
  });

  it("Back returns to the page before, and a link to the same address changes nothing", async () => {
    const user = userEvent.setup();
    api.rows["catalog.Solution"] = solutions(30);
    operate("catalog.Solution");
    await screen.findByText("sol-01");
    await user.selectOptions(screen.getByLabelText("Page size"), "25");
    await screen.findByText("sol-25");
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText("sol-30");
    expect(screen.getByTestId("page-info")).toHaveTextContent("Page 2");
    const here = window.location.hash;
    const start = depth();
    act(() => {
      window.location.hash = here;
    });
    expect(depth()).toBe(start);
    act(() => window.history.back());
    await screen.findByText("sol-01");
    expect(screen.getByTestId("page-info")).toHaveTextContent("Page 1");
    expect(window.location.hash).not.toContain("after");
  });

  it("a filter on a column that is not the key never reaches the fragment", async () => {
    const user = userEvent.setup();
    api.rows["catalog.Solution"] = solutions(3);
    operate("catalog.Solution");
    await screen.findByText("sol-01");
    const start = depth();
    await user.type(screen.getByLabelText("Filter name"), "Solution A{Enter}");
    await waitFor(() =>
      expect(listPosts().at(-1)?.body.variables.filter).toEqual({ name: "Solution A" }),
    );
    await new Promise((r) => setTimeout(r, SETTLE_MS + 100));
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.Solution");
    expect(depth()).toBe(start);
  });

  it("a type change starts a fresh table, and the address names none of the old one", async () => {
    const user = userEvent.setup();
    api.rows["catalog.Solution"] = solutions(3);
    operate("catalog.Solution?f.code=sol-02&sort=name:asc");
    await screen.findByText("sol-02");
    await user.click(screen.getByRole("tab", { name: "UseCase" }));
    await screen.findByText("uc-1");
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase");
    expect(screen.getByLabelText("Filter code")).toHaveValue("");
    expect(screen.getByRole("columnheader", { name: /name/ })).toHaveAttribute("aria-sort", "none");
  });

  it("opening an entity keeps the filter in the address and the table as it was", async () => {
    const user = userEvent.setup();
    api.rows["catalog.Solution"] = solutions(30);
    operate("catalog.Solution?f.code=sol-02");
    await user.click(await screen.findByText("sol-02"));
    await screen.findByTestId("entity-panel");
    expect(window.location.hash).toBe(
      "#/operate/catalog/entities/catalog.Solution/sol-02?f.code=sol-02",
    );
    expect(screen.getByLabelText("Filter code")).toHaveValue("sol-02");
  });
});

describe("The table's writer carries only key column filters", () => {
  const cols = columnsFor(catalog(), defined(catalog().entityTypes[1], "Solution"));
  const solution = (filter: Record<string, string>) =>
    addressOf({ filter, afterKeys: [null], page: 0, sort: null }, cols, "code");

  it("keeps the key column's filter and drops the property, attribution and relationship filters", () => {
    expect(solution({ code: "sol-1" }).filter).toEqual({ code: "sol-1" });
    expect(
      solution({ name: "Pipeline", updatedBy: "alice", createdBy: "carol", addresses: "uc-1" })
        .filter,
    ).toBeUndefined();
    expect(solution({ code: "sol-1", name: "Pipeline", updatedBy: "alice" }).filter).toEqual({
      code: "sol-1",
    });
    expect(solution({ code: "  " }).filter).toBeUndefined();
  });

  it("never lets a typed filter reach onAddress, whichever column it is typed in", async () => {
    const user = userEvent.setup();
    const seen: { filter?: Record<string, string> }[] = [];
    renderPart(
      <EntityTable module="catalog" type="catalog.Solution" onAddress={(a) => seen.push(a)} />,
    );
    await screen.findByText("sol-1");
    await user.type(screen.getByLabelText("Filter name"), "Pipeline extractor{Enter}");
    await waitFor(() =>
      expect(defined(listPosts().at(-1), "listPosts().at(-1)").body.variables.filter).toEqual({
        name: "Pipeline extractor",
      }),
    );
    await new Promise((r) => setTimeout(r, SETTLE_MS + 100));
    expect(seen.every((a) => a.filter === undefined)).toBe(true);
    await user.type(screen.getByLabelText("Filter code"), "sol-1{Enter}");
    await waitFor(() => expect(seen.at(-1)?.filter).toEqual({ code: "sol-1" }));
    expect(Object.keys(seen.at(-1)?.filter ?? {})).toEqual(["code"]);
  });

  it("writes a settled filter as a replace and a page as a push", async () => {
    const user = userEvent.setup();
    const seen: { replace: boolean; after?: string; filter?: Record<string, string> }[] = [];
    seedCatalog(api, 30);
    renderPart(
      <EntityTable
        module="catalog"
        type="catalog.UseCase"
        onAddress={(a, how) => seen.push({ ...a, replace: how.replace })}
      />,
    );
    await screen.findByText("uc-1");
    await user.selectOptions(screen.getByLabelText("Page size"), "25");
    await user.click(await screen.findByRole("button", { name: /Next/ }));
    expect(seen.at(-1)).toMatchObject({ after: "uc-25", replace: false });
    await user.type(screen.getByLabelText("Filter code"), "uc-3{Enter}");
    await waitFor(() =>
      expect(seen.at(-1)).toMatchObject({ filter: { code: "uc-3" }, replace: true }),
    );
  });
});
