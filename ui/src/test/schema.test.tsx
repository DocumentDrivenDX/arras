// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createClient } from "../api/client";
import { ApiError } from "../api/errors";
import type { ModuleInfo } from "../api/types";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { defined } from "./defined";
import { catalog, err, type FakeApi, json, stage, wire } from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
});

function sixTypes(): ModuleInfo {
  const base = catalog();
  const names = ["Ticket", "Customer", "Party", "Document", "Task", "Note"];
  const proto = defined(base.entityTypes[0], "base.entityTypes[0]");
  return {
    ...base,
    entityTypes: names.map((n) => ({ ...proto, name: `catalog.${n}` })),
    relationships: [
      ["has", "Ticket", "Customer", "1", "0..*"],
      ["involves", "Ticket", "Party", "0..*", "0..*"],
      ["holds", "Ticket", "Document", "1", "0..*"],
      ["owes", "Task", "Ticket", "0..*", "1"],
      ["annotates", "Note", "Document", "0..*", "0..1"],
    ].map(([name, s, t, sm, tm]) => ({
      name: defined(name, "name"),
      source: [`catalog.${s}`],
      target: [`catalog.${t}`],
      sourceMultiplicity: defined(sm, "sm"),
      targetMultiplicity: defined(tm, "tm"),
      lifecycle: "independent",
      inverse: null,
    })),
    actions: [],
  };
}

describe("Schema (US-060)", () => {
  it("US-060-AC1: only the modules the principal may read appear in the list", async () => {
    // The server's `modules` answers only readable modules; a second module the viewer cannot read is absent.
    api.modules = [catalog()];
    renderConsole();
    const rail = await screen.findByRole("navigation", { name: "Modules" });
    expect(within(rail).getAllByRole("button")).toHaveLength(1);
    expect(within(rail).getByRole("button", { name: /catalog/ })).toBeInTheDocument();
    expect(within(rail).queryByText("secret")).toBeNull();
  });

  it("US-060-AC2: a module shows each type's properties, relationships and capabilities, and each action's typed inputs", async () => {
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    const type = await screen.findByTestId("type-catalog.Solution");
    expect(within(type).getByText("coverageLevel")).toBeInTheDocument();
    expect(within(type).getAllByText(/filter columns:/).length).toBe(2);
    expect(within(type).getAllByText("mutable").length).toBeGreaterThan(0);
    const rel = screen.getByTestId("rel-addresses");
    expect(rel).toHaveTextContent("0..* → 0..*");
    expect(rel).toHaveTextContent("addressedBy");
    // Placement and revision.
    expect(screen.getByText(/record: memory/)).toBeInTheDocument();
    expect(screen.getByText(/revision:/)).toHaveTextContent('{"memory":1}');
    // An action's typed inputs, preconditions and effects.
    const decl = screen.getByTestId("action-decl-catalog.CorrectSolution");
    await user.click(within(decl).getByText("catalog.CorrectSolution"));
    expect(decl).toHaveTextContent("solution");
    expect(decl).toHaveTextContent("ref");
    expect(decl).toHaveTextContent("no such solution");
    expect(decl).toHaveTextContent("update Solution");
  });

  it("US-060-AC3: the diagram draws every relationship of a six-type module with its multiplicities", async () => {
    api.modules = [sixTypes()];
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    // The compact diagram is open beside the relationship list.
    expect(screen.getByRole("button", { name: "Diagram" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("diagram-node")).toHaveLength(6);
    const edges = screen.getAllByTestId("diagram-edge");
    expect(edges).toHaveLength(5);
    expect(edges[0]).toHaveTextContent("has");
    expect(edges[0]).toHaveTextContent("1 → 0..*");
    expect(edges[4]).toHaveTextContent("0..* → 0..1");
  });

  it("the diagram collapses to leave the relationship list alone", async () => {
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    expect(screen.getAllByTestId("diagram-node").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Diagram" }));
    expect(screen.queryAllByTestId("diagram-node")).toHaveLength(0);
    expect(screen.getByTestId("rel-addresses")).toBeInTheDocument();
  });

  it("US-060-AC3: a relationship end in another module is drawn by name only", async () => {
    const m = catalog();
    defined(m.relationships[0], "m.relationships[0]").target = ["billing.Invoice"];
    api.modules = [m];
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    const nodes = screen.getAllByTestId("diagram-node");
    expect(
      nodes.some(
        (n) => n.textContent?.includes("Invoice") && n.textContent.includes("module billing"),
      ),
    ).toBe(true);
  });

  it("US-060-AC4: a module the viewer cannot read shows the same not-found answer as an unknown module", async () => {
    // The server knows `hidden` but this viewer may not read it: the meta query leaves it out and a
    // read of it answers 404 NOT_FOUND, exactly as for a module that does not exist (CONTRACT-006).
    api.on((r) => (r.path.endsWith("/graphql/hidden") ? json(404, wire.gqlNotFound()) : undefined));
    const client = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    const hidden = await client
      .moduleQuery("hidden", "{ thingList { items { key } } }")
      .catch((e: unknown) => e);
    const unknown = await client
      .moduleQuery("does-not-exist", "{ thingList { items { key } } }")
      .catch((e: unknown) => e);
    expect(hidden).toBeInstanceOf(ApiError);
    expect((hidden as ApiError).kind).toBe("not_found");
    expect((unknown as ApiError).kind).toBe("not_found");
    expect((hidden as ApiError).message).toBe((unknown as ApiError).message);

    window.location.hash = "#/hidden/graph";
    const a = renderConsole({ hashRouting: true });
    const first = await screen.findByRole("alert");
    expect(first).toHaveTextContent("Not found");
    expect(first).toHaveTextContent("There is nothing at this address, or you cannot read it.");
    // The rail lists only what the viewer may read, and the hidden module's name is nowhere but the route.
    expect(
      within(screen.getByRole("navigation", { name: "Modules" })).queryByText("hidden"),
    ).toBeNull();
    const text = first.textContent;
    a.unmount();
    window.location.hash = "#/does-not-exist/graph";
    renderConsole({ hashRouting: true });
    expect((await screen.findByRole("alert")).textContent).toBe(text);
  });

  it("US-060 edge: the schema page shows the revision at load and offers a refresh", async () => {
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    const before = api.posts(/\/graphql$/).length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(api.posts(/\/graphql$/).length).toBeGreaterThan(before));
  });
});

describe("Version, sign-in and refusals (ADR-021, CONTRACT-009)", () => {
  it("a contract version mismatch blocks rendering and names both versions", async () => {
    api.versions = { interface: 2, actions: 1, console: 2, operate: 3 };
    renderConsole();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("operate contract version 2");
    expect(alert).toHaveTextContent("server reports 3");
    // Nothing else was read: no GraphQL request was made.
    expect(api.posts(/graphql/)).toHaveLength(0);
    expect(screen.queryByRole("navigation", { name: "Modules" })).toBeNull();
  });

  it("a 401 calls onUnauthorized and shows a sign-in-again state", async () => {
    const onUnauthorized = vi.fn();
    api.on((r) => (r.path.endsWith("/graphql") ? json(401, wire.gqlSignIn()) : undefined));
    renderConsole({ onUnauthorized });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sign in again");
    expect(alert).toHaveTextContent("token_expired");
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("a 403 shows a no-access state with the reason", async () => {
    api.on((r) => (r.path.endsWith("/graphql") ? err(403, wire.refused()) : undefined));
    renderConsole();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No access");
    expect(alert).toHaveTextContent("no_access");
  });

  it("a 404 shows not found", async () => {
    api.on((r) => (r.path.endsWith("/graphql") ? json(404, wire.gqlNotFound()) : undefined));
    renderConsole();
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found");
  });

  it("sends the host's headers on every request and puts nothing in the URL or browser storage", async () => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    renderConsole({ getHeaders: () => ({ authorization: "Bearer host-owned" }) });
    await screen.findByRole("navigation", { name: "Modules" });
    expect(api.log.length).toBeGreaterThan(1);
    expect(api.log.every((r) => r.headers.authorization === "Bearer host-owned")).toBe(true);
    expect(api.log.every((r) => !r.url.includes("?"))).toBe(true);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });
});

describe("Schema: the selected type and the view, held by the route", () => {
  it("marks the type the route selects, and reports a choice or a second click on it", async () => {
    const user = userEvent.setup();
    const chosen: (string | undefined)[] = [];
    renderPart(
      <SchemaBrowser
        module="catalog"
        selectedType="catalog.Solution"
        onSelectType={(t) => chosen.push(t)}
      />,
    );
    await screen.findByTestId("schema");
    expect(screen.getByTestId("type-catalog.Solution")).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("type-catalog.UseCase")).not.toHaveAttribute("aria-current");
    await user.click(screen.getByRole("button", { name: "Select catalog.UseCase" }));
    await user.click(screen.getByRole("button", { name: "Select catalog.Solution" }));
    expect(chosen).toEqual(["catalog.UseCase", undefined]);
  });

  it("offers no choice of a type when nothing takes it", async () => {
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    expect(screen.queryByRole("button", { name: /^Select catalog\./ })).toBeNull();
  });

  it("with onView, the UMF source is the route's: opening and leaving it are reported, not kept", async () => {
    const user = userEvent.setup();
    const views: boolean[] = [];
    renderPart(<SchemaBrowser module="catalog" umf={false} onView={(v) => views.push(v)} />);
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    expect(views).toEqual([true]);
    // the route has not changed, so the page still shows the registry
    expect(screen.getByRole("button", { name: "Live registry" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
