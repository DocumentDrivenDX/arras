// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { DevHost } from "../dev/DevHost";
import { nameProblem } from "../dev/sandbox";
import * as library from "../index";
import { defined } from "./defined";
import { err, type FakeApi, json, type Recorded, stage, wire } from "./fake";
import { inside, reachable, SRC } from "./importGraph";

const EMBED = join(SRC, "embed.tsx");
const DEV = join(SRC, "dev");

// The standalone host's sandbox toolbar (OPR-15): fixed people and a made-up name with a role, the
// headers that say so, and the dev host's control calls. It lives in src/dev/ and is not in the library.
let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  api = stage();
});

const consoleCalls = () =>
  api.log.filter((r) => r.path.startsWith("/api/console") || r.path.startsWith("/api/operate"));
const controls = () => api.log.filter((r) => r.path === "/api/dev/control").map((r) => r.body);
async function host() {
  const user = userEvent.setup();
  render(<DevHost defaultMode="admin" />);
  await screen.findByLabelText("Person");
  await screen.findByRole("navigation", { name: "Modules" });
  return user;
}

describe("the library does not export the toolbar (US-076-AC7)", () => {
  it("lists no sandbox or dev-host component among its exports", () => {
    const names = Object.keys(library);
    expect(names.filter((n) => /sandbox|devhost|toolbar|identity/i.test(n))).toEqual([]);
    expect(names).toContain("ArrasConsole");
  });

  it("the entry the package serves (embed.tsx) reaches nothing in src/dev, where the toolbar lives, by any chain of imports", () => {
    const reached = reachable(EMBED);
    expect(reached.length).toBeGreaterThan(100); // the walk follows the shell into the console and the browser
    expect(reached).toContain(join(SRC, "shell/ArrasApp.tsx"));
    expect(reached.filter((f) => inside(f, DEV)).map((f) => relative(SRC, f))).toEqual([]);
    expect(readFileSync(join(SRC, "main.tsx"), "utf8")).toMatch(/from\s+["']\.\/dev\/DevHost["']/);
    expect(reachable(join(SRC, "main.tsx")).some((f) => inside(f, DEV))).toBe(true);
  });

  it("a chain from the entry into src/dev is found, through relative, alias, package and dynamic imports (negative controls)", () => {
    const at = (p: string) => join(SRC, p);
    const chain = (via: string, hop: string): Record<string, string> => ({
      [at("embed.tsx")]: `import { ArrasApp } from "${via}";`,
      [at("shell/index.ts")]: `export { ArrasApp } from "${hop}";`,
      [at("shell/ArrasApp.tsx")]: 'import { Toolbar } from "../dev/SandboxToolbar";',
      [at("dev/SandboxToolbar.tsx")]: "export const Toolbar = 1;",
    });
    for (const [via, hop] of [
      ["./shell", "./ArrasApp"],
      ["@/shell/index", "./ArrasApp.tsx"],
      ["arras-ui/shell", "@/shell/ArrasApp"],
    ] as const) {
      const files = chain(via, hop);
      const found = reachable(at("embed.tsx"), (p) => files[p]);
      expect(found, `${via} then ${hop}`).toContain(at("dev/SandboxToolbar.tsx"));
    }
    const dynamic = {
      [at("embed.tsx")]: 'const m = () => import("./lib/late");',
      [at("lib/late.ts")]: 'import "../dev/sandbox";',
      [at("dev/sandbox.ts")]: "export {};",
    };
    expect(reachable(at("embed.tsx"), (p) => dynamic[p])).toContain(at("dev/sandbox.ts"));
    // a module that reaches no dev module, and an import cycle, are walked without finding one
    const clean = {
      [at("embed.tsx")]: 'import "./shell";',
      [at("shell/index.ts")]: 'import "../embed";\nimport "./styles.css";\nimport "react";',
    };
    expect(reachable(at("embed.tsx"), (p) => clean[p])).toEqual([
      at("embed.tsx"),
      at("shell/index.ts"),
    ]);
  });
});

describe("name rule", () => {
  it.each(["ana", "a", "a-b_c9", "a".repeat(32)])("%s is allowed", (n) =>
    expect(nameProblem(n, ["alice"])).toBeNull(),
  );
  it.each(["", "Ana", "1ana", "a b", "a".repeat(33), "ana\r\nx-evil: 1", "-a", "é"])(
    "%j is not",
    (n) => expect(nameProblem(n, ["alice"])).not.toBeNull(),
  );
  it("a sandbox person's name is not", () =>
    expect(nameProblem("root", ["alice", "root"])).toMatch(/sandbox's own people/));
});

describe("the person picker", () => {
  it("reads /api/people, offers the fixed people, shows the dev host badge and views as the default person", async () => {
    await host();
    const select = screen.getByLabelText("Person");
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["alice", "bob", "carol", "dave", "root", "Custom name and role…"]);
    expect(select).toHaveValue("alice");
    expect(screen.getByText("dev host: no sign-in")).toBeInTheDocument();
    expect(consoleCalls().at(-1)?.headers["x-arras-user"]).toBe("alice");
    expect(consoleCalls().at(-1)?.headers["x-arras-role"]).toBeUndefined();
  });

  it("choosing a fixed person remounts the console as them: header x-arras-user, no role", async () => {
    const user = await host();
    api.log.length = 0;
    await user.selectOptions(screen.getByLabelText("Person"), "carol");
    await waitFor(() =>
      expect(consoleCalls().some((r) => r.headers["x-arras-user"] === "carol")).toBe(true),
    );
    // (calls of the console just unmounted may still be in flight; the last ones are carol's)
    const last = defined(consoleCalls().at(-1), "a console call");
    expect([last.headers["x-arras-user"], last.headers["x-arras-role"]]).toEqual([
      "carol",
      undefined,
    ]);
    expect(window.location.href).not.toContain("carol"); // no person in a URL
  });
});

describe("custom name and role", () => {
  it("roles come from the server; a valid name with a role is sent as x-arras-user and x-arras-role", async () => {
    const user = await host();
    await user.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    expect(
      within(screen.getByLabelText("Role"))
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["none", "viewer", "editor", "schema author", "auditor", "maintainer"]);
    api.log.length = 0;
    await user.type(screen.getByLabelText("Name"), "ana");
    await user.selectOptions(screen.getByLabelText("Role"), "schema author");
    await user.click(screen.getByRole("button", { name: "Use" }));
    await waitFor(() =>
      expect(consoleCalls().some((r) => r.headers["x-arras-user"] === "ana")).toBe(true),
    );
    const last = defined(consoleCalls().at(-1), "a console call");
    expect([last.headers["x-arras-user"], last.headers["x-arras-role"]]).toEqual([
      "ana",
      "schema author",
    ]);
    // the remounted toolbar shows who this is, still in custom mode
    expect(screen.getByLabelText("Person")).toHaveDisplayValue("Custom name and role…");
    expect(screen.getByLabelText("Name")).toHaveValue("ana");
    expect(screen.getByTitle(/made-up person/)).toHaveTextContent("ana · schema author");
  });

  it("an invalid name is rejected before any request, with the reason", async () => {
    const user = await host();
    await user.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    api.log.length = 0;
    for (const bad of ["Ana", "1ana", "a b", "x".repeat(33), "root", "alice"]) {
      await user.clear(screen.getByLabelText("Name"));
      await user.type(screen.getByLabelText("Name"), bad);
      await user.click(screen.getByRole("button", { name: "Use" }));
      expect(await screen.findByRole("alert")).toBeInTheDocument();
      expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
    }
    expect(api.log).toEqual([]); // nothing was sent: no console call, no control, no people
    expect(screen.getByLabelText("Person")).toHaveValue("\u0000custom");
  });

  it("choosing role viewer with a made-up name yields the console as that person: the backend's refusals are shown", async () => {
    // The double answers by the headers: a viewer is refused every write.
    api.on((r: Recorded) =>
      r.path.endsWith("/validate") && r.headers["x-arras-role"] === "viewer"
        ? err(403, wire.refused())
        : undefined,
    );
    const user = await host();
    await user.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    await user.type(screen.getByLabelText("Name"), "zed");
    await user.selectOptions(screen.getByLabelText("Role"), "viewer");
    await user.click(screen.getByRole("button", { name: "Use" }));
    await waitFor(() => expect(consoleCalls().at(-1)?.headers["x-arras-user"]).toBe("zed"));
    await user.click(await screen.findByRole("tab", { name: "Actions" }));
    await user.click(await screen.findByRole("button", { name: /CorrectSolution/ }));
    await user.type(await screen.findByLabelText(/^solution/), "sol-1");
    await user.type(screen.getByLabelText(/^level/), "x");
    await user.tab();
    expect(await screen.findByText(/The provider refused you/)).toHaveTextContent("no_access");
  });
});

describe("sandbox controls", () => {
  async function open() {
    const user = await host();
    await user.click(screen.getByText("Sandbox"));
    return user;
  }

  it("names the backends from the registry's status and sends outage and mend for each", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Outage memory_replica" }));
    await waitFor(() =>
      expect(controls()).toEqual([
        { op: "outage", backend: "memory_replica", reason: "unreachable" },
      ]),
    );
    await user.click(screen.getByRole("button", { name: "Mend memory_replica" }));
    await user.click(screen.getByRole("button", { name: "Outage memory" }));
    await user.click(screen.getByRole("button", { name: "Mend memory" }));
    await waitFor(() => expect(controls()).toHaveLength(4));
    expect(controls().slice(1)).toEqual([
      { op: "outage", backend: "memory_replica", reason: null },
      { op: "outage", backend: "memory", reason: "unreachable" },
      { op: "outage", backend: "memory", reason: null },
    ]);
    await waitFor(() =>
      expect(screen.getByTestId("sandbox-note")).toHaveTextContent("memory is mended"),
    );
  });

  it("uses whatever backend names the registry reports", async () => {
    api.status = [{ backend: "truss", available: true, reason: null, position: null, lag: null }];
    const user = await open();
    await user.click(await screen.findByRole("button", { name: "Outage truss" }));
    await waitFor(() =>
      expect(controls()).toEqual([{ op: "outage", backend: "truss", reason: "unreachable" }]),
    );
  });

  it("shows an outage the registry reports, and the console re-reads after a control", async () => {
    api.status = [
      { ...defined(api.status[0], "the record status"), available: false, reason: "unreachable" },
      defined(api.status[1], "the replica status"),
    ];
    await open();
    expect(await screen.findByText("unavailable (unreachable)")).toBeInTheDocument();
    const before = api.posts(/\/api\/console\/graphql$/).length;
    await userEvent.setup().click(screen.getByRole("button", { name: "Mend memory" }));
    await waitFor(() =>
      expect(api.posts(/\/api\/console\/graphql$/).length).toBeGreaterThan(before),
    );
  });

  it("expires and restores the viewed person's token, by name", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Expire token" }));
    await user.click(screen.getByRole("button", { name: "Restore token" }));
    await waitFor(() =>
      expect(controls()).toEqual([
        { op: "expire", user: "alice" },
        { op: "restore", user: "alice" },
      ]),
    );
  });

  it("the viewed person is the made-up name when one is chosen", async () => {
    const user = await host();
    await user.selectOptions(screen.getByLabelText("Person"), "Custom name and role…");
    await user.type(screen.getByLabelText("Name"), "kai");
    await user.click(screen.getByRole("button", { name: "Use" }));
    await user.click(await screen.findByText("Sandbox"));
    await user.click(screen.getByRole("button", { name: "Expire token" }));
    await waitFor(() => expect(controls()).toEqual([{ op: "expire", user: "kai" }]));
  });

  it("runs the replica's feed", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Run the replica's feed" }));
    await waitFor(() => expect(controls()).toEqual([{ op: "feed" }]));
  });

  it("says when the dev host refuses a control", async () => {
    api.on((r) =>
      r.path === "/api/dev/control" ? json(400, { error: "unknown control" }) : undefined,
    );
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Run the replica's feed" }));
    await waitFor(() =>
      expect(screen.getByTestId("sandbox-note")).toHaveTextContent("refused it (400)"),
    );
  });
});
