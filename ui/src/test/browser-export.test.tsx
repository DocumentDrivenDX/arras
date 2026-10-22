// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { renderBrowser } from "./render";

const saved = vi.hoisted(() => ({ calls: [] as [string, string][] }));
vi.mock("../lib/download", async (orig) => ({
  ...(await orig<typeof import("../lib/download")>()),
  downloadText: (name: string, text: string) => saved.calls.push([name, text]),
}));

let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  fake = stageBrowser();
  saved.calls = [];
  window.location.hash = "#/explore/catalog";
});
afterEach(() => {
  window.location.hash = "";
});

const exportButton = () => screen.findByRole("button", { name: "Export graph" });

describe("exporting the graph", () => {
  it("offers Export only where the host offers edits", async () => {
    renderBrowser({ canEdit: false });
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.queryByRole("button", { name: "Export graph" })).toBeNull();
  });

  it("reads the whole graph a page at a time and saves one canonical file named for the module", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await user.click(await exportButton());
    await waitFor(() => expect(saved.calls).toHaveLength(1));
    const [name, text] = saved.calls[0] ?? ["", ""];
    expect(name).toBe("catalog.graph.json");
    const file = JSON.parse(text);
    expect(file).toMatchObject({
      format: "arras.graph",
      version: 1,
      module: "catalog",
      complete: true,
    });
    const kinds = file.records
      .map((r: Record<string, unknown>) => ("type" in r ? "e" : "r"))
      .join("");
    expect(kinds).toMatch(/^e+r+$/); // entities, then links
    expect(file.records[0]).toEqual({
      type: "UseCase",
      key: "uc-1",
      properties: expect.objectContaining({ name: "Alert review" }),
    });
    expect(text.endsWith("}\n")).toBe(true);
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Saved catalog.graph.json: \d+ records\./,
    );
  });

  it("sends the module in a POST body, never in a URL", async () => {
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await user.click(await exportButton());
    await waitFor(() => expect(saved.calls).toHaveLength(1));
    const exports = fake.requests.filter((r) => r.path.endsWith("/export"));
    expect(exports.length).toBeGreaterThan(0);
    for (const r of exports) {
      expect(r.method).toBe("POST");
      expect(r.url).not.toMatch(/catalog|\?/);
      expect(r.body).toMatchObject({ module: "catalog" });
    }
  });

  it("says when the file is not the whole graph", async () => {
    fake.exportOmitted = ["Product"];
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await user.click(await exportButton());
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Not the whole graph: Product could not be read.",
    );
    expect(JSON.parse(saved.calls[0]?.[1] ?? "{}")).toMatchObject({
      complete: false,
      omitted: ["Product"],
    });
  });

  it("saves nothing and says why when the export is refused", async () => {
    fake.exportStatus = 403;
    const user = userEvent.setup();
    renderBrowser({ canEdit: true });
    await user.click(await exportButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("You can't export this module.");
    expect(saved.calls).toEqual([]);
  });
});
