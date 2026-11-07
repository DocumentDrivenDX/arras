// SPDX-License-Identifier: MIT OR Apache-2.0
// The static read-only host's entry (ADR-031, CONTRACT-012): a page that loads a UMF module document and an
// `arras.graph` file from its own directory (named in `arras-static.json`) and shows the Graph Browser over
// them. Nothing is sent anywhere; there is no credential, no person and no write.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { readBrandMeta } from "../lib/brand";
import { ArrasApp } from "../shell";
import "../styles.css";
import "../page.css";
import { createStaticClient, loadStore, staticSchemaApi } from "./backend";
import { readConfig } from "./config";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("static.html has no #root element");
const root = createRoot(rootElement);

function Failure({ message }: { message: string }) {
  return (
    <main role="alert" className="gb-main">
      <h1>This graph could not be loaded</h1>
      <p>{message}</p>
    </main>
  );
}

async function fetchText(url: string): Promise<string> {
  const res = await fetch(url, { credentials: "omit" });
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
  return res.text();
}

async function boot(): Promise<void> {
  root.render(<p role="status">Loading…</p>);
  try {
    const config = readConfig(await fetchText("arras-static.json"));
    const [moduleText, graphText] = await Promise.all([
      fetchText(config.module),
      fetchText(config.graph),
    ]);
    const store = await loadStore(moduleText, graphText);
    const brand = readBrandMeta(document);
    root.render(
      <StrictMode>
        <ArrasApp
          client={createStaticClient(store, moduleText)}
          schemaApi={staticSchemaApi()}
          brand={config.brand ?? brand}
        />
      </StrictMode>,
    );
  } catch (e) {
    root.render(<Failure message={e instanceof Error ? e.message : String(e)} />);
  }
}

void boot();
