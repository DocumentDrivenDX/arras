// SPDX-License-Identifier: MIT OR Apache-2.0
// The entry a host serves (`arras.ui.create_app`): the shell with no sandbox toolbar. Every URL is
// derived from where this page was loaded, so it works under any path prefix the host mounts it at:
// the API surfaces are `api/console`, `api/operate` and `api/schema` beside the page, and UMF's schema
// browser is `umf-explorer/`. The host authenticates the viewer (the page sends the browser's own
// cookies, same origin) and the console stores no credential.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { readBrandMeta } from "./lib/brand";
import { ArrasApp } from "./shell";
import "./styles.css";
import "./page.css";

/** The page's own directory as a path with a trailing slash: `/ontology/` for `/ontology/#/explore`. */
export const pageRoot = (href: string) => new URL(".", href).pathname;

const root = pageRoot(window.location.href);
const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("embed.html has no #root element");
createRoot(rootElement).render(
  <StrictMode>
    <ArrasApp
      operateBase={`${root}api/operate`}
      consoleBase={`${root}api/console`}
      schemaBase={`${root}api/schema`}
      explorerBase={`${root}umf-explorer`}
      brand={readBrandMeta(document)}
    />
  </StrictMode>,
);
