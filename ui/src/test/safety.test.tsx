// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { createClient } from "../api/client";
import { ActionForm } from "../areas/ActionForm";
import {
  err,
  type FakeApi,
  json,
  type Recorded,
  seedCatalog,
  stage,
  validation,
  wire,
} from "./fake";
import { renderConsole, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});
const validateCall = (r: Recorded) => r.method === "POST" && r.path.endsWith("/validate");

describe("Safety (US-064)", () => {
  it("US-064-AC1: the client exposes only reads and the three action verbs (a change to this list is a change to the write surface)", () => {
    const c = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    const surface = Object.keys(c)
      .filter((k) => k !== "config")
      .sort();
    // Reads: version, viewer, meta, status, moduleQuery, query (POST /query, a read), export (POST /export, a read), changes, loads, schemaCatalog (a GET).
    // Writes: only the three action verbs. (viewer and meta are the reads both modes share, CONTRACT-010.)
    expect(surface).toEqual([
      "batch",
      "changes",
      "export",
      "invoke",
      "loads",
      "meta",
      "moduleQuery",
      "query",
      "schemaCatalog",
      "status",
      "validate",
      "version",
      "viewer",
    ]);
  });

  it("US-064-AC1: a whole session posts only to the action verbs, the audit reads and GraphQL", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/entities/catalog.Solution";
    api.on((r) => (validateCall(r) ? json(200, validation()) : undefined));
    renderConsole({ hashRouting: true });
    await user.click(await screen.findByText("sol-1"));
    await user.click(await screen.findByRole("button", { name: /CorrectSolution/ }));
    await user.type(await screen.findByLabelText(/^level/), "x");
    await user.tab();
    await screen.findByTestId("effects");
    const allowed = [
      /\/api\/console\/graphql(\/[^/]+)?$/,
      /\/api\/operate\/actions\/[^/]+\/[^/]+\/(validate|invoke|batch)$/,
      /\/api\/operate\/audit\/(changes|loads)$/,
    ];
    const posts = api.log.filter((r) => r.method === "POST");
    expect(posts.length).toBeGreaterThan(3);
    expect(posts.every((r) => allowed.some((a) => a.test(r.path)))).toBe(true);
    // Reads are never made with anything but GET /version, and every other call is a POST.
    expect(
      api.log
        .filter((r) => r.method !== "POST")
        .every((r) => r.method === "GET" && r.path.endsWith("/version")),
    ).toBe(true);
    expect(posts.some((r) => r.path.endsWith("/invoke"))).toBe(false);
  });

  it("US-064-AC2: two viewers with different grants each get the provider's own answer", async () => {
    const user = userEvent.setup();
    // The provider answers by the viewer the host's headers name.
    api.on((r) => {
      if (!validateCall(r)) return undefined;
      return r.headers["x-person"] === "carol" ? err(403, wire.refused()) : json(200, validation());
    });
    const a = renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1", level: "x" }}
      />,
      {
        getHeaders: () => ({ "x-person": "alice" }),
      },
    );
    await user.click(await screen.findByTestId("validate"));
    await screen.findByTestId("effects");
    expect(screen.getByTestId("confirm")).toBeEnabled();
    a.unmount();
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1", level: "x" }}
      />,
      {
        getHeaders: () => ({ "x-person": "carol" }),
      },
    );
    await user.click(await screen.findByTestId("validate"));
    await screen.findByText(/The provider refused you/);
    expect(screen.queryByTestId("confirm")).toBeNull();
  });

  it("US-064: controls stay disabled after a refusal, and the reason is shown", async () => {
    const user = userEvent.setup();
    api.on((r) => (validateCall(r) ? err(403, wire.refused()) : undefined));
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1", level: "x" }}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    const alert = await screen.findByText(/The provider refused you/);
    expect(alert).toHaveTextContent("no_access");
    expect(screen.getByTestId("validate")).toBeDisabled();
    expect(screen.getByLabelText(/^solution/)).toBeDisabled();
  });

  it("US-064-AC5: a host that does not offer the action answers 403, and the form shows 'not offered'", async () => {
    const user = userEvent.setup();
    api.on((r) => (validateCall(r) ? err(403, wire.notOffered()) : undefined));
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1", level: "x" }}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    const alert = await screen.findByText(/This host does not offer that action to you/);
    expect(alert.closest("[role=alert]")).toHaveTextContent("Not offered");
    expect(screen.queryByTestId("confirm")).toBeNull();
  });

  it("US-064-AC4: an error body is shown by type and message only; a backend's detail is never in the UI", async () => {
    const user = userEvent.setup();
    // The server omits `detail`; if one arrived anyway the UI would still not print it.
    api.on((r) =>
      validateCall(r)
        ? err(503, {
            type: "Unavailable",
            message: "memory is unavailable (down)",
            backend: "memory",
            reason: "down",
            detail: "password=hunter2 inputs.level=x",
          })
        : undefined,
    );
    renderPart(
      <ActionForm
        module="catalog"
        action="catalog.CorrectSolution"
        prefill={{ solution: "sol-1", level: "x" }}
      />,
    );
    await user.click(await screen.findByTestId("validate"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Backend unavailable");
    expect(alert).toHaveTextContent("memory");
    expect(document.body).not.toHaveTextContent("hunter2");
  });

  it("US-064: the UI offers no raw edit, SQL, registration or import", async () => {
    const user = userEvent.setup();
    // A host that does not mount the schema surface (CONTRACT-011) has no import (US-074-AC5); with it
    // mounted the Schema area's Import view exists, tested in schema-import.test.tsx.
    api.schemaMounted = false;
    window.location.hash = "#/catalog/entities/catalog.UseCase";
    renderConsole({ hashRouting: true });
    await screen.findByText("uc-1");
    // Table cells are read-only: nothing editable, no row delete or add control.
    expect(
      screen
        .getByLabelText("catalog.UseCase table")
        .querySelectorAll("td input, td textarea, td [contenteditable]"),
    ).toHaveLength(0);
    for (const label of [
      /\bsql\b/i,
      /register/i,
      /import/i,
      /delete row/i,
      /add row/i,
      /insert/i,
    ]) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
    for (const tab of ["Model", "Actions"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      for (const label of [/\bsql\b/i, /register/i, /import/i])
        expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
    await waitFor(() => expect(screen.queryByRole("textbox", { name: /sql/i })).toBeNull());
  });
});
