// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type {
  Annotation,
  SchemaBrowserOptions,
  Selection,
} from "@documentdrivendx/umf-schema-browser";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UmfSource } from "../areas/UmfSource";
import { annotationsFor, definitionKey, relationshipKey, toEntries } from "../areas/umfBrowser";
import { defined } from "../test/defined";
import { asBob, client, control, renderLive, renderLiveConsole, withDevHost } from "./harness";
import { REPO_ROOT } from "./server";

// The UMF source view against the real dev host: the catalog and the live registry are read by
// the console's client with the person's header, and the package function receives exactly those
// (entries, annotations), then select() and setAnnotations() as the real registry changes. jsdom
// cannot run the package's frame, so its mount is recorded here; e2e/umf-explorer.spec.ts runs it.
withDevHost();

interface Mount {
  options: SchemaBrowserOptions;
  selects: Selection[];
  annotations: Record<string, Annotation[]>[];
  destroyed: boolean;
  load: () => void;
}
const mounted: Mount[] = [];
vi.mock("@documentdrivendx/umf-schema-browser", () => ({
  mountSchemaBrowser: (container: HTMLElement, options: SchemaBrowserOptions) => {
    let load!: () => void;
    const ready = new Promise<void>((resolveReady) => {
      load = resolveReady;
    });
    const m: Mount = { options, selects: [], annotations: [], destroyed: false, load };
    mounted.push(m);
    const iframe = document.createElement("iframe");
    container.append(iframe);
    return {
      iframe,
      ready,
      select: (s: Selection) => {
        m.selects.push(s);
        return Promise.resolve(s);
      },
      focus: () => {},
      setAnnotations: (a: Record<string, Annotation[]>) => {
        m.annotations.push(a);
      },
      destroy: () => {
        m.destroyed = true;
      },
    };
  },
}));

beforeEach(() => {
  mounted.length = 0;
});
const live = () => mounted.filter((m) => !m.destroyed);
// What the browser shows now: the newest setAnnotations call, else what it was mounted with.
const current = (m: Mount) =>
  m.annotations[m.annotations.length - 1] ?? m.options.annotations ?? {};
const USE_CASE = definitionKey("catalog", "UseCase");
const firstMount = () => defined(mounted[0], "the first mount");
const liveMount = () => defined(live()[0], "a live mount");
const newest = (m: Mount) =>
  defined(m.annotations[m.annotations.length - 1], "a setAnnotations call");
const entriesOf = (m: Mount) => defined(m.options.entries, "the mount's entries");
const notesFor = (notes: Record<string, Annotation[]>, key: string) =>
  defined(notes[key], `annotations for ${key}`);

describe("UMF source against the dev host (OPR-11)", () => {
  it("alice: the browser is given alice's live catalog, the module selected, and badges from alice's live registry", async () => {
    const expected = toEntries(await client("alice").schemaCatalog());
    const meta = await client("alice").meta();
    const { unmount } = renderLive(
      <UmfSource module="catalog" explorerBase="/umf-explorer" />,
      "alice",
    );
    await waitFor(() => expect(mounted).toHaveLength(1));
    expect(firstMount().options).toMatchObject({
      assetsUrl: "/umf-explorer/",
      selection: { schema: "arras:catalog" },
      entries: expected,
      readOnlyLocalFiles: true,
      hideHero: true,
    });
    expect(defined(entriesOf(firstMount())[0], "the first entry").schemaFormat).toBe("umf");
    // The registry may be read before or after the mount (a slow runner reads it after): either
    // way the browser ends up showing alice's live badges, so wait for that rather than assume.
    await waitFor(() =>
      expect(current(firstMount())).toEqual(annotationsFor(meta.modules, meta.status, expected)),
    );
    const notes = current(firstMount());
    // One annotation per backend, real tones (package 1.1.2 reserves a map line for each).
    for (const record of [USE_CASE, definitionKey("catalog", "Solution")])
      expect(notesFor(notes, record).map((a) => [a.badge, a.tone])).toEqual([
        ["memory · mutable", "positive"],
        ["memory_replica · read-only", "neutral"],
      ]);
    expect(notesFor(notes, "arras:catalog").map((a) => [a.badge, a.tone])).toEqual([
      ["record: memory", "positive"],
      ["replica: memory_replica", "neutral"],
    ]);
    expect(
      notesFor(notes, relationshipKey("catalog", "solution-addresses")).map((a) => [
        a.badge,
        a.tone,
      ]),
    ).toEqual([["follows: memory, memory_replica", "info"]]);
    unmount();
    expect(firstMount().destroyed).toBe(true);
  });

  it("a memory_replica outage, refreshed: setAnnotations on the same mount; mended: back", async () => {
    renderLive(<UmfSource module="catalog" />, "alice");
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = liveMount();
    await act(async () => m.load());
    const user = userEvent.setup();
    await control({ op: "outage", backend: "memory_replica", reason: "unreachable" });
    try {
      await user.click(await screen.findByRole("button", { name: "Refresh badges" }));
      // The newest setAnnotations call must show the outage. An older read that was already in
      // flight may land first, so wait for the state rather than for a number of calls.
      const latest = () => newest(m);
      await waitFor(() =>
        expect(notesFor(latest(), USE_CASE).map((a) => [a.badge, a.tone])).toEqual([
          ["memory · mutable", "positive"],
          ["memory_replica · unavailable", "warning"],
        ]),
      );
      expect(notesFor(latest(), "arras:catalog").map((a) => [a.badge, a.tone])).toContainEqual([
        "memory_replica · unavailable",
        "warning",
      ]);
    } finally {
      await control({ op: "outage", backend: "memory_replica", reason: null });
    }
    await user.click(screen.getByRole("button", { name: "Refresh badges" }));
    await waitFor(() =>
      expect(notesFor(newest(m), USE_CASE).map((a) => a.badge)).toEqual([
        "memory · mutable",
        "memory_replica · read-only",
      ]),
    );
    expect(mounted).toHaveLength(1);
  });

  it("an operator who reads no module (bob, with his read revoked): the empty state, and nothing is mounted", async () => {
    await asBob([], async () => {
      renderLive(<UmfSource module="catalog" />, "bob");
      expect(await screen.findByTestId("umf-empty")).toHaveTextContent(
        "No registered UMF documents are readable for you",
      );
      expect(mounted).toHaveLength(0);
    });
  });

  it("bob with an expired token: sign in again, the host is told; restored, Retry mounts", async () => {
    const onUnauthorized = vi.fn();
    await control({ op: "expire", user: "bob" });
    try {
      renderLive(<UmfSource module="catalog" />, "bob", { onUnauthorized });
      const error = await screen.findByTestId("umf-catalog-error");
      expect(error).toHaveTextContent("Sign in again");
      expect(onUnauthorized).toHaveBeenCalled();
      expect(mounted).toHaveLength(0);
    } finally {
      await control({ op: "restore", user: "bob" });
    }
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mounted).toHaveLength(1));
    expect(entriesOf(firstMount()).map((e) => e.id)).toEqual(["arras:catalog"]);
  });

  it("dark: mounted in the dark theme with the same real tones as light (no neutral-in-dark workaround)", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q === "(prefers-color-scheme: dark)",
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
    try {
      renderLive(<UmfSource module="catalog" />, "alice");
      await waitFor(() => expect(live()).toHaveLength(1));
      const m = liveMount();
      expect(m.options.theme).toBe("dark");
      await waitFor(() =>
        expect(current(m)[USE_CASE]?.map((a) => [a.badge, a.tone])).toEqual([
          ["memory · mutable", "positive"],
          ["memory_replica · read-only", "neutral"],
        ]),
      );
      expect(notesFor(current(m), "arras:catalog")[0]).toMatchObject({
        badge: "record: memory",
        tone: "positive",
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });

  // Last: it registers a second module on this file's dev host.
  it("a second registered module, chosen in the console's rail, is select() on the same mount", async () => {
    const doc = readFileSync(
      resolve(REPO_ROOT, "src/arras/conformance/module.umf.json"),
      "utf8",
    ).replaceAll('"catalog"', '"intake"');
    await control({ op: "register", document: doc });
    const user = userEvent.setup();
    renderLiveConsole("alice");
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = liveMount();
    expect(entriesOf(m).map((e) => e.id)).toEqual(["arras:catalog", "arras:intake"]);
    await waitFor(() =>
      expect(current(m)[definitionKey("intake", "UseCase")]?.map((a) => a.badge)).toEqual([
        "memory · mutable",
        "memory_replica · read-only",
      ]),
    );
    await act(async () => m.load());
    await user.click(screen.getByRole("button", { name: /^intake/ }));
    await waitFor(() => expect(m.selects).toEqual([{ schema: "arras:intake" }]));
    expect(mounted).toHaveLength(1);
    expect(m.destroyed).toBe(false);
  });
});
