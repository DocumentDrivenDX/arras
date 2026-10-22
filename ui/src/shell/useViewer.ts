// SPDX-License-Identifier: MIT OR Apache-2.0
// Asks `GET /viewer` once (CONTRACT-010 E). A failure of any kind means Explore only: the shell
// never assumes the viewer is an operator.
import { useEffect, useRef, useState } from "react";
import { createClient } from "../api/client";
import type { Viewer } from "../api/types";
import type { Mode } from "./modeRoute";

export interface Conn {
  operateBase?: string;
  consoleBase?: string;
  getHeaders?: () => Record<string, string>;
  onUnauthorized?: () => void;
}

export interface ViewerState {
  /** False until the answer (or its failure) has arrived. */
  settled: boolean;
  modes: Mode[];
}

const USER_ONLY: Mode[] = ["user"];

export function useViewer(conn: Conn): ViewerState {
  const [state, setState] = useState<ViewerState>({ settled: false, modes: USER_ONLY });
  const latest = useRef(conn);
  latest.current = conn;
  useEffect(() => {
    let live = true;
    const c = latest.current;
    const client = createClient({
      operateBase: c.operateBase ?? "/api/operate",
      consoleBase: c.consoleBase ?? "/api/console",
      getHeaders: () => latest.current.getHeaders?.() ?? {},
      onUnauthorized: () => latest.current.onUnauthorized?.(),
    });
    client.viewer().then(
      (v: Viewer) => {
        if (live)
          setState({
            settled: true,
            modes: v.modes.includes("admin") ? ["user", "admin"] : USER_ONLY,
          });
      },
      () => {
        if (live) setState({ settled: true, modes: USER_ONLY });
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return state;
}
