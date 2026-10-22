// SPDX-License-Identifier: MIT OR Apache-2.0
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EntityTypeInfo, QueryColumn } from "../api/types";
import { QueryArea } from "../areas/QueryArea";
import { QuerySessionProvider, useQuerySessionState } from "../areas/queryHistory";
import type { QueryStarter } from "../areas/useQueryStarter";
import { keyColumn, keyedType } from "../lib/queryKeys";
import { starterSql } from "../lib/starterSql";
import { defined } from "./defined";
import { type FakeApi, seedCatalog, stage } from "./fake";
import { renderPart } from "./render";

const prop = (name: string, type = "string") => ({
  name,
  type,
  required: true,
  cardinality: "one" as const,
});
const typeOf = (name: string, key: string, props: string[]): EntityTypeInfo => ({
  name,
  key,
  properties: props.map((p) => prop(p)) as EntityTypeInfo["properties"],
  capabilities: {},
});

describe("starterSql", () => {
  it("selects the key, then the first declared properties, quoted, ordered by the key", () => {
    const t = typeOf("shop.Product", "sku", ["sku", "name", "price", "a", "b", "c", "d"]);
    expect(starterSql(t)).toBe(
      'SELECT u."sku", u."name", u."price", u."a", u."b" FROM "shop"."Product" u ORDER BY u."sku" LIMIT 50',
    );
  });

  it("quotes reserved words and puts the key first wherever it is declared", () => {
    const t = typeOf("desk.Ticket", "order", ["group", "order"]);
    expect(starterSql(t)).toBe(
      'SELECT u."order", u."group" FROM "desk"."Ticket" u ORDER BY u."order" LIMIT 50',
    );
  });

  it("a type with only its key selects just the key", () => {
    expect(starterSql(typeOf("m.T", "id", ["id"]))).toBe(
      'SELECT u."id" FROM "m"."T" u ORDER BY u."id" LIMIT 50',
    );
  });

  it("leaves out a property whose name the registry does not admit, and has no starter without a key", () => {
    expect(starterSql(typeOf("m.T", "id", ["id", "bad name", 'q"x', "ok"]))).toBe(
      'SELECT u."id", u."ok" FROM "m"."T" u ORDER BY u."id" LIMIT 50',
    );
    expect(starterSql(typeOf("m.T", "bad key", ["bad key"]))).toBeNull();
  });
});

describe("keyedType and keyColumn", () => {
  const types = [typeOf("catalog.UseCase", "code", ["code", "name"])];
  const cols: QueryColumn[] = [
    { name: "code", scalar: true, type: "string" },
    { name: "name", scalar: true, type: "string" },
  ];
  const seen = (sql: string) => keyedType(sql, "catalog", types)?.name ?? null;

  it("resolves bare and quoted statements over one type of the module", () => {
    expect(seen("SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 5")).toBe(
      "catalog.UseCase",
    );
    expect(seen('select x.* from "catalog"."UseCase" x limit 1')).toBe("catalog.UseCase");
  });

  it("does not guess for joins, lists, other modules, unknown types or a second FROM", () => {
    expect(seen("SELECT u.code FROM catalog.UseCase u JOIN catalog.Solution s ON 1=1")).toBeNull();
    expect(seen("SELECT u.code FROM catalog.UseCase u, catalog.Solution s")).toBeNull();
    expect(seen("SELECT u.code FROM other.UseCase u")).toBeNull();
    expect(seen("SELECT u.code FROM catalog.Nope u")).toBeNull();
    expect(
      seen("SELECT u.code FROM catalog.UseCase u WHERE u.code IN (SELECT 1 FROM catalog.UseCase)"),
    ).toBeNull();
    expect(seen("SELECT 1")).toBeNull();
  });

  it("ignores a keyword inside a string literal or a comment", () => {
    expect(seen("SELECT u.code FROM catalog.UseCase u WHERE u.name = 'a join b' -- from x")).toBe(
      "catalog.UseCase",
    );
  });

  it("the key column is the declared key's own scalar column, else none", () => {
    const t = defined(types[0], "type");
    expect(keyColumn(cols, t)).toBe("code");
    expect(keyColumn([cols[1] as QueryColumn], t)).toBeNull();
    expect(keyColumn([{ name: "code", scalar: false, type: "keys" }], t)).toBeNull();
    expect(keyColumn(cols, null)).toBeNull();
  });
});

let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
  seedCatalog(api);
});

const STARTER_UC =
  'SELECT u."code", u."name", u."workArea" FROM "catalog"."UseCase" u ORDER BY u."code" LIMIT 50';
const input = () => screen.getByTestId("query-input") as HTMLTextAreaElement;
const queries = () => api.posts(/\/operate\/query$/);

/** The Query area and something else, over one session held above both (as the console's shell holds it). */
function Harness({ starter, onOpenEntity }: { starter?: QueryStarter; onOpenEntity?: () => void }) {
  const session = useQuerySessionState();
  const [here, setHere] = useState(true);
  return (
    <QuerySessionProvider session={session}>
      <button type="button" onClick={() => setHere((h) => !h)}>
        toggle
      </button>
      {here ? (
        <QueryArea module="catalog" starter={starter} onOpenEntity={onOpenEntity} />
      ) : (
        <div>elsewhere</div>
      )}
    </QuerySessionProvider>
  );
}

describe("Query area: a starter", () => {
  it("fills an empty draft without running it", async () => {
    renderPart(<Harness starter={{ type: "catalog.UseCase", id: 1 }} />);
    await waitFor(() => expect(input().value).toBe(STARTER_UC));
    expect(queries()).toHaveLength(0);
    expect(screen.queryByTestId("query-starter-offer")).toBeNull();
  });
});

function WithDraft({ starter }: { starter: QueryStarter }) {
  const session = useQuerySessionState();
  const [on, setOn] = useState(false);
  return (
    <QuerySessionProvider session={session}>
      <button type="button" onClick={() => setOn(true)}>
        open
      </button>
      <QueryArea module="catalog" starter={on ? starter : undefined} />
    </QuerySessionProvider>
  );
}

describe("Query area: a starter over a draft", () => {
  it("offers instead of overwriting; Keep leaves the draft, Replace puts the starter in", async () => {
    const user = userEvent.setup();
    const starter = { type: "catalog.UseCase", id: 1 };
    renderPart(<WithDraft starter={starter} />);
    fireEvent.change(input(), { target: { value: "SELECT my draft" } });
    await user.click(screen.getByRole("button", { name: "open" }));
    const offer = await screen.findByTestId("query-starter-offer");
    expect(input().value).toBe("SELECT my draft");
    expect(offer).toHaveTextContent("Your draft is kept");
    await user.click(screen.getByRole("button", { name: "Keep my draft" }));
    expect(screen.queryByTestId("query-starter-offer")).toBeNull();
    expect(input().value).toBe("SELECT my draft");
    expect(queries()).toHaveLength(0);
  });

  it("Replace puts the starter in the editor, still unrun", async () => {
    const user = userEvent.setup();
    renderPart(<WithDraft starter={{ type: "catalog.UseCase", id: 1 }} />);
    fireEvent.change(input(), { target: { value: "SELECT my draft" } });
    await user.click(screen.getByRole("button", { name: "open" }));
    await user.click(await screen.findByRole("button", { name: /Replace the draft/ }));
    expect(input().value).toBe(STARTER_UC);
    expect(screen.queryByTestId("query-starter-offer")).toBeNull();
    expect(queries()).toHaveLength(0);
  });
});

describe("Query area: the draft survives leaving the area (the session above it)", () => {
  it("keeps the text, consistency and history across unmount and remount, in memory only", async () => {
    const user = userEvent.setup();
    const sql = "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 50";
    renderPart(<Harness />);
    fireEvent.change(input(), { target: { value: sql } });
    await user.click(screen.getByRole("button", { name: "BULK" }));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findByText("uc-1");
    fireEvent.change(input(), { target: { value: `${sql} -- edited` } });
    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByText("elsewhere")).toBeInTheDocument();
    expect(screen.queryByTestId("query-input")).toBeNull();
    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(input().value).toBe(`${sql} -- edited`);
    expect(screen.getByRole("button", { name: "BULK" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("history-entry")).toHaveLength(1);
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });

  it("a starter already handled is not applied again when the area remounts with it", async () => {
    const user = userEvent.setup();
    renderPart(<Harness starter={{ type: "catalog.UseCase", id: 1 }} />);
    await waitFor(() => expect(input().value).toBe(STARTER_UC));
    fireEvent.change(input(), { target: { value: "SELECT mine" } });
    await user.click(screen.getByRole("button", { name: "toggle" }));
    await user.click(screen.getByRole("button", { name: "toggle" }));
    expect(input().value).toBe("SELECT mine");
    expect(screen.queryByTestId("query-starter-offer")).toBeNull();
  });
});

describe("Query area: result keys as links", () => {
  const run = async (user: ReturnType<typeof userEvent.setup>, sql: string) => {
    fireEvent.change(input(), { target: { value: sql } });
    await user.click(screen.getByRole("button", { name: "Run" }));
    await screen.findAllByTestId("query-row");
  };

  it("links the key column of a statement over one known type, and the callback gets the type and key", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    renderPart(<Harness onOpenEntity={open} />);
    await run(user, "SELECT u.code, u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 50");
    const links = screen.getAllByTestId("query-key-link");
    expect(links).toHaveLength(3);
    await user.click(screen.getByRole("button", { name: "Open UseCase uc-1" }));
    expect(open).toHaveBeenCalledWith("catalog.UseCase", "uc-1");
    // the text is still text: the name column has no link
    expect(screen.getAllByTestId("query-row")[0]?.querySelectorAll("button").length).toBe(2);
  });

  it("leaves the cells plain when the statement cannot be resolved to one type, or no callback is given", async () => {
    const user = userEvent.setup();
    const { unmount } = renderPart(<Harness onOpenEntity={vi.fn()} />);
    await run(user, "SELECT u.name FROM catalog.UseCase u ORDER BY u.code LIMIT 50");
    expect(screen.queryAllByTestId("query-key-link")).toHaveLength(0);
    unmount();
    renderPart(<Harness />);
    await run(user, "SELECT u.code FROM catalog.UseCase u ORDER BY u.code LIMIT 50");
    expect(screen.queryAllByTestId("query-key-link")).toHaveLength(0);
  });
});
