// SPDX-License-Identifier: MIT OR Apache-2.0
// The shell (ADR-025): one interface, two modes. Explore (the `user` mode id) is the Graph Browser; Operate
// (the `admin` mode id) is the Operator Console, offered only when the host says the viewer is an operator
// (`GET /viewer`). With Operate absent the page carries no control, link or hint to it, and the operate surface is called
// for nothing but the viewer's modes.
import type { QueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrasConsole, type ArrasConsoleProps } from "../ArrasConsole";
import { ArrasProvider, createQueryClient } from "../api/context";
import { type QuerySession, useQuerySessionState } from "../areas/queryHistory";
import { GraphBrowser, type GraphBrowserProps } from "../browser/GraphBrowser";
import { type ExploreLocation, parseExplore } from "../browser/location";
import { Skeleton } from "../browser/states";
import { Scope } from "../components/Scope";
import { ShortcutsHelp } from "../console/ShortcutsHelp";
import type { Route } from "../route";
import { crossLinks, targetOfLocation } from "./links";
import { ModeSwitch } from "./ModeSwitch";
import {
  canonicalMode,
  effectiveMode,
  exploreFor,
  exploreForRoute,
  hashKind,
  type Mode,
  operateFor,
  operateHash,
  routeForExplore,
} from "./modeRoute";
import { ExplorePalette, OperatePalette } from "./ShellPalette";
import { useShellState } from "./ShellState";
import { useShellShortcuts } from "./useShellShortcuts";
import { useViewer } from "./useViewer";

export interface ArrasAppProps
  extends Omit<
      ArrasConsoleProps,
      | "hashRouting"
      | "hashPrefix"
      | "toolbar"
      | "route"
      | "onRoute"
      | "querySession"
      | "hosted"
      | "links"
    >,
    Pick<GraphBrowserProps, "location" | "onLocation" | "queryClient"> {
  /** The mode to open in when the fragment names none (an operator only); default user. */
  defaultMode?: Mode;
  /** Extra header content (the dev host's person picker), shown in both modes. */
  toolbar?: ReactNode;
}

/** The fragment as it is now, with an alias mode id (`browse`, `admin`) rewritten in place (replace, not push). */
function currentHash(rewrite: boolean): string {
  const canonical = rewrite ? canonicalMode(window.location.hash) : undefined;
  if (canonical) window.history.replaceState(window.history.state, "", canonical);
  return window.location.hash;
}

/** `controlled`: the host owns the location, so the fragment is read but never rewritten. */
const useHash = (controlled: boolean) => {
  const [hash, setHash] = useState(() => currentHash(!controlled));
  useEffect(() => {
    const on = () => setHash(currentHash(!controlled));
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => {
      window.removeEventListener("hashchange", on);
      window.removeEventListener("popstate", on);
    };
  }, [controlled]);
  return hash;
};

const MODE_KEY = "gbMode";

function remembered(): Mode | undefined {
  const s: unknown = window.history.state;
  const v = s && typeof s === "object" ? (s as Record<string, unknown>)[MODE_KEY] : undefined;
  return v === "admin" || v === "user" ? v : undefined;
}

function remember(mode: Mode) {
  const s: unknown = window.history.state;
  const base = s && typeof s === "object" ? (s as Record<string, unknown>) : {};
  window.history.replaceState({ ...base, [MODE_KEY]: mode }, "");
}

interface LinkDeps {
  offered: boolean;
  controlled: boolean;
  location: ExploreLocation | undefined;
  onLocation: ArrasAppProps["onLocation"];
  choose: (next: Mode) => void;
  setOperateRoute: (r: Route) => void;
  setLocal: (m: Mode) => void;
}

/**
 * The cross-mode link primitive (Rule 7), for an operator only: where the host owns the location a
 * link switches mode and sets the other mode's route; otherwise it is the other mode's fragment.
 * `operateHere` is the palette's Open in Operate, which carries the page that is open.
 */
function useCrossLinks(d: LinkDeps) {
  const { offered, controlled, location, onLocation, choose, setOperateRoute, setLocal } = d;
  const openOperate = useCallback(
    (route: Route) => {
      setOperateRoute(route);
      setLocal("admin");
    },
    [setOperateRoute, setLocal],
  );
  const openExplore = useCallback(
    (loc: ExploreLocation) => {
      onLocation?.(loc);
      setLocal("user");
    },
    [onLocation, setLocal],
  );
  const links = useMemo(
    () => (offered ? crossLinks({ hash: !controlled, openOperate, openExplore }) : undefined),
    [offered, controlled, openOperate, openExplore],
  );
  const operateHere = useCallback(() => {
    const parsed = parseExplore(window.location.hash);
    const hashed = parsed.kind === "explore" ? parsed.loc : {};
    const at = targetOfLocation(controlled ? (location ?? {}) : hashed);
    if (at && links) links.toOperate(at.target, at.area).go();
    else choose("admin");
  }, [controlled, location, links, choose]);
  return { links, operateHere };
}

/**
 * Mode and its switch: the fragment's prefix is the mode, and what is open (module, type, entity)
 * carries across the switch both ways. Where the host owns the location the shell keeps the
 * console's route itself and hands the host the Explore location through `onLocation`.
 */
function useMode(props: ArrasAppProps) {
  const viewer = useViewer(props);
  const controlled = props.location !== undefined; // the host owns the location: never touch the URL
  const hash = useHash(controlled);
  const [local, setLocal] = useState<Mode | undefined>(() => remembered() ?? props.defaultMode);
  const offered = viewer.modes.includes("admin");
  const fromHash = effectiveMode({
    hash,
    modes: viewer.modes,
    defaultMode: props.defaultMode,
    remembered: remembered(),
  });
  const mode: Mode = controlled ? (offered ? (local ?? "user") : "user") : fromHash;
  const [operateRoute, setOperateRoute] = useState<Route>({ area: "model" });
  // The console's unprefixed fragment form is rewritten to an operate route, so the prefix always says the mode.
  // The address is read live, not from `hash`: the console may already have replaced it in this very commit
  // (its default type), and a rewrite of the older fragment would put the type-less address back.
  useEffect(() => {
    const here = window.location.hash;
    if (!controlled && offered && hashKind(hash) === "legacy" && hashKind(here) === "legacy")
      window.history.replaceState(window.history.state, "", operateHash(here));
  }, [controlled, offered, hash]);
  useEffect(() => {
    if (offered && !controlled) remember(mode); // a host that owns the location owns history.state
  }, [offered, controlled, mode]);
  const { location, onLocation } = props;
  const choose = useCallback(
    (next: Mode) => {
      if (controlled) {
        if (next === mode) return;
        if (next === "admin") setOperateRoute(routeForExplore(location ?? {}));
        else onLocation?.(exploreForRoute(operateRoute));
        setLocal(next);
        return;
      }
      // The console moves the fragment with pushState, which the page does not hear: read it live.
      const here = window.location.hash;
      window.location.hash = next === "admin" ? operateFor(here) : exploreFor(here);
    },
    [controlled, mode, location, onLocation, operateRoute],
  );
  const { links, operateHere } = useCrossLinks({
    offered,
    controlled,
    location,
    onLocation,
    choose,
    setOperateRoute,
    setLocal,
  });
  // Until the host has said whether the viewer may use operate, a route that asks for it is not
  // answered with Explore: no browser read is made from a mode the viewer may be about to leave.
  const kind = hashKind(hash);
  const asksOperate =
    kind === "operate" ||
    kind === "legacy" ||
    (kind === "none" && (remembered() ?? props.defaultMode) === "admin");
  const pending = !viewer.settled && !controlled && asksOperate;
  return {
    mode,
    offered,
    choose,
    controlled,
    pending,
    operateRoute,
    setOperateRoute,
    links,
    operateHere,
  };
}

/**
 * The Query history and draft, kept at the shell so a mode switch keeps them; emptied when the person
 * being viewed changes (`identity`), so one person's queries are never shown to the next.
 */
function useShellSession(identity: string | undefined): QuerySession {
  const session = useQuerySessionState();
  const seen = useRef(identity);
  const { clear, setDraft, starterSeen } = session;
  useEffect(() => {
    if (seen.current === identity) return;
    seen.current = identity;
    clear();
    setDraft({ sql: "", consistency: "latest" });
    starterSeen.current = null;
  }, [identity, clear, setDraft, starterSeen]);
  return session;
}

function ShellBody(props: ArrasAppProps & { queryClient: QueryClient }) {
  const { defaultMode: _mode, toolbar, explorerBase, ...conn } = props;
  const {
    mode,
    offered,
    choose,
    controlled,
    pending,
    operateRoute,
    setOperateRoute,
    links,
    operateHere,
  } = useMode(props);
  const state = useShellState();
  const session = useShellSession(props.identity);
  useShellShortcuts(mode, state);
  const { closePalette } = state;
  // A palette left open across a mode switch (Back, a pasted address) belongs to the mode it opened in.
  useEffect(() => {
    void mode;
    closePalette();
  }, [mode, closePalette]);
  if (pending)
    return (
      <div className="gb">
        <main className="gb-main">
          <Skeleton />
        </main>
      </div>
    );
  const modeSwitch = offered ? <ModeSwitch mode={mode} onChange={choose} /> : undefined;
  const palette = { open: state.paletteOpen, onClose: closePalette };
  const body =
    mode === "admin" ? (
      <ArrasConsole
        {...conn}
        explorerBase={explorerBase}
        querySession={session}
        hashRouting={!controlled}
        hashPrefix="operate"
        route={controlled ? operateRoute : undefined}
        onRoute={controlled ? (r) => setOperateRoute(r) : undefined}
        links={links && { toExplore: links.toExplore }}
        hosted={{
          singleKeys: state.singleKeys,
          onSingleKeys: state.setSingleKeys,
          openHelp: state.openHelp,
          palette: (at) => <OperatePalette {...palette} {...at} />,
        }}
        toolbar={
          <>
            {modeSwitch}
            {toolbar}
          </>
        }
      />
    ) : (
      <GraphBrowser
        {...conn}
        canEdit={offered}
        editing={state.editing}
        onEditing={state.setEditing}
        singleKeys={state.singleKeys}
        palette={(at) => (
          <ExplorePalette {...palette} {...at} toOperate={offered ? operateHere : undefined} />
        )}
        modeSwitch={modeSwitch}
        toolbar={toolbar}
        links={links && { toOperate: links.toOperate }}
      />
    );
  return (
    <>
      {body}
      {state.helpOpen && (
        <ShortcutsHelp
          operate={offered}
          singleKeys={state.singleKeys}
          onSingleKeys={state.setSingleKeys}
          onClose={state.closeHelp}
        />
      )}
    </>
  );
}

/**
 * The shell: one `QueryClient` (the host's, or one made here), one provider, the Query session, the
 * edit-mode lock, the single-key switch, the shortcut help and the palette, shared by both modes.
 */
export function ArrasApp(props: ArrasAppProps) {
  const { queryClient: given, brand } = props;
  const qc = useMemo(() => given ?? createQueryClient(), [given]);
  const { operateBase, consoleBase, schemaBase, getHeaders, onUnauthorized } = props;
  return (
    <Scope>
      <ArrasProvider
        operateBase={operateBase}
        consoleBase={consoleBase}
        schemaBase={schemaBase}
        getHeaders={getHeaders}
        onUnauthorized={onUnauthorized}
        brand={brand}
        queryClient={qc}
      >
        <ShellBody {...props} queryClient={qc} />
      </ArrasProvider>
    </Scope>
  );
}
