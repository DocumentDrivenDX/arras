// SPDX-License-Identifier: MIT OR Apache-2.0
// The standalone entry for the development host: mounts the console under the sandbox toolbar
// (src/dev/). The toolbar sends the chosen sandbox person, or a made-up name and role, as headers only the
// dev host reads. Nothing is stored in the browser, and no person name goes into a URL.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { DevHost } from "./dev/DevHost";
import { readBrandMeta } from "./lib/brand";
import "./styles.css";
import "./page.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("index.html has no #root element");
const brand = readBrandMeta(document);
createRoot(rootElement).render(
  <StrictMode>
    <DevHost brand={brand} />
  </StrictMode>,
);
