// SPDX-License-Identifier: MIT OR Apache-2.0
// The one search read (SD-013 Search): one key family, one text check, a limit that makes the
// palette's and the browser's answers separate entries, and an applied action that reaches it.
import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { ArrasProvider, type ProviderProps } from "../api/context";
import {
  checkText,
  invalidateSearch,
  PALETTE_LIMIT,
  SEARCH_LIMIT,
  searchKey,
  searchQuery,
  useEntitySearch,
  useSearch,
} from "../api/search";
import { ActionForm } from "../areas/ActionForm";
import { useAction } from "../browser/useAction";
import { catalog, type FakeApi, json, receipt, seedCatalog, stage, validation } from "./fake";

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const client = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Number.POSITIVE_INFINITY } },
  });
const provider = (qc: QueryClient) => ({ queryClient: qc }) as ProviderProps;
const within = (qc: QueryClient, ui: ReactNode) =>
  render(createElement(ArrasProvider, provider(qc), ui));
const searches = () =>
  api.posts(/\/graphql\/catalog$/).filter((r) => r.body.query.includes("_search"));
const limits = () => searches().map((r) => (r.body.variables as { limit: number }).limit);

function Browser({ text, limit }: { text: string; limit?: number }) {
  const q = useSearch(catalog(), text, [], true, limit);
  return createElement(
    "p",
    { "data-testid": "b" },
    `${q.data?.text ?? "none"} ${q.isPlaceholderData ? "placeholder" : "fresh"} ${q.data?.hits.length ?? 0}`,
  );
}

function Palette({ text }: { text: string }) {
  const s = useEntitySearch(catalog(), text, true);
  return createElement("p", { "data-testid": "p" }, `${s.current ? "current" : "stale"}`);
}

describe("one search read for every surface", () => {
  it("has one text check, with the contract's bounds", () => {
    expect(checkText("  lumen   alert ")).toEqual({ ok: true, text: "lumen alert" });
    expect(checkText("h")).toEqual({ ok: false, reason: "short" });
    expect(checkText("a b c d e f g")).toEqual({ ok: false, reason: "words" });
  });

  it("keys every search under [gb, search] with the limit last, sorted types", () => {
    const m = catalog();
    const k = searchKey(m, "lumen", ["UseCase", "Solution"], 8);
    expect(k.slice(0, 2)).toEqual(["gb", "search"]);
    expect(k.slice(2, 3)).toEqual([m.name]);
    expect(k.at(-3)).toBe("lumen");
    expect(k.at(-2)).toEqual(["Solution", "UseCase"]);
    expect(k.at(-1)).toBe(8);
  });

  it("selects the full shape: score, matched, entity with its badge fragments, counts, freshness", () => {
    const q = searchQuery(catalog());
    for (const part of [
      "score",
      "matched",
      "entity { key type",
      "counts",
      "notSearched",
      "freshness",
    ])
      expect(q).toContain(part);
  });

  it("asks 50 for the browser and 8 for the palette, each its own cache entry", async () => {
    const qc = client();
    within(
      qc,
      createElement(
        "div",
        null,
        createElement(Browser, { text: "lumen" }),
        createElement(Palette, { text: "lumen" }),
      ),
    );
    await waitFor(() => expect(screen.getByTestId("p")).toHaveTextContent("current"));
    await waitFor(() => expect(screen.getByTestId("b")).toHaveTextContent(/lumen fresh/));
    expect([...limits()].sort((a, b) => a - b)).toEqual([PALETTE_LIMIT, SEARCH_LIMIT]);
    const keys = qc
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey);
    expect(keys).toHaveLength(2);
    for (const k of keys) expect(k.slice(0, 2)).toEqual(["gb", "search"]);
    expect(new Set(keys.map((k) => k.at(-1)))).toEqual(new Set([PALETTE_LIMIT, SEARCH_LIMIT]));
  });

  it("never shows an earlier text's answer for a later one as current", async () => {
    const qc = client();
    const { rerender } = within(qc, createElement(Browser, { text: "lumen" }));
    await waitFor(() => expect(screen.getByTestId("b")).toHaveTextContent(/^lumen fresh/));
    rerender(createElement(ArrasProvider, provider(qc), createElement(Browser, { text: "logs" })));
    // The previous answer stays, marked as a placeholder, until the new text's own answer lands.
    expect(screen.getByTestId("b")).toHaveTextContent(/^lumen placeholder/);
    await waitFor(() => expect(screen.getByTestId("b")).toHaveTextContent(/^logs fresh/));
  });

  it("an applied action in the console invalidates the search read", async () => {
    const user = userEvent.setup();
    api.on((r) => (r.path.endsWith("/validate") ? json(200, validation()) : undefined));
    api.on((r) => (r.path.endsWith("/invoke") ? json(200, receipt()) : undefined));
    const qc = client();
    const key = searchKey(catalog(), "lumen", [], SEARCH_LIMIT);
    qc.setQueryData(key, {
      text: "lumen",
      hits: [],
      counts: [],
      notSearched: [],
      truncated: false,
    });
    expect(qc.getQueryState(key)?.isInvalidated).toBe(false);
    within(
      qc,
      createElement(ActionForm, {
        module: "catalog",
        action: "catalog.CorrectSolution",
        prefill: { solution: "sol-1", level: "partial" },
      }),
    );
    await user.click(await screen.findByTestId("validate"));
    await user.click(await screen.findByTestId("confirm"));
    await screen.findByTestId("receipt");
    expect(qc.getQueryState(key)?.isInvalidated).toBe(true);
  });

  it("an applied action in Explore invalidates the search read", async () => {
    const user = userEvent.setup();
    api.on((r) => (r.path.endsWith("/validate") ? json(200, validation()) : undefined));
    api.on((r) => (r.path.endsWith("/invoke") ? json(200, receipt()) : undefined));
    const qc = client();
    const key = searchKey(catalog(), "lumen", [], SEARCH_LIMIT);
    qc.setQueryData(key, {
      text: "lumen",
      hits: [],
      counts: [],
      notSearched: [],
      truncated: false,
    });
    expect(qc.getQueryState(key)?.isInvalidated).toBe(false);
    function Apply() {
      const a = useAction(catalog());
      return createElement(
        "button",
        {
          type: "button",
          "data-testid": "apply",
          onClick: () =>
            void a.run("catalog.CorrectSolution", { solution: "sol-1", level: "partial" }),
        },
        "apply",
      );
    }
    within(qc, createElement(Apply));
    await user.click(screen.getByTestId("apply"));
    await waitFor(() => expect(qc.getQueryState(key)?.isInvalidated).toBe(true));
  });

  it("invalidateSearch marks every search entry, and nothing else under gb", async () => {
    const qc = client();
    const a = searchKey(catalog(), "lumen", [], SEARCH_LIMIT);
    const b = searchKey(catalog(), "lumen", [], PALETTE_LIMIT);
    qc.setQueryData(a, 1);
    qc.setQueryData(b, 2);
    qc.setQueryData(["gb", "list", "catalog"], 3);
    await invalidateSearch(qc);
    expect(qc.getQueryState(a)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(b)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(["gb", "list", "catalog"])?.isInvalidated).toBe(false);
  });
});
