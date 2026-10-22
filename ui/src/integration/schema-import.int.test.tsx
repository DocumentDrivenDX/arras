// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createSchemaApi } from "../api/client";
import { ArrasProvider } from "../api/context";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { defined } from "../test/defined";
import {
  call,
  client,
  conn,
  renderLive,
  renderLiveConsole,
  server,
  testQueryClient,
  withDevHost,
} from "./harness";
import { registered, withProperty } from "./umf";

// Schema import (OPR-12, OPR-13) against the real dev host: people with the `schema` grant plan and register,
// others are refused by the backend, and the schema views follow. No fetch double.
withDevHost();

const ANA = { name: "ana", role: "schema author" };
const VIC = { name: "vic", role: "viewer" };
const user = () => userEvent.setup();
const file = (text: string, name = "catalog.umf.json") =>
  new File([text], name, { type: "application/json" });

async function openImport(who: Parameters<typeof renderLive>[1] = ANA) {
  const u = user();
  renderLive(<SchemaBrowser module="catalog" />, who);
  await u.click(await screen.findByRole("button", { name: "Import" }));
  return u;
}
async function validate(u: ReturnType<typeof userEvent.setup>, text: string) {
  await u.upload(screen.getByLabelText("UMF document"), file(text));
  await u.click(screen.getByRole("button", { name: "Validate" }));
}

describe("import against the dev host", () => {
  it("not mounted: no import control is rendered (the version probe is a 404 or not the surface's JSON)", async () => {
    // Nothing is served at this base on the dev host (it answers the page or a 404, never `{contracts: {schema}}`).
    renderLiveConsole(ANA, { schemaBase: `${server().base}/api/not-mounted` });
    await screen.findByTestId("schema");
    expect(
      await createSchemaApi({
        ...conn(ANA),
        schemaBase: `${server().base}/api/not-mounted`,
      }).offered(),
    ).toBe(false);
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
    expect(screen.queryByTestId("schema-import")).toBeNull();
  });

  it("the version probe finds the mounted surface", async () => {
    expect(
      await createSchemaApi({ ...conn(ANA), schemaBase: `${server().base}/api/schema` }).offered(),
    ).toBe(true);
  });

  it("a viewer is refused by the backend: the reason is shown and Apply and import are disabled", async () => {
    const u = await openImport(VIC);
    await validate(u, withProperty(await registered("alice"), "viewerNote", { required: false }));
    const why = await screen.findByTestId("schema-refused");
    expect(why).toHaveTextContent("No access");
    expect(why).toHaveTextContent("no_access");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByLabelText("UMF document")).toBeDisabled();
  });

  it("an incompatible document (a required property while records exist) shows the rule and offers no Apply", async () => {
    const u = await openImport(ANA);
    await validate(u, withProperty(await registered("alice"), "mustHave", { required: true }));
    const violations = await screen.findByTestId("plan-violations");
    expect(violations).toHaveTextContent("incompatible_change");
    expect(violations).toHaveTextContent(/records exist/);
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
    // nothing was applied: the registered document is unchanged
    expect(await registered("alice")).not.toContain("mustHave");
  });

  it("a document that does not parse shows its violation (400), no Apply", async () => {
    const u = await openImport(ANA);
    await validate(u, "this is not json");
    expect(await screen.findByTestId("schema-invalid")).toHaveTextContent("invalid_document");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });

  it("a stale revision shows the conflict and offers a fresh validate", async () => {
    const u = await openImport(ANA);
    const base = await registered("alice");
    const winner = withProperty(base, "winner", { required: false });
    await validate(u, withProperty(winner, "raced", { required: false }));
    await screen.findByTestId("plan-changes");
    // someone else registers first (a change this document keeps), so the plan's revision no longer holds
    const other = await call("/api/schema/register", { document: winner }, ANA);
    expect(other.status).toBe(200);
    await u.click(screen.getByRole("button", { name: "Apply" }));
    const conflict = await screen.findByTestId("schema-conflict");
    expect(conflict).toHaveTextContent("moved on");
    expect(await registered("alice")).not.toContain("raced");
    await u.click(within(conflict).getByRole("button", { name: "Validate again" }));
    // against the new revision the plan is computed afresh: only `raced` is still to add
    await waitFor(() => expect(screen.queryByTestId("schema-conflict")).toBeNull());
    expect(await screen.findByTestId("plan-property")).toHaveTextContent("catalog.UseCase.raced");
    expect(screen.getByTestId("plan-property")).not.toHaveTextContent("winner");
  });

  it("a schema author validates and applies an optional property: the revision is shown and the schema view shows the new property", async () => {
    const u = await openImport(ANA);
    const base = await registered("alice");
    await validate(u, withProperty(base, "notes", { required: false }));
    const plan = await screen.findByTestId("plan");
    expect(await within(plan).findByTestId("plan-property")).toHaveTextContent(
      "addedcatalog.UseCase.notes",
    );
    const before = (await client(ANA).meta()).modules[0]?.revision;
    await u.click(screen.getByRole("button", { name: "Apply" }));
    const done = await screen.findByTestId("schema-applied");
    expect(done).toHaveTextContent("Registered catalog");
    const after = defined((await client(ANA).meta()).modules[0], "the module");
    expect(after.revision).not.toEqual(before);
    expect(done).toHaveTextContent(JSON.stringify(after.revision));
    // the schema views follow: the live registry card has the property, and the revision chip the new revision
    await u.click(screen.getByRole("button", { name: "Live registry" }));
    const type = await screen.findByTestId("type-catalog.UseCase");
    await waitFor(() => expect(type).toHaveTextContent("notes"));
    expect(screen.getByText(/revision:/)).toHaveTextContent(JSON.stringify(after.revision));
    // attributed to ana, and the document read back is what was applied
    expect(await registered("alice")).toBe(withProperty(base, "notes", { required: false }));
    // the same document again changes nothing
    await u.click(screen.getByRole("button", { name: "Import" }));
    await validate(u, withProperty(base, "notes", { required: false }));
    expect(await screen.findByTestId("plan-unchanged")).toBeInTheDocument();
  });

  it("an expired token is a sign-in, not a refusal, and mending it restores the view", async () => {
    const { control } = await import("./harness");
    let signIns = 0;
    const u = user();
    render(
      <ArrasProvider queryClient={testQueryClient()} {...conn(ANA, () => void signIns++)}>
        <SchemaBrowser module="catalog" />
      </ArrasProvider>,
    );
    await u.click(await screen.findByRole("button", { name: "Import" }));
    await control({ op: "expire", user: "ana" });
    try {
      await validate(u, await registered("alice"));
      expect((await screen.findAllByText("Sign in again")).length).toBeGreaterThan(0);
      expect(signIns).toBeGreaterThan(0);
      expect(screen.getByLabelText("UMF document")).toBeEnabled();
    } finally {
      await control({ op: "restore", user: "ana" });
    }
  });
});
