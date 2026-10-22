// SPDX-License-Identifier: MIT OR Apache-2.0
// The Graph Browser (FEAT-011, ADR-021 to ADR-025): an interface over the ontology that reads as
// the viewer. It reaches Arras over HTTP only (GraphQL reads on the console surface) and holds no
// credential. The location is the page's whole identity (module, type, key, history, after) and is
// kept in the URL fragment unless the host owns it (`location`, `onLocation`); view state (the
// search text, the chosen types, the scroll position) never enters the URL. Its writes are an
// in-place edit of a property by a declared action, plus Retire, the Actions menu and New (CONTRACT-010
// F), all offered only where the host sets `canEdit` (`useEdit`).
import {
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrasProviderOnce, type ProviderProps } from "../api/context";
import { useSearchPause } from "../api/search";
import type { ModuleInfo } from "../api/types";
import { Scope } from "../components/Scope";
import type { LinkTo } from "../kit";
import { BrowserProvider, useBrowser } from "./context";
import { Entry } from "./Entry";
import {
  type ExploreLocation,
  type LocationProps,
  readViewState,
  saveViewState,
  useBrowserLocation,
} from "./location";
import { ModuleChooser } from "./ModuleChooser";
import { searchServed, useBrowserMeta } from "./meta";
import { NodePage } from "./NodePage";
import { moduleOf, type Resolved, resolveLocation } from "./resolve";
import { BackendDown, Expired, Failed, NotAvailable, Skeleton } from "./states";
import { TopBar } from "./TopBar";
import { usePageTitle } from "./useBrowserTitle";
import { stateOf } from "./useNode";

export interface GraphBrowserProps extends LocationProps {
  operateBase?: ProviderProps["operateBase"];
  consoleBase?: ProviderProps["consoleBase"];
  /** A host's own auth headers, read on every request. The browser stores no credential. */
  getHeaders?: ProviderProps["getHeaders"];
  /** Called on a 401 so the host can sign the viewer in again. */
  onUnauthorized?: ProviderProps["onUnauthorized"];
  /** What the interface is called (name, wordmark, page title); the default is Arras. */
  brand?: ProviderProps["brand"];
  /** Supply a query client (tests); one is created otherwise. */
  queryClient?: ProviderProps["queryClient"];
  /**
   * Offer the writes: in-place edits of a property that a declared action updates, Retire, the Actions
   * menu and New (CONTRACT-010 F). The shell sets it for an operator (the viewer's `admin` mode id); the
   * backends' grants still decide what is applied.
   */
  canEdit?: boolean;
  /**
   * Edit mode, the lock that shows the edit controls, when the host keeps it (the shell, so a switch of
   * mode keeps it) with `onEditing`; the browser keeps its own without them.
   */
  editing?: boolean;
  onEditing?: (on: boolean) => void;
  /**
   * Whether the plain-key shortcuts are on (`/` focuses the search box); the host's Single-key shortcuts
   * switch. Default on.
   */
  singleKeys?: boolean;
  /**
   * The host's command palette, drawn inside the browser so it opens places through the browser's own
   * `go` and reads the module the page is in. The host (the shell) owns its keys and its open state.
   */
  palette?: (at: {
    module: ModuleInfo | undefined;
    go: (loc: ExploreLocation, opts?: { replace?: boolean }) => void;
  }) => ReactNode;
  /**
   * The link into Operate, handed in by the shell for an operator (Rule 7). Without it the browser
   * draws no cross-mode link and carries no word of the other mode.
   */
  links?: { toOperate: LinkTo };
  /** The host's mode switch, placed in the top bar (the shell, ADR-025). */
  modeSwitch?: ReactNode;
  /** Extra top bar content (the dev host's person picker). */
  toolbar?: ReactNode;
}

interface Search {
  draft: string;
  setDraft: (v: string) => void;
  types: string[];
  setTypes: Dispatch<SetStateAction<string[]>>;
}

/** The search text and chosen types, kept in the history entry's own state (never in the URL). */
function useSearchState(locKey: string): Search {
  const [draft, setDraft] = useState(() => readViewState().text ?? "");
  const [types, setTypes] = useState<string[]>(() => readViewState().types ?? []);
  const latest = useRef({ draft, types });
  latest.current = { draft, types };
  // Arriving at an entry: take what it saved (Back), or give it what the reader has.
  useEffect(() => {
    void locKey;
    const saved = readViewState();
    if (saved.text !== undefined || saved.types !== undefined) {
      setDraft(saved.text ?? "");
      setTypes(saved.types ?? []);
    } else saveViewState({ text: latest.current.draft, types: latest.current.types });
  }, [locKey]);
  useEffect(() => saveViewState({ text: draft, types }), [draft, types]);
  return { draft, setDraft, types, setTypes };
}

/** Edit mode is the reader's choice for the session; the host's when it keeps it, else the browser's. */
function useEditLock(host: { editing?: boolean; onEditing?: (on: boolean) => void }) {
  const [own, setOwn] = useState(false);
  const { onEditing } = host;
  const set = useCallback(
    (on: boolean) => {
      setOwn(on);
      onEditing?.(on);
    },
    [onEditing],
  );
  return { on: host.editing ?? own, set };
}

/** Not available: the way on is the module's entry when the module is known, else the start. */
function Unavailable({ module }: { module?: ModuleInfo }) {
  const { go } = useBrowser();
  return (
    <NotAvailable
      onBack={() => go(module ? { module: module.name } : {})}
      backTo={module ? (module.view?.title ?? module.name) : undefined}
    />
  );
}

function Body({ resolved, search, text }: { resolved: Resolved; search: Search; text: string }) {
  switch (resolved.kind) {
    case "none":
      return <Unavailable />;
    case "na":
      return <Unavailable module={resolved.module} />;
    case "chooser":
      return <ModuleChooser modules={resolved.modules} />;
    case "entry":
      return (
        <Entry
          module={resolved.module}
          text={searchServed(resolved.module) ? text : ""}
          types={search.types}
          onTypes={search.setTypes}
          after={resolved.after}
        />
      );
    case "node":
      return (
        <NodePage
          key={`${resolved.entry.type.name}/${resolved.key}`}
          entry={resolved.entry}
          keyText={resolved.key}
          history={resolved.history}
          root={{ label: search.draft.trim() ? `Search: ${search.draft.trim()}` : "Explore" }}
        />
      );
  }
}

function Browser(props: GraphBrowserProps) {
  const { modeSwitch, toolbar, location, onLocation, canEdit, singleKeys = true, palette } = props;
  const toOperate = props.links?.toOperate;
  const metaQ = useBrowserMeta();
  const router = useBrowserLocation({ location, onLocation });
  const locKey = JSON.stringify(router.parsed);
  const search = useSearchState(locKey);
  const text = useSearchPause(search.draft);
  const meta = metaQ.data;
  const resolved = meta ? resolveLocation(meta, router.parsed) : undefined;
  const { setTypes, setDraft } = search;
  const open = useCallback(
    (loc: ExploreLocation, opts?: { replace?: boolean }) => {
      saveViewState({ scroll: window.scrollY });
      router.go(loc, opts);
      if (loc.key !== undefined && !opts?.replace) window.scrollTo(0, 0);
    },
    [router],
  );
  const hasSearch = search.draft.trim() !== "";
  const go = useCallback(
    (loc: ExploreLocation, opts?: { replace?: boolean }) => {
      // A type's list is shown without a search over it; the module's entry, with no narrowing
      // left over when nothing is being searched. A replace moves the page's own position only
      // (defensive: the entry's saved search is restored on arrival, so the guard is not what keeps it).
      if (!opts?.replace && loc.key === undefined && loc.type) setDraft("");
      else if (!opts?.replace && loc.key === undefined && !hasSearch) setTypes([]);
      open(loc, opts);
    },
    [open, hasSearch, setDraft, setTypes],
  );
  const edit = canEdit === true;
  // Edit mode is the reader's choice for the session: it survives moving between nodes, and is
  // never on for a viewer who is not offered the writes.
  const lock = useEditLock(props);
  const setEditing = lock.set;
  const editing = edit && lock.on;
  const ctx = useMemo(
    () => (meta ? { meta, go, canEdit: edit, editing, setEditing, toOperate } : null),
    [meta, go, edit, editing, setEditing, toOperate],
  );
  const current = resolved && moduleOf(resolved);
  usePageTitle(meta, resolved);
  const showSearch = !!current && searchServed(current);
  // A location that names a type opens its list.
  const listed = resolved?.kind === "entry" ? resolved.type : undefined;
  useEffect(() => {
    if (listed) setTypes((on) => (on.length === 1 && on[0] === listed ? on : [listed]));
  }, [listed, setTypes]);
  const onDraft = (v: string) => {
    setDraft(v);
    if (resolved?.kind === "node" && v.trim()) open({ module: resolved.entry.module.name });
  };
  return (
    <div className="gb" data-testid="gb">
      <TopBar
        modules={meta?.modules ?? []}
        module={current}
        status={meta?.status ?? []}
        onModule={(name) => go({ module: name })}
        search={showSearch ? { value: search.draft, onChange: onDraft } : null}
        modeSwitch={modeSwitch}
        toolbar={toolbar}
        slashFocus={singleKeys}
      />
      <main className="gb-main" id="gb-main" aria-busy={metaQ.isPending}>
        {ctx && resolved ? (
          <BrowserProvider value={ctx}>
            <Body resolved={resolved} search={search} text={text} />
          </BrowserProvider>
        ) : (
          <MetaState q={metaQ} />
        )}
      </main>
      {palette?.({ module: current, go })}
    </div>
  );
}

function MetaState({ q }: { q: ReturnType<typeof useBrowserMeta> }) {
  if (q.isPending) return <Skeleton />;
  const s = stateOf(q.error);
  if (s.status === "expired") return <Expired />;
  if (s.status === "na") return <NotAvailable />;
  if (s.status === "down")
    return <BackendDown backend={s.backend} onRetry={() => void q.refetch()} />;
  return <Failed onRetry={() => void q.refetch()} />;
}

export function GraphBrowser(props: GraphBrowserProps) {
  const {
    modeSwitch,
    toolbar,
    location,
    onLocation,
    canEdit,
    editing,
    onEditing,
    singleKeys,
    palette,
    links,
    ...conn
  } = props;
  return (
    <Scope>
      <ArrasProviderOnce {...conn}>
        <Browser
          modeSwitch={modeSwitch}
          toolbar={toolbar}
          canEdit={canEdit}
          location={location}
          onLocation={onLocation}
          editing={editing}
          onEditing={onEditing}
          singleKeys={singleKeys}
          palette={palette}
          links={links}
        />
      </ArrasProviderOnce>
    </Scope>
  );
}
