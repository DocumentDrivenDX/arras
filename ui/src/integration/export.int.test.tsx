// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createSchemaApi } from "../api/client";
import type { SchemaCatalog } from "../api/types";
import { ALL_FILE_NAME } from "../areas/exportFiles";
import { SchemaExport } from "../areas/SchemaExport";
import { defined } from "../test/defined";
import { call, conn, renderLive, withDevHost } from "./harness";

// Export (OPR-14) against the real dev host: the file holds the text the catalog holds, and the same
// document validates against the same deployment as "nothing would change" (US-075-AC4).
withDevHost();

const catalog = async (who: Parameters<typeof call>[2] = "alice") =>
  (await call("/api/operate/explorer/schema-catalog.json", undefined, who)).body as SchemaCatalog;

describe("export against the dev host", () => {
  it("Export saves the registered document byte for byte, and validating it says nothing would change", async () => {
    const real = defined(
      (await catalog()).entries.find((e) => e.id === "arras:catalog"),
      "the catalog entry",
    );
    const save = vi.fn();
    renderLive(<SchemaExport module="catalog" save={save} />, "alice");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export" }));
    expect(save).toHaveBeenCalledWith("catalog.umf.json", real.text);
    expect(save.mock.calls[0]?.[1]).toBe(real.text);
    const plan = await createSchemaApi({
      ...conn({ name: "ana", role: "schema author" }),
    }).validate(save.mock.calls[0]?.[1] as string);
    expect(plan).toMatchObject({ module: "catalog", ok: true, changed: false, changes: [] });
  });

  it("Export all saves the catalog's entries as {version: 1, entries}", async () => {
    const real = await catalog();
    const save = vi.fn();
    renderLive(<SchemaExport module="catalog" save={save} />, "alice");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Export all" }));
    expect(save.mock.calls[0]?.[0]).toBe(ALL_FILE_NAME);
    expect(JSON.parse(save.mock.calls[0]?.[1] as string)).toEqual({
      version: 1,
      entries: real.entries.filter((e) => e.schemaFormat === "umf"),
    });
  });

  it("a person who may read no module (role none) is offered no export", async () => {
    const who = { name: "nil", role: "none" };
    expect((await catalog(who)).entries).toEqual([]);
    const { container } = renderLive(<SchemaExport module="catalog" save={vi.fn()} />, who);
    await vi.waitFor(async () => expect((await catalog(who)).entries).toEqual([]));
    await new Promise((r) => setTimeout(r, 300));
    expect(container.querySelector(".arras-root")).toBeEmptyDOMElement();
  });
});
