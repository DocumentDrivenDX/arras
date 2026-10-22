// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DevHost } from "../dev/DevHost";
import { control, headersFor, server, withDevHost } from "./harness";
import { registered } from "./umf";

// The sandbox toolbar (OPR-15) in the standalone host's page, against the real dev host: roles and made-up
// names are minted by the server, the console runs as that person, and the controls break and mend it.
withDevHost();
afterEach(() => {
  window.location.hash = "";
});

async function page() {
  const u = userEvent.setup();
  render(
    <DevHost
      apiBase={server().base}
      defaultMode="admin"
      extraHeaders={() => ({ origin: server().base })}
    />,
  );
  await screen.findByLabelText("Person");
  return u;
}
async function asCustom(u: Awaited<ReturnType<typeof page>>, name: string, role: string) {
  await u.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
  await u.clear(screen.getByLabelText("Name"));
  await u.type(screen.getByLabelText("Name"), name);
  await u.selectOptions(screen.getByLabelText("Role"), role);
  await u.click(screen.getByRole("button", { name: "Use" }));
}

describe("the toolbar against the dev host", () => {
  it("offers the server's fixed people and roles, and starts as the default person", async () => {
    await page();
    const people = await (await fetch(`${server().base}/api/people`)).json();
    const select = screen.getByLabelText("Person");
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual([...people.people, "Custom name and role…"]);
    expect(select).toHaveValue(people.default);
    expect(screen.getByText("dev host: no sign-in")).toBeInTheDocument();
    expect(await screen.findByRole("navigation", { name: "Modules" })).toHaveTextContent("catalog");
  });

  it("role viewer with a made-up name: the console runs as that person, who is refused every write", async () => {
    const u = await page();
    await asCustom(u, "zed", "viewer");
    // reads: the module is shown
    expect(await screen.findByRole("navigation", { name: "Modules" })).toHaveTextContent("catalog");
    // writes: the provider's refusal, with its reason
    await u.click(await screen.findByRole("tab", { name: "Actions" }));
    await u.click(await screen.findByRole("button", { name: /CorrectSolution/ }));
    await u.type(await screen.findByLabelText(/^solution/), "sol-1");
    await u.type(screen.getByLabelText(/^level/), "x");
    await u.tab();
    expect(await screen.findByText(/The provider refused you/)).toHaveTextContent("no_access");
    // import is refused by the backend too
    await u.click(screen.getByRole("tab", { name: "Model" }));
    await u.click(await screen.findByRole("button", { name: "Import" }));
    // a document that parses, so it is the grant that decides (an unparsable one is a 400 first)
    await u.upload(
      screen.getByLabelText("UMF document"),
      new File([await registered("alice")], "catalog.umf.json"),
    );
    await u.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByTestId("schema-refused")).toHaveTextContent("no_access");
  });

  it("role schema author with a made-up name sees the Import view and is not refused a plan", async () => {
    const u = await page();
    await asCustom(u, "ana", "schema author");
    await u.click(await screen.findByRole("button", { name: "Import" }));
    await u.upload(screen.getByLabelText("UMF document"), new File(["not json"], "x.json"));
    await u.click(screen.getByRole("button", { name: "Validate" }));
    // refused as a document, not as a person: the grant is held
    expect(await screen.findByTestId("schema-invalid")).toBeInTheDocument();
    expect(screen.queryByTestId("schema-refused")).toBeNull();
  });

  it("role none shows no module, as for a person with no access (US-076-AC3)", async () => {
    const u = await page();
    await asCustom(u, "nil", "none");
    expect(await screen.findByTestId("no-modules")).toHaveTextContent(
      "No modules are readable by you",
    );
  });

  it("an invalid name or the administrator's name is rejected in the browser: no request is made", async () => {
    const u = await page();
    await u.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    await screen.findByRole("navigation", { name: "Modules" });
    const spy = vi.spyOn(globalThis, "fetch");
    for (const bad of ["Zed", "1zed", "z z", "x".repeat(33), "root", "alice"]) {
      await u.clear(screen.getByLabelText("Name"));
      await u.type(screen.getByLabelText("Name"), bad);
      await u.click(screen.getByRole("button", { name: "Use" }));
      expect(await screen.findByRole("alert")).toBeInTheDocument();
    }
    // Reads of the console already open may still be settling; none is for another person, and no control or people call is made.
    const sent = spy.mock.calls.map((c) => ({
      url: String(c[0]),
      user: new Headers(c[1]?.headers).get("x-arras-user"),
    }));
    expect(sent.filter((c) => c.user !== "alice")).toEqual([]);
    expect(sent.filter((c) => /\/api\/(dev|people)/.test(c.url))).toEqual([]);
    spy.mockRestore();
  });

  it("the administrator as a fixed person is shown refused by the console", async () => {
    const u = await page();
    await u.selectOptions(screen.getByLabelText("Person"), "root");
    // root registers modules and is refused every user operation: no access, with the reason
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No access");
    expect(alert).toHaveTextContent("no_access");
    expect(screen.queryByRole("navigation", { name: "Modules" })).toBeNull();
  });

  it("a backend outage is shown and mended from the toolbar", async () => {
    const u = await page();
    await screen.findByRole("navigation", { name: "Modules" });
    await u.click(screen.getByText("Sandbox"));
    try {
      await u.click(await screen.findByRole("button", { name: "Outage memory" }));
      expect(await screen.findByText("unavailable (unreachable)")).toBeInTheDocument();
      await u.click(screen.getByRole("button", { name: "Mend memory" }));
      expect(await screen.findAllByText("available")).not.toHaveLength(0);
      await waitFor(() => expect(screen.queryByText("unavailable (unreachable)")).toBeNull());
    } finally {
      await control({ op: "outage", backend: "memory", reason: null });
    }
  });

  it("expiring the viewed person's token shows a sign-in; restoring it brings the console back", async () => {
    const u = await page();
    await asCustom(u, "kai", "viewer");
    await screen.findByRole("navigation", { name: "Modules" });
    await u.click(screen.getByText("Sandbox"));
    try {
      await u.click(screen.getByRole("button", { name: "Expire token" }));
      expect((await screen.findAllByText("Sign in again")).length).toBeGreaterThan(0);
      await u.click(screen.getByRole("button", { name: "Restore token" }));
      expect(await screen.findByRole("navigation", { name: "Modules" })).toHaveTextContent(
        "catalog",
      );
    } finally {
      await control({ op: "restore", user: "kai" });
    }
  });

  it("runs the replica's feed", async () => {
    const u = await page();
    await u.click(await screen.findByText("Sandbox"));
    await u.click(screen.getByRole("button", { name: "Run the replica's feed" }));
    await waitFor(() =>
      expect(screen.getByTestId("sandbox-note")).toHaveTextContent("The replica's feed ran."),
    );
  });

  it("headersFor sends a role only for a made-up person", () => {
    expect(headersFor("alice")).not.toHaveProperty("x-arras-role");
    expect(headersFor({ name: "ana", role: "viewer" })).toMatchObject({
      "x-arras-user": "ana",
      "x-arras-role": "viewer",
    });
  });
});
