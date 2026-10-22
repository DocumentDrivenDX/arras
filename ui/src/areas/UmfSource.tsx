// SPDX-License-Identifier: MIT OR Apache-2.0
import {
  type BrowserError,
  mountSchemaBrowser,
  type Selection,
} from "@documentdrivendx/umf-schema-browser";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useClient } from "../api/context";
import { ApiError } from "../api/errors";
import { SCHEMA_CATALOG_KEY, useMeta } from "../api/queries";
import type { SchemaCatalog } from "../api/types";
import { Notice } from "../components/ui";
import { type Mount, SelectionBar, UmfStatus } from "./UmfSourceParts";
import {
  annotationsFor,
  CATEGORIES,
  entryId,
  hostTheme,
  selectionFor,
  toEntries,
  typeForSelection,
} from "./umfBrowser";

export { entryId, toEntries } from "./umfBrowser";

/** Where the host serves the package's `assets/` directory (ui/README.md, "UMF source"). */
export const DEFAULT_EXPLORER_BASE = "/umf-explorer";

const DARK = "(prefers-color-scheme: dark)";
const THEME_ATTRIBUTES = ["data-appearance", "data-theme", "class", "style"];

/**
 * The elements a host's theme provider may write its attributes on: the page's root element and every ancestor
 * of the console's root, which is where a provider wraps it. Each is watched for its attributes only.
 */
function themeTargets(): Element[] {
  const targets = new Set<Element>([document.documentElement]);
  for (let a = document.querySelector(".arras-root")?.parentElement ?? null; a; a = a.parentElement)
    targets.add(a);
  return [...targets];
}

/**
 * Changes of the system's preference, and of the host's own switch: the `data-appearance`, `data-theme`,
 * `class` or inline `style` (a `color-scheme`, or the theme's tokens) of the page's root element and of the
 * console's ancestors. Nothing else on the page is watched, and no subtree. A provider may write its attribute
 * after the console has mounted (its effect runs after the console's own), or on an element that had none, so
 * the ancestors are resolved again on every change and once more after mount. An element that stops being an
 * ancestor (the console was moved) is no longer watched: an observer cannot drop one target, so when the set
 * differs it is disconnected and observes the current set.
 */
function subscribeTheme(on: () => void): () => void {
  const q = window.matchMedia?.(DARK);
  q?.addEventListener("change", on);
  const options = { attributes: true, attributeFilter: THEME_ATTRIBUTES };
  let watched = new Set<Element>();
  const watch = new MutationObserver(() => {
    resolve();
    on();
  });
  const resolve = () => {
    const now = themeTargets();
    if (now.length === watched.size && now.every((t) => watched.has(t))) return;
    watch.disconnect();
    watched = new Set(now);
    for (const t of now) watch.observe(t, options);
  };
  resolve();
  // Providers' effects run after this subscription: look again once they have, and say if anything changed.
  let live = true;
  const settle = () => {
    if (!live) return;
    resolve();
    on();
  };
  queueMicrotask(settle);
  const frame =
    typeof requestAnimationFrame === "function" ? requestAnimationFrame(settle) : undefined;
  return () => {
    live = false;
    if (frame !== undefined) cancelAnimationFrame(frame);
    q?.removeEventListener("change", on);
    watch.disconnect();
  };
}
/**
 * The theme the console shows the browser: its colour scheme and the variables it takes from the console's
 * tokens, as one string so that a change of either (a theme switched with the appearance unchanged) is a new
 * snapshot. Kept current.
 */
function useThemeKey(): string {
  return useSyncExternalStore(
    subscribeTheme,
    () => JSON.stringify(hostTheme(document)),
    () => "",
  );
}

export interface UmfSourceProps {
  module: string;
  explorerBase?: string;
  /** Open an entity type in the Data area (the console's router). */
  onOpenData?: (type: string) => void;
  /** Show an entity type in the Graph area (the console's router). */
  onShowGraph?: (type: string) => void;
  /** Move keyboard focus into the browser once it is ready (the view was opened by keyboard). */
  focusOnReady?: boolean;
  /** The entity type selected in the browser (the route's); it is selected there when the browser opens and when it changes. */
  type?: string;
  /** The person selected an entity type in the browser. */
  onSelectType?: (type: string) => void;
}

/**
 * OPR-11: the module's registered UMF document in UMF's own schema browser (the npm package
 * `@documentdrivendx/umf-schema-browser`, host contract 1.1). The catalog is read with the
 * console's client, so the host's headers, the expired-token signal and the bound on requests in
 * flight apply; the entries are handed to `mountSchemaBrowser`, whose iframe loads the package's
 * assets from `explorerBase`. The browser is mounted only while this view is shown and only once
 * per catalog and colour scheme: a module change is a `select`, a registry change `setAnnotations`.
 */
export function UmfSource({
  module,
  explorerBase = DEFAULT_EXPLORER_BASE,
  onOpenData,
  onShowGraph,
  focusOnReady = false,
  type: routeType,
  onSelectType,
}: UmfSourceProps) {
  const client = useClient();
  const meta = useMeta();
  const base = `${explorerBase.replace(/\/+$/, "")}/`;
  // The catalog is shared with Export and import (SCHEMA_CATALOG_KEY), which may have read it already: opening
  // this view reads it again, and a failed read (an expired token) shows its error, never the older entries.
  const catalog = useQuery<SchemaCatalog, ApiError>({
    queryKey: SCHEMA_CATALOG_KEY,
    queryFn: () => client.schemaCatalog(),
    retry: false,
    refetchOnMount: "always",
  });
  const entries = useMemo(
    () => (catalog.data && !catalog.error ? toEntries(catalog.data) : null),
    [catalog.data, catalog.error],
  );
  const listed = !!entries?.some((e) => e.id === entryId(module));
  const theme = useThemeKey();
  const annotations = useMemo(
    () =>
      entries && meta.data ? annotationsFor(meta.data.modules, meta.data.status, entries) : {},
    [entries, meta.data],
  );
  const info = meta.data?.modules.find((m) => m.name === module);
  // The mount point; it is re-keyed on a retry or a change of the theme, so the browser mounts afresh.
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const handle = useRef<ReturnType<typeof mountSchemaBrowser> | null>(null);
  const [mount, setMount] = useState<Mount>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [reported, setReported] = useState<BrowserError | null>(null);
  // The latest values, read when the browser is mounted, without remounting it when they change.
  const latest = useRef({ module, annotations, focusOnReady, routeType, onSelectType });
  latest.current = { module, annotations, focusOnReady, routeType, onSelectType };
  const shown = useRef<{ module: string; annotations: string } | null>(null);

  useEffect(() => {
    const el = container;
    if (!el || !entries || !listed) return;
    setMount({ state: "loading" });
    setSelected(null);
    setReported(null);
    let live = true;
    const fail = (why: string) =>
      live && setMount((s) => (s.state === "sign_in" ? s : { state: "failed", why }));
    const {
      module: first,
      annotations: notes,
      focusOnReady: focus,
      routeType: at,
    } = latest.current;
    const { theme, themeVariables } = hostTheme(el);
    let h: ReturnType<typeof mountSchemaBrowser>;
    try {
      h = mountSchemaBrowser(el, {
        assetsUrl: base,
        entries,
        categories: CATEGORIES,
        selection: selectionFor(first, at),
        annotations: notes,
        readOnlyLocalFiles: true,
        hideHero: true,
        theme,
        themeVariables,
        title: "UMF schema browser",
        height: "100%",
        onSelect: (s) => live && setSelected(s),
        onNavigate: (s) => live && setSelected(s),
        onCatalogError: (e) => {
          if (!live) return;
          if (e.status === 401)
            setMount({
              state: "sign_in",
              error: new ApiError(401, {
                type: "Refused",
                reason: "token_expired",
                message: e.message,
              }),
            });
          else fail(e.message);
        },
        onError: (e) => live && e.code !== "SUPERSEDED" && e.code !== "CATALOG" && setReported(e),
      });
    } catch (e) {
      fail(e instanceof Error ? e.message : String(e));
      return () => {
        live = false;
      };
    }
    handle.current = h;
    shown.current = { module: first, annotations: JSON.stringify(notes) };
    h.ready.then(
      () => {
        if (!live) return;
        setMount({ state: "ready" });
        if (focus) h.focus();
      },
      // Also the rejection `destroy()` causes before ready: ignored once this mount is gone.
      (e: unknown) => fail(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      live = false;
      handle.current = null;
      shown.current = null;
      h.destroy();
    };
  }, [container, entries, listed, base]);

  // Another module in the same catalog: select its entry in the mounted browser.
  useEffect(() => {
    const h = handle.current;
    if (!h || !shown.current || shown.current.module === module) return;
    shown.current.module = module;
    setSelected(null);
    h.select({ schema: entryId(module) }).catch((e: unknown) =>
      setReported({ code: "SELECTION", message: e instanceof Error ? e.message : String(e) }),
    );
  }, [module]);

  // The registry changed (a refresh, an outage): replace the annotations in place.
  useEffect(() => {
    const h = handle.current;
    const next = JSON.stringify(annotations);
    if (!h || !shown.current || shown.current.annotations === next) return;
    shown.current.annotations = next;
    h.setAnnotations(annotations);
  }, [annotations]);

  const type = typeForSelection(selected, info);
  const chosen = useRef(type);
  chosen.current = type;

  // The route selects another type (Back, a link): select it in the mounted browser. Only the route's
  // own change does this; what the person selects in the browser is what the route then follows.
  useEffect(() => {
    const h = handle.current;
    if (!h || !shown.current || chosen.current === routeType) return;
    h.select(selectionFor(module, routeType)).catch((e: unknown) =>
      setReported({ code: "SELECTION", message: e instanceof Error ? e.message : String(e) }),
    );
  }, [module, routeType]);

  // The person selected an entity type in the browser: the route follows.
  useEffect(() => {
    if (type && type !== latest.current.routeType) latest.current.onSelectType?.(type);
  }, [type]);
  const failed = mount.state === "failed" || mount.state === "sign_in";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2" data-testid="umf-source">
      <Notice>
        <strong>The declared UMF document</strong>, as it was registered, in UMF&apos;s schema
        browser. The badges are this deployment&apos;s <strong>live registry</strong>: what each
        backend serves. The <em>Live registry</em> view shows{" "}
        <strong>what this deployment serves</strong> in full: each backend&apos;s capabilities, the
        actions and the revision. Neither says what a backend enforces; the backends decide access.
      </Notice>
      <UmfStatus
        catalog={catalog}
        listed={listed}
        entries={entries}
        module={module}
        mount={mount}
        base={base}
        onRetry={() => setAttempt((n) => n + 1)}
      />
      {listed && !failed && mount.state === "ready" && (
        <SelectionBar
          selected={selected}
          entries={entries}
          type={type}
          onOpenData={onOpenData}
          onShowGraph={onShowGraph}
          onRefresh={() => void meta.refetch()}
        />
      )}
      {reported && mount.state === "ready" && (
        <Notice tone="warn" role="status">
          UMF&apos;s schema browser reported <span className="arras-mono">{reported.code}</span>:{" "}
          {reported.message}
        </Notice>
      )}
      {listed && (
        <div
          key={`${attempt}:${theme}`}
          ref={setContainer}
          data-testid="umf-browser"
          className={`h-[max(640px,calc(100dvh-260px))] shrink-0 overflow-hidden rounded border border-line bg-surface ${failed ? "hidden" : ""}`}
        />
      )}
    </div>
  );
}
