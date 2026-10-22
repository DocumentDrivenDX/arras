// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GraphBrowser } from "../browser/GraphBrowser";
import { conn, type Person, testQueryClient, withDevHost } from "./harness";

// The route audit's cold renders (FR-74): each Explore address opens, with a new query client and no
// history state, on the real dev host. alice and carol read the catalog and see what the address
// names; dave reads nothing and gets the one not-available page, as does an address naming nothing.
// Operate addresses are cold-rendered in admin-routes.int.test.tsx.
withDevHost();

afterEach(() => {
  window.location.hash = "";
  window.history.replaceState(null, "", "/");
  document.title = "";
});

/** A cold render: a new client, no history state, the address as the only input. */
function cold(person: Person, hash: string) {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(<GraphBrowser queryClient={testQueryClient()} {...conn(person)} />);
}

const heading = (name: string | RegExp) => () => screen.findByRole("heading", { level: 1, name });

/** The address, what a fresh render shows there, and a piece of the title it sets. */
const ADDRESSES: [string, string, () => Promise<unknown>, string][] = [
  ["chooser", "#/explore", heading(/catalog/i), ""],
  ["module entry", "#/explore/catalog", heading(/catalog/i), ""],
  [
    "type list",
    "#/explore/catalog/Solution",
    async () => {
      await screen.findByRole("link", { name: /Pattern extractor/ });
      expect(screen.getByRole("link", { name: /Capacity lookup/ })).toBeInTheDocument();
    },
    "Solutions",
  ],
  [
    "type list with position",
    "#/explore/catalog/Solution?after=sol-extract",
    async () => {
      await screen.findByRole("link", { name: /Minutes drafter/ });
      expect(screen.queryByRole("link", { name: /Pattern extractor/ })).toBeNull();
      expect(screen.queryByRole("link", { name: /Capacity lookup/ })).toBeNull();
    },
    "Solutions",
  ],
  [
    "entity",
    "#/explore/catalog/Solution/sol-extract",
    heading("Pattern extractor"),
    "Pattern extractor",
  ],
  [
    "entity with History",
    "#/explore/catalog/Solution/sol-extract/history",
    heading("Pattern extractor"),
    "Pattern extractor",
  ],
  [
    "another entity",
    "#/explore/catalog/UseCase/uc-pipeline-review",
    heading("Pipeline review"),
    "Pipeline review",
  ],
];

const NOTHING: [string, string][] = [
  ["an absent key", "#/explore/catalog/Solution/no-such-solution"],
  ["an unknown type", "#/explore/catalog/NoSuchType"],
  ["an unknown module", "#/explore/nowhere/Solution/sol-extract"],
  ["a stray segment", "#/explore/catalog/Solution/sol-extract/history/more"],
  ["a query other than a position", "#/explore/catalog/Solution?q=pattern"],
];

const notAvailable = async () => {
  const page = await screen.findByTestId("gb-state");
  expect(page).toHaveTextContent("Not available");
  expect(screen.getAllByTestId("gb-state")).toHaveLength(1);
  return page;
};

describe.each(["alice", "carol"] as const)("a cold render at each Explore address as %s", (who) => {
  it.each(ADDRESSES)("%s: %s restores its state", async (_name, hash, shown, title) => {
    cold(who, hash);
    await shown();
    expect(screen.queryByTestId("gb-state")).toBeNull();
    await waitFor(() => expect(document.title.endsWith(" · Arras")).toBe(true));
    expect(document.title).toContain(title);
    expect(window.location.hash).toBe(hash);
  });

  it.each(NOTHING)("%s is the not-available page", async (_name, hash) => {
    cold(who, hash);
    await notAvailable();
    await waitFor(() => expect(document.title).toBe("Arras"));
  });
});

/** What the page says; only its way on differs, to a module the viewer can read. */
const words = (page: HTMLElement) => [...page.querySelectorAll("h1, p")].map((e) => e.textContent);

describe("a cold render as dave, who reads nothing", () => {
  it.each(ADDRESSES.filter(([, hash]) => hash !== "#/explore"))(
    "%s: %s is the same not-available page as one naming nothing",
    async (_name, hash) => {
      const { unmount } = cold("carol", "#/explore/catalog/Solution/no-such-solution");
      const missing = words(await notAvailable());
      unmount();
      cold("dave", hash);
      expect(words(await notAvailable())).toEqual(missing);
      expect(document.title).not.toContain("Pattern extractor");
    },
  );
});
