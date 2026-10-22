// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "../api/context";
import { ArrasApp, type ArrasAppProps } from "../shell";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { qc } from "./render";

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  fake = stageBrowser();
  fake.mods = fake.mods.slice(0, 1); // one module: the entry opens at once
});
afterEach(() => {
  window.location.hash = "";
});

const app = (props: ArrasAppProps = {}) => render(<ArrasApp queryClient={qc()} {...props} />);
const mode = (name: "Explore" | "Operate") => screen.getByRole("button", { name });

describe("the shell: one interface, two modes (US-072)", () => {
  it("US-072-AC1: an operator opens in Explore with Explore pressed and Operate not", async () => {
    app();
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await waitFor(() => expect(screen.getByRole("group", { name: "Mode" })).toBeInTheDocument());
    expect(mode("Explore")).toHaveAttribute("aria-pressed", "true");
    expect(mode("Operate")).toHaveAttribute("aria-pressed", "false");
  });

  it("US-072-AC2: pressing Operate opens the Operator Console, the prefix becomes operate, and the module and type carry over to Data", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.Solution/sol-1");
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Entities" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    expect(mode("Operate")).toHaveAttribute("aria-pressed", "true");
    expect(mode("Explore")).toHaveAttribute("aria-pressed", "false");
  });

  it("US-072-AC3: pressing Explore in Operate shows the Explore page she last left", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    await user.click(mode("Explore"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("US-072-AC4: for a viewer who is not an operator nothing refers to Operate and the operate surface is called for nothing but /viewer", async () => {
    fake.viewerModes = ["user"];
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    const { container } = app();
    await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    await waitFor(() => expect(fake.requests.some((r) => r.path.endsWith("/viewer"))).toBe(true));
    expect(screen.queryByRole("group", { name: "Mode" })).toBeNull();
    expect(screen.queryByRole("button", { name: /operate|explore/i })).toBeNull();
    expect(container.innerHTML).not.toMatch(/operate/i);
    expect(container.querySelector('[href*="operate"]')).toBeNull();
    const operate = fake.requests.filter((r) => r.path.includes("/api/operate"));
    expect(operate.map((r) => `${r.method} ${r.path}`)).toEqual(["GET /api/operate/viewer"]);
  });

  it("US-072-AC4: a viewer that cannot be asked (the answer fails) is never assumed to be an operator", async () => {
    fake.viewerModes = "fail";
    const { container } = app();
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await waitFor(() => expect(fake.requests.some((r) => r.path.endsWith("/viewer"))).toBe(true));
    await act(async () => undefined);
    expect(screen.queryByRole("group", { name: "Mode" })).toBeNull();
    expect(container.innerHTML).not.toMatch(/operate/i);
  });

  it("US-072-AC6: an Operate location opened by a non-operator shows the Explore entry", async () => {
    fake.viewerModes = ["user"];
    window.location.hash = "#/operate/catalog/entities/catalog.UseCase";
    app();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("console-header")).toBeNull();
    // and the console's earlier fragment form is the Explore entry for the same viewer
    window.location.hash = "#/catalog/model";
    await act(async () => undefined);
    expect(screen.getByRole("heading", { level: 1, name: "Product catalog" })).toBeInTheDocument();
  });

  it("US-072-AC6: while the viewer is not yet known an Operate or alias route shows a skeleton and makes no browser read", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    fake.viewerModes = ["user"];
    fake.api.on((r) =>
      r.method === "GET" && r.path.endsWith("/viewer")
        ? gate.then(() => ({ status: 200, body: { user: "carol", modes: ["user"] } }))
        : undefined,
    );
    window.location.hash = "#/operate/catalog/entities/catalog.UseCase";
    app();
    expect(await screen.findByRole("status")).toHaveAttribute("aria-busy", "true");
    await act(async () => new Promise((r) => setTimeout(r, 30)));
    expect(fake.requests.filter((r) => r.path.includes("/api/console"))).toEqual([]);
    expect(screen.queryByTestId("gb")).toBeNull();
    release();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
  });

  it("#/admin and #/browse are aliases: opened, they show the same mode and are replaced by #/operate and #/explore, not pushed", async () => {
    window.location.hash = "#/admin/catalog/entities/catalog.UseCase";
    const before = window.history.length;
    const first = app();
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    await waitFor(() =>
      expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase"),
    );
    expect(window.history.length).toBe(before);
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Entities" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    first.unmount();
    window.location.hash = "#/browse/catalog/Solution/sol-1";
    const second = app();
    expect(await screen.findByRole("button", { name: "Operate" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1"));
    expect(await screen.findByTestId("gb")).toBeInTheDocument();
    second.unmount();
  });

  it("the console's earlier fragment form is an Operate route for an operator and is rewritten with the prefix", async () => {
    window.location.hash = "#/catalog/entities/catalog.UseCase";
    app();
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    await waitFor(() =>
      expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase"),
    );
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Entities" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
  });

  it("a legacy-alias fragment with no type becomes one address: the console's default-type replace is not undone by the shell's rewrite, and adds no entry", async () => {
    // The shell and the console each rewrite the address in place. With what the console needs already cached
    // it opens in the same commit the shell learns the viewer is an operator, so both rewrites run together.
    const client = qc();
    window.location.hash = "#/operate/catalog/entities/catalog.UseCase";
    const warm = render(<ArrasApp queryClient={client} />);
    await screen.findByTestId("console-header");
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Entities" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    warm.unmount();
    window.location.hash = "#/catalog/entities";
    const before = window.history.length;
    // Every write to the address, in order: the invariant is on the sequence, not on where it happens to end,
    // because the console re-applies its default type when the address loses it, which hides the bad order.
    const writes: string[] = [];
    const real = window.history.replaceState.bind(window.history);
    const replace = vi.spyOn(window.history, "replaceState").mockImplementation((...a) => {
      if (a[2] !== undefined && a[2] !== null) writes.push(String(a[2]));
      return real(...a);
    });
    const push = vi.spyOn(window.history, "pushState");
    let pushes = -1;
    try {
      render(<ArrasApp queryClient={client} />);
      await screen.findByTestId("console-header");
      await waitFor(() =>
        expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase"),
      );
      await new Promise((r) => setTimeout(r, 50));
    } finally {
      pushes = push.mock.calls.length;
      replace.mockRestore();
      push.mockRestore();
    }
    const typed = writes.indexOf("#/operate/catalog/entities/catalog.UseCase");
    expect(typed).toBeGreaterThanOrEqual(0);
    // Once the type is in the address nothing writes the address without it again.
    expect(writes.slice(typed)).toEqual(
      writes.slice(typed).map(() => "#/operate/catalog/entities/catalog.UseCase"),
    );
    expect(pushes).toBe(0);
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase");
    expect(window.history.length).toBe(before);
  });

  it("an operator with defaultMode admin and no fragment opens in Operate; an Explore fragment still says Explore", async () => {
    const { unmount } = app({ defaultMode: "admin" });
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    unmount();
    window.history.replaceState(null, "", "/");
    window.location.hash = "#/explore/catalog";
    app({ defaultMode: "admin" });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
  });

  it("US-072-AC8: both options are reachable with Tab and activated with Enter or Space, the state in aria-pressed", async () => {
    const user = userEvent.setup();
    app();
    await screen.findByRole("group", { name: "Mode" });
    mode("Explore").focus();
    await user.tab();
    expect(mode("Operate")).toHaveFocus();
    await user.keyboard("{Enter}");
    await screen.findByTestId("console-header");
    expect(mode("Operate")).toHaveAttribute("aria-pressed", "true");
    mode("Explore").focus();
    await user.keyboard(" ");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
    expect(mode("Explore")).toHaveAttribute("aria-pressed", "true");
  });

  it("a host that owns the location keeps an earlier-mode fragment of its own as it is", async () => {
    for (const own of ["#/admin/host-page", "#/browse/host-page"]) {
      window.location.hash = own;
      const { unmount } = app({ location: { module: "catalog" } });
      await screen.findByRole("heading", { level: 1, name: "Product catalog" });
      expect(window.location.hash).toBe(own);
      unmount();
    }
  });

  it("a host that owns the location keeps the mode in memory and never writes the URL", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/host-owned";
    app({ location: { module: "catalog" } });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    expect(await screen.findByTestId("console-header")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/host-owned");
    await user.click(mode("Explore"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
  });

  it("the switch sits in the top bar before the host's toolbar, and in Operate in the console's header", async () => {
    const user = userEvent.setup();
    app({ toolbar: <span>picker</span> });
    const top = (await screen.findByRole("banner")) as HTMLElement;
    expect(within(top).getByText("picker")).toBeInTheDocument();
    const html = top.innerHTML;
    expect(html.indexOf("Explore")).toBeLessThan(html.indexOf("picker"));
    await user.click(mode("Operate"));
    await screen.findByTestId("console-header");
    expect(within(screen.getByRole("banner")).getByText("picker")).toBeInTheDocument();
  });
});

describe("the shell carries what is open across the switch, both ways", () => {
  const sol1 = "Lumen alert correlation (S-017)";

  it("Operate to Explore opens the browser's page for the entity open in Operate", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/entities/catalog.Solution/sol-1";
    app();
    await screen.findByTestId("console-header");
    await user.click(await screen.findByRole("button", { name: "Explore" }));
    expect(await screen.findByRole("heading", { level: 1, name: sol1 })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("follows what the console is showing, not the last Explore location", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: sol1 });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.Solution/sol-1");
    // the operator moves on to another type; Explore opens that type's list, not the earlier node
    await user.click(await screen.findByRole("tab", { name: "UseCase" }));
    expect(window.location.hash).toBe("#/operate/catalog/entities/catalog.UseCase");
    await user.click(mode("Explore"));
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase"));
  });

  it("falls back to the module's entry when the console shows no type", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model";
    app();
    await screen.findByTestId("console-header");
    await user.click(mode("Explore"));
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog"));
  });

  it("each switch is a history entry: Back returns to the other mode", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    app();
    await screen.findByRole("heading", { level: 1, name: sol1 });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    act(() => window.history.back());
    expect(await screen.findByRole("heading", { level: 1, name: sol1 })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1");
  });

  it("a host that owns the location gets the Explore location of what the console shows through onLocation", async () => {
    const user = userEvent.setup();
    const seen: unknown[] = [];
    app({
      location: { module: "catalog", type: "Solution", key: "sol-1" },
      onLocation: (l) => seen.push(l),
    });
    await user.click(await screen.findByRole("button", { name: "Operate" }));
    await screen.findByTestId("console-header");
    await user.click(await screen.findByRole("tab", { name: "UseCase" }));
    await user.click(mode("Explore"));
    expect(seen).toContainEqual({ module: "catalog", type: "UseCase" });
    expect(window.location.hash).toBe("");
  });

  it("a viewer who is not an operator never reaches Operate by a route that carries an entity", async () => {
    fake.viewerModes = ["user"];
    window.location.hash = "#/operate/catalog/entities/catalog.Solution/sol-1";
    app();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("console-header")).toBeNull();
  });
});

describe("state across a mode switch (SD-013 D6)", () => {
  const sol1 = "Lumen alert correlation (S-017)";
  const metaReads = () =>
    fake.requests.filter(
      (r) =>
        r.method === "POST" &&
        r.path.endsWith("/api/console/graphql") &&
        r.body.query.includes("record replicas"),
    ).length;
  const toOperate = (user: ReturnType<typeof userEvent.setup>) =>
    user.click(screen.getByRole("button", { name: "Operate" }));
  const toExplore = (user: ReturnType<typeof userEvent.setup>) =>
    user.click(screen.getByRole("button", { name: "Explore" }));

  it("Explore, Operate and Explore again make one meta read, on the one query client the shell made", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    render(<ArrasApp />);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    await screen.findByRole("group", { name: "Mode" });
    await toOperate(user);
    await screen.findByTestId("console-header");
    await screen.findByRole("tab", { name: "UseCase" });
    await toExplore(user);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    expect(metaReads()).toBe(1);
  });

  it("a query client the host passes is the one both modes read through", async () => {
    const user = userEvent.setup();
    const client = createQueryClient();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    render(<ArrasApp queryClient={client} />);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    expect(client.getQueryData(["meta"])).toBeDefined();
    await toOperate(user);
    await screen.findByRole("tab", { name: "UseCase" });
    await toExplore(user);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    expect(metaReads()).toBe(1);
    expect(client.getQueryCache().findAll({ queryKey: ["meta"] })).toHaveLength(1);
  });

  it("keeps edit mode across a switch, and never turns it on for another viewer", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/explore/catalog/Solution/sol-1";
    render(<ArrasApp queryClient={createQueryClient()} />);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    const lock = await screen.findByRole("button", { name: "Edit mode" });
    expect(lock).toHaveAttribute("aria-pressed", "false");
    await user.click(lock);
    expect(screen.getByRole("button", { name: "Edit mode" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await toOperate(user);
    await screen.findByTestId("console-header");
    await toExplore(user);
    await screen.findByRole("heading", { level: 1, name: sol1 });
    expect(await screen.findByRole("button", { name: "Edit mode" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps the Query draft and history across a switch", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/query";
    render(<ArrasApp queryClient={createQueryClient()} />);
    const box = await screen.findByTestId("query-input", {}, { timeout: 5000 });
    await user.click(box);
    await user.paste("select 1");
    await user.click(screen.getByTestId("query-run"));
    await screen.findByTestId("history-entry");
    await user.click(box);
    await user.paste(" -- kept");
    await toExplore(user);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await toOperate(user);
    await user.click(await screen.findByRole("tab", { name: "Query" }));
    expect(await screen.findByTestId("query-input")).toHaveValue("select 1 -- kept");
    expect(screen.getAllByTestId("history-entry")).toHaveLength(1);
  });

  it("keeps the single-key switch across a switch", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model";
    render(<ArrasApp queryClient={createQueryClient()} />);
    await screen.findByTestId("console-header");
    await user.keyboard("?");
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("switch", { name: "Single-key shortcuts" }));
    await user.keyboard("{Escape}");
    await toExplore(user);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    await user.keyboard("?");
    expect(screen.queryByRole("dialog")).toBeNull();
    await toOperate(user);
    await screen.findByTestId("console-header");
    await user.keyboard("3");
    expect(screen.getByRole("tab", { name: "Model", selected: true })).toBeInTheDocument();
    await user.keyboard("?");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: /Keyboard shortcuts/ }));
    const again = await screen.findByRole("dialog");
    expect(within(again).getByRole("switch", { name: "Single-key shortcuts" })).not.toBeChecked();
  });

  it("the person being viewed changing empties the Query history and draft", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/query";
    const client = createQueryClient();
    const { rerender } = render(<ArrasApp queryClient={client} identity="alice" />);
    const box = await screen.findByTestId("query-input", {}, { timeout: 5000 });
    await user.click(box);
    await user.paste("select 1");
    await user.click(screen.getByTestId("query-run"));
    await screen.findByTestId("history-entry");
    rerender(<ArrasApp queryClient={client} identity="carol" />);
    await waitFor(() => expect(screen.queryByTestId("history-entry")).toBeNull());
    expect(await screen.findByTestId("query-input")).toHaveValue("");
  });
});
