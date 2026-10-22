// SPDX-License-Identifier: MIT OR Apache-2.0
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import { graphText, readGraph } from "../browser/graphFile";
import { client, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";

// Exporting the graph through the real operate surface (CONTRACT-003, Export; CONTRACT-009): the page
// shape, the operator gate, and that the file the UI writes is byte for byte the file the library
// reads and writes back.
withDevHost();

describe("POST /export against the real dev host", () => {
  it("answers a page of records as the viewer: entities first, then links, in a stable order", async () => {
    const page = await client("alice").export({ module: "catalog", limit: 500 });
    expect(page.items.length).toBeGreaterThan(0);
    expect(Object.keys(page).sort()).toEqual(["freshness", "items", "nextCursor", "omitted"]);
    const kinds = page.items.map((r) => ("type" in r ? "e" : "r")).join("");
    expect(kinds).toMatch(/^e+r*$/);
    const again = await client("alice").export({ module: "catalog", limit: 500 });
    expect(again.items).toEqual(page.items);
  });

  it("pages walk the same records as one read", async () => {
    const c = client("alice");
    const whole = await readGraph(c, "catalog");
    const seen: Record<string, unknown>[] = [];
    let after: string | undefined;
    do {
      const p = await c.export({ module: "catalog", limit: 3, ...(after ? { after } : {}) });
      seen.push(...p.items);
      after = p.nextCursor ?? undefined;
    } while (after);
    expect(seen).toEqual(whole.records);
  });

  it("is the operators' to read: a person who is not one is refused before anything is read", async () => {
    const e = await client("carol")
      .export({ module: "catalog" })
      .catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).status).toBe(403);
  });

  it("refuses a module the viewer cannot read as if it were not there, and a bad page", async () => {
    await expect(client("alice").export({ module: "nowhere" })).rejects.toBeInstanceOf(ApiError);
    await expect(client("alice").export({ module: "catalog", limit: 501 })).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("the file the UI writes", () => {
  it("is exactly the file the library reads and writes back", async () => {
    const graph = await readGraph(client("alice"), "catalog");
    const text = graphText(graph);
    const roundTrip = spawnSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        "import sys; from arras import graphfile; t = sys.stdin.read(); sys.stdout.write(graphfile.dumps(graphfile.loads(t)))",
      ],
      { cwd: REPO_ROOT, input: text, encoding: "utf8", timeout: 120_000 },
    );
    expect(roundTrip.stderr).toBe("");
    expect(roundTrip.status).toBe(0);
    expect(roundTrip.stdout).toBe(text);
  }, 150_000);
});
