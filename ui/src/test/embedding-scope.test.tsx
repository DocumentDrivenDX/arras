// SPDX-License-Identifier: MIT OR Apache-2.0
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode, useEffect, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { ArrasProvider, createQueryClient, useClient, useRefusals } from "../api/context";
import { ApiError } from "../api/errors";
import { GraphBrowser } from "../browser/GraphBrowser";
import type { ExploreLocation } from "../browser/location";
import { ArrasApp } from "../shell";
import { stageBrowser } from "./browserFake";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function Probe({ load }: { load: () => Promise<string> }) {
  const client = useClient();
  const q = useQuery({ queryKey: ["same-key"], queryFn: load, staleTime: Infinity });
  const { refusals, refuse } = useRefusals();
  const qc = useQueryClient();
  return (
    <section>
      <output>{q.data ?? "waiting"}</output>
      <span>{client.config.operateBase}</span>
      <span>{Object.keys(refusals).length} refusals</span>
      <button
        type="button"
        onClick={() => refuse("action", new ApiError(403, { type: "Refused" }))}
      >
        Refuse
      </button>
      <button type="button" onClick={() => void qc.invalidateQueries()}>
        Refresh
      </button>
    </section>
  );
}

describe("embedding session ownership", () => {
  it.each([false, true])(
    "survives StrictMode effect replay with a supplied cache: %s",
    async (supplied) => {
      const client = supplied ? createQueryClient() : undefined;
      render(
        <StrictMode>
          <ArrasProvider queryClient={client}>
            <Probe load={async () => "strict-data"} />
          </ArrasProvider>
        </StrictMode>,
      );
      expect(await screen.findByText("strict-data")).toBeInTheDocument();
    },
  );

  it("does not deliver an old identity's late sign-in callback to the host", async () => {
    const response = deferred<Response>();
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response.promise);
    const signIn = vi.fn();
    function ViewerRead() {
      const client = useClient();
      useEffect(() => {
        void client.viewer().catch(() => {});
      }, [client]);
      return null;
    }
    const { rerender } = render(
      <ArrasProvider identity="old" onUnauthorized={signIn}>
        <ViewerRead />
      </ArrasProvider>,
    );
    rerender(
      <ArrasProvider identity="new" onUnauthorized={signIn}>
        <span>New identity</span>
      </ArrasProvider>,
    );
    await act(async () =>
      response.resolve(
        new Response(
          JSON.stringify({
            error: { type: "Refused", reason: "token_expired", message: "expired" },
          }),
          { status: 401, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    expect(signIn).not.toHaveBeenCalled();
  });

  it("replaces cached data, refusals and form state before rendering a new identity", async () => {
    const bob = deferred<string>();
    const { rerender, container } = render(
      <ArrasProvider identity="alice">
        <Probe load={async () => "alice-private"} />
        <input defaultValue="" />
      </ArrasProvider>,
    );
    await screen.findByText("alice-private");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "private draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Refuse" }));
    expect(screen.getByText("1 refusals")).toBeInTheDocument();
    expect(container.querySelector(".arras-root section")).not.toBeNull();
    rerender(
      <ArrasProvider identity="bob">
        <Probe load={() => bob.promise} />
        <input defaultValue="" />
      </ArrasProvider>,
    );
    expect(screen.queryByText("alice-private")).toBeNull();
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.getByText("0 refusals")).toBeInTheDocument();
    await act(async () => bob.resolve("bob-private"));
    expect(await screen.findByText("bob-private")).toBeInTheDocument();
  });

  it("isolates late old-session results and changes of API base", async () => {
    const old = deferred<string>();
    const { rerender } = render(
      <ArrasProvider operateBase="/first">
        <Probe load={() => old.promise} />
      </ArrasProvider>,
    );
    expect(screen.getByText("waiting")).toBeInTheDocument();
    rerender(
      <ArrasProvider operateBase="/second">
        <Probe load={async () => "second"} />
      </ArrasProvider>,
    );
    await screen.findByText("second");
    await act(async () => old.resolve("obsolete"));
    expect(screen.queryByText("obsolete")).toBeNull();
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("keeps independent providers isolated even with identical query keys", async () => {
    render(
      <>
        <ArrasProvider identity="a">
          <Probe load={async () => "only-a"} />
        </ArrasProvider>
        <ArrasProvider identity="b">
          <Probe load={async () => "only-b"} />
        </ArrasProvider>
      </>,
    );
    await screen.findByText("only-a");
    await screen.findByText("only-b");
  });

  it("clears an exclusive supplied cache on identity changes and release", async () => {
    const client = createQueryClient();
    const { rerender, unmount } = render(
      <ArrasProvider queryClient={client} identity="a">
        <Probe load={async () => "first"} />
      </ArrasProvider>,
    );
    await screen.findByText("first");
    const next = deferred<string>();
    rerender(
      <ArrasProvider queryClient={client} identity="b">
        <Probe load={() => next.promise} />
      </ArrasProvider>,
    );
    expect(screen.queryByText("first")).toBeNull();
    expect(client.getQueryData(["same-key"])).toBeUndefined();
    await act(async () => next.resolve("second"));
    await screen.findByText("second");
    unmount();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });

  it("refuses simultaneous independent ownership of a supplied cache", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const client = createQueryClient();
    expect(() =>
      render(
        <>
          <ArrasProvider identity="a" queryClient={client}>
            <span>A</span>
          </ArrasProvider>
          <ArrasProvider identity="b" queryClient={client}>
            <span>B</span>
          </ArrasProvider>
        </>,
      ),
    ).toThrow(/exclusive/);
  });

  it("rejects silently conflicting nested entry configuration", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() =>
      render(
        <ArrasProvider identity="a">
          <ArrasConsole identity="b" />
        </ArrasProvider>,
      ),
    ).toThrow(/Conflicting Arras identity/);
  });

  it("rechecks viewer modes on an identity change in the complete shell", async () => {
    const fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
    const { rerender } = render(
      <ArrasApp identity="operator" location={{ module: "catalog" }} pageEffects={false} />,
    );
    await screen.findByRole("button", { name: "Operate" });
    fake.viewerModes = ["user"];
    rerender(<ArrasApp identity="viewer" location={{ module: "catalog" }} pageEffects={false} />);
    expect(screen.queryByRole("button", { name: "Operate" })).toBeNull();
    await waitFor(() =>
      expect(fake.requests.filter((r) => r.path.endsWith("/viewer"))).toHaveLength(2),
    );
    expect(screen.queryByRole("button", { name: "Operate" })).toBeNull();
  });
});

describe("host page ownership", () => {
  it("keeps accessibility IDs and labels local to each embedded browser", async () => {
    const fake = stageBrowser();
    fake.mods = fake.mods.slice(0, 1);
    const location = { module: "catalog", type: "Solution", key: "sol-1" };
    const { container } = render(
      <>
        <GraphBrowser location={location} pageEffects={false} />
        <GraphBrowser location={location} pageEffects={false} />
      </>,
    );
    await screen.findAllByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
    const ids = [...container.querySelectorAll("[id]")].map((el) => el.id);
    expect(ids.length).toBeGreaterThan(1);
    expect(new Set(ids).size).toBe(ids.length);
    for (const root of container.querySelectorAll(".arras-root")) {
      for (const el of root.querySelectorAll("[aria-labelledby]")) {
        for (const id of el.getAttribute("aria-labelledby")?.split(" ") ?? [])
          expect(root.contains(document.getElementById(id))).toBe(true);
      }
    }
  });

  it.each(["browser", "shell"])(
    "the controlled %s leaves history, scroll, title and host shortcuts alone",
    async (kind) => {
      const fake = stageBrowser();
      fake.mods = fake.mods.slice(0, 1);
      document.title = "Host application";
      window.history.replaceState(
        { host: "retained", gb: { text: "host-owned-search", scroll: 900 } },
        "",
        "/#host-route",
      );
      const replace = vi.spyOn(window.history, "replaceState");
      const push = vi.spyOn(window.history, "pushState");
      const back = vi.spyOn(window.history, "back");
      const scroll = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
      function Host() {
        const [location, onLocation] = useState<ExploreLocation>({
          module: "catalog",
          type: "Solution",
          key: "sol-1",
        });
        return kind === "shell" ? (
          <ArrasApp location={location} onLocation={onLocation} pageEffects={false} />
        ) : (
          <GraphBrowser location={location} onLocation={onLocation} canEdit pageEffects={false} />
        );
      }
      const user = userEvent.setup();
      render(
        <>
          <button type="button">Host control</button>
          <Host />
        </>,
      );
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" });
      const search = screen.getByRole("textbox", { name: "Search Product catalog" });
      expect(search).toHaveValue("");
      await user.click(screen.getByRole("button", { name: "History" }));
      const history = await screen.findByTestId("gb-history");
      await user.click(within(history).getByRole("button", { name: /Back to/ }));
      await screen.findByRole("button", { name: "History" });
      await user.click(screen.getByRole("button", { name: "Host control" }));
      await user.keyboard("/?{Control>}k{/Control}");
      expect(screen.getByRole("button", { name: "Host control" })).toHaveFocus();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.title).toBe("Host application");
      expect(window.location.hash).toBe("#host-route");
      expect(window.history.state).toEqual({
        host: "retained",
        gb: { text: "host-owned-search", scroll: 900 },
      });
      expect(replace).not.toHaveBeenCalled();
      expect(push).not.toHaveBeenCalled();
      expect(back).not.toHaveBeenCalled();
      expect(scroll).not.toHaveBeenCalled();
    },
  );
});
