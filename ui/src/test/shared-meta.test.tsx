// SPDX-License-Identifier: MIT OR Apache-2.0
import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { createClient } from "../api/client";
import { GraphBrowser } from "../browser/GraphBrowser";
import { findQualified } from "../browser/meta";
import { planLabels, readLabels, targetOf } from "../browser/planner";
import { planRefLabels, readRefLabels, refId } from "../lib/relLabels";
import { titleOf } from "../lib/template";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { defined } from "./defined";

// One meta read and one title source (SD-013, Entity titles and labels): the console and the browser
// share the ["meta"] query, and an entity has the same name in both.
let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "#/explore/catalog";
  fake = stageBrowser();
});
afterEach(() => {
  window.location.hash = "";
});

const metaReads = () =>
  fake.requests.filter((r) => r.method === "POST" && /\/api\/console\/graphql$/.test(r.path));

describe("one meta read for both modes", () => {
  it("makes the two requests of one read, once, when the browser and the console share a client", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 5_000 } },
    });
    render(
      <>
        <GraphBrowser queryClient={queryClient} />
        <ArrasConsole queryClient={queryClient} />
      </>,
    );
    expect(await screen.findByText("Use cases, solutions and products")).toBeVisible();
    expect((await screen.findAllByText("Query")).length).toBeGreaterThan(0); // the console has read it too
    const reads = metaReads();
    // the registry and the views: two requests, not one read per mode
    expect(reads.filter((r) => r.body.query.includes("declared"))).toHaveLength(1);
    expect(reads.filter((r) => r.body.query.includes("actions {"))).toHaveLength(1);
    expect(queryClient.getQueryData(["meta"])).toBeDefined();
  });
});

describe("one title source", () => {
  it("names an entity alike in the console's chips and the browser's node title", async () => {
    const client = createClient({ operateBase: "/api/operate", consoleBase: "/api/console" });
    const meta = await client.meta();
    const m = defined(meta.modules.find((x) => x.name === "catalog"));
    const refs = ["catalog.Solution", "catalog.UseCase"].flatMap((type) =>
      (fake.rows[type] ?? []).map((row) => ({ module: "catalog", type, key: row.key })),
    );
    expect(refs.length).toBeGreaterThan(1);

    const chips: Record<string, string> = {};
    for (const plan of planRefLabels(m, refs)) {
      const r = await client.moduleQuery<Record<string, Record<string, unknown> | null>>(
        m.name,
        plan.query,
        plan.variables,
      );
      Object.assign(chips, readRefLabels(plan, r.data));
    }

    const nodes: Record<string, string> = {};
    for (const plan of planLabels(refs.map(targetOf), (q) => findQualified(meta, q))) {
      const r = await client.moduleQuery<Record<string, Record<string, unknown> | null>>(
        plan.module,
        plan.query,
        plan.variables,
      );
      const answer = readLabels(plan, { data: r.data, errors: r.errors }, (t, row) =>
        titleOf(defined(findQualified(meta, t.type)).view.title, row, t.key),
      );
      for (const [id, s] of Object.entries(answer)) if (s.state === "ok") nodes[id] = s.title;
    }

    expect(Object.keys(nodes)).toHaveLength(refs.length);
    for (const r of refs) {
      const title = defined(nodes[refId(r)]);
      // a chip shows no label when the title is only the key
      expect(chips[refId(r)] ?? r.key).toBe(title);
    }
    expect(nodes["catalog.Solution:sol-1"]).toBe("Lumen alert correlation (S-017)");
  });
});
