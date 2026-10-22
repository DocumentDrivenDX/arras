// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { QueryArea } from "../areas/QueryArea";
import { DevHost } from "../dev/DevHost";
import { defined } from "../test/defined";
import {
  call,
  conn,
  control,
  renderLive,
  renderLiveConsole,
  server,
  unique,
  type Who,
  withDevHost,
} from "./harness";

// The Query area (OPR-16, OPR-17) against the real dev host: real grants, real freshness, real cursors, real
// errors. The sandbox's demo catalog has 14 use cases and 11 solutions; the paging test adds more.
withDevHost();
afterEach(() => {
  window.location.hash = "";
  vi.restoreAllMocks();
});

const CODES = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 100";
// One use case: the paging test adds rows that sort before the demo's, so the console tests ask for a key.
const ONE =
  "SELECT u.code, u.name FROM catalog.UseCase u WHERE u.code = 'uc-pipeline' ORDER BY u.code LIMIT 1";
const input = () => screen.getByTestId("query-input") as HTMLTextAreaElement;
const entries = () => within(screen.getByTestId("query-history")).queryAllByTestId("history-entry");
const rowsText = () => screen.getAllByTestId("query-row").map((r) => r.textContent ?? "");

async function run(user: ReturnType<typeof userEvent.setup>, text: string) {
  fireEvent.change(input(), { target: { value: text } });
  await user.click(screen.getByRole("button", { name: "Run" }));
}

describe("a real query as different people (US-077)", () => {
  it("alice runs a query and reads the grid, its LATEST freshness from the record store and its revision", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    await run(user, CODES);
    expect(await screen.findByText("uc-pipeline")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["code", "name"]);
    expect(screen.getByTestId("query-count-rows")).toHaveTextContent(/^\d+ rows$/);
    const f = screen.getByTestId("freshness");
    expect(f).toHaveTextContent("LATEST");
    expect(f).toHaveTextContent("record: memory");
    expect(screen.getByTestId("query-info")).toHaveTextContent(/revision memory \d+/);
    // The same answer as the library gives the same person.
    const direct = await call("/api/operate/query", { module: "catalog", sql: CODES, limit: 100 });
    expect(direct.status).toBe(200);
    expect(rowsText()).toHaveLength((direct.body as { rows: unknown[] }).rows.length);
  });

  it("US-077-AC2: BULK is answered by the replica, and the freshness says so", async () => {
    const user = userEvent.setup();
    await control({ op: "feed" });
    renderLive(<QueryArea module="catalog" />);
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await run(user, CODES);
    await screen.findByText("uc-pipeline");
    const f = screen.getByTestId("freshness");
    expect(f).toHaveTextContent("BULK");
    expect(f).toHaveTextContent("replica: memory_replica");
  });

  it("x.* with RELATED_KEYS shows a relationship as its keys, and the appended fact columns", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    await run(
      user,
      "SELECT s.*, RELATED_KEYS(s.addresses, 100) AS addresses FROM catalog.Solution s WHERE s.code = 'sol-1' ORDER BY s.code LIMIT 1",
    );
    await screen.findByText("Pipeline extractor");
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads).toContain("addresses");
    expect(heads).toContain("_version");
    const row = defined(screen.getAllByTestId("query-row")[0], "a row");
    expect(within(row).getByText("uc-pipeline")).toBeInTheDocument();
    expect(within(row).getAllByText("null").length).toBeGreaterThan(0); // _original_author, _load_id
  });

  it("a made-up operator with the viewer role (read only) reads", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />, { name: "vic", role: "viewer" });
    await run(user, CODES);
    expect(await screen.findByText("uc-pipeline")).toBeInTheDocument();
  });

  it("carol is no operator: the surface answers 403 REFUSED not_operator before any work, and the area shows it", async () => {
    const user = userEvent.setup();
    const raw = await call("/api/operate/query", { module: "catalog", sql: CODES }, "carol");
    expect([raw.status, raw.body]).toEqual([403, { error: "REFUSED", reason: "not_operator" }]);
    renderLive(<QueryArea module="catalog" />, "carol");
    await run(user, CODES);
    const e = await screen.findByTestId("query-error");
    expect(e).toHaveTextContent("No access");
    expect(e).toHaveTextContent("not_operator");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("US-077-AC6: an operator with role none is told 'not found' exactly as for an unknown module", async () => {
    const user = userEvent.setup();
    const answers: string[] = [];
    for (const who of [
      { name: "nil", role: "none" },
      { name: "nix", role: "none" },
    ] as Who[]) {
      const view = renderLive(<QueryArea module="catalog" />, who);
      await run(user, CODES);
      const e = await screen.findByTestId("query-error");
      expect(e).toHaveTextContent("Not found");
      expect(e).toHaveTextContent("No such module or type, or you cannot read it");
      expect(screen.queryByRole("table")).toBeNull();
      answers.push(e.textContent ?? "");
      view.unmount();
    }
    // An unknown module answers the same words.
    renderLive(<QueryArea module="nothing" />);
    await run(user, "SELECT u.code FROM nothing.Here u ORDER BY u.code LIMIT 5");
    const unknown = (await screen.findByTestId("query-error")).textContent ?? "";
    expect(unknown.replace(/nothing/, "catalog")).toBe(answers[0]);
  });

  it("US-077-AC4: a query that does not parse lists its violations and shows no grid", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    await run(user, "DELETE FROM catalog.UseCase WHERE code = 'x'");
    const e = await screen.findByTestId("query-error");
    expect(e).toHaveTextContent("Invalid request");
    const v = within(e).getAllByRole("listitem");
    expect(v.length).toBeGreaterThan(0);
    expect(v[0]).toHaveTextContent(/sql/);
    expect(screen.queryByRole("table")).toBeNull();
    expect(e).not.toHaveTextContent("WHERE");
  });

  it("US-077-AC5: a construct the backend does not serve is shown with what is supported", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    await run(
      user,
      "SELECT u.code FROM catalog.UseCase u WHERE u.workArea = 'x' ORDER BY u.code LIMIT 5",
    );
    const e = await screen.findByTestId("query-error");
    expect(e).toHaveTextContent("Not supported");
    expect(e).toHaveTextContent("filter workArea (optional string)");
    expect(e).toHaveTextContent("a filter is on a required");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("US-077-AC5: an outage of the record store is a 503 naming the backend, never an empty grid, and mends", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    await run(user, CODES);
    await screen.findByText("uc-pipeline");
    await control({ op: "outage", backend: "memory", reason: "unreachable" });
    try {
      await user.click(screen.getByRole("button", { name: "Run" }));
      const e = await screen.findByTestId("query-error");
      expect(e).toHaveTextContent("Backend unavailable");
      expect(e).toHaveTextContent("memory is unavailable (unreachable)");
      expect(screen.queryByRole("table")).toBeNull();
      expect(screen.queryByText("No rows")).toBeNull();
    } finally {
      await control({ op: "outage", backend: "memory", reason: null });
    }
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("uc-pipeline")).toBeInTheDocument();
    expect(screen.queryByTestId("query-error")).toBeNull();
  });

  it("an expired token asks the host to sign in again and the history is kept", async () => {
    const user = userEvent.setup();
    const signIn = vi.fn();
    renderLive(<QueryArea module="catalog" />, "bob", { onUnauthorized: signIn });
    await run(user, CODES);
    await screen.findByText("uc-pipeline");
    await control({ op: "expire", user: "bob" });
    try {
      await user.click(screen.getByRole("button", { name: "Run" }));
      const e = await screen.findByTestId("query-error");
      expect(e).toHaveTextContent("Sign in again");
      expect(e).toHaveTextContent("history here is kept");
      expect(signIn).toHaveBeenCalled();
    } finally {
      await control({ op: "restore", user: "bob" });
    }
    // The same text and consistency twice in a row is one entry, with the latest time and outcome.
    expect(entries()).toHaveLength(1);
    expect(entries()[0]).toHaveTextContent("Sign in again (401)");
  });

  it("the client refuses nothing it should send: a 4,000-character query goes, 4,001 is stopped in the browser", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" />);
    const pad = " ".repeat(4000 - CODES.length);
    await run(user, CODES + pad);
    expect(await screen.findByText("uc-pipeline")).toBeInTheDocument();
    fireEvent.change(input(), { target: { value: `${CODES}${pad} ` } });
    expect(screen.getByRole("button", { name: "Run" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("query-too-long")).toBeInTheDocument();
    // The server's own answer to the same text is the 400 the console prevents.
    const over = await call("/api/operate/query", { module: "catalog", sql: `${CODES}${pad} ` });
    expect(over.status).toBe(400);
  });
});

describe("a page is the statement's own (US-077-AC3)", () => {
  it("a query of more than 100 rows shows 100, says the limit cut it, and the next page is a keyset", async () => {
    const user = userEvent.setup();
    const p = unique("pg");
    for (let b = 0; b < 2; b++) {
      const items = Array.from({ length: 60 }, (_, i) => ({
        code: `${p}-${b}-${String(i).padStart(2, "0")}`,
        name: `Paged ${b} ${i}`,
      }));
      expect(
        (await call("/api/operate/actions/catalog/AddUseCase/batch", { items, atomic: false }))
          .status,
      ).toBe(200);
    }
    renderLive(<QueryArea module="catalog" />);
    await run(user, "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 1000");
    await screen.findAllByTestId("query-row");
    expect(screen.getAllByTestId("query-row")).toHaveLength(100);
    expect(screen.getByTestId("query-truncated")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next page/ })).toBeNull();
    const first = rowsText();
    const last = defined(first.at(-1), "the last code");
    await run(
      user,
      `SELECT u.code FROM catalog.UseCase u WHERE u.code > '${last}' ORDER BY u.code LIMIT 1000`,
    );
    await waitFor(() => expect(rowsText()).not.toEqual(first));
    const second = rowsText();
    expect(second.length).toBeGreaterThan(0);
    expect(second.some((t) => first.includes(t))).toBe(false); // the keyset continues past the first page
    const all = [...first, ...second];
    expect(new Set(all).size).toBe(all.length);
    expect(all.length).toBe(14 + 120);
    expect(screen.queryByTestId("query-truncated")).toBeNull();
  });

  it("a smaller page size is honoured by the server, and says the limit cut it", async () => {
    const user = userEvent.setup();
    renderLive(<QueryArea module="catalog" pageSize={5} />);
    await run(user, CODES);
    await screen.findAllByTestId("query-row");
    expect(screen.getAllByTestId("query-row")).toHaveLength(5);
    expect(screen.getByTestId("query-truncated")).toBeInTheDocument();
  });
});

describe("history in the console, per person (US-078)", () => {
  it("survives moving between tabs, and choosing another person empties it", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/query";
    render(
      <DevHost
        apiBase={server().base}
        defaultMode="admin"
        extraHeaders={() => ({ origin: server().base })}
      />,
    );
    await screen.findByLabelText("Person");
    await screen.findByTestId("query-input");
    await run(user, ONE);
    await screen.findByText("uc-pipeline");
    await user.click(screen.getByRole("tab", { name: "Entities" }));
    await screen.findByTestId("entity-table");
    await user.click(screen.getByRole("tab", { name: "Query" }));
    await waitFor(() => expect(entries()).toHaveLength(1));
    expect(entries()[0]).toHaveTextContent("1 row");
    // choose another person (a made-up viewer): a new console, no history, no draft
    await user.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "vic");
    await user.selectOptions(screen.getByLabelText("Role"), "viewer");
    await user.click(screen.getByRole("button", { name: "Use" }));
    await waitFor(() => expect(screen.getByTestId("query-history-empty")).toBeInTheDocument());
    expect(input().value).toBe("");
    await run(user, ONE);
    await screen.findByText("uc-pipeline");
    expect(entries()).toHaveLength(1);
    // carol is no operator: the page shows Explore, with no console and no Query
    await user.selectOptions(screen.getByLabelText("Person"), "carol");
    await waitFor(() => expect(screen.queryByTestId("query-input")).toBeNull());
  });

  it("Run again runs as the person now viewed: alice's entry, run again as a person with no access, is answered as that person is", async () => {
    const user = userEvent.setup();
    let who: Who = "alice";
    window.location.hash = "#/catalog/query";
    render(<ArrasConsole {...conn(() => who)} hashRouting />);
    await screen.findByTestId("query-input");
    await run(user, ONE);
    await screen.findByText("uc-pipeline");
    who = { name: "nil", role: "none" }; // the host's headers now name another person
    await user.click(
      within(defined(entries()[0], "an entry")).getByRole("button", { name: /Run again/ }),
    );
    const e = await screen.findByTestId("query-error");
    expect(e).toHaveTextContent("Not found");
    expect(screen.queryByRole("table")).toBeNull();
    expect(input().value).toBe(ONE);
    expect(entries()).toHaveLength(1); // the same text again: one entry, now with the latest outcome
    expect(entries()[0]).toHaveTextContent("Not found (404)");
  });

  it("nothing is stored in the browser: not local or session storage, IndexedDB, a cookie or a URL", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const cookie = vi.fn();
    const desc = defined(
      Object.getOwnPropertyDescriptor(Document.prototype, "cookie"),
      "the cookie descriptor",
    );
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => desc.get?.call(document) ?? "",
      set: (v: string) => cookie(v),
    });
    const open = vi.fn();
    vi.stubGlobal("indexedDB", { open });
    const secret = "needle-7c1d";
    try {
      window.location.hash = "#/catalog/query";
      renderLiveConsole("alice", { hashRouting: true });
      await screen.findByTestId("query-input");
      await run(
        user,
        `SELECT u.code FROM catalog.UseCase u WHERE u.name = '${secret}' ORDER BY u.code LIMIT 5`,
      );
      await screen.findByText("No rows");
      await run(user, "DELETE FROM x");
      await screen.findByTestId("query-error");
      await run(user, ONE);
      await screen.findByText("uc-pipeline");
      expect(setItem).not.toHaveBeenCalled();
      expect(cookie).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
      expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
      expect(decodeURIComponent(window.location.href)).not.toContain(secret);
      expect(window.location.search).toBe("");
      expect(window.location.hash).toBe("#/catalog/query");
    } finally {
      delete (document as unknown as Record<string, unknown>).cookie;
      vi.unstubAllGlobals();
    }
  });
});
