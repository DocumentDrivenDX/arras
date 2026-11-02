// SPDX-License-Identifier: MIT OR Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Scope } from "../components/Scope";
import { type Brand, BrandProvider } from "../lib/brand";
import { createFormFocus, FormFocusContext } from "../lib/formFocus";
import { PageEffects } from "../lib/pageEffects";
import { CacheLease } from "./cacheScope";
import {
  type ArrasClient,
  type ClientConfig,
  createClient,
  createSchemaApi,
  DEFAULT_SCHEMA_BASE,
  type SchemaApi,
} from "./client";
import { ApiError } from "./errors";

const Ctx = createContext<ArrasClient | null>(null);

export function useClient(): ArrasClient {
  const c = useContext(Ctx);
  if (!c)
    throw new Error("Arras components must be rendered inside <ArrasProvider> or <ArrasConsole>");
  return c;
}

const SchemaCtx = createContext<SchemaApi | null>(null);

/** The schema surface's client (CONTRACT-011); the console offers import only when it answers. */
export function useSchemaApi(): SchemaApi {
  const c = useContext(SchemaCtx);
  if (!c)
    throw new Error("Arras components must be rendered inside <ArrasProvider> or <ArrasConsole>");
  return c;
}

/** Actions the provider refused this viewer: their controls stay disabled, with the reason (US-064). */
interface Refusals {
  refusals: Record<string, ApiError>;
  refuse: (key: string, e: ApiError) => void;
}
const RefusalCtx = createContext<Refusals>({ refusals: {}, refuse: () => {} });
export const useRefusals = () => useContext(RefusalCtx);

/** The host's sign-in, when it supplied `onUnauthorized`: what a "Sign in again" control calls. Undefined when it gave none. */
const SignInCtx = createContext<(() => void) | undefined>(undefined);
export const useSignIn = () => useContext(SignInCtx);

/** The one query client of an interface: a failed read is not repeated, a window refocus does not re-read. */
export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: (n, e) => !(e instanceof ApiError) && n < 1,
        refetchOnWindowFocus: false,
        staleTime: 5_000,
      },
    },
  });

export interface ProviderProps {
  /** Change when the person, tenant or authorization session changes. */
  identity?: string;
  /** Own the document title, window scrolling and global shortcuts. Default true. */
  pageEffects?: boolean;
  operateBase?: string;
  consoleBase?: string;
  /** Where the schema administration surface (CONTRACT-011) is mounted, if the host mounts it. */
  schemaBase?: string;
  getHeaders?: () => Record<string, string>;
  onUnauthorized?: () => void;
  /** What the interface is called (name, wordmark, page title, tagline); the default is Arras. */
  brand?: Brand;
  /** An exclusive Arras cache, cancelled and cleared on scope release; private by default. */
  queryClient?: QueryClient;
  children: ReactNode;
}

export function ArrasProvider(props: ProviderProps) {
  const scope = JSON.stringify([
    props.identity ?? "",
    props.operateBase ?? "/api/operate",
    props.consoleBase ?? "/api/console",
    props.schemaBase ?? DEFAULT_SCHEMA_BASE,
  ]);
  return props.queryClient ? (
    <CacheLease key={scope} scope={scope} client={props.queryClient}>
      <ProviderScope {...props} />
    </CacheLease>
  ) : (
    <ProviderScope key={scope} {...props} />
  );
}

const ScopeConfig = createContext<ProviderProps | null>(null);

function ProviderScope(props: ProviderProps) {
  const formFocus = useRef(createFormFocus()).current;
  const live = useRef(true);
  useLayoutEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const {
    operateBase = "/api/operate",
    consoleBase = "/api/console",
    schemaBase = DEFAULT_SCHEMA_BASE,
    children,
  } = props;
  // Hosts pass new function identities every render; keep the client stable and call the latest.
  const getHeaders = useRef(props.getHeaders);
  const onUnauthorized = useRef(props.onUnauthorized);
  getHeaders.current = props.getHeaders;
  onUnauthorized.current = props.onUnauthorized;
  const revisionChanged = useRef<() => void>(() => {});
  const client = useMemo(() => {
    const cfg: ClientConfig = {
      operateBase,
      consoleBase,
      getHeaders: () => {
        if (!live.current) throw new Error("Arras session has been released");
        return getHeaders.current?.() ?? {};
      },
      onUnauthorized: () => {
        if (live.current) onUnauthorized.current?.();
      },
      onRevisionChanged: () => {
        if (live.current) revisionChanged.current();
      },
    };
    return createClient(cfg);
  }, [operateBase, consoleBase]);
  const schema = useMemo(
    () =>
      createSchemaApi({
        operateBase,
        consoleBase,
        schemaBase,
        getHeaders: () => {
          if (!live.current) throw new Error("Arras session has been released");
          return getHeaders.current?.() ?? {};
        },
        onUnauthorized: () => {
          if (live.current) onUnauthorized.current?.();
        },
      }),
    [operateBase, consoleBase, schemaBase],
  );
  const qc = useMemo(() => props.queryClient ?? createQueryClient(), [props.queryClient]);
  useEffect(() => {
    if (props.queryClient) return;
    return () => {
      void qc.cancelQueries();
      qc.clear();
    };
  }, [qc, props.queryClient]);
  // A module read that answers REVISION_CHANGED means the registry moved: the meta read (shared by
  // both modes) is made again, and what depends on its revision is read under the new one.
  revisionChanged.current = () =>
    void qc.invalidateQueries({ queryKey: ["meta"] }, { cancelRefetch: false });
  const [refusals, setRefusals] = useState<Record<string, ApiError>>({});
  const refuse = useCallback(
    (key: string, e: ApiError) => setRefusals((r) => ({ ...r, [key]: e })),
    [],
  );
  const hasSignIn = props.onUnauthorized !== undefined;
  const signIn = useMemo(
    () =>
      hasSignIn
        ? () => {
            if (live.current) onUnauthorized.current?.();
          }
        : undefined,
    [hasSignIn],
  );
  const refusalValue = useMemo(() => ({ refusals, refuse }), [refusals, refuse]);
  return (
    <ScopeConfig.Provider value={props}>
      <Scope>
        <PageEffects.Provider value={props.pageEffects ?? true}>
          <Ctx.Provider value={client}>
            <SchemaCtx.Provider value={schema}>
              <RefusalCtx.Provider value={refusalValue}>
                <SignInCtx.Provider value={signIn}>
                  <QueryClientProvider client={qc}>
                    <FormFocusContext.Provider value={formFocus}>
                      <BrandProvider brand={props.brand}>{children}</BrandProvider>
                    </FormFocusContext.Provider>
                  </QueryClientProvider>
                </SignInCtx.Provider>
              </RefusalCtx.Provider>
            </SchemaCtx.Provider>
          </Ctx.Provider>
        </PageEffects.Provider>
      </Scope>
    </ScopeConfig.Provider>
  );
}

/**
 * A part mounted by a hosting shell shares the shell's provider (one client, one query client, one set of
 * refusals); mounted alone it is its own host and gets one.
 */
export function ArrasProviderOnce(props: ProviderProps) {
  const parent = useContext(ScopeConfig);
  if (!parent) return <ArrasProvider {...props} />;
  const defaults = {
    operateBase: "/api/operate",
    consoleBase: "/api/console",
    schemaBase: DEFAULT_SCHEMA_BASE,
    identity: "",
  };
  for (const key of ["operateBase", "consoleBase", "schemaBase", "identity"] as const) {
    if (props[key] !== undefined && props[key] !== (parent[key] ?? defaults[key]))
      throw new Error(
        `Conflicting Arras ${key}; use an explicit ArrasProvider for an independent scope`,
      );
  }
  if (props.pageEffects !== undefined && props.pageEffects !== (parent.pageEffects ?? true))
    throw new Error("Conflicting Arras pageEffects; configure the enclosing provider");
  if (props.getHeaders !== undefined && props.getHeaders !== parent.getHeaders)
    throw new Error(
      "Conflicting Arras getHeaders; configure the enclosing provider or create an independent scope",
    );
  if (props.queryClient && props.queryClient !== parent.queryClient)
    throw new Error(
      "Conflicting Arras queryClient; use an explicit ArrasProvider for an independent scope",
    );
  return props.children;
}
