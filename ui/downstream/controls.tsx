// SPDX-License-Identifier: MIT OR Apache-2.0
// Separate checker fixture keeps standalone widget samples off canonical application screenshots.
import { createRoot } from "react-dom/client";
import { AcceptanceHost } from "@documentdrivendx/arras-ui/testkit/host";
import { NeutralThemeControls, NeutralThemeProvider } from "@arras-fixtures/neutral-theme";
import "@documentdrivendx/arras-ui/styles.css";
import "@arras-fixtures/neutral-theme/theme.css";

createRoot(document.getElementById("root")!).render(
  <NeutralThemeProvider>
    <div className="arras-root">
      <NeutralThemeControls />
      <hr />
      <AcceptanceHost />
    </div>
  </NeutralThemeProvider>,
);
