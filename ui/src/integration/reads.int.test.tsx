// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { DataArea } from "../areas/DataArea";
import { EntityTable } from "../areas/EntityTable";
import { GraphArea } from "../areas/GraphArea";
import { buildGraphQuery } from "../lib/graph";
import { defined } from "../test/defined";
import { call, client, gql, invoke, renderLive, unique, withDevHost } from "./harness";

// Reads against the real dev host (US-061): the table, the entity panel, a relationship followed to
// its real target, freshness, and the graph drawn from the real `<type>List` answers.
withDevHost();

const uses = (n: number, prefix: string) =>
  call("/api/operate/actions/catalog/AddUseCase/batch", {
    items: Array.from({ length: n }, (_, i) => ({
      code: `${prefix}-${String(i).padStart(2, "0")}`,
      name: `Paged ${i}`,
      workArea: "paging",
    })),
    atomic: true,
  });

describe("Data (US-061) on the real server", () => {
  let prefix = "";
  beforeAll(async () => {
    prefix = unique("pg");
    const r = await uses(30, prefix); // with the demo's use cases, more than one page of 25
    expect(r.status).toBe(200);
  });

  it("pages after the last key shown and shows the page's freshness from the record store", async () => {
    const user = userEvent.setup();
    const all = await gql<{ data: { useCaseList: { items: { key: string }[] } } }>(
      "{ useCaseList(limit: 100) { items { key } truncated } }",
      undefined,
      "alice",
      "catalog",
    );
    const keys = all.body.data.useCaseList.items.map((x) => x.key);
    expect(keys.length).toBeGreaterThan(25);
    renderLive(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText(defined(keys[0], "the first key"));
    await user.selectOptions(screen.getByLabelText("Page size"), "25");
    await waitFor(() => expect(screen.getByTestId("page-info")).toHaveTextContent("25 rows"));
    expect(screen.getByText("truncated")).toBeInTheDocument();
    const fresh = screen.getByTestId("freshness");
    expect(fresh).toHaveTextContent("LATEST");
    expect(fresh).toHaveTextContent("record: memory");
    expect(fresh).toHaveTextContent(/position fake:\d+/);
    expect(screen.queryByText(defined(keys[25], "the 26th key"))).toBeNull();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    await screen.findByText(defined(keys[25], "the 26th key")); // the page after the 25th key
    expect(screen.getByTestId("page-info")).toHaveTextContent("Page 2");
    expect(screen.queryByText(defined(keys[24], "the 25th key"))).toBeNull();
    await user.click(screen.getByRole("button", { name: /Previous/ }));
    await screen.findByText(defined(keys[0], "the first key"));
  });

  it("BULK reads the replica and says so, with its lag", async () => {
    const user = userEvent.setup();
    renderLive(<EntityTable module="catalog" type="catalog.Solution" />);
    await screen.findByText("sol-1");
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await waitFor(() =>
      expect(screen.getByTestId("freshness")).toHaveTextContent("replica: memory_replica"),
    );
    expect(screen.getByTestId("freshness")).toHaveTextContent("BULK");
    expect(screen.getByTestId("freshness")).toHaveTextContent("not current");
    await waitFor(() =>
      expect(screen.getByTestId("freshness")).toHaveTextContent(/replica lag \d/),
    );
  });

  it("filters on a declared column with whole-value equality", async () => {
    const user = userEvent.setup();
    renderLive(<EntityTable module="catalog" type="catalog.UseCase" />);
    await screen.findByText("uc-pipeline");
    await user.type(screen.getByLabelText("Filter name"), "Pipeline mapping{Enter}");
    await waitFor(() => expect(screen.getByTestId("page-info")).toHaveTextContent("1 rows"));
    expect(screen.getByText("uc-pipeline")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Filter name"));
    await user.type(screen.getByLabelText("Filter name"), "Pipeline{Enter}");
    expect(await screen.findByText("No entries match the filter")).toBeInTheDocument();
  });

  it("an entity shows its attribution, and a relationship opens its real target", async () => {
    const user = userEvent.setup();
    const code = unique("sol");
    const uc = unique("uc");
    expect(
      (
        await invoke(
          "AddUseCase",
          { code: uc, name: "Followed use case", workArea: "finance" },
          "bob",
        )
      ).status,
    ).toBe(200);
    expect(
      (await invoke("AddSolution", { code, name: "Follower", useCase: uc }, "alice")).status,
    ).toBe(200);
    renderLive(
      <DataArea
        module="catalog"
        type="catalog.Solution"
        onType={() => undefined}
        onHistory={() => undefined}
      />,
    );
    await screen.findByText("sol-1");
    // The new solution may be on a later page; filter to it.
    await user.type(screen.getByLabelText("Filter code"), `${code}{Enter}`);
    await user.click(await screen.findByText(code));
    const panel = await screen.findByTestId("entity-panel");
    expect(await within(panel).findByTestId("prop-name")).toHaveTextContent("Follower");
    expect(within(panel).getByTestId("entity-created-by")).toHaveTextContent("alice");
    expect(within(panel).getByTestId("entity-updated-by")).toHaveTextContent("alice");
    expect(within(panel).getByTestId("entity-version")).toHaveTextContent("1");
    await user.click(within(panel).getByRole("button", { name: uc }));
    // The target, read with `target` only now, is the use case bob created.
    await waitFor(() =>
      expect(within(panel).getByTestId("prop-name")).toHaveTextContent("Followed use case"),
    );
    expect(within(panel).getByTestId("prop-workArea")).toHaveTextContent("finance");
    expect(within(panel).getByTestId("entity-created-by")).toHaveTextContent("bob");
    await user.click(within(panel).getByRole("button", { name: /back/ }));
    await waitFor(() =>
      expect(within(panel).getByTestId("prop-name")).toHaveTextContent("Follower"),
    );
  });
});

describe("Graph on the real server", () => {
  it("draws one node per entity and one edge per reference that the real list reads return", async () => {
    const meta = await client("alice").meta();
    const m = defined(
      meta.modules.find((x) => x.name === "catalog"),
      "the catalog module",
    );
    let entities = 0;
    let refs = 0;
    for (const t of m.entityTypes) {
      const r = await gql<{ data: Record<string, { items: Record<string, unknown>[] }> }>(
        buildGraphQuery(m, t),
        { limit: 100, consistency: "LATEST" },
        "alice",
        "catalog",
      );
      const items = defined(Object.values(r.body.data)[0], "the list result").items;
      entities += items.length;
      if (t.name === "catalog.Solution")
        refs += items.reduce((n, x) => n + ((x.addresses as unknown[]) ?? []).length, 0);
    }
    renderLive(<GraphArea module="catalog" />);
    const area = await screen.findByTestId("graph-area");
    await waitFor(() =>
      expect(within(area).getAllByTestId("node").length).toBe(Math.min(entities, 150)),
    );
    // Each `addresses` reference is one edge; the inverse read (addressedBy) draws the same edges.
    expect(within(area).getAllByTestId("edge")).toHaveLength(refs);
    expect(screen.getByRole("button", { name: /addresses/ })).toHaveTextContent(String(refs));
    expect(screen.getByTestId("freshness")).toHaveTextContent("record: memory");
  });

  it("selecting a node opens the entity with its attribution", async () => {
    const user = userEvent.setup();
    renderLive(<GraphArea module="catalog" />);
    const node = await screen.findByRole("button", { name: /Solution Pipeline extractor/ });
    await user.click(node);
    const panel = await screen.findByTestId("entity-panel");
    expect(await within(panel).findByTestId("prop-name")).toHaveTextContent("Pipeline extractor");
    expect(within(panel).getByTestId("entity-created-by")).toHaveTextContent("alice");
    expect(node.closest('[data-testid="node"]')).toHaveAttribute("data-selected", "true");
  });
});
