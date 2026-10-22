// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { entryId, toEntries } from "../areas/umfBrowser";
import { defined } from "../test/defined";
import { asBob, client, control, type Person, server, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";

// The catalog UMF's schema browser is given (CONTRACT-009, GET explorer/schema-catalog.json), from
// the real dev host, raw and through the console's client. The console reads it with the host's
// headers and hands the entries to the package (src/integration/umf-source.int.test.tsx renders
// that; e2e/umf-explorer.spec.ts runs the real package in a browser).
withDevHost();

const REGISTERED = readFileSync(
  resolve(REPO_ROOT, "src/arras/conformance/module.umf.json"),
  "utf8",
);
const PATH = "/api/operate/explorer/schema-catalog.json";

interface Entry {
  id: string;
  title: string;
  category: string;
  path: string;
  text: string;
  format: string;
  description: string;
  schemaFormat: string;
}

async function catalog(headers: Record<string, string>, path = PATH) {
  const r = await fetch(`${server().base}${path}`, { headers });
  return {
    status: r.status,
    headers: r.headers,
    body: (await r.json()) as {
      version: number;
      entries: Entry[];
      error?: { type: string; reason?: string };
    },
  };
}
const as = (p: Person) => ({ "x-arras-user": p });

describe("the schema browser's catalog (OPR-11, CONTRACT-009)", () => {
  it("each module the viewer reads, with its registered document verbatim", async () => {
    const r = await catalog(as("alice"));
    expect(r.status).toBe(200);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(r.headers.get("access-control-allow-origin")).toBeNull();
    expect(r.body.version).toBe(1);
    expect(r.body.entries.map((e) => e.id)).toEqual(["arras:catalog"]);
    const [e] = r.body.entries;
    expect(e).toMatchObject({
      title: "catalog",
      category: "domain",
      path: "catalog.umf.json",
      format: "json",
      schemaFormat: "umf",
    });
    expect(defined(e, "the catalog entry").text).toBe(REGISTERED); // byte for byte what was registered, not a re-serialization
    expect(defined(e, "the catalog entry").description).toMatch(
      /^Registered at revision memory \d+; record store memory; replicas memory_replica\.$/,
    );
  });

  it("through the console's client: the same catalog, mapped to the package's entries field for field", async () => {
    const raw = (await catalog(as("bob"))).body;
    const got = await client("bob").schemaCatalog();
    expect(got).toEqual(raw);
    const entries = toEntries(got);
    expect(entries).toEqual([
      {
        id: "arras:catalog",
        title: "catalog",
        category: "domain",
        path: "catalog.umf.json",
        text: REGISTERED,
        format: "json",
        description: defined(raw.entries[0], "the first raw entry").description,
        schemaFormat: "umf",
      },
    ]);
    expect(entryId("catalog")).toBe(defined(entries[0], "the first entry").id);
  });

  it("every entry is inline: its text is in the catalog, with no source URL, pack manifest or companion to fetch on selection", async () => {
    // Package 1.1.2 stopped fetching unselected pack manifests and ontology companions; this
    // catalog gives the browser nothing of that kind, so a selection fetches nothing at all
    // (e2e/umf-explorer.spec.ts counts the frame's requests).
    const r = await catalog(as("alice"));
    for (const e of r.body.entries) {
      expect(typeof e.text).toBe("string");
      expect(Object.keys(e).sort()).toEqual([
        "category",
        "description",
        "format",
        "id",
        "path",
        "schemaFormat",
        "text",
        "title",
      ]);
      expect(e.path).not.toMatch(/^[a-z]+:|^\//); // a name for display, not a URL
    }
  });

  it("is per viewer: bob reads the module, an operator who reads none gets an empty catalog, carol is no operator, an unknown person is not signed in", async () => {
    expect((await catalog(as("bob"))).body.entries).toHaveLength(1);
    await asBob([], async () => {
      expect((await catalog(as("bob"))).body).toEqual({ version: 1, entries: [] });
      expect(await client("bob").schemaCatalog()).toEqual({ version: 1, entries: [] });
    });
    // carol and dave are not operators (CONTRACT-010): the operate surface refuses them before any work
    for (const who of ["carol", "dave"] as const) {
      const r = await catalog(as(who));
      expect([who, r.status, r.body]).toEqual([
        who,
        403,
        { error: "REFUSED", reason: "not_operator" },
      ]);
    }
    const nobody = await catalog(as("nobody"));
    expect(nobody.status).toBe(401);
    expect(nobody.body.error?.type).toBe("Refused");
  });

  it("names the person only by the host's header: a cookie names nobody", async () => {
    const r = await catalog({ cookie: "arras_user=dave" });
    expect(r.body.entries).toHaveLength(1); // the dev host's default person, not dave
  });

  it("an expired token is a 401 the client signals as sign in again, and restoring it mends the catalog", async () => {
    await control({ op: "expire", user: "bob" });
    let signedOut = 0;
    try {
      const r = await catalog(as("bob"));
      expect(r.status).toBe(401);
      expect(r.body.error).toMatchObject({ type: "Refused", reason: "token_expired" });
      expect(JSON.stringify(r.body)).not.toContain("token-bob");
      const e = await client("bob", () => signedOut++)
        .schemaCatalog()
        .catch((x: unknown) => x);
      expect(e).toMatchObject({ status: 401, kind: "sign_in" });
      expect(signedOut).toBe(1);
    } finally {
      await control({ op: "restore", user: "bob" });
    }
    expect((await client("bob").schemaCatalog()).entries).toHaveLength(1);
  });

  it("an outage of the record store is a 503, never an empty catalog", async () => {
    await control({ op: "outage", backend: "memory", reason: "unreachable" });
    try {
      const r = await catalog(as("alice"));
      expect(r.status).toBe(503);
      expect(r.body.error).toMatchObject({
        type: "Unavailable",
        reason: "unreachable",
        backend: "memory",
      });
      expect(
        await client("alice")
          .schemaCatalog()
          .catch((x: unknown) => x),
      ).toMatchObject({ status: 503, kind: "unavailable" });
    } finally {
      await control({ op: "outage", backend: "memory", reason: null });
    }
  });

  it("holds no entity data: a use case added through an action never appears", async () => {
    const flat = JSON.stringify((await catalog(as("alice"))).body);
    expect(flat).not.toContain("uc-pipeline-review"); // the demo's data
    expect(flat).not.toContain("Pattern extractor");
  });
});
