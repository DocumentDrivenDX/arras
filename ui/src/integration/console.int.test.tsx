// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SUPPORTED_OPERATE_VERSION } from "../api/types";
import { ActionForm } from "../areas/ActionForm";
import { AuditView } from "../areas/AuditView";
import { EntityTable } from "../areas/EntityTable";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import {
  asBob,
  call,
  client,
  control,
  gql,
  renderLive,
  renderLiveConsole,
  server,
  withDevHost,
} from "./harness";

// The console shell, the schema and every refusal, against the real dev host.
withDevHost();
afterEach(() => {
  window.location.hash = "";
});

describe("version gate and schema (US-060)", () => {
  it("checks GET /version first and renders the modules the server reports", async () => {
    const v = await call<{ contracts: { operate: string } }>("/api/operate/version");
    expect(v.body.contracts.operate).toBe(SUPPORTED_OPERATE_VERSION);
    const spy = vi.spyOn(globalThis, "fetch");
    renderLiveConsole("alice");
    const rail = await screen.findByRole("navigation", { name: "Modules" });
    expect(within(rail).getByRole("button", { name: /catalog/ })).toHaveTextContent("memory");
    expect(screen.getByTitle("contract versions")).toHaveTextContent(
      `operate v${SUPPORTED_OPERATE_VERSION}`,
    );
    const urls = spy.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toBe(`${server().base}/api/operate/version`);
    spy.mockRestore();
  });

  it("shows the real module's types, relationships, actions and revision", async () => {
    const user = userEvent.setup();
    renderLive(<SchemaBrowser module="catalog" />);
    const type = await screen.findByTestId("type-catalog.Solution");
    expect(type).toHaveTextContent("coverageLevel");
    expect(screen.getByTestId("rel-addresses")).toHaveTextContent("addressedBy");
    expect(screen.getByText(/revision:/)).toHaveTextContent('{"memory":1}');
    const decl = screen.getByTestId("action-decl-catalog.AddSolution");
    await user.click(within(decl).getByText("catalog.AddSolution"));
    expect(decl).toHaveTextContent("no such use case");
    expect(screen.getAllByTestId("diagram-node")).toHaveLength(2);
  });
});

describe("refusals as the server answers them (US-064)", () => {
  // The sandbox's operators are alice, bob and root; carol and dave are not (CONTRACT-010), so these
  // read-only and no-journal operators are bob with part of his access revoked for the test.
  it("an operator who can read but not write: the provider's refusal and its reason, controls disabled", async () => {
    const user = userEvent.setup();
    await asBob(["read"], async () => {
      renderLive(<EntityTable module="catalog" type="catalog.Solution" />, "bob");
      expect(await screen.findByText("sol-1")).toBeInTheDocument();
      renderLive(
        <ActionForm
          module="catalog"
          action="catalog.CorrectSolution"
          prefill={{ solution: "sol-1", level: "full" }}
        />,
        "bob",
      );
      await user.click(await screen.findByTestId("validate"));
      const alert = await screen.findByText(/The provider refused you/);
      expect(alert).toHaveTextContent("no_access");
      expect(screen.queryByTestId("confirm")).toBeNull();
      expect(screen.getByLabelText(/^level/)).toBeDisabled();
    });
  });

  it("an operator who cannot read the journal or the loads: no access, not a sign-in", async () => {
    const user = userEvent.setup();
    const onUnauthorized = vi.fn();
    await asBob(["read", "write"], async () => {
      renderLive(<AuditView module="catalog" />, "bob", { onUnauthorized });
      expect(await screen.findByRole("alert")).toHaveTextContent("No access");
      await user.click(screen.getByRole("tab", { name: "Import loads" }));
      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(
          "You do not have access to this (no_access)",
        ),
      );
      expect(onUnauthorized).not.toHaveBeenCalled();
    });
  });

  it("dave has no access: no modules, and a deep link answers not found", async () => {
    window.location.hash = "#/catalog/entities/catalog.Solution";
    renderLiveConsole("dave", { hashRouting: true });
    expect(await screen.findByTestId("no-modules")).toHaveTextContent(
      "No modules are readable by you",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Not found");
    expect(screen.queryByText("sol-1")).toBeNull();
    // The server answers dave's direct read of the module as it would an unknown module.
    const e = await client("dave")
      .moduleQuery("catalog", "{ solutionList { items { key } } }")
      .catch((x: unknown) => x);
    expect(e).toMatchObject({ kind: "not_found", status: 404 });
    const unknown = await client("alice")
      .moduleQuery("no-such-module", "{ solutionList { items { key } } }")
      .catch((x: unknown) => x);
    expect(unknown).toMatchObject({
      kind: "not_found",
      status: 404,
      message: (e as Error).message,
    });
  });

  it("a person the host does not know is asked to sign in", async () => {
    const onUnauthorized = vi.fn();
    renderLiveConsole("nobody", { onUnauthorized });
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in again");
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("an expired token (control endpoint): the console says sign in again and calls onUnauthorized", async () => {
    await control({ op: "expire", user: "bob" });
    try {
      const onUnauthorized = vi.fn();
      const view = renderLiveConsole("bob", { onUnauthorized });
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Sign in again");
      expect(alert).not.toHaveTextContent("Not found");
      expect(alert).not.toHaveTextContent("No access");
      expect(onUnauthorized).toHaveBeenCalled();
      view.unmount();

      // The operator surface and a module read say the same.
      const c = client("bob", onUnauthorized);
      await expect(
        c.validate("catalog", "catalog.CorrectSolution", { inputs: {} }),
      ).rejects.toMatchObject({ kind: "sign_in", status: 401 });
      await expect(c.changes({ module: "catalog" })).rejects.toMatchObject({
        kind: "sign_in",
        reason: "token_expired",
      });
      await expect(c.meta()).rejects.toMatchObject({ kind: "sign_in", reason: "token_expired" });
      // The real answer on the module path; 404 here (an expired token read as "no such module") was a server bug.
      await expect(
        c.moduleQuery("catalog", "{ solutionList { items { key } } }"),
      ).rejects.toMatchObject({ kind: "sign_in" });
    } finally {
      await control({ op: "restore", user: "bob" });
    }
    await expect(client("bob").meta()).resolves.toMatchObject({ modules: [{ name: "catalog" }] });
  });

  it("an expired token on GraphQL answers with the reason, as a 401 or a 200 (both are a sign-in)", async () => {
    await control({ op: "expire", user: "bob" });
    try {
      const r = await gql<{ errors: { extensions: unknown }[] }>(
        "{ modules { name } }",
        undefined,
        "bob",
      );
      expect([200, 401]).toContain(r.status);
      expect(r.body.errors[0]?.extensions).toMatchObject({
        code: "REFUSED",
        reason: "token_expired",
      });
    } finally {
      await control({ op: "restore", user: "bob" });
    }
  });
});

describe("a backend outage (control endpoint) and recovery", () => {
  it("the Unavailable state names the backend; mending it makes the same screens work again", async () => {
    const user = userEvent.setup();
    await control({ op: "outage", backend: "memory", reason: "unreachable" });
    try {
      renderLive(<EntityTable module="catalog" type="catalog.Solution" />);
      const notice = (await screen.findByText("UNAVAILABLE")).closest("[role=alert]");
      expect(notice).toHaveTextContent("memory unavailable (unreachable)");
      expect(notice).toHaveTextContent(
        "The table stays usable; try the other consistency or retry.",
      );
      // BULK reads the replica, which still answers, and says it is not current.
      await user.click(screen.getByRole("button", { name: "BULK" }));
      expect(await screen.findByText("sol-1")).toBeInTheDocument();
      const fresh = screen.getByTestId("freshness");
      expect(fresh).toHaveTextContent("replica: memory_replica");
      await waitFor(() => expect(fresh).toHaveTextContent("memory unavailable"));
      expect(fresh).toHaveTextContent("not current");

      renderLive(
        <ActionForm
          module="catalog"
          action="catalog.CorrectSolution"
          prefill={{ solution: "sol-1", level: "full" }}
        />,
      );
      await user.click(await screen.findByTestId("validate"));
      const alert = await screen.findByText("Backend unavailable");
      expect(alert.closest("[role=alert]")).toHaveTextContent(
        "memory is unavailable (unreachable).",
      );
    } finally {
      await control({ op: "outage", backend: "memory", reason: null });
    }
    await user.click(screen.getByTestId("validate"));
    await waitFor(() => expect(screen.getByTestId("confirm")).toBeEnabled());
    // Back on LATEST the record store answers again (the table's Retry is exercised in e2e/flows.spec.ts).
    await user.click(screen.getByRole("button", { name: "LATEST" }));
    await waitFor(() => expect(screen.queryByText("UNAVAILABLE")).toBeNull());
    await waitFor(() =>
      expect(screen.getByTestId("freshness")).toHaveTextContent("record: memory"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("freshness")).not.toHaveTextContent("memory unavailable"),
    );
  });

  it("a memory_replica outage leaves the record store's reads and writes working", async () => {
    await control({ op: "outage", backend: "memory_replica", reason: "migration_failed" });
    try {
      const st = await client("alice").status();
      expect(st.find((s) => s.backend === "memory_replica")).toMatchObject({
        available: false,
        reason: "migration_failed",
      });
      renderLive(<EntityTable module="catalog" type="catalog.Solution" />);
      expect(await screen.findByText("sol-1")).toBeInTheDocument();
      expect(screen.getByTestId("freshness")).toHaveTextContent("record: memory");
    } finally {
      await control({ op: "outage", backend: "memory_replica", reason: null });
    }
  });
});
