// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExploreLocation } from "../browser/location";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

// SD-013, Explore state in the address (FR-74): the list's position, the History address, the page
// that is not available and the document title are all the location's.
const nodePageProps = vi.hoisted(() => [] as Record<string, unknown>[]);
vi.mock("../browser/NodePage", async (original) => {
  const actual = await original<typeof import("../browser/NodePage")>();
  return {
    ...actual,
    NodePage: (props: Parameters<typeof actual.NodePage>[0]) => {
      nodePageProps.push(props as unknown as Record<string, unknown>);
      return actual.NodePage(props);
    },
  };
});

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  document.title = "page";
  nodePageProps.length = 0;
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const open = (hash: string) => {
  window.location.hash = hash;
  return renderBrowser();
};

const goBack = () =>
  act(async () => {
    window.history.back();
    await new Promise((r) => setTimeout(r, 30));
  });

const bulk = (n: number) => {
  const rows = fake.rows["catalog.UseCase"];
  for (let i = 0; i < n; i++)
    rows?.push({
      key: `uc-z-${String(i).padStart(3, "0")}`,
      props: { code: `z${i}`, name: `Bulk ${String(i).padStart(3, "0")}` },
    });
};

/** The `afterKey` each use-case list read was sent with, in order. */
const afterKeys = () =>
  fake.requests
    .filter((r) => String(r.body.query).includes("useCaseList"))
    .map((r) => (r.body.variables as { afterKey?: string | null }).afterKey ?? null);

const rowNames = () =>
  [...document.querySelectorAll(".gb-hits .gb-t")]
    .map((e) => e.textContent ?? "")
    .filter((t) => t.startsWith("Bulk"));

describe("a list's position is in the address (US-066, US-071)", () => {
  it("an address with ?after= reads its first page after that key; Show next replaces the address with the new position", async () => {
    bulk(150);
    const user = userEvent.setup();
    open("#/explore/catalog/UseCase?after=uc-z-009");
    await waitFor(() => expect(rowNames()).toHaveLength(50));
    expect(afterKeys()).toEqual(["uc-z-009"]);
    expect(rowNames()[0]).toBe("Bulk 010");
    const entries = window.history.length;
    await user.click(screen.getByRole("button", { name: "Show next 50" }));
    await waitFor(() => expect(rowNames()).toHaveLength(100));
    expect(afterKeys()).toEqual(["uc-z-009", "uc-z-059"]);
    await waitFor(() =>
      expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-z-059"),
    );
    expect(window.history.length).toBe(entries);
    // the reader's list is not cut back to the new position
    expect(rowNames()).toHaveLength(100);
    expect(rowNames()[0]).toBe("Bulk 010");
  });

  it("a list that begins at the start has no position in its address until Show next", async () => {
    bulk(60);
    const user = userEvent.setup();
    open("#/explore/catalog/UseCase");
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(40));
    expect(window.location.hash).toBe("#/explore/catalog/UseCase");
    await user.click(screen.getByRole("button", { name: "Show next 50" }));
    await waitFor(() => expect(window.location.hash).toMatch(/\?after=uc-z-04\d$/));
  });

  it("Back from an opened entity returns to the positioned list", async () => {
    bulk(150);
    const user = userEvent.setup();
    open("#/explore/catalog/UseCase?after=uc-z-009");
    await waitFor(() => expect(rowNames()).toHaveLength(50));
    await user.click(screen.getByRole("button", { name: "Show next 50" }));
    await waitFor(() =>
      expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-z-059"),
    );
    await user.click(await screen.findByRole("link", { name: /Bulk 100/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Bulk 100" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/explore/catalog/UseCase/uc-z-100");
    await goBack();
    expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-z-059");
    await waitFor(() => expect(rowNames()[0]).toBe("Bulk 060"));
    expect(rowNames()).toHaveLength(50);
  });

  it("a list that starts after a key with nothing after it shows the empty state, not an error", async () => {
    open("#/explore/catalog/UseCase?after=zzz");
    expect(await screen.findByText("There are none.")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show next/ })).not.toBeInTheDocument();
  });

  it("an address that changes from outside starts the list again at the new position", async () => {
    bulk(150);
    open("#/explore/catalog/UseCase?after=uc-z-009");
    await waitFor(() => expect(rowNames()[0]).toBe("Bulk 010"));
    act(() => {
      window.location.hash = "#/explore/catalog/UseCase?after=uc-z-099";
    });
    await waitFor(() => expect(rowNames()[0]).toBe("Bulk 100"));
    expect(afterKeys().at(-1)).toBe("uc-z-099");
  });
});

describe("the History address (US-071)", () => {
  it("/history is the entity's page, with history passed to the node page", async () => {
    open("#/explore/catalog/Solution/sol-1/history");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Lumen alert correlation (S-017)" }),
    ).toBeInTheDocument();
    expect(nodePageProps.at(-1)).toMatchObject({ keyText: "sol-1", history: true });
  });

  it("the entity's own address is not History", async () => {
    open("#/explore/catalog/Solution/sol-1");
    await screen.findByRole("heading", { level: 1, name: /Lumen/ });
    expect(nodePageProps.at(-1)).toMatchObject({ keyText: "sol-1", history: false });
  });
});

describe("the page that is not available (US-067-AC6)", () => {
  it("leads to the module's entry when the module is known, and names no key, type or reason", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Ghost/g-1");
    const state = await screen.findByTestId("gb-state");
    expect(state).not.toHaveTextContent(/Ghost|g-1/);
    await user.click(screen.getByRole("button", { name: "Back to Product catalog" }));
    expect(window.location.hash).toBe("#/explore/catalog");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Product catalog" }),
    ).toBeInTheDocument();
  });

  it("an absent entity of a known module leads to the module's entry too", async () => {
    const user = userEvent.setup();
    open("#/explore/catalog/Solution/ghost");
    await user.click(await screen.findByRole("button", { name: "Back to Product catalog" }));
    expect(window.location.hash).toBe("#/explore/catalog");
  });

  it("an unknown module leads to the start", async () => {
    const user = userEvent.setup();
    open("#/explore/nowhere/Solution/sol-1");
    await user.click(await screen.findByRole("button", { name: "Back to search" }));
    expect(window.location.hash).toBe("#/explore");
  });
});

describe("the document title names the place, the brand last", () => {
  it("the chooser is the brand alone", async () => {
    open("#/explore");
    await screen.findByTestId("gb");
    await waitFor(() => expect(document.title).toBe("Arras"));
  });

  it("the entry is the module", async () => {
    open("#/explore/catalog");
    await waitFor(() => expect(document.title).toBe("Product catalog · Arras"));
  });

  it("a list is the type's plural label, then the module", async () => {
    open("#/explore/catalog/UseCase");
    await waitFor(() => expect(document.title).toBe("Use cases · Product catalog · Arras"));
  });

  it("an entity is its title, then the type, the module and the brand", async () => {
    open("#/explore/catalog/Solution/sol-1");
    await waitFor(() =>
      expect(document.title).toBe(
        "Lumen alert correlation (S-017) · Solutions · Product catalog · Arras",
      ),
    );
  });

  it("an entity still loading is its type, module and brand, never its key", async () => {
    const hold = fake.holdNode("sol-1");
    open("#/explore/catalog/Solution/sol-1");
    await waitFor(() => expect(hold.held()).toBeGreaterThan(0));
    expect(document.title).toBe("Solutions · Product catalog · Arras");
    expect(document.title).not.toContain("sol-1");
    hold.release();
    await waitFor(() =>
      expect(document.title).toBe(
        "Lumen alert correlation (S-017) · Solutions · Product catalog · Arras",
      ),
    );
  });

  it.each([
    ["an unknown module", "#/explore/nowhere/Solution/sol-1"],
    ["an unknown type", "#/explore/catalog/Nothing/sol-1"],
    ["an absent key", "#/explore/catalog/Solution/no-such-key"],
  ])("%s is the brand alone", async (_name, hash) => {
    open(hash);
    await screen.findByText("Not available");
    expect(document.title).toBe("Arras");
  });
});

describe("a replace moves the page's own position only (US-071)", () => {
  type Go = (loc: ExploreLocation, opts?: { replace?: boolean }) => void;
  let go: Go;
  const mount = (hash: string) => {
    window.location.hash = hash;
    return renderBrowser({
      palette: (at) => {
        go = at.go;
        return null;
      },
    });
  };
  const goTo = (loc: ExploreLocation, opts?: { replace?: boolean }) => act(() => go(loc, opts));
  const search = () => screen.getByRole("textbox", { name: /Search/ }) as HTMLInputElement;
  const chip = (name: RegExp) => screen.getByRole("radio", { name });

  it("keeps the search draft on a replace within the type list and clears it on a push", async () => {
    const user = userEvent.setup();
    mount("#/explore/catalog");
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "bulk");
    expect(search().value).toBe("bulk");
    await goTo({ module: "catalog", type: "UseCase", after: "uc-1" }, { replace: true });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-1"));
    expect(search().value).toBe("bulk");
    await goTo({ module: "catalog", type: "UseCase" });
    await waitFor(() => expect(search().value).toBe(""));
  });

  it("keeps the chosen types on a replace to the entry and clears them on a push", async () => {
    const user = userEvent.setup();
    mount("#/explore/catalog");
    await user.click(await screen.findByRole("radio", { name: /Solutions/ }));
    expect(chip(/Solutions/)).toHaveAttribute("aria-checked", "true");
    await goTo({ module: "catalog" }, { replace: true });
    expect(chip(/Solutions/)).toHaveAttribute("aria-checked", "true");
    await goTo({ module: "catalog" });
    await waitFor(() => expect(chip(/^All/)).toHaveAttribute("aria-checked", "true"));
  });

  it("scrolls to the top when a push opens a key, not when a replace does", async () => {
    const user = userEvent.setup();
    const scroll = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    mount("#/explore/catalog");
    await user.type(await screen.findByRole("textbox", { name: /Search/ }), "bulk");
    await goTo({ module: "catalog", type: "Solution", key: "sol-1" }, { replace: true });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/Solution/sol-1"));
    expect(scroll).not.toHaveBeenCalledWith(0, 0);
    await goTo({ module: "catalog", type: "Solution", key: "sol-1", history: true });
    await waitFor(() => expect(scroll).toHaveBeenCalledWith(0, 0));
    scroll.mockRestore();
  });

  it("a replace adds no history entry; a push adds one", async () => {
    mount("#/explore/catalog");
    await screen.findByTestId("gb");
    const entries = window.history.length;
    await goTo({ module: "catalog", type: "UseCase", after: "uc-1" }, { replace: true });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-1"));
    expect(window.history.length).toBe(entries);
    await goTo({ module: "catalog", type: "UseCase", after: "uc-2" });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-2"));
    expect(window.history.length).toBe(entries + 1);
  });

  it("Back after a replace returns to the entry before the replaced one", async () => {
    mount("#/explore/catalog");
    await screen.findByTestId("gb");
    await goTo({ module: "catalog", type: "UseCase" });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase"));
    await goTo({ module: "catalog", type: "UseCase", after: "uc-1" }, { replace: true });
    await waitFor(() => expect(window.location.hash).toBe("#/explore/catalog/UseCase?after=uc-1"));
    await goBack();
    expect(window.location.hash).toBe("#/explore/catalog");
  });
});

describe("a host that owns the location can tell a replace from a push (FR-71 seams)", () => {
  it("Show next reaches onLocation with replace, and a palette's go carries the same options", async () => {
    bulk(150);
    const user = userEvent.setup();
    const seen: [ExploreLocation, { replace?: boolean } | undefined][] = [];
    let go: ((loc: ExploreLocation, opts?: { replace?: boolean }) => void) | undefined;
    renderBrowser({
      location: { module: "catalog", type: "UseCase", after: "uc-z-009" },
      onLocation: (loc, opts) => seen.push([loc, opts]),
      palette: (at) => {
        go = at.go;
        return null;
      },
    });
    await waitFor(() => expect(rowNames()).toHaveLength(50));
    await user.click(screen.getByRole("button", { name: "Show next 50" }));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual([
      { module: "catalog", type: "UseCase", after: "uc-z-059" },
      { replace: true },
    ]);
    act(() => go?.({ module: "catalog", type: "Solution" }));
    expect(seen[1]).toEqual([{ module: "catalog", type: "Solution" }, undefined]);
    expect(window.location.hash).toBe("");
  });
});
