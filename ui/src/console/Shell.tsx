// SPDX-License-Identifier: MIT OR Apache-2.0

import { type ReactNode, useCallback, useEffect, useState } from "react";
import { useMeta, useVersion } from "../api/queries";
import { type ModuleInfo, SUPPORTED_OPERATE_VERSION } from "../api/types";
import { NotFound, VersionMismatch } from "../areas/ConsoleNotices";
import { SingleKeysCtx } from "../components/SingleKeys";
import { Spinner } from "../components/ui";
import { Button } from "../ds";
import type { LinkTo } from "../kit";
import { useNarrow } from "../lib/useMediaQuery";
import { KEYBOARD_SHORTCUTS } from "../lib/vocabulary";
import type { Route } from "../route";
import { CommandPalette } from "./CommandPalette";
import { ConsoleHeader } from "./ConsoleHeader";
import { ModulePicker, ModuleRail } from "./ModuleRail";
import { ModuleView } from "./ModuleView";
import { NoModules, QueryError } from "./notices";
import { ShortcutsHelp } from "./ShortcutsHelp";
import { useAreaShortcuts } from "./useAreaShortcuts";
import { useAudit } from "./useAudit";
import { useOperateTitle } from "./useDocumentTitle";
import { type Go, type RouteSource, useRoute } from "./useRoute";
import { useViewState } from "./viewState";

/**
 * What a hosting shell gives the console in place of its own single-key switch, shortcut help and palette:
 * the shell owns them for both modes, so a switch of mode keeps them. The console reads the switch and
 * opens the shell's help from its header.
 */
export interface Hosted {
  singleKeys: boolean;
  onSingleKeys: (on: boolean) => void;
  openHelp: () => void;
  /** The shell's command palette, drawn where the console's own would be: the module, whether Changes is shown, and the route change. */
  palette?: (at: { module: ModuleInfo | undefined; auditShown: boolean; go: Go }) => ReactNode;
}

export interface ShellProps extends Pick<RouteSource, "route" | "onRoute"> {
  /** Set by a hosting shell: it owns the single-key switch, the shortcut help and the palette. */
  hosted?: Hosted;
  /** Keep the route in `location.hash` (standalone host); embedded consoles keep it in memory. */
  hashRouting?: boolean;
  /** With `hashRouting`: a first path segment owned by a hosting shell (`operate`), kept on every route. */
  hashPrefix?: string;
  /** Extra header content (the dev host's sandbox toolbar). */
  toolbar?: ReactNode;
  explorerBase?: string;
  /** The link into Explore, handed in by a hosting shell for an operator (Rule 7); none draws no cross-mode link. */
  links?: { toExplore: LinkTo };
}

/**
 * The single-key switch and the help: held in memory for the page's lifetime, or the hosting shell's.
 */
function useConsoleKeys(hosted: Hosted | undefined) {
  const [singleKeys, setSingleKeys] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);
  const openOwnHelp = useCallback(() => setHelpOpen(true), []);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  return {
    singleKeys: hosted ? hosted.singleKeys : singleKeys,
    setSingleKeys,
    openHelp: hosted ? hosted.openHelp : openOwnHelp,
    helpOpen,
    closeHelp,
  };
}

/** The palette: the hosting shell's, drawn here, or the console's own. */
function ConsolePalette({
  hosted,
  at,
}: {
  hosted: Hosted | undefined;
  at: { module: ModuleInfo | undefined; auditShown: boolean; go: Go };
}) {
  if (hosted) return hosted.palette?.(at) ?? null;
  return <CommandPalette {...at} />;
}

/** What stands in for the module view while the version, the modules or the route are not good. */
function shellBody(o: {
  version: ReturnType<typeof useVersion>;
  supported: boolean;
  meta: ReturnType<typeof useMeta>;
  modules: ModuleInfo[];
  current: ModuleInfo | undefined;
  route: Route;
}): ReactNode {
  const { version, meta } = o;
  if (version.isPending) return <Spinner label="Checking version" />;
  if (version.error)
    return <QueryError error={version.error} retry={() => void version.refetch()} />;
  if (!o.supported) return <VersionMismatch reported={version.data.contracts.operate} />;
  if (meta.isPending) return <Spinner label="Loading modules" />;
  if (meta.error) return <QueryError error={meta.error} retry={() => void meta.refetch()} />;
  if (o.modules.length === 0) return <NoModules module={o.route.module} />;
  // The same answer for an unknown module and one the viewer may not read (US-060 AC4).
  if (o.route.module && !o.current) return <NotFound />;
  return null;
}

/** The console: header, module rail and the module's view; the route and the view state live here. */
export function Shell({
  hashRouting = false,
  hashPrefix,
  toolbar,
  explorerBase,
  route: hostRoute,
  onRoute,
  hosted,
  links,
}: ShellProps) {
  const version = useVersion();
  const supported = version.data?.contracts.operate === SUPPORTED_OPERATE_VERSION;
  const meta = useMeta(supported);
  const [route, go] = useRoute({ hashRouting, prefix: hashPrefix, route: hostRoute, onRoute });
  const s = useViewState();
  const narrow = useNarrow();
  const modules = meta.data?.modules ?? [];
  const current = route.module ? modules.find((m) => m.name === route.module) : undefined;
  const { auditShown, area } = useAudit(current, route.area);
  const { setGraphType } = s;
  // "Show <Type> in Graph" holds for that visit only.
  useEffect(() => {
    if (area !== "graph") setGraphType(null);
  }, [area, setGraphType]);

  const keys = useConsoleKeys(hosted);
  const { singleKeys, openHelp } = keys;
  useAreaShortcuts(current, auditShown, go, s.lastAction, {
    enabled: singleKeys,
    onHelp: hosted ? undefined : openHelp,
  });
  useOperateTitle(route, area, current);

  // Open the first module when none is chosen.
  useEffect(() => {
    if (!route.module && modules[0])
      go({ module: modules[0].name, area: "model" }, { replace: true });
  }, [route.module, modules, go]);

  const body =
    shellBody({ version, supported, meta, modules, current, route }) ??
    (current && (
      <ModuleView
        module={current}
        route={route}
        go={go}
        area={area}
        auditShown={auditShown}
        s={s}
        explorerBase={explorerBase}
        toExplore={links?.toExplore}
        fragment={hashRouting && hostRoute === undefined ? { prefix: hashPrefix } : undefined}
      />
    ));

  const pickModule = (mod: ModuleInfo) => {
    // The UMF source stays open across a module change made from the rail.
    const carryUmf = area === "model" && route.area === "model" && route.view === "umf";
    go({
      module: mod.name,
      area: area === "changes" ? "model" : area,
      ...(carryUmf ? { view: "umf" as const } : {}),
    });
  };
  const listed = supported && modules.length > 0;
  return (
    <SingleKeysCtx.Provider value={singleKeys}>
      <div className="flex h-full min-w-0 flex-col overflow-hidden bg-bg text-fg">
        <ConsolePalette
          hosted={hosted}
          at={{ module: supported ? current : undefined, auditShown, go }}
        />
        <ConsoleHeader
          operateVersion={version.data?.contracts.operate}
          toolbar={
            <>
              <Button variant="text" size="sm" onClick={openHelp}>
                {KEYBOARD_SHORTCUTS}
                {singleKeys ? " (?)" : ""}
              </Button>
              {toolbar}
            </>
          }
          modulePicker={
            listed && narrow ? (
              <ModulePicker modules={modules} current={current} onPick={pickModule} />
            ) : undefined
          }
        />
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          {listed && !narrow && (
            <ModuleRail modules={modules} current={current} onPick={pickModule} />
          )}
          <main className="flex min-h-0 min-w-0 flex-1 flex-col">{body}</main>
        </div>
        {!hosted && keys.helpOpen && (
          <ShortcutsHelp
            operate
            singleKeys={singleKeys}
            onSingleKeys={keys.setSingleKeys}
            onClose={keys.closeHelp}
          />
        )}
      </div>
    </SingleKeysCtx.Provider>
  );
}
