// SPDX-License-Identifier: MIT OR Apache-2.0
import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ArrasConsole, type ArrasConsoleProps } from "../ArrasConsole";
import { ArrasProvider } from "../api/context";
import { GraphBrowser, type GraphBrowserProps } from "../browser/GraphBrowser";

export const qc = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } } });

/** A part inside a provider, as a host would mount it. */
export function renderPart(
  ui: ReactElement,
  props: { getHeaders?: () => Record<string, string>; onUnauthorized?: () => void } = {},
) {
  return render(
    <ArrasProvider queryClient={qc()} {...props}>
      {ui}
    </ArrasProvider>,
  );
}

export function renderConsole(props: ArrasConsoleProps = {}) {
  return render(<ArrasConsole {...props} />);
}

/** The Graph Browser as a host mounts it, with a fresh query client. */
export function renderBrowser(props: GraphBrowserProps = {}) {
  return render(<GraphBrowser queryClient={qc()} {...props} />);
}
