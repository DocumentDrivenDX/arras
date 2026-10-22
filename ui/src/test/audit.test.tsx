// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { AuditView } from "../areas/AuditView";
import { NavProvider } from "../components/NavLink";
import { crossLinks } from "../shell/links";
import { defined } from "./defined";
import { catalog, err, type FakeApi, json, type Recorded, seedCatalog, stage, wire } from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const changes = (r: Recorded) => r.method === "POST" && r.path.endsWith("/audit/changes");
const calls = () => api.log.filter(changes);

const change = wire.change;
const page = (items: unknown[], nextCursor: string | null = null) =>
  json(200, wire.page(items, nextCursor));

describe("Audit (US-063)", () => {
  it("US-063-AC1: an entity's history shows the person, time, action and entities touched, and no input values", async () => {
    // Even if a response carried extra fields, the view renders only the contract's fields.
    api.on((r) =>
      changes(r)
        ? page([{ ...change(), inputs: { level: "SECRET-INPUT-VALUE" }, detail: "SECRET-DETAIL" }])
        : undefined,
    );
    renderPart(<AuditView module="catalog" entity={{ type: "catalog.Solution", key: "sol-1" }} />);
    const row = await screen.findByTestId("change-row");
    expect(row).toHaveTextContent("ana");
    expect(row).toHaveTextContent("2026-10-09 14:02:11");
    expect(row).toHaveTextContent("catalog.CorrectSolution");
    expect(row).toHaveTextContent("update Solution sol-1");
    expect(row).toHaveTextContent("v2");
    expect(row).toHaveTextContent("g-4");
    expect(screen.getByTestId("audit")).not.toHaveTextContent("SECRET");
    expect(defined(calls()[0], "calls()[0]").body).toEqual({
      module: "catalog",
      type: "catalog.Solution",
      key: "sol-1",
      limit: 50,
    });
    expect(defined(calls()[0], "calls()[0]").url).not.toContain("sol-1");
  });

  it("US-063-AC2: a module's changes filter by person and time in the POST body, newest first, at most 100 per page", async () => {
    const user = userEvent.setup();
    api.on((r) =>
      changes(r) ? page([change({ group: "g-9" }), change({ group: "g-8" })], "2") : undefined,
    );
    renderPart(<AuditView module="catalog" />);
    await screen.findAllByTestId("change-row");
    await user.type(screen.getByLabelText("Person"), "ana");
    fireEvent.change(screen.getByLabelText("Since"), { target: { value: "2026-10-09T00:00" } });
    await user.selectOptions(screen.getByLabelText("Action"), "catalog.CorrectSolution");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(defined(calls().at(-1), "calls().at(-1)").body.by).toBe("ana"));
    const body = defined(calls().at(-1), "calls().at(-1)").body;
    expect(body.module).toBe("catalog");
    expect(body.action).toBe("catalog.CorrectSolution");
    // datetime-local is the viewer's local time; it is sent as UTC with its offset (CONTRACT-009 400s without one).
    expect(body.since).toBe(new Date(2026, 9, 9, 0, 0).toISOString());
    expect(body.since).toMatch(/Z$/);
    expect(body.limit).toBeLessThanOrEqual(100);
    expect(calls().every((r) => !r.url.includes("ana"))).toBe(true);
    // Newest first is the server's order and the view keeps it.
    const rows = screen.getAllByTestId("change-row");
    expect(rows[0]).toHaveTextContent("g-9");
    expect(rows[1]).toHaveTextContent("g-8");
    expect(screen.getByTestId("committed-only")).toHaveTextContent(
      "newest first".replace("n", "N"),
    ); // "Newest first."
    // The next page uses the cursor.
    await user.click(screen.getByRole("button", { name: /Older/ }));
    await waitFor(() => expect(defined(calls().at(-1), "calls().at(-1)").body.after).toBe("2"));
  });

  it("US-063-AC3: a receipt's group id looks up the same change", async () => {
    const user = userEvent.setup();
    api.on((r) => (changes(r) ? page(r.body.group === "g-4" ? [change()] : []) : undefined));
    renderPart(<AuditView module="catalog" />);
    await user.click(await screen.findByRole("tab", { name: "Receipt by group" }));
    await user.type(screen.getByLabelText("Group id"), "g-4");
    await user.click(screen.getByRole("button", { name: "Search" }));
    const row = await screen.findByTestId("change-row");
    expect(row).toHaveTextContent("g-4");
    expect(row).toHaveTextContent("ana");
    expect(defined(calls().at(-1), "calls().at(-1)").body).toMatchObject({
      module: "catalog",
      group: "g-4",
    });
  });

  it("US-063-AC4: a viewer without the journal grant sees the refusal and the reason", async () => {
    api.on((r) => (changes(r) ? err(403, wire.refused("changes")) : undefined));
    renderPart(<AuditView module="catalog" entity={{ type: "catalog.Solution", key: "sol-1" }} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No access");
    expect(alert).toHaveTextContent("no_access");
    expect(alert).not.toHaveTextContent("Sign in");
  });

  it("US-063 edge: an expired token shows a sign-in prompt, not a refusal", async () => {
    api.on((r) => (changes(r) ? err(401, wire.tokenExpired("changes")) : undefined));
    renderPart(<AuditView module="catalog" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sign in again");
    expect(alert).not.toHaveTextContent("No access");
  });

  it("US-063-AC5: a module whose record store is a replica reader has no change history; the feed position and lag are shown", async () => {
    api.modules = [catalog({ record: "memory_replica", replicas: [] })];
    api.on((r) => (changes(r) ? err(501, wire.unsupported()) : undefined));
    renderPart(<AuditView module="catalog" />);
    const box = await screen.findByTestId("no-history");
    expect(box).toHaveTextContent("No change history");
    await waitFor(() => expect(box).toHaveTextContent("memory_replica"));
    expect(box).toHaveTextContent("feed position fake:3");
    expect(box).toHaveTextContent("lag 0.0");
  });

  it("US-063-AC5: the Audit tab stays visible for a module whose record store keeps no journal so the state can be read", async () => {
    window.location.hash = "#/catalog/model";
    api.modules = [catalog({ record: "memory_replica", replicas: [] })];
    api.on((r) => (changes(r) ? err(501, wire.unsupported()) : undefined));
    renderConsole({ hashRouting: true });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Changes" }));
    expect(await screen.findByTestId("no-history")).toBeInTheDocument();
  });

  it("US-063: the Audit area is hidden unless the backend serves it (a 501 probe hides it)", async () => {
    window.location.hash = "#/catalog/model";
    api.on((r) => (changes(r) ? err(501, wire.unsupported()) : undefined));
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Model" });
    await waitFor(() => expect(calls()).toHaveLength(1)); // the probe
    expect(defined(calls()[0], "calls()[0]").body).toEqual({ module: "catalog", limit: 1 });
    expect(screen.queryByRole("tab", { name: "Changes" })).toBeNull();
    // A deep link to the hidden area falls back to Schema.
    expect(screen.getByRole("tab", { name: "Model", selected: true })).toBeInTheDocument();
  });

  it("US-063: the Audit area is shown when the probe succeeds, and History opens from an entity", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution";
    api.on((r) => (changes(r) ? page([change()]) : undefined));
    renderConsole({ hashRouting: true });
    await screen.findByRole("tab", { name: "Changes" });
    await user.click(await screen.findByText("sol-1"));
    await user.click(await screen.findByRole("button", { name: "History" }));
    const row = await screen.findByTestId("change-row");
    expect(row).toHaveTextContent("ana");
    const entityQuery = calls().find((r) => r.body.key === "sol-1");
    expect(defined(entityQuery, "entityQuery").body).toMatchObject({
      module: "catalog",
      type: "catalog.Solution",
      key: "sol-1",
    });
    // The entity is in the fragment, so a refresh or a shared link shows the same history.
    expect(window.location.hash).toBe("#/catalog/changes/catalog.Solution/sol-1");
  });

  it("US-063 edge: the trail says it shows committed changes only", async () => {
    renderPart(<AuditView module="catalog" />);
    expect(await screen.findByTestId("committed-only")).toHaveTextContent("committed changes only");
    expect(screen.getByTestId("committed-only")).toHaveTextContent(
      "refused attempt or a validate-only run is not recorded",
    );
  });

  it("US-063: import loads list who initiated them and the counts", async () => {
    const user = userEvent.setup();
    api.on((r) => (r.path.endsWith("/audit/loads") ? page([wire.load()]) : undefined));
    renderPart(<AuditView module="catalog" />);
    await user.click(await screen.findByRole("tab", { name: "Import loads" }));
    const table = await screen.findByTestId("loads");
    expect(within(table).getByText("ld-1")).toBeInTheDocument();
    expect(table).toHaveTextContent("root");
    expect(
      defined(api.posts(/audit\/loads$/)[0], "api.posts(/audit/loads$/)[0]").body,
    ).toMatchObject({ module: "catalog" });
  });

  it("lists each provider's journal and reads the chosen one", async () => {
    const user = userEvent.setup();
    api.modules = [
      catalog({ providers: { "catalog.AddUseCase": "vault", "catalog.AddSolution": "vault" } }),
    ];
    api.on((r) => {
      if (changes(r))
        return page([change({ group: r.body.provider === "vault" ? "g-vault" : "g-memory" })]);
      if (r.path.endsWith("/audit/loads"))
        return page([
          wire.load({ load_id: r.body.provider === "vault" ? "ld-vault" : "ld-memory" }),
        ]);
      return undefined;
    });
    renderPart(<AuditView module="catalog" />);
    // the record store first, then the distinct providers; the default is the record store and names no provider
    const select = await screen.findByLabelText("Provider");
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["memory (record store)", "vault"]);
    expect(await screen.findByText("g-memory")).toBeInTheDocument();
    expect(defined(calls()[0], "calls()[0]").body.provider).toBeUndefined();
    // choosing a provider re-reads its journal, with the choice in the POST body and never the URL
    await user.selectOptions(select, "vault");
    expect(await screen.findByText("g-vault")).toBeInTheDocument();
    expect(defined(calls().at(-1), "calls().at(-1)").body).toMatchObject({
      module: "catalog",
      provider: "vault",
    });
    expect(calls().every((r) => !r.url.includes("vault"))).toBe(true);
    // a filter keeps the provider; so do the loads
    await user.type(screen.getByLabelText("Person"), "ana");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(defined(calls().at(-1), "calls().at(-1)").body).toMatchObject({
        by: "ana",
        provider: "vault",
      }),
    );
    await user.click(screen.getByRole("tab", { name: "Import loads" }));
    expect(await screen.findByText("ld-vault")).toBeInTheDocument();
    expect(
      defined(api.posts(/audit\/loads$/).at(-1), "api.posts(/audit\\/loads$/).at(-1)").body,
    ).toMatchObject({
      module: "catalog",
      provider: "vault",
    });
    await user.selectOptions(screen.getByLabelText("Provider"), "memory");
    expect(await screen.findByText("ld-memory")).toBeInTheDocument();
    expect(
      defined(api.posts(/audit\/loads$/).at(-1), "api.posts(/audit\\/loads$/).at(-1)").body
        .provider,
    ).toBeUndefined();
  });

  it("offers no provider selector when the record store applies every action", async () => {
    renderPart(<AuditView module="catalog" />);
    await screen.findByTestId("committed-only");
    expect(screen.queryByLabelText("Provider")).toBeNull();
  });
});

describe("Changes in the address (CONTRACT-010 D)", () => {
  const open = (query: string) => {
    window.location.hash = `#/operate/catalog/changes${query}`;
    return renderConsole({ hashRouting: true, hashPrefix: "operate" });
  };
  const depth = () => window.history.length;
  // The page reads: the console also asks once, with a limit of 1, whether the module has a journal.
  const listed = () => calls().filter((c) => c.body.limit === 50);
  beforeEach(() => {
    api.on((r) => (changes(r) && r.body.limit !== 1 ? page([change()]) : undefined));
  });

  it("restores the action and the time range from a fresh render", async () => {
    open("?action=catalog.CorrectSolution&since=2026-01-01T00:00:00Z&until=2026-02-01T00:00:00Z");
    await screen.findAllByTestId("change-row");
    const body = defined(listed().at(-1), "listed().at(-1)").body;
    expect(body.action).toBe("catalog.CorrectSolution");
    expect(body.since).toBe("2026-01-01T00:00:00Z");
    expect(body.until).toBe("2026-02-01T00:00:00Z");
    expect(screen.getByLabelText("Action")).toHaveValue("catalog.CorrectSolution");
    expect(screen.getByLabelText("Since")).not.toHaveValue("");
    expect(screen.getByLabelText("Until")).not.toHaveValue("");
  });

  it("restores the import loads view", async () => {
    api.on((r) => (r.path.endsWith("/audit/loads") ? page([wire.load()]) : undefined));
    open("?action=catalog.CorrectSolution&since=2026-01-01T00:00:00Z&view=loads");
    await screen.findByTestId("loads");
    expect(screen.getByRole("tab", { name: "Import loads", selected: true })).toBeInTheDocument();
    expect(api.posts(/audit\/loads$/)).not.toHaveLength(0);
  });

  it("restores an entity's history", async () => {
    open("/catalog.Solution/sol-1");
    await screen.findByTestId("history-chip");
    expect(calls().some((c) => c.body.type === "catalog.Solution" && c.body.key === "sol-1")).toBe(
      true,
    );
  });

  it("a submitted form pushes its filters, and the person typed is not in the address", async () => {
    const user = userEvent.setup();
    open("");
    await screen.findAllByTestId("change-row");
    const start = depth();
    await user.type(screen.getByLabelText("Person"), "ana");
    await user.selectOptions(screen.getByLabelText("Action"), "catalog.CorrectSolution");
    expect(window.location.hash).toBe("#/operate/catalog/changes");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(window.location.hash).toBe("#/operate/catalog/changes?action=catalog.CorrectSolution"),
    );
    expect(depth()).toBe(start + 1);
    expect(window.location.hash).not.toContain("ana");
    expect(defined(listed().at(-1), "listed().at(-1)").body.by).toBe("ana");
  });

  it("a date being typed replaces the entry; the person is kept in memory across a push", async () => {
    const user = userEvent.setup();
    open("?action=catalog.CorrectSolution");
    await screen.findAllByTestId("change-row");
    await user.type(screen.getByLabelText("Person"), "ana");
    const start = depth();
    fireEvent.change(screen.getByLabelText("Since"), { target: { value: "2026-10-09T00:00" } });
    await waitFor(() => expect(window.location.hash).toContain("since="));
    expect(depth()).toBe(start);
    expect(window.location.hash).toContain("action=catalog.CorrectSolution");
    await user.click(screen.getByRole("tab", { name: "Import loads" }));
    await waitFor(() => expect(window.location.hash).toBe("#/operate/catalog/changes?view=loads"));
    expect(depth()).toBe(start + 1);
    await user.click(
      within(screen.getByRole("tablist", { name: "Changes views" })).getByRole("tab", {
        name: "Changes",
      }),
    );
    expect(screen.getByLabelText("Person")).toHaveValue("ana");
  });

  it("Back restores the filters of the page before", async () => {
    const user = userEvent.setup();
    open("");
    await screen.findAllByTestId("change-row");
    await user.selectOptions(screen.getByLabelText("Action"), "catalog.CorrectSolution");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(window.location.hash).toContain("action="));
    act(() => window.history.back());
    await waitFor(() => expect(window.location.hash).toBe("#/operate/catalog/changes"));
    await waitFor(() => expect(screen.getByLabelText("Action")).toHaveValue(""));
  });
});

describe("View in Explore on Changes rows (FR-71)", () => {
  const toExplore = crossLinks({
    hash: true,
    openOperate: () => {},
    openExplore: () => {},
  }).toExplore;
  const rows = () => {
    api.on((r) => (changes(r) ? page([change()]) : undefined));
  };

  it("each changed entity that still exists links to its Explore page, for an operator", async () => {
    rows();
    renderPart(
      <NavProvider go={() => {}} auditShown toExplore={toExplore}>
        <AuditView module="catalog" />
      </NavProvider>,
    );
    const row = await screen.findByTestId("change-row");
    expect(within(row).getByRole("link", { name: /View in Explore/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/Solution/sol-1",
    );
  });

  it("draws no link without the shell's primitive", async () => {
    rows();
    renderPart(<AuditView module="catalog" />);
    const row = await screen.findByTestId("change-row");
    expect(within(row).queryByText(/Explore/)).toBeNull();
  });
});
