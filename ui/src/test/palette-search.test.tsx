// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasProvider } from "../api/context";
import { searchQuery, useEntitySearch } from "../api/search";
import { catalog, type FakeApi, json, stage } from "./fake";
import { qc, renderPart } from "./render";

let api: FakeApi;
beforeEach(() => {
  api = stage();
});

type Page = { hits: unknown[]; notSearched: unknown[]; truncated: boolean };
const page = (over: Partial<Page> = {}): Page => ({
  hits: [{ type: "Solution", key: "sol-1", label: "Lumen (S-017)", excerpt: null }],
  notSearched: [],
  truncated: false,
  ...over,
});
const answer = (reply: (text: string) => unknown) =>
  api.on((r) =>
    r.path.endsWith("/graphql/catalog") && r.body.query.includes("_search")
      ? json(200, {
          data: null,
          ...(reply(String(textOf(r.body.variables))) as object),
        })
      : undefined,
  );
const textOf = (v: unknown) => String((v as { text?: string }).text);
const searches = () =>
  api.posts(/\/graphql\/catalog$/).filter((r) => r.body.query.includes("_search"));

function Probe({ text, enabled = true }: { text: string; enabled?: boolean }) {
  const s = useEntitySearch(catalog(), text, enabled);
  return (
    <div>
      <p data-testid="state">
        {s.error ? `error:${s.error.code}` : s.data ? `hits:${s.data.hits.length}` : "none"}
        {s.current ? " current" : " stale"}
        {s.data?.truncated ? " truncated" : ""}
        {s.data?.notSearched.map((n) => ` skipped:${n.type}:${n.reason}`).join("")}
      </p>
      <p data-testid="check">{s.check.ok ? "ok" : s.check.reason}</p>
    </div>
  );
}
const state = () => screen.getByTestId("state").textContent ?? "";

describe("the palette's search read", () => {
  it("asks once, after a pause, with the text in the POST body only", async () => {
    answer(() => ({ data: { _search: page() } }));
    renderPart(<Probe text="lumen" />);
    expect(searches()).toHaveLength(0); // debounced: nothing yet
    await waitFor(() => expect(state()).toBe("hits:1 current"));
    expect(searches()).toHaveLength(1);
    const [req] = searches();
    expect(req?.method).toBe("POST");
    expect(req?.url).not.toMatch(/lumen/i);
    expect(req?.url).not.toContain("?");
    expect(req?.body.query).toBe(searchQuery(catalog()));
    expect(req?.body.variables).toMatchObject({ text: "lumen", limit: 8, types: null });
    expect(JSON.stringify(req?.headers)).not.toMatch(/lumen/i);
  });

  it("asks nothing for text that cannot be searched, or when disabled", async () => {
    answer(() => ({ data: { _search: page() } }));
    const client = qc();
    const { rerender } = render(
      <ArrasProvider queryClient={client}>
        <Probe text="h" />
      </ArrasProvider>,
    );
    await new Promise((r) => setTimeout(r, 350));
    expect(screen.getByTestId("check")).toHaveTextContent("short");
    expect(searches()).toHaveLength(0);
    rerender(
      <ArrasProvider queryClient={client}>
        <Probe text="lumen" enabled={false} />
      </ArrasProvider>,
    );
    await new Promise((r) => setTimeout(r, 350));
    expect(searches()).toHaveLength(0);
  });

  it("keeps the previous answer, marked stale, while the next loads, and never shows it as the new text's", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    api.on(async (r) => {
      if (!r.path.endsWith("/graphql/catalog") || !r.body.query.includes("_search"))
        return undefined;
      const text = textOf(r.body.variables);
      if (text === "second") await gate;
      return json(200, {
        data: {
          _search: page({
            hits:
              text === "first" ? [{ type: "Solution", key: "a", label: "A", excerpt: null }] : [],
          }),
        },
      });
    });
    const client = qc();
    const { rerender } = render(
      <ArrasProvider queryClient={client}>
        <Probe text="first" />
      </ArrasProvider>,
    );
    await waitFor(() => expect(state()).toBe("hits:1 current"));
    rerender(
      <ArrasProvider queryClient={client}>
        <Probe text="second" />
      </ArrasProvider>,
    );
    await waitFor(() =>
      expect(searches().map((r) => textOf(r.body.variables))).toContain("second"),
    );
    expect(state()).toBe("hits:1 stale");
    await act(async () => release());
    await waitFor(() => expect(state()).toBe("hits:0 current"));
  });

  it("reports truncated and each type that was not searched", async () => {
    answer(() => ({
      data: {
        _search: page({
          truncated: true,
          notSearched: [{ type: "UseCase", reason: "no_capability" }],
        }),
      },
    }));
    renderPart(<Probe text="lumen" />);
    await waitFor(() => expect(state()).toContain("truncated"));
    expect(state()).toContain("skipped:UseCase:no_capability");
  });

  it.each(["BAD_QUERY", "UNSUPPORTED", "UNAVAILABLE"])(
    "an %s answer is an error code, not a throw of words",
    async (code) => {
      answer(() => ({ errors: [{ message: "secret words echoed", extensions: { code } }] }));
      renderPart(<Probe text="lumen" />);
      await waitFor(() => expect(state()).toContain(`error:${code}`));
      expect(document.body.textContent).not.toContain("secret words");
    },
  );
});

describe("the text stays out of every channel but the POST body", () => {
  it("writes nothing to the console, the URL, history or storage", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((k) =>
      vi.spyOn(console, k).mockImplementation(() => undefined),
    );
    answer(() => ({ errors: [{ message: "m", extensions: { code: "BAD_QUERY" } }] }));
    const hash = window.location.hash;
    renderPart(<Probe text="needle-text" />);
    await waitFor(() => expect(state()).toContain("error:BAD_QUERY"));
    const seen = spies.map((x) => x.mock.calls.flat().join(" ")).join("\n");
    for (const x of spies) x.mockRestore();
    expect(seen).not.toContain("needle-text");
    expect(window.location.href).not.toContain("needle");
    expect(window.location.hash).toBe(hash);
    expect(JSON.stringify({ ...localStorage })).not.toContain("needle");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("needle");
    expect(JSON.stringify(window.history.state)).not.toContain("needle");
    for (const r of api.log) {
      expect(r.url).not.toContain("needle");
      if (r.body.query?.includes("_search"))
        expect(JSON.stringify(r.body.query)).not.toContain("needle");
    }
  });
});
