// SPDX-License-Identifier: MIT OR Apache-2.0
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { QueryArea } from "../areas/QueryArea";
import { CELL_MAX_CHARS, QueryGrid, TITLE_MAX_CHARS } from "../areas/QueryGrid";
import { QuerySessionProvider, useQuerySessionState } from "../areas/queryHistory";
import { defined } from "./defined";
import { err, type FakeApi, json, seedCatalog, stage, wire } from "./fake";
import { renderConsole, renderPart } from "./render";

// The Query area (OPR-16, OPR-17; US-077, US-078) against the fetch double, whose /query answers with the
// server's statuses and bodies (src/test/fake.ts, tied to the real host by drift.int.test.ts).

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});
afterEach(() => vi.restoreAllMocks());

const SQL = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 50";
const queries = () => api.posts(/\/operate\/query$/);
const input = () => screen.getByTestId("query-input") as HTMLTextAreaElement;
const setText = (text: string) => fireEvent.change(input(), { target: { value: text } });
const area = (pageSize?: number) => renderPart(<QueryArea module="catalog" pageSize={pageSize} />);

async function run(user: ReturnType<typeof userEvent.setup>, text = SQL) {
  setText(text);
  await user.click(screen.getByRole("button", { name: "Run" }));
}
const first = () => defined(entries()[0], "the newest entry");
const row = <T,>(list: T[], i: number): T => defined(list[i], `item ${i}`);
const entries = () => within(screen.getByTestId("query-history")).queryAllByTestId("history-entry");

describe("Query: a grid (US-077)", () => {
  it("US-077-AC1: runs the text as a POST body and shows one column per selected column, the rows, count, freshness and revision", async () => {
    const user = userEvent.setup();
    area();
    await run(user);
    expect(await screen.findByText("uc-1")).toBeInTheDocument();
    expect(queries()).toHaveLength(1);
    expect(queries()[0]?.body).toEqual({
      module: "catalog",
      sql: SQL,
      consistency: "latest",
      limit: 100,
    });
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["code", "name"]);
    expect(screen.getAllByTestId("query-row")).toHaveLength(3);
    expect(screen.getByTestId("query-count-rows")).toHaveTextContent("3 rows");
    const info = screen.getByTestId("query-info");
    expect(within(info).getByTestId("freshness")).toHaveTextContent("LATEST");
    expect(within(info).getByTestId("freshness")).toHaveTextContent("record: memory");
    expect(within(info).getByTestId("freshness")).toHaveTextContent("position fake:3");
    expect(info).toHaveTextContent("revision memory 1");
    expect(screen.queryByText("truncated")).toBeNull();
  });

  it("US-077-AC2: BULK is sent as bulk and the freshness names the replica", async () => {
    const user = userEvent.setup();
    area();
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await run(user);
    await screen.findByText("uc-1");
    expect(queries()[0]?.body.consistency).toBe("bulk");
    const f = screen.getByTestId("freshness");
    expect(f).toHaveTextContent("BULK");
    expect(f).toHaveTextContent("replica: memory_replica");
  });

  it("US-077-AC7: the text is only in a POST body: not in a URL, the hash, an error message or storage", async () => {
    const user = userEvent.setup();
    const secret = "s3cret-needle-in-a-query";
    api.on((r) => (/\/operate\/query$/.test(r.path) ? err(400, wire.invalidQuery()) : undefined));
    area();
    await run(user, `SELECT u.code FROM catalog.UseCase u WHERE u.name = '${secret}'`);
    await screen.findByTestId("query-error");
    const q = defined(queries()[0], "the request");
    expect(q.method).toBe("POST");
    expect(q.url).not.toContain(secret);
    expect(JSON.stringify(q.body)).toContain(secret);
    expect(api.log.filter((r) => r.url.includes(secret) || r.url.includes("SELECT"))).toEqual([]);
    expect(window.location.href).not.toContain(secret);
    // The error shows the library's violations, not the text.
    expect(screen.getByTestId("query-error")).not.toHaveTextContent(secret);
  });

  it("runs with Ctrl+Enter and with Cmd+Enter, and a blank editor runs nothing", async () => {
    const user = userEvent.setup();
    area();
    expect(screen.getByRole("button", { name: "Run" })).toHaveAttribute("aria-disabled", "true");
    setText(SQL);
    await user.click(input());
    await user.keyboard("{Control>}{Enter}{/Control}");
    await screen.findByText("uc-1");
    expect(queries()).toHaveLength(1);
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    await waitFor(() => expect(queries()).toHaveLength(2));
    // A plain Enter is a newline, not a run.
    await user.keyboard("{Enter}");
    expect(queries()).toHaveLength(2);
  });

  it("the editor is a labelled monospace textarea with spellcheck off, and there is no way to write", () => {
    area();
    const t = input();
    expect(t.tagName).toBe("TEXTAREA");
    expect(t).toHaveAttribute("spellcheck", "false");
    expect(t.className).toContain("arras-mono");
    expect(screen.getByRole("group", { name: "Consistency" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|save|delete|update|insert/i })).toBeNull();
  });

  it("counts characters against 4,000 and blocks Run over the bound, with a message, sending nothing", async () => {
    const user = userEvent.setup();
    area();
    setText("x".repeat(4000));
    expect(screen.getByTestId("query-chars")).toHaveTextContent("4,000 / 4,000");
    expect(screen.getByRole("button", { name: "Run" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByTestId("query-too-long")).toBeNull();
    setText("x".repeat(4001));
    expect(screen.getByTestId("query-chars")).toHaveTextContent("4,001 / 4,000");
    expect(screen.getByTestId("query-too-long")).toHaveTextContent("1 characters over");
    expect(screen.getByRole("button", { name: "Run" })).toHaveAttribute("aria-disabled", "true");
    await user.click(input());
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(queries()).toHaveLength(0);
    // The bound counts characters, not UTF-16 units: 4,000 astral characters are within the bound.
    setText("\u{1F600}".repeat(4000));
    expect(screen.getByRole("button", { name: "Run" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("null is shown apart from empty text, lists as joined text, numbers right-aligned, long text clipped with its title", () => {
    const long = "word ".repeat(60).trim();
    renderPart(
      <QueryGrid
        columns={[
          { name: "a", scalar: true, type: "string" },
          { name: "n", scalar: true, type: "integer" },
          { name: "keys", scalar: false, type: "keys" },
          { name: "b", scalar: true, type: "boolean" },
        ]}
        rows={[
          { a: null, n: 7, keys: ["k1", "k2"], b: true },
          { a: "", n: null, keys: [], b: false },
          { a: long, n: "12.50", keys: ["only"], b: null },
        ]}
      />,
    );
    const rows = screen.getAllByTestId("query-row");
    const [r1, r2, r3] = rows.map((r) => within(r).getAllByRole("cell"));
    expect(r1?.[0]).toHaveTextContent("null");
    expect(r1?.[0]).toHaveAttribute("title", "null");
    expect(r2?.[0]).toHaveTextContent('""');
    expect(r2?.[0]).not.toHaveTextContent("null");
    expect(r1?.[2]).toHaveTextContent("k1, k2");
    expect(r2?.[2]).toHaveTextContent("(none)");
    expect(r1?.[1]).toHaveClass("num");
    expect(r3?.[1]).toHaveClass("num");
    expect(r1?.[3]).toHaveTextContent("true");
    expect(r1?.[0]).not.toHaveClass("num");
    expect(screen.getByRole("columnheader", { name: "n" })).toHaveClass("num");
    expect(r3?.[0]).toHaveAttribute("title", long);
    // The first cell of each row is its one tab stop; arrow keys move between rows; Enter opens the row.
    const stops = rows.map((r) => within(r).getAllByRole("button")[0] as HTMLElement);
    expect(stops.map((b) => b.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
    row(stops, 0).focus();
    fireEvent.keyDown(row(stops, 0), { key: "ArrowDown" });
    expect(document.activeElement).toBe(stops[1]);
    expect(stops.map((b) => b.getAttribute("tabindex"))).toEqual(["-1", "0", "-1"]);
    fireEvent.keyDown(row(stops, 1), { key: "End" });
    expect(document.activeElement).toBe(stops[2]);
    fireEvent.keyDown(row(stops, 2), { key: "Home" });
    expect(document.activeElement).toBe(stops[0]);
    expect(row(stops, 0)).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row(stops, 0));
    expect(row(stops, 0)).toHaveAttribute("aria-expanded", "true");
  });

  it("x.* shows the declared fields and the facts the backend appends, and no relationship column", async () => {
    const user = userEvent.setup();
    area();
    await run(user, "SELECT u.* FROM catalog.UseCase u ORDER BY u.code LIMIT 50");
    await screen.findByText("uc-1");
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toContain("_version");
    expect(headers).not.toContain("addressedBy"); // relationship keys are RELATED_KEYS, asked for
  });

  it("an answer with no rows says so, and a truncated answer says it was cut short", async () => {
    const user = userEvent.setup();
    api.rows["catalog.UseCase"] = [];
    area();
    await run(user);
    expect(await screen.findByText("No rows")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    api.on((r) =>
      /\/operate\/query$/.test(r.path)
        ? json(200, wire.queryResult({ truncated: true }))
        : undefined,
    );
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findAllByText(/truncated/i)).not.toHaveLength(0);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});

describe("Query: one page per statement (US-077-AC3)", () => {
  it("a page the limit cut says so and how to go on; the request names the module and carries no cursor", async () => {
    const user = userEvent.setup();
    seedCatalog(api, 5);
    area(2);
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await run(user);
    await screen.findByText("uc-1");
    expect(screen.getAllByTestId("query-row")).toHaveLength(2);
    expect(queries()[0]?.body).toEqual({
      module: "catalog",
      sql: SQL,
      consistency: "bulk",
      limit: 2,
    });
    expect(screen.getByTestId("query-truncated")).toHaveTextContent("keyset");
    expect(screen.queryByRole("button", { name: /Next page/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Previous page/ })).toBeNull();
    expect(screen.getByTestId("query-live")).toHaveTextContent("2 rows, truncated");
  });

  it("a page the limit did not cut is not marked truncated", async () => {
    const user = userEvent.setup();
    seedCatalog(api, 5);
    area(10);
    await run(user);
    await screen.findByText("uc-1");
    expect(screen.getAllByTestId("query-row")).toHaveLength(5);
    expect(screen.queryByTestId("query-truncated")).toBeNull();
  });

  it("a statement without its order and LIMIT is the backend's Unsupported, shown as such", async () => {
    const user = userEvent.setup();
    area();
    await run(user, "SELECT u.code FROM catalog.UseCase u");
    expect(await screen.findByTestId("query-error")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("Query: errors as the library states them (US-077-AC4, AC5, AC6)", () => {
  const cases: [string, ReturnType<typeof err>, RegExp[]][] = [
    [
      "400: every violation, path, code and message",
      err(400, {
        ...wire.invalidQuery(),
        violations: [
          ...(wire.invalidQuery().violations ?? []),
          { path: "sql.zip", code: "unknown_field", message: "UseCase has no property 'zip'" },
        ],
      }),
      [
        /sql\s*syntax: expected '.', found 'FROM'/,
        /sql\.zip\s*unknown_field: UseCase has no property 'zip'/,
      ],
    ],
    [
      "404: as for any module that is unknown or unreadable",
      err(404, wire.unknownModule()),
      [/Not found/, /No such module or type, or you cannot read it/],
    ],
    [
      "501: the construct and what is supported",
      err(501, wire.unsupportedQuery()),
      [/Not supported/, /filter workArea \(optional string\)/, /a filter is on a required/],
    ],
    [
      "401: asks the host to sign in again",
      err(401, wire.tokenExpired()),
      [/Sign in again/, /history here is kept/],
    ],
    ["403: the reason", err(403, wire.refused("read")), [/No access/, /no_access/]],
    [
      "409: not yet current",
      err(409, { type: "Conflict", message: "replica has not reached fake:9" }),
      [/Conflict/, /not yet current/],
    ],
    [
      "503: names the backend",
      err(503, wire.unavailable()),
      [/Backend unavailable/, /memory is unavailable \(unreachable\)/],
    ],
  ];
  it.each(cases)("%s, and never an empty grid", async (_n, reply, texts) => {
    const user = userEvent.setup();
    const signedIn = vi.fn();
    api.on((r) => (/\/operate\/query$/.test(r.path) ? reply : undefined));
    renderPart(<QueryArea module="catalog" />, { onUnauthorized: signedIn });
    await run(user);
    const e = await screen.findByTestId("query-error");
    for (const t of texts) expect(e.textContent).toMatch(t);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("No rows")).toBeNull();
    expect(signedIn).toHaveBeenCalledTimes(reply.status === 401 ? 1 : 0);
    // The history keeps the failure by its kind, not its body.
    expect(entries()).toHaveLength(1);
    expect(entries()[0]).toHaveTextContent(`(${reply.status})`);
  });

  it("a new run clears the previous grid, and an error never sits beside a stale grid", async () => {
    const user = userEvent.setup();
    area();
    await run(user);
    await screen.findByText("uc-1");
    let release: (() => void) | undefined;
    api.on(async (r) => {
      if (!/\/operate\/query$/.test(r.path)) return undefined;
      await new Promise<void>((res) => (release = res));
      return err(503, wire.unavailable());
    });
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(screen.queryByRole("table")).toBeNull(); // cleared as the new run starts
    expect(screen.getByRole("button", { name: /Running/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    act(() => release?.());
    await screen.findByTestId("query-error");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("uc-1")).toBeNull();
  });

  it("a dropped connection is a network error, not a grid", async () => {
    const user = userEvent.setup();
    api.on((r) => {
      if (/\/operate\/query$/.test(r.path)) throw new TypeError("Failed to fetch");
      return undefined;
    });
    area();
    await run(user);
    expect(await screen.findByTestId("query-error")).toHaveTextContent("Network error");
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("Query: this session's history (US-078)", () => {
  it("US-078-AC1: newest first with consistency, time and the row count or the failure", async () => {
    const user = userEvent.setup();
    area();
    await run(user, "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 50");
    await screen.findByText("uc-1");
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await run(user, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 50");
    await waitFor(() => expect(entries()).toHaveLength(2));
    api.on((r) =>
      /\/operate\/query$/.test(r.path) ? err(404, wire.unknownModule("zzz")) : undefined,
    );
    await run(user, "SELECT x.code FROM zzz.Thing x");
    await waitFor(() => expect(entries()).toHaveLength(3));
    const [a, b, c] = entries();
    expect(a).toHaveTextContent("zzz.Thing");
    expect(a).toHaveTextContent("BULK");
    expect(a).toHaveTextContent("Not found (404)");
    expect(b).toHaveTextContent("catalog.Solution");
    expect(b).toHaveTextContent("BULK");
    expect(b).toHaveTextContent("1 row");
    expect(c).toHaveTextContent("catalog.UseCase");
    expect(c).toHaveTextContent("LATEST");
    expect(c).toHaveTextContent("3 rows");
    expect(within(defined(c, "the oldest entry")).getByText(/\d\d:\d\d:\d\d/)).toBeInTheDocument();
    // The failure's reason, not its body.
    expect(a).not.toHaveTextContent("no module");
  });

  it("the same query twice in a row is listed once with the latest time; a different consistency is another entry", async () => {
    const user = userEvent.setup();
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-10-11T10:00:00Z"));
      area();
      await run(user);
      await waitFor(() => expect(entries()).toHaveLength(1));
      expect(entries()[0]).toHaveTextContent("10:00:00");
      vi.setSystemTime(new Date("2026-10-11T10:05:00Z"));
      await user.click(screen.getByRole("button", { name: "Run" }));
      await waitFor(() => expect(entries()[0]).toHaveTextContent("10:05:00"));
      expect(entries()).toHaveLength(1);
      await user.click(screen.getByRole("button", { name: "BULK" }));
      await user.click(screen.getByRole("button", { name: "Run" }));
      await waitFor(() => expect(entries()).toHaveLength(2));
      // Not "in a row": A, B, A is three entries.
      await run(user, "SELECT s.code FROM catalog.Solution s ORDER BY s.code LIMIT 50");
      await waitFor(() => expect(entries()).toHaveLength(3));
      await run(user, SQL);
      await waitFor(() => expect(entries()).toHaveLength(4));
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps at most 50, dropping the oldest", async () => {
    const user = userEvent.setup();
    area();
    for (let i = 0; i < 52; i++) {
      setText(`SELECT u.code FROM catalog.UseCase u WHERE u.code = 'n${i}'`);
      fireEvent.submit(defined(input().closest("form"), "the form"));
      await waitFor(() => expect(queries()).toHaveLength(i + 1));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Run" })).not.toHaveAttribute(
          "aria-disabled",
          "true",
        ),
      );
    }
    await waitFor(() => expect(entries()).toHaveLength(50));
    expect(entries()[0]).toHaveTextContent("n51");
    expect(entries()[49]).toHaveTextContent("n2");
    expect(screen.queryByText(/'n1'$/)).toBeNull();
    expect(user).toBeDefined();
  }, 60_000); // 52 runs: slow on a loaded machine

  it("US-078-AC2: choosing an entry puts its text and consistency in the editor and runs nothing", async () => {
    const user = userEvent.setup();
    area();
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await run(user);
    await screen.findByText("uc-1");
    await user.click(screen.getByRole("button", { name: "LATEST" }));
    setText("something else");
    await user.click(within(first()).getByTitle(/without running it/));
    expect(input().value).toBe(SQL);
    expect(screen.getByRole("button", { name: "BULK" })).toHaveAttribute("aria-pressed", "true");
    expect(queries()).toHaveLength(1);
  });

  it("US-078-AC3: Run again runs it now as the current person", async () => {
    const user = userEvent.setup();
    let who = "alice";
    renderPart(<QueryArea module="catalog" />, { getHeaders: () => ({ "x-who": who }) });
    await run(user);
    await screen.findByText("uc-1");
    expect(queries()[0]?.headers["x-who"]).toBe("alice");
    setText("changed");
    who = "bob";
    await user.click(within(first()).getByRole("button", { name: /Run again/ }));
    await waitFor(() => expect(queries()).toHaveLength(2));
    expect(queries()[1]?.body.sql).toBe(SQL);
    expect(queries()[1]?.headers["x-who"]).toBe("bob");
    expect(input().value).toBe(SQL);
  });

  it("US-078-AC4: Clear history empties it and it stays empty", async () => {
    const user = userEvent.setup();
    area();
    expect(screen.getByRole("button", { name: "Clear history" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await run(user);
    await screen.findByText("uc-1");
    await user.click(screen.getByRole("button", { name: "Clear history" }));
    expect(entries()).toHaveLength(0);
    expect(screen.getByTestId("query-history-empty")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "BULK" }));
    expect(entries()).toHaveLength(0);
  });

  it("the history and the draft survive moving between the console's tabs, and are not shared by another console", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/query";
    const first = renderConsole({ hashRouting: true });
    await user.click(await screen.findByTestId("query-input"));
    setText(SQL);
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("uc-1");
    await user.click(screen.getByRole("tab", { name: "Entities" }));
    await screen.findByTestId("entity-table");
    expect(screen.queryByTestId("query-history")).toBeNull();
    await user.click(screen.getByRole("tab", { name: "Query" }));
    await waitFor(() => expect(entries()).toHaveLength(1));
    expect(input().value).toBe(SQL); // the draft too
    expect(window.location.hash).toBe("#/catalog/query");
    // Another person: the host mounts the console afresh (a new key), so it starts empty.
    first.unmount();
    renderConsole({ hashRouting: true });
    await screen.findByTestId("query-input");
    expect(entries()).toHaveLength(0);
    expect(input().value).toBe("");
  });
});

describe("Query: what can I query?", () => {
  it("lists the viewed module's types with their columns and relationships, and a click puts a query in the editor", async () => {
    const user = userEvent.setup();
    area();
    const panel = screen.getByTestId("query-types");
    await user.click(within(panel).getByText("What can I query?"));
    const types = await within(panel).findAllByTestId("query-type");
    expect(types).toHaveLength(2);
    expect(types[0]).toHaveTextContent("catalog.UseCase");
    expect(types[0]).toHaveTextContent("columns: code, name");
    expect(types[0]).toHaveTextContent("optional, not filtered: workArea");
    expect(types[0]).toHaveTextContent("relationships: addressedBy");
    expect(types[1]).toHaveTextContent("relationships: addresses");
    await user.click(within(row(types, 1)).getByRole("button", { name: "catalog.Solution" }));
    // every name a Weft quoted identifier; a LIMIT one over the page, so `truncated` says there are more
    expect(input().value).toBe(
      'SELECT x."code", x."name" FROM "catalog"."Solution" x ORDER BY x."code" LIMIT 101',
    );
    expect(queries()).toHaveLength(0);
    await user.click(
      within(row(types, 0)).getByRole("button", { name: /every property of catalog.UseCase/ }),
    );
    expect(input().value).toBe('SELECT x.* FROM "catalog"."UseCase" x ORDER BY x."code" LIMIT 101');
    // The inserted text runs against the fake as written.
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("uc-1");
  });
});

describe("Query: a template over a type larger than a page", () => {
  it("asks for one row over the page, so a type with more rows than the page says truncated", async () => {
    const user = userEvent.setup();
    seedCatalog(api, 5);
    area(2);
    await user.click(within(screen.getByTestId("query-types")).getByText("What can I query?"));
    const types = await screen.findAllByTestId("query-type");
    await user.click(
      within(row(types, 0)).getByRole("button", { name: /every property of catalog.UseCase/ }),
    );
    expect(input().value).toBe('SELECT x.* FROM "catalog"."UseCase" x ORDER BY x."code" LIMIT 3');
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("uc-1");
    expect(screen.getAllByTestId("query-row")).toHaveLength(2);
    expect(screen.getByTestId("query-truncated")).toHaveTextContent('x."<key>" > :last');
  });
});

/** The Query area of whichever module the test views, over one session (as the console's shell holds it). */
function Viewing() {
  const session = useQuerySessionState();
  const [module, setModule] = useState("catalog");
  return (
    <QuerySessionProvider session={session}>
      <button type="button" onClick={() => setModule("lab")}>
        view lab
      </button>
      <QueryArea module={module} />
    </QuerySessionProvider>
  );
}

describe("Query: a history entry keeps its module (OPR-17, US-078-AC1, AC2, AC3)", () => {
  it("shows the module it read, lists one text per module, and choosing or running it again reads that module whichever is viewed", async () => {
    const user = userEvent.setup();
    const catalog = defined(api.modules[0], "the catalog module");
    api.modules = [...api.modules, { ...catalog, name: "lab" }];
    renderPart(<Viewing />);
    expect(screen.getByTestId("query-module")).toHaveTextContent("catalog");
    await run(user);
    await screen.findByText("uc-1");
    expect(within(first()).getByTestId("history-module")).toHaveTextContent("catalog");
    await user.click(screen.getByRole("button", { name: "view lab" }));
    expect(screen.getByTestId("query-module")).toHaveTextContent("lab");
    await run(user); // the same text over the module viewed now: another entry
    await waitFor(() => expect(queries()).toHaveLength(2));
    expect(queries()[1]?.body.module).toBe("lab");
    await waitFor(() => expect(entries()).toHaveLength(2));
    expect(within(first()).getByTestId("history-module")).toHaveTextContent("lab");
    const older = defined(entries()[1], "the catalog entry");
    await user.click(within(older).getByRole("button", { name: /Run again/ }));
    await waitFor(() => expect(queries()).toHaveLength(3));
    expect(queries()[2]?.body.module).toBe("catalog"); // the entry's module, not the one viewed
    expect(screen.getByTestId("query-module")).toHaveTextContent("catalog");
    const lab = defined(
      entries().find((e) => within(e).getByTestId("history-module").textContent === "lab"),
      "the lab entry",
    );
    await user.click(within(lab).getByTitle(/without running it/));
    expect(screen.getByTestId("query-module")).toHaveTextContent("lab"); // its module, in the editor
    expect(queries()).toHaveLength(3);
  });
});

describe("Query: nothing is stored in the browser (OPR-07, US-078-AC6)", () => {
  it("writes nothing to local or session storage, IndexedDB or a cookie, and no URL holds the text", async () => {
    const user = userEvent.setup();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const open = vi.fn();
    vi.stubGlobal("indexedDB", { open });
    const cookie = vi.fn();
    const desc = defined(
      Object.getOwnPropertyDescriptor(Document.prototype, "cookie"),
      "the cookie descriptor",
    );
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => desc.get?.call(document),
      set: (v: string) => cookie(v),
    });
    const secret = "needle-9f3a";
    window.location.hash = "#/catalog/query";
    try {
      renderConsole({ hashRouting: true });
      await screen.findByTestId("query-input");
      for (const consistency of ["LATEST", "BULK", "LATEST"]) {
        await user.click(screen.getByRole("button", { name: consistency }));
        setText(`SELECT u.code FROM catalog.UseCase u WHERE u.name = '${secret}-${consistency}'`);
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() =>
          expect(screen.getByRole("button", { name: "Run" })).not.toHaveAttribute(
            "aria-disabled",
            "true",
          ),
        );
      }
      await user.click(within(first()).getByRole("button", { name: /Run again/ }));
      await waitFor(() => expect(queries()).toHaveLength(4));
      await user.click(screen.getByRole("button", { name: "Clear history" }));
      expect(setItem).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
      expect(cookie).not.toHaveBeenCalled();
      expect(window.localStorage.length).toBe(0);
      expect(window.sessionStorage.length).toBe(0);
      expect(window.location.hash).toBe("#/catalog/query");
      expect(window.location.search).toBe("");
      expect(decodeURIComponent(window.location.href)).not.toContain(secret);
      expect(decodeURIComponent(window.location.href)).not.toContain("SELECT");
    } finally {
      delete (document as unknown as Record<string, unknown>).cookie;
      vi.unstubAllGlobals();
    }
  });
});

describe("Query: identity, focus, announcements and the grid's robustness", () => {
  it("a console given another `identity` starts with an empty history and draft; the same identity keeps them", async () => {
    const user = userEvent.setup();
    window.location.hash = "#/catalog/query";
    const props = { hashRouting: true as const, getHeaders: () => ({ "x-who": "alice" }) };
    const { rerender } = renderConsole({ ...props, identity: "fixed:alice" });
    await screen.findByTestId("query-input");
    setText(SQL);
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("uc-1");
    expect(entries()).toHaveLength(1);
    rerender(<ArrasConsole {...props} identity="fixed:alice" />);
    expect(entries()).toHaveLength(1);
    rerender(
      <ArrasConsole hashRouting getHeaders={() => ({ "x-who": "carol" })} identity="fixed:carol" />,
    );
    await waitFor(() => expect(screen.getByTestId("query-history-empty")).toBeInTheDocument());
    expect(input().value).toBe("");
  });

  it("Run uses aria-disabled while a request runs: focus stays on it, and a second click is ignored", async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    api.on(async (r) => {
      if (!/\/operate\/query$/.test(r.path)) return undefined;
      await new Promise<void>((res) => (release = res));
      return undefined;
    });
    area();
    setText(SQL);
    const button = screen.getByRole("button", { name: "Run" });
    button.focus();
    await user.click(button);
    await waitFor(() => expect(button).toHaveAttribute("aria-disabled", "true"));
    expect(button).not.toBeDisabled();
    expect(document.activeElement).toBe(button);
    await user.click(button); // ignored
    const n = queries().length;
    act(() => release?.());
    await screen.findByText("uc-1");
    expect(queries()).toHaveLength(n);
    expect(document.activeElement).toBe(button);
  });

  it("announces Running… for a first run, once, in one polite live region", async () => {
    const user = userEvent.setup();
    let release: (() => void) | undefined;
    api.on(async (r) => {
      if (!/\/operate\/query$/.test(r.path)) return undefined;
      await new Promise<void>((res) => (release = res));
      return undefined;
    });
    area();
    setText(SQL);
    await user.click(screen.getByRole("button", { name: "Run" }));
    const live = screen.getByTestId("query-live");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent("Running…");
    act(() => release?.());
    await screen.findByText("uc-1");
    expect(live).toHaveTextContent("3 rows");
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("the result is a table labelled once, with duplicate or look-alike column names keyed without a warning", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderPart(
      <QueryGrid
        columns={[
          { name: "code", scalar: true, type: "string" },
          { name: "code", scalar: true, type: "string" },
          { name: "code ", scalar: true, type: "string" },
        ]}
        rows={[{ code: "a", "code ": "b" }]}
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("grid")).toBeNull();
    expect(screen.getAllByLabelText("Query result")).toHaveLength(1);
    expect(screen.getAllByRole("columnheader")).toHaveLength(3);
    expect(screen.getAllByRole("cell")).toHaveLength(3);
    expect(errors.mock.calls.filter((c) => String(c[0]).includes("same key"))).toEqual([]);
  });

  it("caps a cell's text at 10,000 characters with a note, and its title at 500", () => {
    const big = "x".repeat(CELL_MAX_CHARS * 2);
    renderPart(
      <QueryGrid
        columns={[{ name: "a", scalar: true, type: "string" }]}
        rows={[{ a: big }, { a: "y".repeat(CELL_MAX_CHARS) }]}
      />,
    );
    const [c1, c2] = screen.getAllByRole("cell");
    expect(c1?.textContent?.startsWith(`${"x".repeat(CELL_MAX_CHARS)}…`)).toBe(true);
    expect(c1?.textContent?.length).toBeLessThan(CELL_MAX_CHARS + 40);
    expect(c1).toHaveTextContent("[truncated in view]");
    expect(c1?.getAttribute("title")?.length).toBe(TITLE_MAX_CHARS + 1);
    expect(c2?.textContent).toHaveLength(CELL_MAX_CHARS); // exactly the cap: not cut
    expect(c2).not.toHaveTextContent("truncated in view");
  });

  it("the Query 404 reads 'No such module or type', as the other areas' wording is unchanged", async () => {
    const user = userEvent.setup();
    api.on((r) => (/\/operate\/query$/.test(r.path) ? err(404, wire.unknownModule()) : undefined));
    area();
    await run(user);
    expect(await screen.findByTestId("query-error")).toHaveTextContent(
      "No such module or type, or you cannot read it",
    );
    expect(screen.getByTestId("query-error")).not.toHaveTextContent("action");
  });

  it("Run again has a generic name described by its entry; no query text is in a label, and the text is masked for session replay", async () => {
    const user = userEvent.setup();
    area();
    await run(user);
    await screen.findByText("uc-1");
    const again = within(first()).getByRole("button", { name: "Run again" });
    expect(again).not.toHaveAttribute("aria-label");
    const d = defined(again.getAttribute("aria-describedby"), "aria-describedby");
    expect(document.getElementById(d)).toHaveTextContent(SQL);
    expect(document.getElementById(d)).toHaveAttribute("data-dd-privacy", "mask");
    expect(input()).toHaveAttribute("data-dd-privacy", "mask");
    expect(document.querySelectorAll("[aria-label*='SELECT']")).toHaveLength(0);
  });
});
