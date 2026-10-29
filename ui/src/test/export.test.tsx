// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SchemaCatalog, SchemaCatalogEntry } from "../api/types";
import { ALL_FILE_NAME, catalogFile, exportFor, fileNameFor, readable } from "../areas/exportFiles";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { SchemaExport } from "../areas/SchemaExport";
import { downloadText, REVOKE_AFTER_MS } from "../lib/download";
import { defined } from "./defined";
import { type FakeApi, json, stage, wire } from "./fake";
import { renderConsole, renderPart } from "./render";

// Export (OPR-14): exactly the text the schema catalog holds, named <module>.umf.json; the catalog
// of readable documents as arras-schema-catalog.json; "not shown" notes never saved; nothing for a
// module the catalog has no entry for.

const entry = (module: string, over: Partial<SchemaCatalogEntry> = {}): SchemaCatalogEntry => ({
  ...defined(wire.schemaCatalog().entries[0], "an entry"),
  id: `arras:${module}`,
  title: module,
  path: `${module}.umf.json`,
  // not pretty-printed, CRLF, non-ASCII and no trailing newline: the bytes registered are the bytes saved
  text: `{"umf":"1.0",\r\n  "module":"${module}", "name":"Zoë   ✓"}`,
  ...over,
});
const note = (module: string): SchemaCatalogEntry =>
  entry(module, {
    path: `${module}.not-shown.json`,
    text: '{"note":"not shown: over 1 MiB"}',
    schemaFormat: "json-schema",
    description: "Not shown.",
  });
const catalogOf = (...entries: SchemaCatalogEntry[]): SchemaCatalog => ({ version: 1, entries });

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
});
const serve = (c: SchemaCatalog) =>
  api.on((r) => (r.path.endsWith("/explorer/schema-catalog.json") ? json(200, c) : undefined));

describe("what is exported, from the catalog alone", () => {
  const c = catalogOf(entry("catalog"), entry("other"), note("big"));
  it("a document: its text as held; a note: too large; no entry: none", () => {
    const mine = exportFor(c, "catalog");
    expect(mine).toMatchObject({ state: "document", fileName: "catalog.umf.json" });
    expect(mine.state === "document" && mine.entry.text).toBe(c.entries[0]?.text);
    expect(exportFor(c, "big")).toEqual({ state: "too_large" });
    expect(exportFor(c, "attached")).toEqual({ state: "none" });
    expect(exportFor(undefined, "catalog")).toEqual({ state: "none" });
    expect(fileNameFor("m")).toBe("m.umf.json");
  });

  it("the catalog file holds the readable entries only, as {version: 1, entries}", () => {
    expect(readable(c)).toMatchObject({ notes: 1 });
    const file = catalogFile(c);
    expect(JSON.parse(file)).toEqual({ version: 1, entries: [c.entries[0], c.entries[1]] });
    expect(file).not.toContain("not shown");
    expect(file).not.toContain("big");
    expect(file.endsWith("\n")).toBe(true);
  });
});

describe("the Export controls", () => {
  it("Export saves the module's document byte for byte as <module>.umf.json", async () => {
    const c = catalogOf(entry("catalog"), entry("other"));
    serve(c);
    const save = vi.fn();
    renderPart(<SchemaExport module="catalog" save={save} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export" }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0]?.[0]).toBe("catalog.umf.json");
    expect(save.mock.calls[0]?.[1]).toBe(c.entries[0]?.text); // identical string: no re-serialisation
  });

  it("Export all saves arras-schema-catalog.json with the readable entries, and says what it left out", async () => {
    const c = catalogOf(entry("catalog"), note("big"), entry("other"));
    serve(c);
    const save = vi.fn();
    renderPart(<SchemaExport module="catalog" save={save} />);
    const all = await screen.findByRole("button", { name: "Export all" });
    expect(all).toHaveAttribute(
      "title",
      expect.stringContaining("1 too large to export is left out"),
    );
    await userEvent.setup().click(all);
    const [name, text] = defined(save.mock.calls[0], "a save") as [string, string];
    expect(name).toBe(ALL_FILE_NAME);
    expect(JSON.parse(text)).toEqual({ version: 1, entries: [c.entries[0], c.entries[2]] });
  });

  it("a module the catalog shows only as a note is too large to export: no Export, the note is never saved", async () => {
    serve(catalogOf(entry("catalog"), note("big")));
    const save = vi.fn();
    renderPart(<SchemaExport module="big" save={save} />);
    expect(await screen.findByText("Too large to export")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Export all" }));
    expect(save.mock.calls.every((c) => !String(c[1]).includes("not shown"))).toBe(true);
    expect(
      save.mock.calls.every((c) => c[0] !== "big.umf.json" && c[0] !== "big.not-shown.json"),
    ).toBe(true);
  });

  it("an attached module (no catalog entry) offers no Export, while Export all remains for the others", async () => {
    serve(catalogOf(entry("catalog")));
    renderPart(<SchemaExport module="attached" save={vi.fn()} />);
    await screen.findByRole("button", { name: "Export all" });
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
  });

  it("only the modules the viewer may read are in the catalog, so Export all names no other", async () => {
    // The catalog is the viewer's own: two of three modules readable.
    serve(catalogOf(entry("one"), entry("two")));
    const save = vi.fn();
    renderPart(<SchemaExport module="one" save={save} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export all" }));
    const ids = (JSON.parse(save.mock.calls[0]?.[1] as string) as SchemaCatalog).entries.map(
      (e) => e.id,
    );
    expect(ids).toEqual(["arras:one", "arras:two"]);
  });

  it("renders nothing while the catalog is unread or has nothing, and nothing when it fails", async () => {
    api.on((r) =>
      r.path.endsWith("/explorer/schema-catalog.json")
        ? json(403, { error: wire.refused("catalog") })
        : undefined,
    );
    const { container } = renderPart(<SchemaExport module="catalog" save={vi.fn()} />);
    await waitFor(() =>
      expect(api.log.some((r) => r.path.endsWith("schema-catalog.json"))).toBe(true),
    );
    expect(container.querySelector(".arras-root")).toBeEmptyDOMElement();
  });
});

describe("in the Schema area", () => {
  it("is next to the live registry and the UMF source views, per module", async () => {
    serve(catalogOf(entry("catalog")));
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    const live = await screen.findByTestId("schema");
    expect(await within(live).findByRole("button", { name: "Export" })).toBeInTheDocument();
    expect(within(live).getByRole("button", { name: "Export all" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    expect(await screen.findByRole("button", { name: "Export" })).toBeInTheDocument();
  });
});

describe("sharing the catalog with the UMF source view", () => {
  it("opening the UMF source reads the catalog again, and a failed read shows its error, not the entries Export read", async () => {
    let reads = 0;
    api.on((r) => {
      if (!r.path.endsWith("/explorer/schema-catalog.json")) return undefined;
      return ++reads === 1
        ? json(200, catalogOf(entry("catalog")))
        : json(401, { error: wire.tokenExpired() });
    });
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByRole("button", { name: "Export" }); // read once, for Export
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    expect(await screen.findByTestId("umf-catalog-error")).toHaveTextContent("Sign in again");
    expect(reads).toBe(2);
  });
});

describe("the console's real download", () => {
  it("clicks an <a download> on a Blob URL, keeps the page free of storage and revokes the URL", async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    const create = vi.fn((b: Blob) => {
      blobs.push(b);
      return "blob:fake-1";
    });
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    let clicked: { download: string; href: string } | null = null;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked = { download: this.download, href: this.href };
    });
    const set = vi.spyOn(Storage.prototype, "setItem");
    const text = '{"a":1}\r\n';
    downloadText("catalog.umf.json", text);
    expect(clicked).toEqual({ download: "catalog.umf.json", href: "blob:fake-1" });
    expect(await blobs[0]?.text()).toBe(text);
    expect(blobs[0]?.type).toBe("application/json");
    expect(document.querySelector("a[download]")).toBeNull(); // the anchor is removed
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_AFTER_MS);
    expect(revoke).toHaveBeenCalledWith("blob:fake-1");
    expect(set).not.toHaveBeenCalled();
    click.mockRestore();
    set.mockRestore();
    vi.useRealTimers();
  });
});

describe("the console wires Export to the download helper", () => {
  it("a click on Export in the console downloads the module's document", async () => {
    serve(catalogOf(entry("catalog")));
    const create = vi.fn(() => "blob:x");
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderConsole();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export" }));
    expect(create).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    click.mockRestore();
  });
});
