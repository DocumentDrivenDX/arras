// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import { ArrasProviderOnce, type ProviderProps } from "./api/context";
import { describeError } from "./api/errors";
import {
  type QuerySession,
  QuerySessionProvider,
  useQuerySessionState,
} from "./areas/queryHistory";
import { Scope } from "./components/Scope";
import { type Hosted, Shell } from "./console/Shell";
import type { LinkTo } from "./kit";
import { type Area, formatHash, parseHash, type Route } from "./route";

export type { Area, Route };
export { formatHash, parseHash };

export interface ArrasConsoleProps {
  /** Where the operator surface (CONTRACT-009) is mounted. */
  operateBase?: string;
  /** Where the console GraphQL surface (CONTRACT-006) is mounted. */
  consoleBase?: string;
  /** A host's own auth headers, read on every request. The console stores no credential. */
  getHeaders?: () => Record<string, string>;
  /** Called on a 401 so the host can sign the viewer in again. */
  onUnauthorized?: () => void;
  /** Keep the route in `location.hash` (standalone host); embedded consoles keep it in memory. */
  hashRouting?: boolean;
  /** With `hashRouting`: a first path segment owned by a hosting shell (`operate`), kept on every route. */
  hashPrefix?: string;
  /**
   * A host that owns the location passes the route it shows and takes every change through
   * `onRoute` (`replace` says the entry is rewritten, not added). The console then neither reads nor
   * writes the URL; without `route` it keeps the route itself (`hashRouting`, or in memory).
   */
  route?: Route;
  onRoute?: (route: Route, opts: { replace: boolean }) => void;
  /** Extra header content (the dev host's sandbox toolbar). */
  toolbar?: ReactNode;
  /**
   * Where the host serves the `assets/` directory of UMF's schema browser package (default
   * `/umf-explorer`). The console reads the catalog itself, from the operator surface, with
   * `getHeaders`; the host's page policy must allow the browser (ui/README.md, "UMF source").
   */
  explorerBase?: string;
  /**
   * Where the schema administration surface (CONTRACT-011) is mounted (default `/api/schema`). The Schema
   * area offers import only when `GET {schemaBase}/version` answers; a host that does not mount it has none.
   */
  schemaBase?: string;
  /**
   * Who is being viewed, as a string that changes whenever the person does. The Query area's history and draft
   * (held in memory above the tabs) are emptied when it changes, so one person's queries are never shown to
   * the next. Omit it and the history is kept for the life of the console: a host that switches person without
   * mounting the console afresh must pass it.
   */
  identity?: string;
  /** What the interface is called (name, wordmark, page title); the default is Arras. */
  brand?: ProviderProps["brand"];
  /** A query client the host shares with the Graph Browser, so the two read the registry once. */
  queryClient?: ProviderProps["queryClient"];
  /** A Query history and draft the host keeps above the console (a shell, across a mode switch); the console holds its own otherwise. */
  querySession?: QuerySession;
  /**
   * Set by a hosting shell, which owns the single-key switch, the shortcut help and the command palette
   * for both modes: the console then mounts neither the help nor the palette. Alone, it keeps its own.
   */
  hosted?: Hosted;
  /**
   * Set by a hosting shell for an operator: the link into Explore (Rule 7). The console draws **View
   * in Explore** where it is given and no cross-mode link otherwise.
   */
  links?: { toExplore: LinkTo };
}

/**
 * The query history and draft, in memory: the host's when it passes one, else the console's own, emptied
 * whenever `identity` changes (the key).
 */
function QuerySessionRoot({ session, children }: { session?: QuerySession; children: ReactNode }) {
  const own = useQuerySessionState();
  return <QuerySessionProvider session={session ?? own}>{children}</QuerySessionProvider>;
}

/** The whole Operator Console: module rail, Schema, Graph, Data, Actions, Query and (when served) Audit areas. */
export function ArrasConsole(props: ArrasConsoleProps) {
  const {
    hashRouting,
    hashPrefix,
    toolbar,
    explorerBase,
    identity,
    route,
    onRoute,
    querySession,
    hosted,
    links,
    ...conn
  } = props;
  return (
    <Scope>
      <ArrasProviderOnce {...conn}>
        <QuerySessionRoot key={identity ?? ""} session={querySession}>
          <Shell
            hashRouting={hashRouting}
            route={route}
            onRoute={onRoute}
            hashPrefix={hashPrefix}
            toolbar={toolbar}
            explorerBase={explorerBase}
            hosted={hosted}
            links={links}
          />
        </QuerySessionRoot>
      </ArrasProviderOnce>
    </Scope>
  );
}

export { describeError };
