// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GraphBrowser } from "../browser/GraphBrowser";
import { crossLinks } from "../shell/links";
import { wire } from "../test/fake";
import { asBob, conn, invoke, type Person, testQueryClient, unique, withDevHost } from "./harness";

// An entity's History panel (FR-69) against the real dev host: the journal's rows as the operator
// sees them, and the answers of a missing grant and of an authority with no journal.
withDevHost();

afterEach(() => {
  window.location.hash = "";
  vi.restoreAllMocks();
});

const links = crossLinks({ hash: true, openOperate: () => {}, openExplore: () => {} });

const browser = (person: Person, hash: string, withLinks = false) => {
  window.history.replaceState(null, "", "/");
  window.location.hash = hash;
  return render(
    <GraphBrowser
      queryClient={testQueryClient()}
      canEdit
      {...(withLinks ? { links } : {})}
      {...conn(person)}
    />,
  );
};

describe("an entity's history on the real journal", () => {
  it("as alice, after an edit the panel shows the change: who, the action and the entity", async () => {
    const code = unique("hist");
    expect((await invoke("AddUseCase", { code, name: "History subject" }, "alice")).status).toBe(
      200,
    );
    browser("alice", `#/explore/catalog/UseCase/${code}/history`);
    const row = await screen.findByTestId("gb-change");
    expect(row).toHaveTextContent("alice");
    expect(row).toHaveTextContent("AddUseCase");
    expect(await within(row).findByRole("link", { name: /History subject/ })).toBeInTheDocument();
  });

  it("as alice, the change's group links to Operate's receipt view; without the primitive it is text", async () => {
    const code = unique("hist");
    expect((await invoke("AddUseCase", { code, name: "Group link" }, "alice")).status).toBe(200);
    const first = browser("alice", `#/explore/catalog/UseCase/${code}/history`, true);
    const row = await screen.findByTestId("gb-change");
    const group = row.querySelector(".gb-hist-group")?.textContent ?? "";
    expect(group).not.toBe("");
    expect(within(row).getByRole("link", { name: group })).toHaveAttribute(
      "href",
      `#/operate/catalog/changes?group=${group}`,
    );
    first.unmount();
    browser("alice", `#/explore/catalog/UseCase/${code}/history`);
    const plain = await screen.findByTestId("gb-change");
    expect(within(plain).queryByRole("link", { name: group })).toBeNull();
    expect(plain).toHaveTextContent(group);
  });

  it("a role without the journal grant gets one polite sentence, not an error panel", async () => {
    const code = unique("hist");
    expect((await invoke("AddUseCase", { code, name: "No grant" }, "alice")).status).toBe(200);
    await asBob(["read", "write"], async () => {
      browser("bob", `#/explore/catalog/UseCase/${code}/history`);
      expect(await screen.findByText(/do not have access to the history/)).toBeInTheDocument();
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  it("an authority that keeps no journal answers 501 and the panel says so in a sentence", async () => {
    // The sandbox has no module whose record store keeps no journal, so the 501 is the contract's
    // own body (checked against openapi.json by the drift guard) put in front of the real read.
    const code = unique("hist");
    expect((await invoke("AddUseCase", { code, name: "Not kept" }, "alice")).status).toBe(200);
    const real = globalThis.fetch;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) =>
      String(input instanceof Request ? input.url : input).endsWith("/audit/changes")
        ? Promise.resolve(
            new Response(JSON.stringify({ error: wire.unsupported() }), {
              status: 501,
              headers: { "content-type": "application/json" },
            }),
          )
        : real(input, init),
    );
    browser("alice", `#/explore/catalog/UseCase/${code}/history`);
    expect(await screen.findByText(/keeps no history of changes/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
