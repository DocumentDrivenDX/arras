// SPDX-License-Identifier: MIT OR Apache-2.0
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createSchemaApi } from "../api/client";
import type { ApiError } from "../api/errors";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { groupChanges } from "../areas/SchemaImport";
import { err, type FakeApi, json, type Recorded, schemaWire, stage } from "./fake";
import { renderConsole, renderPart } from "./render";

// Schema import (OPR-12, OPR-13) with the fetch double: the plan beside the registered document, Apply
// only for an ok and changed plan, the plan's revision as expected_revision, and every answer the
// surface can give (CONTRACT-011).
let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
});

const DOC = '{"umf": "1.0", "modules": []}';
const isPost = (verb: "validate" | "register") => (r: Recorded) =>
  r.method === "POST" && r.path === `/api/schema/${verb}`;

async function openImport(props: { getHeaders?: () => Record<string, string> } = {}) {
  const user = userEvent.setup();
  renderPart(<SchemaBrowser module="catalog" />, props);
  await user.click(await screen.findByRole("button", { name: "Import" }));
  return user;
}
const choose = (user: ReturnType<typeof userEvent.setup>, text = DOC, name = "catalog.umf.json") =>
  user.upload(
    screen.getByLabelText("UMF document"),
    new File([text], name, { type: "application/json" }),
  );

describe("the surface is offered only when mounted (US-074-AC5)", () => {
  it("probes GET /api/schema/version and shows Import when it answers contract 1", async () => {
    await openImport();
    expect(api.log.find((r) => r.path === "/api/schema/version")?.method).toBe("GET");
    expect(screen.getByTestId("schema-import")).toBeInTheDocument();
  });

  it("a 404 on the version hides Import and the import view", async () => {
    api.schemaMounted = false;
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    await waitFor(() => expect(api.log.some((r) => r.path === "/api/schema/version")).toBe(true));
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
    expect(screen.queryByTestId("schema-import")).toBeNull();
    expect(api.posts(/\/api\/schema\//)).toHaveLength(0);
  });

  it("a network failure, or a contract version this console does not speak, hides it too", async () => {
    const offered = (c: Partial<Parameters<typeof createSchemaApi>[0]> = {}) =>
      createSchemaApi({ operateBase: "/api/operate", consoleBase: "/api/console", ...c }).offered();
    api.on((r) =>
      r.path === "/api/schema/version" ? json(200, { contracts: { schema: 2 } }) : undefined,
    );
    expect(await offered()).toBe(false);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("offline"))),
    );
    expect(await offered()).toBe(false);
  });

  it("schemaBase moves the mount; the console sends no credential of its own", async () => {
    const api2 = stage();
    const seen: string[] = [];
    api2.on((r) => {
      if (r.path.startsWith("/custom/"))
        seen.push(`${r.method} ${r.path} ${r.headers.authorization ?? ""}`);
      return r.path === "/custom/version" ? json(200, schemaWire.version()) : undefined;
    });
    renderConsole({ schemaBase: "/custom/", getHeaders: () => ({ authorization: "Bearer t" }) });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Import" }));
    expect(seen).toEqual(["GET /custom/version Bearer t"]);
  });
});

describe("validate (OPR-12)", () => {
  it("sends the file's text in a POST body, shows the plan grouped by element beside the registered document, and nothing is applied", async () => {
    api.on((r) =>
      isPost("validate")(r)
        ? json(
            200,
            schemaWire.plan({
              changes: [
                ...schemaWire.plan().changes,
                { kind: "retired", element: "action", name: "catalog.Old", detail: "" },
                { kind: "changed", element: "type", name: "catalog.Solution", detail: "key" },
              ],
            }),
          )
        : undefined,
    );
    const user = await openImport();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    const plan = await screen.findByTestId("plan");
    const [call] = api.posts(/\/api\/schema\/validate$/);
    expect(call?.body).toEqual({ document: DOC });
    expect(call?.url).not.toContain("umf"); // the document is never in a URL
    expect(await within(plan).findByTestId("plan-type")).toHaveTextContent(
      "changedcatalog.Solutionkey",
    );
    expect(within(plan).getByTestId("plan-property")).toHaveTextContent(
      "addedcatalog.UseCase.notesoptional string",
    );
    expect(within(plan).getByTestId("plan-action")).toHaveTextContent("retiredcatalog.Old");
    expect((screen.getByTestId("current-document") as HTMLTextAreaElement).value).toContain(
      '"module": "catalog"',
    );
    expect(api.posts(/\/api\/schema\/register$/)).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Apply" })).toBeEnabled();
  });

  it("an incompatible plan lists every violation with its code and message and offers no Apply", async () => {
    api.on((r) => (isPost("validate")(r) ? json(200, schemaWire.planIncompatible()) : undefined));
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    const v = await screen.findByTestId("plan-violations");
    expect(v).toHaveTextContent("incompatible_change");
    expect(v).toHaveTextContent("cannot add a required property while 14 records exist");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("a plan that changes nothing says so and offers no Apply", async () => {
    api.on((r) => (isPost("validate")(r) ? json(200, schemaWire.planUnchanged()) : undefined));
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByTestId("plan-unchanged")).toHaveTextContent("Nothing would change");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("a document that does not parse shows every violation (400) and no Apply", async () => {
    api.on((r) => (isPost("validate")(r) ? err(400, schemaWire.invalidDocument()) : undefined));
    const user = await openImport();
    await choose(user, "nope");
    await user.click(screen.getByRole("button", { name: "Validate" }));
    const bad = await screen.findByTestId("schema-invalid");
    expect(bad).toHaveTextContent("invalid_document");
    expect(bad).toHaveTextContent("not valid JSON");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("501 says import is not offered for the module", async () => {
    api.on((r) =>
      isPost("validate")(r)
        ? err(501, { type: "Unsupported", message: "not supported" })
        : undefined,
    );
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByTestId("schema-unsupported")).toHaveTextContent(
      "Import is not offered for this module",
    );
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("413 says the document is too large", async () => {
    api.on((r) =>
      isPost("validate")(r)
        ? err(413, { type: "TooLarge", message: "document too large" })
        : undefined,
    );
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText(/document is too large/i)).toBeInTheDocument();
  });

  it("a plan for another module names it, and reads that module's registered document", async () => {
    api.on((r) =>
      isPost("validate")(r) ? json(200, schemaWire.plan({ module: "elsewhere" })) : undefined,
    );
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText(/This document is for/)).toHaveTextContent("elsewhere");
    expect(screen.getByTestId("current-registered")).toHaveTextContent(
      "No registered document for elsewhere is readable for you",
    );
  });

  it("choosing another file clears the plan", async () => {
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByTestId("plan-changes");
    await choose(user, "{}", "other.json");
    expect(screen.queryByTestId("plan-changes")).toBeNull();
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("an answer to an older validate is dropped when a newer one was sent", async () => {
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    let n = 0;
    api.on(async (r) => {
      if (!isPost("validate")(r)) return undefined;
      if (++n === 1) {
        await held;
        return json(200, schemaWire.plan({ module: "stale-one" }));
      }
      return json(200, schemaWire.plan({ module: "fresh-one" }));
    });
    const user = await openImport();
    await choose(user);
    // the first is held; a newer file's validate is sent and answered first
    void user.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(n).toBe(1));
    await choose(user, "{}", "b.json");
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(screen.getByTestId("plan")).toHaveTextContent("fresh-one"));
    release();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("plan")).not.toHaveTextContent("stale-one");
  });
});

describe("apply (OPR-13)", () => {
  async function validated() {
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByTestId("plan-changes");
    return user;
  }

  it("registers with the plan's revision as expected_revision, shows the new revision and refreshes meta and the catalog", async () => {
    const user = await validated();
    const metaReads = () => api.posts(/\/api\/console\/graphql$/).length;
    const catalogReads = () =>
      api.log.filter((r) => r.path.endsWith("/explorer/schema-catalog.json")).length;
    const [m0, c0] = [metaReads(), catalogReads()];
    await user.click(screen.getByRole("button", { name: "Apply" }));
    const done = await screen.findByTestId("schema-applied");
    expect(done).toHaveTextContent("Registered catalog");
    expect(done).toHaveTextContent('{"memory":2}');
    const [call] = api.posts(/\/api\/schema\/register$/);
    expect(call?.body).toEqual({ document: DOC, expected_revision: { memory: 1 } });
    await waitFor(() => {
      expect(metaReads()).toBeGreaterThan(m0);
      expect(catalogReads()).toBeGreaterThan(c0);
    });
    // applied once: the same plan cannot be applied again
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("a stale revision (409) shows the conflict, applies nothing and offers a fresh validate", async () => {
    api.on((r) => (isPost("register")(r) ? err(409, schemaWire.conflict()) : undefined));
    const user = await validated();
    await user.click(screen.getByRole("button", { name: "Apply" }));
    const conflict = await screen.findByTestId("schema-conflict");
    expect(conflict).toHaveTextContent("moved on");
    expect(screen.queryByTestId("schema-applied")).toBeNull();
    const before = api.posts(/\/api\/schema\/validate$/).length;
    await user.click(within(conflict).getByRole("button", { name: "Validate again" }));
    await waitFor(() => expect(api.posts(/\/api\/schema\/validate$/)).toHaveLength(before + 1));
    await waitFor(() => expect(screen.queryByTestId("schema-conflict")).toBeNull());
  });

  it("a 403 shows the reason and disables Apply, Validate and the file choice for this view", async () => {
    api.on((r) => (isPost("validate")(r) ? err(403, schemaWire.refused()) : undefined));
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    const why = await screen.findByTestId("schema-refused");
    expect(why).toHaveTextContent("No access");
    expect(why).toHaveTextContent("no_access");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByLabelText("UMF document")).toBeDisabled();
  });

  it("a host's authorize_schema refusal (403 without a reason) is shown and disables the same way", async () => {
    api.on((r) => (isPost("validate")(r) ? err(403, schemaWire.notAuthorized()) : undefined));
    const user = await openImport();
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByTestId("schema-refused")).toHaveTextContent("No access");
    expect(screen.getByLabelText("UMF document")).toBeDisabled();
  });

  it("a 403 on register disables a plan that was ok", async () => {
    api.on((r) => (isPost("register")(r) ? err(403, schemaWire.refused()) : undefined));
    const user = await validated();
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await screen.findByTestId("schema-refused");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("an expired token (401) asks the host to sign in again and does not disable import", async () => {
    api.on((r) => (isPost("validate")(r) ? err(401, schemaWire.tokenExpired()) : undefined));
    const onUnauthorized = vi.fn();
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />, { onUnauthorized });
    await user.click(await screen.findByRole("button", { name: "Import" }));
    await choose(user);
    await user.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByRole("button", { name: "Sign in again" })).toBeInTheDocument();
    expect(onUnauthorized).toHaveBeenCalled();
    expect(screen.getByLabelText("UMF document")).toBeEnabled();
  });
});

describe("the schema client", () => {
  it("is the only schema write path: a version probe, validate and register, never a URL with a document", () => {
    const c = createSchemaApi({ operateBase: "/api/operate", consoleBase: "/api/console" });
    expect(Object.keys(c).sort()).toEqual(["offered", "register", "schemaBase", "validate"]);
    expect(c.schemaBase).toBe("/api/schema");
  });

  it("omits expected_revision when the plan had none and maps errors to ApiError", async () => {
    const c = createSchemaApi({ operateBase: "/api/operate", consoleBase: "/api/console" });
    await c.register(DOC, null);
    expect(api.posts(/register$/)[0]?.body).toEqual({ document: DOC });
    api.on((r) => (isPost("register")(r) ? err(409, schemaWire.conflict()) : undefined));
    await expect(c.register(DOC, { memory: 1 })).rejects.toMatchObject({
      status: 409,
      kind: "revision_conflict",
    } satisfies Partial<ApiError>);
  });
});

describe("groupChanges", () => {
  it("groups by element in reading order and drops empty groups", () => {
    const g = groupChanges([
      { kind: "added", element: "action", name: "a", detail: "" },
      { kind: "added", element: "type", name: "t", detail: "" },
    ]);
    expect(g.map((x) => x.element)).toEqual(["type", "action"]);
  });
});
