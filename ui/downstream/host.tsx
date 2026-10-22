// SPDX-License-Identifier: MIT OR Apache-2.0
// Neutral host imports only packed public packages from its temporary node_modules.
import { createRoot } from "react-dom/client";
import { AcceptanceHost } from "@documentdrivendx/arras-ui/testkit/host";
import { NeutralThemeProvider } from "@arras-fixtures/neutral-theme";
import "@documentdrivendx/arras-ui/styles.css";
import "@arras-fixtures/neutral-theme/theme.css";

createRoot(document.getElementById("root")!).render(
  <NeutralThemeProvider>
    <AcceptanceHost />
  </NeutralThemeProvider>,
);
