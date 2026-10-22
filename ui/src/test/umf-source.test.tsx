// SPDX-License-Identifier: MIT OR Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type {
  Annotation,
  BrowserError,
  SchemaBrowserHandle,
  SchemaBrowserOptions,
  Selection,
} from "@documentdrivendx/umf-schema-browser";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type HTMLAttributes, type ReactNode, useEffect, useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ArrasProvider } from "../api/context";
import type { BackendStatus } from "../api/types";
import { SchemaBrowser } from "../areas/SchemaBrowser";
import { UmfSource } from "../areas/UmfSource";
import { annotationsFor, definitionKey, relationshipKey, toEntries } from "../areas/umfBrowser";
import { Scope } from "../components/Scope";
import { defined } from "./defined";
import { catalog, err, type FakeApi, stage, wire } from "./fake";
import { qc, renderConsole, renderPart } from "./render";

// The package function is stubbed: each mount is recorded with its container and options, its
// `ready` is settled by the test, and the handle's calls are recorded. The real package runs under
// Playwright against the dev host (e2e/umf-explorer.spec.ts).
interface Mounted {
  container: HTMLElement;
  options: SchemaBrowserOptions;
  iframe: HTMLIFrameElement;
  load: () => void;
  reject: (e: Error) => void;
  destroyed: boolean;
  selects: Selection[];
  annotations: Record<string, Annotation[]>[];
  focused: number;
}
const mounts: Mounted[] = [];
vi.mock("@documentdrivendx/umf-schema-browser", () => ({
  mountSchemaBrowser: vi.fn(
    (container: HTMLElement, options: SchemaBrowserOptions): SchemaBrowserHandle => {
      const iframe = document.createElement("iframe");
      iframe.title = options.title ?? "UMF schema browser";
      let resolve!: () => void;
      let reject!: (e: Error) => void;
      const ready = new Promise<void>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      const m: Mounted = {
        container,
        options,
        iframe,
        destroyed: false,
        reject,
        load: () => resolve(),
        selects: [],
        annotations: [],
        focused: 0,
      };
      container.append(iframe);
      mounts.push(m);
      return {
        iframe,
        ready,
        select: (s) => {
          m.selects.push(s);
          return Promise.resolve(s);
        },
        focus: () => void m.focused++,
        setAnnotations: (a) => void m.annotations.push(a),
        destroy() {
          m.destroyed = true;
          reject(new Error("Schema browser destroyed before ready."));
          iframe.remove();
        },
      };
    },
  ),
}));

const REGISTERED = readFileSync(
  resolve(__dirname, "../../../src/arras/conformance/module.umf.json"),
  "utf8",
);
let api: FakeApi;
beforeEach(() => {
  window.location.hash = "";
  mounts.length = 0;
  api = stage();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const live = () => mounts.filter((m) => !m.destroyed);
/** The fake's catalog with the registered document as its text, so records and relationships map. */
const realCatalog = (extra: object[] = []) =>
  api.on((r) =>
    r.path.endsWith("/explorer/schema-catalog.json")
      ? {
          status: 200,
          body: {
            version: 1,
            entries: [
              {
                ...defined(wire.schemaCatalog().entries[0], "wire.schemaCatalog().entries[0]"),
                text: REGISTERED,
              },
              ...extra,
            ],
          },
        }
      : undefined,
  );

async function openUmf(ui = <SchemaBrowser module="catalog" />, props = {}) {
  const user = userEvent.setup();
  renderPart(ui, props);
  await screen.findByTestId("schema");
  await user.click(screen.getByRole("button", { name: "UMF source" }));
  return user;
}

describe("Schema: UMF source (OPR-11), the package's mountSchemaBrowser", () => {
  it("mounts only when the view is opened, with the viewer's catalog, the module selected and the console's options", async () => {
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />, {
      getHeaders: () => ({ authorization: "Bearer t" }),
    });
    await screen.findByTestId("schema");
    expect(mounts).toHaveLength(0);
    // The catalog may be read already, for Export (OPR-14); the browser itself is still not mounted.
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    const [m] = live();
    // Read with the console's client: the host's headers went with it.
    const call = defined(
      api.log.find((c) => c.path.endsWith("/api/operate/explorer/schema-catalog.json")),
      'api.log.find((c) => c.path.endsWith("/api/operate/explorer/schema-catalog.json"))',
    );
    expect(call.method).toBe("GET");
    expect(call.headers.authorization).toBe("Bearer t");
    const { onSelect, onNavigate, onCatalogError, onError, themeVariables, ...rest } = defined(
      m,
      "m",
    ).options;
    expect(rest).toEqual({
      assetsUrl: "/umf-explorer/",
      entries: toEntries(wire.schemaCatalog()),
      categories: [{ id: "domain", label: "Registered modules" }],
      selection: { schema: "arras:catalog" },
      annotations: annotationsFor(api.modules, api.status, toEntries(wire.schemaCatalog())),
      readOnlyLocalFiles: true,
      hideHero: true,
      theme: "light",
      title: "UMF schema browser",
      height: "100%",
    });
    for (const f of [onSelect, onNavigate, onCatalogError, onError])
      expect(f).toBeTypeOf("function");
    expect(themeVariables).toBeTypeOf("object");
    expect(defined(m, "m").container).toBe(screen.getByTestId("umf-browser"));
    expect(defined(m, "m").iframe.getAttribute("style")).toBeNull(); // no positioning workaround: height '100%' in a sized container
    expect(screen.getByText("Loading UMF's schema browser…")).toBeInTheDocument();
    await act(async () => defined(m, "m").load());
    expect(screen.queryByText("Loading UMF's schema browser…")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(defined(m, "m").focused).toBe(0); // opened with the pointer
    expect(screen.getByTestId("umf-source")).toHaveTextContent("The declared UMF document");
    expect(screen.getByTestId("umf-source")).toHaveTextContent("what this deployment serves");
    // Back to the live registry: destroyed, the cards are back.
    await user.click(screen.getByRole("button", { name: "Live registry" }));
    expect(defined(m, "m").destroyed).toBe(true);
    expect(screen.queryByTitle("UMF schema browser")).toBeNull();
    expect(screen.getByTestId("type-catalog.UseCase")).toBeInTheDocument();
  });

  it("the annotations carry the live registry for the registered document's records and relationship", async () => {
    realCatalog();
    await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    const a = defined(
      defined(live()[0], "live()[0]").options.annotations,
      'defined(live()[0], "live()[0]").options.annotations',
    );
    // Separate annotations per backend (package 1.1.2 reserves a map line for each), real tones.
    for (const record of ["UseCase", "Solution"])
      expect(
        defined(a[definitionKey("catalog", record)], 'a[definitionKey("catalog", record)]').map(
          (x) => [x.badge, x.tone],
        ),
      ).toEqual([
        ["memory · mutable", "positive"],
        ["memory_replica · read-only", "neutral"],
      ]);
    expect(
      defined(
        defined(
          a[relationshipKey("catalog", "solution-addresses")],
          'a[relationshipKey("catalog", "solution-addresses")]',
        )[0],
        'defined(a[relationshipKey("catalog", "solution-addresses")], "a[relationshipKey(\\"catalog\\", \\"solution-addresses\\")]")[0]',
      ).badge,
    ).toBe("follows: memory, memory_replica");
    expect(defined(a["arras:catalog"], 'a["arras:catalog"]').map((x) => [x.badge, x.tone])).toEqual(
      [
        ["record: memory", "positive"],
        ["replica: memory_replica", "neutral"],
      ],
    );
  });

  it("a registry change is setAnnotations on the same mount; an unchanged refresh sends nothing", async () => {
    realCatalog();
    const user = await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = defined(live()[0], "live()[0]");
    await act(async () => m.load());
    await user.click(screen.getByRole("button", { name: "Refresh badges" }));
    await waitFor(() =>
      expect(
        api.log.filter((c) => c.body?.query?.includes("modules")).length,
      ).toBeGreaterThanOrEqual(2),
    );
    expect(m.annotations).toHaveLength(0);
    api.status = api.status.map(
      (s): BackendStatus =>
        s.backend === "memory_replica" ? { ...s, available: false, reason: "unreachable" } : s,
    ) as typeof api.status;
    api.modules = api.modules.map((mod) => ({
      ...mod,
      entityTypes: mod.entityTypes.map((t) => ({
        ...t,
        capabilities: { memory: defined(t.capabilities.memory, "t.capabilities.memory") },
      })),
    }));
    await user.click(screen.getByRole("button", { name: "Refresh badges" }));
    // Wait for what the browser is given, not for a number of calls.
    await waitFor(() =>
      expect(
        m.annotations.at(-1)?.[definitionKey("catalog", "UseCase")]?.map((x) => x.badge),
      ).toEqual(["memory · mutable", "memory_replica · unavailable"]),
    );
    expect(mounts).toHaveLength(1);
    expect(m.destroyed).toBe(false);
  });

  it("events reach the console's line; a definition that is a type offers Open in Entities and Show in Graph", async () => {
    realCatalog();
    const onOpenData = vi.fn();
    const onShowGraph = vi.fn();
    const user = await openUmf(
      <SchemaBrowser module="catalog" onOpenData={onOpenData} onShowGraph={onShowGraph} />,
    );
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = defined(live()[0], "live()[0]");
    await act(async () => m.load());
    expect(screen.getByTestId("umf-selection")).toHaveTextContent(
      "Select a definition in the browser",
    );
    act(() => defined(m.options.onSelect, "m.options.onSelect")({ schema: "arras:catalog" }));
    expect(screen.getByTestId("umf-selection")).toHaveTextContent("Selected: catalog");
    expect(screen.queryByRole("button", { name: /in Entities/ })).toBeNull();
    act(() =>
      defined(
        m.options.onNavigate,
        "m.options.onNavigate",
      )({
        schema: "arras:catalog",
        definition: definitionKey("catalog", "UseCase"),
      }),
    );
    expect(screen.getByTestId("umf-selection")).toHaveTextContent("Selected: catalog › UseCase");
    await user.click(screen.getByRole("button", { name: "Open UseCase in Entities" }));
    expect(onOpenData).toHaveBeenCalledWith("catalog.UseCase");
    await user.click(screen.getByRole("button", { name: "Show UseCase in Graph" }));
    expect(onShowGraph).toHaveBeenCalledWith("catalog.UseCase");
    act(() =>
      defined(
        m.options.onNavigate,
        "m.options.onNavigate",
      )({
        schema: "arras:catalog",
        relationship: relationshipKey("catalog", "solution-addresses"),
      }),
    );
    expect(screen.getByTestId("umf-selection")).toHaveTextContent(
      "Selected: catalog › relationship solution-addresses",
    );
    expect(screen.queryByRole("button", { name: /in Graph/ })).toBeNull();
  });

  it("through the console, Open in Entities and Show in Graph switch areas with the console's router", async () => {
    realCatalog();
    const user = userEvent.setup();
    renderConsole({ hashRouting: true });
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    await act(async () => defined(live()[0], "live()[0]").load());
    act(() =>
      defined(
        defined(live()[0], "live()[0]").options.onSelect,
        'defined(live()[0], "live()[0]").options.onSelect',
      )({
        schema: "arras:catalog",
        definition: definitionKey("catalog", "Solution"),
      }),
    );
    await user.click(screen.getByRole("button", { name: "Open Solution in Entities" }));
    await waitFor(() => expect(window.location.hash).toBe("#/catalog/entities/catalog.Solution"));
    await user.click(screen.getByRole("tab", { name: "Model" }));
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    await act(async () => defined(live()[0], "live()[0]").load());
    act(() =>
      defined(
        defined(live()[0], "live()[0]").options.onSelect,
        'defined(live()[0], "live()[0]").options.onSelect',
      )({
        schema: "arras:catalog",
        definition: definitionKey("catalog", "Solution"),
      }),
    );
    await user.click(screen.getByRole("button", { name: "Show Solution in Graph" }));
    await waitFor(() => expect(window.location.hash).toBe("#/catalog/graph"));
    const types = await screen.findByRole("group", { name: "Types" });
    expect(types.querySelector('[aria-pressed="false"]')).toHaveTextContent("UseCase");
    expect(types.querySelector('[aria-pressed="true"]')).toHaveTextContent("Solution");
  });

  it("another module of the same catalog is select() on the same mount, not a remount", async () => {
    const other = {
      ...defined(wire.schemaCatalog().entries[0], "wire.schemaCatalog().entries[0]"),
      id: "arras:other",
      title: "other",
    };
    realCatalog([other]);
    function Switcher() {
      const [m, setM] = useState("catalog");
      return (
        <>
          <button type="button" onClick={() => setM(m === "catalog" ? "other" : "catalog")}>
            switch
          </button>
          <UmfSource module={m} />
        </>
      );
    }
    const user = userEvent.setup();
    renderPart(<Switcher />);
    await waitFor(() => expect(live()).toHaveLength(1));
    const first = defined(live()[0], "live()[0]");
    expect(first.options.selection).toEqual({ schema: "arras:catalog" });
    await act(async () => first.load());
    await user.click(screen.getByRole("button", { name: "switch" }));
    expect(first.selects).toEqual([{ schema: "arras:other" }]);
    await user.click(screen.getByRole("button", { name: "switch" }));
    expect(first.selects).toEqual([{ schema: "arras:other" }, { schema: "arras:catalog" }]);
    expect(mounts).toHaveLength(1);
    expect(first.destroyed).toBe(false);
    expect(screen.getAllByTitle("UMF schema browser")).toHaveLength(1);
  });

  it("a module the catalog does not list: the empty state, and the mount is destroyed", async () => {
    function Switcher() {
      const [m, setM] = useState("catalog");
      return (
        <>
          <button type="button" onClick={() => setM("unlisted")}>
            switch
          </button>
          <UmfSource module={m} />
        </>
      );
    }
    const user = userEvent.setup();
    renderPart(<Switcher />);
    await waitFor(() => expect(live()).toHaveLength(1));
    const first = defined(live()[0], "live()[0]");
    await user.click(screen.getByRole("button", { name: "switch" }));
    expect(first.destroyed).toBe(true);
    expect(await screen.findByTestId("umf-empty")).toHaveTextContent(
      "No registered UMF document for unlisted is readable for you",
    );
  });

  it("a colour scheme change remounts in the new theme (theme variables are fixed at mount)", async () => {
    let dark = false;
    const listeners = new Set<() => void>();
    vi.stubGlobal("matchMedia", (q: string) => ({
      get matches() {
        return q === "(prefers-color-scheme: dark)" && dark;
      },
      media: q,
      addEventListener: (_: string, f: () => void) => listeners.add(f),
      removeEventListener: (_: string, f: () => void) => listeners.delete(f),
    }));
    realCatalog();
    await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(defined(live()[0], "live()[0]").options.theme).toBe("light");
    dark = true;
    act(() => {
      for (const f of listeners) f();
    });
    await waitFor(() => expect(defined(live()[0], "live()[0]").options.theme).toBe("dark"));
    expect(mounts).toHaveLength(2);
    expect(live()).toHaveLength(1);
    // The same tones in dark as in light: no neutral-in-dark workaround (package 1.1.2).
    const shown = () => {
      const m = defined(live()[0], "live()[0]");
      return (m.annotations.at(-1) ?? m.options.annotations)?.[
        definitionKey("catalog", "UseCase")
      ]?.map((x) => x.tone);
    };
    await waitFor(() => expect(shown()).toEqual(["positive", "neutral"]));
  });

  it("the host's own switch re-themes the frame: data-appearance on an ancestor, or the system's preference when it has none", async () => {
    let dark = false;
    const listeners = new Set<() => void>();
    vi.stubGlobal("matchMedia", (q: string) => ({
      get matches() {
        return q === "(prefers-color-scheme: dark)" && dark;
      },
      media: q,
      addEventListener: (_: string, f: () => void) => listeners.add(f),
      removeEventListener: (_: string, f: () => void) => listeners.delete(f),
    }));
    realCatalog();
    const user = userEvent.setup();
    render(
      <div data-testid="host" data-appearance="light">
        <ArrasProvider queryClient={qc()}>
          <Scope>
            <SchemaBrowser module="catalog" />
          </Scope>
        </ArrasProvider>
      </div>,
    );
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    const theme = () => defined(live()[0], "live()[0]").options.theme;
    const host = screen.getByTestId("host");
    expect(theme()).toBe("light");
    dark = true; // the system is dark, but the host chose light: it wins
    act(() => {
      for (const f of listeners) f();
    });
    expect(theme()).toBe("light");
    act(() => host.setAttribute("data-appearance", "dark"));
    await waitFor(() => expect(theme()).toBe("dark"));
    dark = false;
    act(() => host.setAttribute("data-appearance", "light"));
    await waitFor(() => expect(theme()).toBe("light"));
    act(() => host.removeAttribute("data-appearance")); // auto: the system's (light)
    expect(theme()).toBe("light");
    dark = true;
    act(() => {
      for (const f of listeners) f();
    });
    await waitFor(() => expect(theme()).toBe("dark"));
    expect(document.documentElement.getAttribute("data-appearance")).toBeNull();
  });

  const renderHosted = async (attrs: HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => {
    realCatalog();
    const user = userEvent.setup();
    render(
      <div data-testid="host" {...attrs}>
        <ArrasProvider queryClient={qc()}>
          <Scope>
            <SchemaBrowser module="catalog" />
          </Scope>
        </ArrasProvider>
      </div>,
    );
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    return screen.getByTestId("host");
  };

  it("a theme change that leaves the appearance as it was re-themes the frame", async () => {
    const host = await renderHosted({ "data-appearance": "light", "data-theme": "one" });
    host.style.setProperty("--surface", "#ffffff");
    act(() => host.setAttribute("data-theme", "one"));
    const paper = () => defined(live().at(-1), "live").options.themeVariables?.["--paper"];
    await waitFor(() => expect(paper()).toBe("#ffffff"));
    const before = mounts.length;
    host.style.setProperty("--surface", "#f0eee6");
    act(() => host.setAttribute("data-theme", "two"));
    await waitFor(() => expect(paper()).toBe("#f0eee6"));
    expect(mounts.length).toBe(before + 1);
    expect(defined(live().at(-1), "live").options.theme).toBe("light");
  });

  it("follows a host's inline color-scheme when it sets no data-appearance", async () => {
    const host = await renderHosted({ style: { colorScheme: "dark" } });
    expect(defined(live()[0], "live()[0]").options.theme).toBe("dark");
    act(() => {
      host.style.colorScheme = "light";
    });
    await waitFor(() => expect(defined(live().at(-1), "live").options.theme).toBe("light"));
  });

  it("watches attributes only, on the page's root element and the console's ancestors, never a subtree", async () => {
    const seen: [Node, MutationObserverInit | undefined][] = [];
    const observe = MutationObserver.prototype.observe;
    const spy = vi.spyOn(MutationObserver.prototype, "observe").mockImplementation(function (
      this: MutationObserver,
      target,
      options,
    ) {
      seen.push([target, options]);
      return observe.call(this, target, options);
    });
    try {
      const host = await renderHosted({ "data-appearance": "light" });
      const mine = seen.filter(([, o]) => o?.attributeFilter?.includes("data-appearance"));
      const targets = mine.map(([t]) => t);
      expect(targets).toContain(document.documentElement);
      expect(targets).toContain(host);
      expect(targets).not.toContain(document.querySelector(".arras-root")); // the console's own root is not a host's
      for (const [, o] of mine) {
        expect(o?.subtree).toBeFalsy();
        expect(o?.attributeFilter).toEqual(["data-appearance", "data-theme", "class", "style"]);
      }
    } finally {
      spy.mockRestore();
    }
  });

  it("an element that stops being an ancestor of the console is no longer watched: a console moved under another host reacts to the new one only", async () => {
    const Real = MutationObserver;
    const watching = new Map<MutationObserver, Set<Node>>();
    let fired = 0;
    class Spy extends Real {
      constructor(callback: MutationCallback) {
        super((records, self) => {
          if (watching.has(self)) fired += 1;
          callback(records, self);
        });
      }
      override observe(target: Node, options?: MutationObserverInit) {
        // the console's own observer is the one that asks for the theme attributes
        if (options?.attributeFilter?.includes("data-theme"))
          watching.set(this, (watching.get(this) ?? new Set()).add(target));
        super.observe(target, options);
      }
      override disconnect() {
        if (watching.has(this)) watching.set(this, new Set());
        super.disconnect();
      }
    }
    vi.stubGlobal("MutationObserver", Spy);
    const old = await renderHosted({ "data-appearance": "light" });
    const root = defined(document.querySelector<HTMLElement>(".arras-root"), ".arras-root");
    const next = document.createElement("div");
    next.setAttribute("data-appearance", "dark");
    document.body.append(next);
    const targets = () => [...watching.values()].flatMap((s) => [...s]);
    try {
      expect(targets()).toContain(old);
      next.append(root); // the console now sits under another host
      act(() => old.setAttribute("data-theme", "left")); // the last change the old host is seen making
      await waitFor(() => expect(targets()).toContain(next));
      expect(targets()).not.toContain(old);
      await waitFor(() => expect(defined(live().at(-1), "live").options.theme).toBe("dark"));
      const before = fired;
      act(() => old.setAttribute("data-theme", "ignored"));
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0)); // the observer's records are delivered in a microtask
      });
      expect(fired).toBe(before);
      act(() => next.setAttribute("data-appearance", "light")); // the new host is heard
      await waitFor(() => expect(defined(live().at(-1), "live").options.theme).toBe("light"));
    } finally {
      old.append(root);
      next.remove();
    }
  });

  let lateHost: HTMLElement | undefined;
  /** A host's provider: it writes its attributes in an effect, which runs after the console's own mount. */
  function LateProvider({ children }: { children: ReactNode }) {
    const el = useRef<HTMLDivElement>(null);
    useEffect(() => {
      const host = el.current;
      if (!host) return;
      host.setAttribute("data-appearance", "dark");
      host.style.setProperty("--surface", "#101010");
      lateHost = host;
    }, []);
    return (
      <div ref={el} data-testid="host">
        <div>{children}</div>
      </div>
    );
  }

  it("a provider that applies its appearance after the console mounted is seen, and each later toggle re-themes the frame", async () => {
    realCatalog();
    render(
      <LateProvider>
        <ArrasProvider queryClient={qc()}>
          <Scope>
            <UmfSource module="catalog" />
          </Scope>
        </ArrasProvider>
      </LateProvider>,
    );
    const theme = () => defined(live().at(-1), "live").options.theme;
    await waitFor(() => expect(live()).toHaveLength(1));
    await waitFor(() => expect(theme()).toBe("dark"));
    const host = defined(lateHost, "the provider's element");
    act(() => host.setAttribute("data-appearance", "light"));
    await waitFor(() => expect(theme()).toBe("light"));
    act(() => host.setAttribute("data-appearance", "dark"));
    await waitFor(() => expect(theme()).toBe("dark"));
  });

  it("a tokens-only provider (custom properties, no color-scheme) written after mount re-themes the frame each time", async () => {
    realCatalog();
    let host: HTMLElement | undefined;
    function TokensProvider({ children }: { children: ReactNode }) {
      const el = useRef<HTMLDivElement>(null);
      useEffect(() => {
        host = el.current ?? undefined;
        host?.style.setProperty("--surface", "#ffffff");
      }, []);
      return (
        <div ref={el}>
          <div>{children}</div>
        </div>
      );
    }
    render(
      <TokensProvider>
        <ArrasProvider queryClient={qc()}>
          <Scope>
            <UmfSource module="catalog" />
          </Scope>
        </ArrasProvider>
      </TokensProvider>,
    );
    const paper = () => defined(live().at(-1), "live").options.themeVariables?.["--paper"];
    await waitFor(() => expect(live()).toHaveLength(1));
    await waitFor(() => expect(paper()).toBe("#ffffff"));
    for (const tone of ["#f0eee6", "#1b1a19"]) {
      act(() => host?.style.setProperty("--surface", tone));
      await waitFor(() => expect(paper()).toBe(tone));
    }
  });

  it("a host's explorerBase is the assetsUrl, through the console", async () => {
    const user = userEvent.setup();
    renderConsole({ explorerBase: "/static/umf" });
    await screen.findByTestId("schema");
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(defined(live()[0], "live()[0]").options.assetsUrl).toBe("/static/umf/");
  });

  it("opened with the keyboard: focus() once ready; with the pointer: not", async () => {
    const user = userEvent.setup();
    renderPart(<SchemaBrowser module="catalog" />);
    await screen.findByTestId("schema");
    screen.getByRole("button", { name: "UMF source" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(defined(live()[0], "live()[0]").focused).toBe(0);
    await act(async () => defined(live()[0], "live()[0]").load());
    expect(defined(live()[0], "live()[0]").focused).toBe(1);
  });

  it("a rejected ready (the package's 30 s bound, or a failure) names where the assets go, and Retry mounts again", async () => {
    const user = await openUmf(<SchemaBrowser module="catalog" explorerBase="/static/umf/" />);
    await waitFor(() => expect(live()).toHaveLength(1));
    await act(async () =>
      defined(live()[0], "live()[0]").reject(new Error("Schema browser initialization timed out")),
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(
      "UMF's schema browser did not load (Schema browser initialization timed out)",
    );
    expect(alert).toHaveTextContent("/static/umf/");
    expect(alert).toHaveTextContent("Content-Security-Policy");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(mounts).toHaveLength(2);
    await act(async () => defined(live()[0], "live()[0]").load());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("onCatalogError with status 401 is sign in again, not a load failure; Retry reads the catalog and mounts again", async () => {
    const user = await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = defined(live()[0], "live()[0]");
    const e: BrowserError = { code: "CATALOG", message: "HTTP 401", status: 401, phase: "catalog" };
    await act(async () => {
      defined(m.options.onCatalogError, "m.options.onCatalogError")(e);
      m.reject(new Error("HTTP 401"));
    });
    const panel = screen.getByTestId("umf-catalog-error");
    expect(panel).toHaveTextContent("Sign in again");
    expect(screen.queryByText(/did not load/)).toBeNull();
    const reads = api.log.filter((c) => c.path.endsWith("/explorer/schema-catalog.json")).length;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(mounts).toHaveLength(2);
    expect(api.log.filter((c) => c.path.endsWith("/explorer/schema-catalog.json")).length).toBe(
      reads + 1,
    );
  });

  it("onCatalogError with another status is the load failure, with the package's message", async () => {
    await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    await act(async () =>
      defined(
        defined(live()[0], "live()[0]").options.onCatalogError,
        'defined(live()[0], "live()[0]").options.onCatalogError',
      )({
        code: "CATALOG",
        message: "Duplicate or missing entry identity",
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "did not load (Duplicate or missing entry identity)",
    );
  });

  it("onError after ready is a notice; a superseded request is not", async () => {
    await openUmf();
    await waitFor(() => expect(live()).toHaveLength(1));
    const m = defined(live()[0], "live()[0]");
    await act(async () => m.load());
    act(() =>
      defined(
        m.options.onError,
        "m.options.onError",
      )({ code: "SUPERSEDED", message: "superseded" }),
    );
    expect(screen.queryByText(/reported/)).toBeNull();
    act(() =>
      defined(
        m.options.onError,
        "m.options.onError",
      )({ code: "SOURCE", message: "bad source", phase: "selection" }),
    );
    expect(screen.getByText(/reported/)).toHaveTextContent(
      "UMF's schema browser reported SOURCE: bad source",
    );
  });

  it("a 401 on the catalog is sign in again: the host is told, and nothing is mounted", async () => {
    api.on((r) =>
      r.path.endsWith("/explorer/schema-catalog.json") ? err(401, wire.tokenExpired()) : undefined,
    );
    const onUnauthorized = vi.fn();
    await openUmf(<SchemaBrowser module="catalog" />, { onUnauthorized });
    const error = await screen.findByTestId("umf-catalog-error");
    expect(error).toHaveTextContent("Sign in again");
    expect(onUnauthorized).toHaveBeenCalled();
    expect(mounts).toHaveLength(0);
  });

  it("an outage is the backend's failure, never an empty catalog", async () => {
    api.on((r) =>
      r.path.endsWith("/explorer/schema-catalog.json")
        ? err(503, { type: "Unavailable", message: "x", reason: "unreachable", backend: "memory" })
        : undefined,
    );
    await openUmf();
    expect(await screen.findByTestId("umf-catalog-error")).toHaveTextContent("Backend unavailable");
    expect(screen.queryByTestId("umf-empty")).toBeNull();
    expect(mounts).toHaveLength(0);
  });

  it("an empty catalog, or one without this module, is the empty state and mounts nothing", async () => {
    api.on((r) =>
      r.path.endsWith("/explorer/schema-catalog.json")
        ? { status: 200, body: { version: 1, entries: [] } }
        : undefined,
    );
    await openUmf();
    expect(await screen.findByTestId("umf-empty")).toHaveTextContent(
      "No registered UMF documents are readable for you",
    );
    expect(mounts).toHaveLength(0);
  });

  it("a catalog that lists other modules but not this one says so", async () => {
    api.on((r) =>
      r.path.endsWith("/explorer/schema-catalog.json")
        ? {
            status: 200,
            body: {
              version: 1,
              entries: [
                {
                  ...defined(wire.schemaCatalog().entries[0], "wire.schemaCatalog().entries[0]"),
                  id: "arras:other",
                },
              ],
            },
          }
        : undefined,
    );
    await openUmf();
    expect(await screen.findByTestId("umf-empty")).toHaveTextContent(
      "No registered UMF document for catalog is readable for you",
    );
    expect(mounts).toHaveLength(0);
  });
});

describe("UMF source in the address (CONTRACT-010 D)", () => {
  const solution = { schema: "arras:catalog", definition: definitionKey("catalog", "Solution") };

  it("#/operate/catalog/model/catalog.Solution?view=umf opens the source with Solution selected", async () => {
    realCatalog();
    window.location.hash = "#/operate/catalog/model/catalog.Solution?view=umf";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await waitFor(() => expect(live()).toHaveLength(1));
    expect(defined(live()[0], "live()[0]").options.selection).toEqual(solution);
    expect(screen.getByRole("button", { name: "UMF source" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opening the source pushes ?view=umf; selecting a type in the browser pushes it into the address", async () => {
    realCatalog();
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await screen.findByTestId("schema");
    const before = window.history.length;
    await user.click(screen.getByRole("button", { name: "UMF source" }));
    expect(window.location.hash).toBe("#/operate/catalog/model?view=umf");
    await waitFor(() => expect(live()).toHaveLength(1));
    await act(async () => defined(live()[0], "live()[0]").load());
    act(() => defined(live()[0], "live()[0]").options.onSelect?.(solution));
    await waitFor(() =>
      expect(window.location.hash).toBe("#/operate/catalog/model/catalog.Solution?view=umf"),
    );
    expect(window.history.length).toBe(before + 2);
    // the browser's own selection is what the address now says: nothing is selected again
    expect(defined(live()[0], "live()[0]").selects).toEqual([]);
  });

  it("Back selects the type the address names in the mounted browser, without a remount", async () => {
    realCatalog();
    const user = userEvent.setup();
    window.location.hash = "#/operate/catalog/model?view=umf";
    renderConsole({ hashRouting: true, hashPrefix: "operate" });
    await waitFor(() => expect(live()).toHaveLength(1));
    const mount = defined(live()[0], "live()[0]");
    await act(async () => mount.load());
    act(() => mount.options.onSelect?.(solution));
    await waitFor(() => expect(window.location.hash).toContain("catalog.Solution"));
    act(() => window.history.back());
    await waitFor(() => expect(window.location.hash).toBe("#/operate/catalog/model?view=umf"));
    await waitFor(() => expect(mount.selects).toEqual([{ schema: "arras:catalog" }]));
    expect(mounts).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Live registry" }));
    expect(window.location.hash).toBe("#/operate/catalog/model");
  });

  describe("the rail's module change", () => {
    const rail = () => screen.getByRole("navigation", { name: "Modules" });
    const pickOther = (user: ReturnType<typeof userEvent.setup>) =>
      user.click(within(rail()).getByRole("button", { name: /other/ }));

    beforeEach(() => {
      realCatalog();
      api.modules = [catalog(), catalog({ name: "other" })];
    });

    it("keeps the UMF source open; Back and Forward restore the exact addresses", async () => {
      const user = userEvent.setup();
      window.location.hash = "#/operate/catalog/model/catalog.UseCase?view=umf";
      renderConsole({ hashRouting: true, hashPrefix: "operate" });
      await waitFor(() => expect(live()).toHaveLength(1));
      const before = window.history.length;
      await pickOther(user);
      expect(window.location.hash).toBe("#/operate/other/model?view=umf");
      expect(window.history.length).toBe(before + 1);
      act(() => window.history.back());
      await waitFor(() =>
        expect(window.location.hash).toBe("#/operate/catalog/model/catalog.UseCase?view=umf"),
      );
      act(() => window.history.forward());
      await waitFor(() => expect(window.location.hash).toBe("#/operate/other/model?view=umf"));
      expect(screen.getByRole("button", { name: "UMF source" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    it("rewrites nothing on a direct navigation: the type stays and no entry is added", async () => {
      window.location.hash = "#/operate/catalog/model?view=umf";
      renderConsole({ hashRouting: true, hashPrefix: "operate" });
      await waitFor(() => expect(live()).toHaveLength(1));
      const before = window.history.length;
      act(() => {
        window.location.hash = "#/operate/other/model/catalog.UseCase";
      });
      await screen.findByRole("button", { name: "UMF source", pressed: false });
      expect(window.location.hash).toBe("#/operate/other/model/catalog.UseCase");
      expect(window.history.length).toBe(before + 1);
    });
  });
});
