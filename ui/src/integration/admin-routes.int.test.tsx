// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArrasApp } from "../shell";
import { conn, type Person, testQueryClient, withDevHost } from "./harness";

// Every Operate address restores on a fresh render against the real dev host (FR-74, CONTRACT-010 D),
// as an operator, and answers a viewer who is not one with the user path and no server error.
withDevHost();
afterEach(() => {
  window.location.hash = "";
  vi.restoreAllMocks();
});

const app = (who: Person) => render(<ArrasApp queryClient={testQueryClient()} {...conn(who)} />);

const SINCE = "2026-01-01T00:00:00Z";

/** The address, what a fresh render shows there, and the document title it sets. */
const ADDRESSES: [string, () => Promise<unknown>, string][] = [
  [
    "model/catalog.Solution",
    () => screen.findByTestId("type-catalog.Solution"),
    "catalog.Solution · Model · catalog",
  ],
  [
    "entities/catalog.Solution?f.code=sol-1&sort=name:desc",
    async () => {
      const row = await screen.findByText("sol-1");
      expect(screen.getByLabelText("Filter code")).toHaveValue("sol-1");
      return row;
    },
    "catalog.Solution · Entities · catalog",
  ],
  [
    "entities/catalog.Solution/sol-1",
    () => screen.findByTestId("entity-panel"),
    "sol-1 · Entities · catalog",
  ],
  [
    "graph/catalog.Solution/sol-1",
    () => screen.findByRole("tab", { name: "Graph", selected: true }),
    "sol-1 · Graph · catalog",
  ],
  [
    `changes?action=catalog.CorrectSolution&since=${SINCE}`,
    async () => {
      await screen.findByLabelText("Changes filter");
      expect(screen.getByLabelText("Action")).toHaveValue("catalog.CorrectSolution");
      return screen.getByLabelText("Since");
    },
    "catalog.CorrectSolution · Changes · catalog",
  ],
  [
    "changes/catalog.Solution/sol-1",
    () => screen.findByTestId("history-chip"),
    "sol-1 · Changes · catalog",
  ],
  ["changes?view=loads", () => screen.findByTestId("loads"), "Changes · catalog"],
  [
    "actions/catalog.CorrectSolution?in.solution=sol-1",
    () => screen.findByRole("tab", { name: "Actions", selected: true }),
    "catalog.CorrectSolution · Actions · catalog",
  ],
];

describe("a fresh render at each Operate address (FR-74)", () => {
  it.each(ADDRESSES)("restores #/operate/catalog/%s as alice", async (path, shown, title) => {
    window.location.hash = `#/operate/catalog/${path}`;
    app("alice");
    await shown();
    expect(screen.queryByTestId("not-found")).toBeNull();
    await waitFor(() => expect(document.title.startsWith(title)).toBe(true));
  });

  it("an address that names nothing is the not-found page for alice too", async () => {
    window.location.hash = "#/operate/catalog/entities/catalog.Solution/no-such-solution";
    app("alice");
    expect(await screen.findByTestId("not-found")).toHaveTextContent("Not found");
  });

  it.each(ADDRESSES)(
    "#/operate/catalog/%s as carol, who is not an operator, is the user path with no server error",
    async (path) => {
      const statuses: number[] = [];
      const real = globalThis.fetch;
      vi.spyOn(globalThis, "fetch").mockImplementation(async (...args) => {
        const r = await real(...args);
        statuses.push(r.status);
        return r;
      });
      window.location.hash = `#/operate/catalog/${path}`;
      app("carol");
      await screen.findByRole("heading", { level: 1, name: /catalog/i });
      await new Promise((r) => setTimeout(r, 300));
      expect(statuses.filter((s) => s >= 500)).toEqual([]);
      for (const id of ["schema", "entity-panel", "audit", "data-table-pane"])
        expect(screen.queryByTestId(id)).toBeNull();
      expect(screen.queryByRole("group", { name: "Mode" })).toBeNull();
    },
  );
});
