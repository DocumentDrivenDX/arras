// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { searchQuery } from "../api/search";
import { GraphBrowser } from "../browser/GraphBrowser";
import { ArrasApp } from "../shell";
import { BrowserFake } from "../test/browserFake";
import {
  call,
  client,
  conn,
  control,
  type Person,
  testQueryClient,
  unique,
  withDevHost,
} from "./harness";
import { shapeDiff } from "./shapes";

// The Graph Browser against the real dev host (FEAT-011): the resolved view, the viewer's modes, the
// operator refusal and node pages read through the real console surface as the sandbox's people.
withDevHost();

afterEach(() => {
  window.location.hash = "";
});

const browser = (person: Person, hash = "#/explore/catalog") => {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(<GraphBrowser queryClient={testQueryClient()} {...conn(person)} />);
};

describe("the resolved view and the viewer's modes", () => {
  it("US-067-AC1: every type of the module carries a resolved view of the CONTRACT-010 shape", async () => {
    const meta = await client("carol").meta();
    const catalog = meta.modules.find((m) => m.name === "catalog");
    expect(catalog?.view?.title).toBeTruthy();
    for (const t of catalog?.entityTypes ?? []) {
      const v = t.view;
      expect(v, t.name).toBeDefined();
      expect(v?.label).toBeTruthy();
      expect(v?.tone).toMatch(/^(slate|blue|teal|green|amber|red|violet|rose)$/);
      expect(v?.title).toMatch(/\{\w+\}/);
      expect(v?.fields.map((f) => f.property)).toContain(t.key);
      expect(v?.sections.length).toBeGreaterThan(0);
      for (const r of v?.relationships ?? []) expect(r.label).toBeTruthy();
    }
  });

  it("the console's meta and the browser's meta are one read: actions and each type's view, in two requests, as alice", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    try {
      const meta = await client("alice").meta();
      const reads = spy.mock.calls.filter(([u]) => String(u).endsWith("/console/graphql"));
      expect(reads).toHaveLength(2); // the registry and the views, merged
      const catalog = meta.modules.find((m) => m.name === "catalog");
      expect(catalog?.actions.length).toBeGreaterThan(0);
      for (const a of catalog?.actions ?? []) expect(a.inputSpecs).toBeDefined();
      expect(catalog?.entityTypes.length).toBeGreaterThan(0);
      for (const t of catalog?.entityTypes ?? []) expect(t.view?.title, t.name).toMatch(/\{\w+\}/);
    } finally {
      spy.mockRestore();
    }
  });

  it("US-072-AC4, AC5: alice is offered both modes and carol Explore only; a person with no principal is refused", async () => {
    expect((await client("alice").viewer()).modes).toEqual(["user", "admin"]);
    expect((await client("carol").viewer()).modes).toEqual(["user"]);
    expect((await call("/api/operate/viewer", undefined, "nobody")).status).toBe(401);
  });

  it("US-072-AC5: every other operate endpoint refuses carol with 403 REFUSED not_operator, before any work", async () => {
    const refusal = { error: "REFUSED", reason: "not_operator" };
    const posts = [
      "/api/operate/audit/changes",
      "/api/operate/audit/loads",
      "/api/operate/actions/catalog/AddUseCase/validate",
      "/api/operate/actions/catalog/AddUseCase/invoke",
      "/api/operate/actions/catalog/AddUseCase/batch",
    ];
    for (const p of posts) {
      const r = await call(p, { inputs: {}, items: [] }, "carol");
      expect([p, r.status, r.body]).toEqual([p, 403, refusal]);
    }
    const catalog = await call("/api/operate/explorer/schema-catalog.json", undefined, "carol");
    expect([catalog.status, catalog.body]).toEqual([403, refusal]);
    // reading is unchanged: the console surface still serves carol what the backend lets her read
    expect((await client("carol").meta()).modules.map((m) => m.name)).toContain("catalog");
  });
});

describe("node pages as the sandbox's people", () => {
  it("US-067-AC1, AC4, AC5: a solution opens as a page with its title, attribution, freshness and a relationship to its use case", async () => {
    browser("carol", "#/explore/catalog/Solution/sol-extract");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Pattern extractor" }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId("gb-attribution")).toHaveTextContent("Last changed by");
    expect(screen.getByTestId("gb-freshness")).toHaveTextContent(/memory · .* LATEST/);
    const group = (await screen.findByRole("heading", { level: 3, name: /^Addresses/ })).closest(
      "section",
    ) as HTMLElement;
    expect(await within(group).findByRole("link", { name: /Pipeline review/ })).toHaveAttribute(
      "href",
      "#/explore/catalog/UseCase/uc-pipeline-review",
    );
  });

  it("US-068-AC2, AC6: following a link opens the use case, whose inverse relationship lists the solution again", async () => {
    const user = userEvent.setup();
    browser("carol", "#/explore/catalog/Solution/sol-extract");
    const group = (await screen.findByRole("heading", { level: 3, name: /^Addresses/ })).closest(
      "section",
    ) as HTMLElement;
    await user.click(await within(group).findByRole("link", { name: /Pipeline review/ }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Pipeline review" }),
    ).toBeInTheDocument();
    const back = (await screen.findByRole("heading", { level: 3, name: /Addressed by/ })).closest(
      "section",
    ) as HTMLElement;
    expect(
      await within(back).findByRole("link", { name: /Pattern extractor/ }),
    ).toBeInTheDocument();
  });

  it("US-067-AC6, US-071-AC3: an absent key and a viewer who may not read are the same page", async () => {
    const { unmount } = browser("carol", "#/explore/catalog/Solution/no-such-solution");
    // The page says the same words; only its way on differs, to a module the viewer can read.
    const words = () =>
      [...screen.getByTestId("gb-state").querySelectorAll("h1, p")].map((e) => e.textContent);
    await screen.findByTestId("gb-state");
    const missing = words();
    unmount();
    // dave has no access to any module
    browser("dave", "#/explore/catalog/Solution/sol-extract");
    await waitFor(() => expect(screen.getByTestId("gb-state")).toBeInTheDocument());
    expect(words()).toEqual(missing);
    expect(missing).toContain("Not available");
  });

  it("US-071-AC5: every request the browser made was a read as the viewer, with no key or person in a path or query", async () => {
    const seen: { method: string; url: string }[] = [];
    const real = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      seen.push({ method: init?.method ?? "GET", url: String(input) });
      return real(input, init);
    }) as typeof fetch;
    try {
      browser("carol", "#/explore/catalog/Solution/sol-extract");
      await screen.findAllByRole("link", { name: /Pipeline review/ });
    } finally {
      globalThis.fetch = real;
    }
    expect(seen.length).toBeGreaterThan(2);
    for (const r of seen) {
      expect(r.method).toBe("POST");
      expect(new URL(r.url).pathname).toMatch(/\/api\/console\/graphql(\/catalog)?$/);
      expect(r.url).not.toMatch(/sol-extract|carol|\?/);
    }
  });
});

describe("search through the real server (US-065, US-066)", () => {
  const box = () => screen.findByRole("textbox", { name: /Search/ });

  it("US-065-AC1, AC3: text finds hits across types in rank order with marked excerpts and the answer's freshness", async () => {
    const user = userEvent.setup();
    browser("carol");
    await user.type(await box(), "pipeline");
    const status = await screen.findByTestId("gb-status", {}, { timeout: 8000 });
    expect(status).toHaveTextContent(/^\d+ results for pipeline · ranked/);
    const hits = screen.getAllByRole("link").filter((l) => l.classList.contains("gb-hit"));
    expect(hits.length).toBeGreaterThanOrEqual(4);
    expect(hits[0]?.querySelector("mark")?.textContent?.toLowerCase()).toBe("pipeline");
    expect(screen.getByTestId("gb-answer-freshness")).toHaveTextContent("memory · LATEST");
    // US-066-AC3, AC4: chips count the hits of each type; choosing one keeps the others visible
    expect(screen.getByRole("radio", { name: /^Solution/ })).toHaveTextContent(/\d/);
    await user.click(screen.getByRole("radio", { name: /^Solution/ }));
    await waitFor(() => {
      const links = screen.getAllByRole("link").filter((l) => l.classList.contains("gb-hit"));
      expect(links.every((l) => l.textContent?.includes("Solution"))).toBe(true);
    });
    expect(screen.getByRole("radio", { name: /^Use case/ })).toBeInTheDocument();
  });

  it("US-065-AC4, AC5: no hit names the text; one character sends nothing", async () => {
    const user = userEvent.setup();
    browser("carol");
    await user.type(await box(), "zzzzqqq");
    expect(
      await screen.findByRole("heading", { name: "No results for “zzzzqqq”" }, { timeout: 8000 }),
    ).toBeInTheDocument();
    await user.clear(await box());
    await user.type(await box(), "z");
    expect(await screen.findByTestId("gb-hint", {}, { timeout: 4000 })).toHaveTextContent(
      "Type at least two characters",
    );
  });

  it("US-065-AC6: a type whose backend serves no search is named as not searched, the others still answer", async () => {
    const user = userEvent.setup();
    await control({ op: "search", backend: "memory", type: "catalog.UseCase", mode: "none" });
    try {
      browser("carol");
      await user.type(await box(), "pipeline");
      const banner = await screen.findByTestId("gb-banner", {}, { timeout: 8000 });
      expect(banner).toHaveTextContent("Use case was not searched.");
      expect(screen.getByRole("radio", { name: /^Use case/ })).toHaveTextContent("not searched");
      expect(
        screen.getAllByRole("link").some((l) => l.textContent?.includes("Pipeline extractor")),
      ).toBe(true);
    } finally {
      await control({ op: "search", backend: "memory", type: "catalog.UseCase", mode: null });
    }
  });
});

describe("a hub through the real server", () => {
  let hub = "";
  beforeAll(async () => {
    hub = unique("uc-hub");
    const made = await call("/api/operate/actions/catalog/AddUseCase/invoke", {
      inputs: { code: hub, name: "Hub use case", workArea: "hub" },
    });
    expect(made.status).toBe(200);
    const batch = await call("/api/operate/actions/catalog/AddSolution/batch", {
      items: Array.from({ length: 25 }, (_, i) => ({
        code: `${hub}-s${String(i).padStart(2, "0")}`,
        name: `Hub solution ${String(i).padStart(2, "0")}`,
        useCase: hub,
      })),
      atomic: true,
    });
    expect(batch.status).toBe(200);
  });

  it("US-068-AC3: 25 solutions are 20 labelled links with Show more for the next five; the picture draws all 25", async () => {
    const user = userEvent.setup();
    browser("alice", `#/explore/catalog/UseCase/${hub}`);
    const group = (await screen.findByRole("heading", { level: 3, name: /Addressed by/ })).closest(
      "section",
    ) as HTMLElement;
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(20));
    expect(group).toHaveTextContent("25");
    await user.click(within(group).getByRole("button", { name: /Show more/ }));
    await waitFor(() => expect(within(group).getAllByRole("link")).toHaveLength(25));
    await waitFor(() =>
      expect(screen.getByTestId("gb-picture-count")).toHaveTextContent("25 of 25 neighbours shown"),
    );
  });
});

describe("the shell on the real server", () => {
  it("US-072-AC1, AC4: alice gets the switch and carol does not, from the real /viewer", async () => {
    window.history.replaceState(null, "", "/");
    window.location.hash = "#/explore/catalog";
    const alice = render(<ArrasApp queryClient={testQueryClient()} {...conn("alice")} />);
    expect(await screen.findByRole("group", { name: "Mode" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explore" })).toHaveAttribute("aria-pressed", "true");
    alice.unmount();
    const carol = render(<ArrasApp queryClient={testQueryClient()} {...conn("carol")} />);
    await screen.findByRole("heading", { level: 1, name: /catalog/i });
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByRole("group", { name: "Mode" })).toBeNull();
    expect(carol.container.innerHTML).not.toMatch(/operate/i);
  });
});

describe("cross-mode links on the real server (FR-71)", () => {
  const sol = "#/explore/catalog/Solution/sol-extract";
  const app = (person: Person) => {
    window.history.replaceState(null, "", "/");
    window.location.hash = sol;
    return render(<ArrasApp queryClient={testQueryClient()} {...conn(person)} />);
  };

  it("alice's node page opens Operate at the entity's Entities, History and Actions", async () => {
    const alice = app("alice");
    const nav = within(await screen.findByTestId("gb-open-in-operate"));
    expect(nav.getByRole("link", { name: /Entities of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/entities/catalog.Solution/sol-extract",
    );
    expect(nav.getByRole("link", { name: /History of/ })).toHaveAttribute(
      "href",
      "#/operate/catalog/changes/catalog.Solution/sol-extract",
    );
    expect(nav.getByRole("link", { name: /Actions of/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/^#\/operate\/catalog\/actions\/[^?]+\?in\.\w+=sol-extract$/),
    );
    alice.unmount();
  });

  it("carol's node page has no link into Operate and no word of it", async () => {
    const carol = app("carol");
    await screen.findByRole("heading", { level: 1 });
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByTestId("gb-open-in-operate")).toBeNull();
    expect(carol.container.innerHTML).not.toMatch(/operate/i);
    carol.unmount();
  });
});

describe("drift guard: the browser's fake answers what the real server answers (CONTRACT-010)", () => {
  // The double installs a fetch stub; the real host is reached with the real fetch.
  const fake = () => {
    const f = new BrowserFake();
    vi.unstubAllGlobals();
    return f;
  };

  it("the resolved view of every type has the keys and JSON types of the contract", async () => {
    const q =
      "{ modules { name entityTypes { name view { declared label pluralLabel icon tone title summary sections { label properties collapsed } search fields { property label format hideWhenEmpty tones } relationships { field label hideWhenEmpty order } } } } }";
    const real = await call<{ data: { modules: { entityTypes: { view: unknown }[] }[] } }>(
      "/api/console/graphql",
      { query: q },
    );
    const mine = fake().answer(null, q).body as typeof real.body;
    const nullable = ["summary", "tones"];
    const realView = real.body.data.modules[0]?.entityTypes[0]?.view;
    const fakeView = mine.data.modules[0]?.entityTypes[0]?.view;
    expect(shapeDiff(realView, fakeView, { nullable })).toEqual([]);
  });

  it("the viewer's modes and the search page have the keys and JSON types of the contract", async () => {
    const viewer = await call("/api/operate/viewer", undefined, "alice");
    expect(shapeDiff(viewer.body, { user: "alice", modes: ["user", "admin"] })).toEqual([]);
    const mod = (await client("alice").meta()).modules.find((m) => m.name === "catalog");
    if (!mod) throw new Error("no catalog");
    const query = searchQuery(mod);
    const real = await call<{ data: { _search: unknown } }>(
      "/api/console/graphql/catalog",
      { query, variables: { text: "pipeline", types: null, limit: 50 } },
      "alice",
    );
    const mine = fake().answer("catalog", query, { text: "lumen", types: null, limit: 50 })
      .body as { data: { _search: unknown } };
    expect(real.status).toBe(200);
    const nullable = ["backend", "excerpt"];
    expect(
      shapeDiff(real.body.data._search, mine.data._search, { nullable, open: [".entity"] }),
    ).toEqual([]);
  });
});
