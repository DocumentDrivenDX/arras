// SPDX-License-Identifier: MIT OR Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ArrasConsole } from "../ArrasConsole";
import { GraphBrowser } from "../browser/GraphBrowser";
import { titleFor } from "../console/useDocumentTitle";
import { type Brand, DEFAULT_BRAND, readBrandMeta, useBrand } from "../lib/brand";
import { ArrasApp } from "../shell";
import { type BrowserFake, stageBrowser } from "./browserFake";
import { qc } from "./render";

// SD-013, Branding (FR-73): the name, wordmark and document title come from one configuration.
let fake: BrowserFake;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.location.hash = "";
  document.title = "page";
  fake = stageBrowser();
  fake.mods = fake.mods.slice(0, 1);
});
afterEach(() => {
  window.location.hash = "";
});

const ATLAS: Brand = { name: "Atlas" };

describe("the brand in the top bar and the document title", () => {
  it("defaults to Arras in the browser", async () => {
    render(<GraphBrowser queryClient={qc()} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.getByRole("banner")).toHaveTextContent("Arras");
    await waitFor(() => expect(document.title.endsWith(" · Arras")).toBe(true));
  });

  it("GraphBrowser takes brand: Atlas in the top bar and the title", async () => {
    render(<GraphBrowser queryClient={qc()} brand={ATLAS} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.getByRole("banner")).toHaveTextContent("Atlas");
    expect(screen.getByRole("banner")).not.toHaveTextContent("Arras");
    await waitFor(() => expect(document.title.endsWith(" · Atlas")).toBe(true));
  });

  it("ArrasConsole takes brand: Atlas in the header and the title", async () => {
    render(<ArrasConsole queryClient={qc()} brand={ATLAS} />);
    const header = await screen.findByTestId("console-header");
    expect(header).toHaveTextContent("Atlas");
    expect(header).not.toHaveTextContent("Arras");
    await waitFor(() => expect(document.title.endsWith(" · Atlas")).toBe(true));
  });

  it("the console with no brand is Arras", async () => {
    render(<ArrasConsole queryClient={qc()} />);
    expect(await screen.findByTestId("console-header")).toHaveTextContent("Arras");
    await waitFor(() => expect(document.title.endsWith(" · Arras")).toBe(true));
  });

  it("ArrasApp passes brand to the browser", async () => {
    render(<ArrasApp queryClient={qc()} brand={ATLAS} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.getByRole("banner")).toHaveTextContent("Atlas");
    await waitFor(() => expect(document.title.endsWith(" · Atlas")).toBe(true));
  });

  it("restores the page's own title when the browser unmounts", async () => {
    const { unmount } = render(<GraphBrowser queryClient={qc()} brand={ATLAS} />);
    await waitFor(() => expect(document.title).not.toBe("page"));
    unmount();
    expect(document.title).toBe("page");
  });
});

describe("the wordmark", () => {
  it("an https:// wordmark is an image named by the brand's name", async () => {
    render(
      <GraphBrowser
        queryClient={qc()}
        brand={{ name: "Atlas", wordmark: "https://example.test/atlas.svg" }}
      />,
    );
    const img = await screen.findByRole("img", { name: "Atlas" });
    expect(img).toHaveAttribute("src", "https://example.test/atlas.svg");
  });

  it("a javascript: wordmark is text, never an image or a URL", async () => {
    render(
      <GraphBrowser
        queryClient={qc()}
        brand={{ name: "Atlas", wordmark: "javascript:alert(1)" }}
      />,
    );
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.getByRole("banner")).toHaveTextContent("javascript:alert(1)");
    expect(screen.queryByRole("img", { name: "Atlas" })).toBeNull();
    expect(screen.getByRole("banner").querySelector("img, [src], [href]")).toBeNull();
  });

  it("HTML in the name is shown as text", async () => {
    render(<GraphBrowser queryClient={qc()} brand={{ name: "<b>Bold</b><img src=x>" }} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    const bar = screen.getByRole("banner");
    expect(bar).toHaveTextContent("<b>Bold</b><img src=x>");
    expect(bar.querySelector("b, img")).toBeNull();
  });
});

describe("the theme's mark", () => {
  it("logo: theme renders the mark labelled by the name, before the name", async () => {
    render(<GraphBrowser queryClient={qc()} brand={{ name: "Atlas", logo: "theme" }} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    const bar = screen.getByRole("banner");
    const mark = bar.querySelector("[data-logo]");
    expect(mark).not.toBeNull();
    expect(mark).toHaveAttribute("aria-label", "Atlas");
    expect(bar).toHaveTextContent("Atlas");
  });

  it("no logo, no mark", async () => {
    render(<GraphBrowser queryClient={qc()} brand={ATLAS} />);
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    expect(screen.getByRole("banner").querySelector("[data-logo]")).toBeNull();
  });

  it("a wordmark wins over the mark", async () => {
    render(
      <GraphBrowser
        queryClient={qc()}
        brand={{ name: "Atlas", logo: "theme", wordmark: "Atlas Labs" }}
      />,
    );
    await screen.findByRole("heading", { level: 1, name: "Product catalog" });
    const bar = screen.getByRole("banner");
    expect(bar.querySelector("[data-logo]")).toBeNull();
    expect(bar).toHaveTextContent("Atlas Labs");
  });

  it("the console header shows the mark too", async () => {
    render(<ArrasConsole queryClient={qc()} brand={{ name: "Atlas", logo: "theme" }} />);
    const header = await screen.findByTestId("console-header");
    expect(header.querySelector("[data-logo]")).not.toBeNull();
  });
});

describe("useBrand and titleFor", () => {
  it("useBrand is the default with no provider", () => {
    let seen: Brand | undefined;
    const Probe = () => {
      seen = useBrand();
      return null;
    };
    render(<Probe />);
    expect(seen).toEqual(DEFAULT_BRAND);
    expect(DEFAULT_BRAND.name).toBe("Arras");
  });

  it("titleFor's name defaults to the default brand and takes another", () => {
    const r = { module: "catalog", area: "entities", type: "catalog.P", key: "k" } as const;
    expect(titleFor(r, "entities")).toBe(`k · Entities · catalog · ${DEFAULT_BRAND.name}`);
    expect(titleFor(r, "entities", "Atlas")).toBe("k · Entities · catalog · Atlas");
    expect(titleFor({ area: "model" }, "model", "Atlas")).toBe("Atlas");
  });
});

describe("readBrandMeta", () => {
  const docWith = (content: string | null): Document => {
    const d = document.implementation.createHTMLDocument("t");
    if (content !== null) {
      const m = d.createElement("meta");
      m.setAttribute("name", "arras-brand");
      m.setAttribute("content", content);
      d.head.append(m);
    }
    return d;
  };

  it("a missing tag is the default", () => {
    expect(readBrandMeta(docWith(null))).toEqual(DEFAULT_BRAND);
  });

  it.each(["{not json", "null", "[]", '"x"', "42", "{}", '{"name": 3}', '{"name": "   "}'])(
    "malformed or nameless %s is the default",
    (c) => {
      expect(readBrandMeta(docWith(c))).toEqual(DEFAULT_BRAND);
    },
  );

  it("reads the fields, trimmed", () => {
    const b = readBrandMeta(
      docWith(
        JSON.stringify({ name: "  Atlas ", title: " Atlas Home", tagline: " t ", wordmark: " W " }),
      ),
    );
    expect(b).toEqual({ name: "Atlas", title: "Atlas Home", tagline: "t", wordmark: "W" });
  });

  it("caps lengths and drops non-string fields", () => {
    const b = readBrandMeta(docWith(JSON.stringify({ name: "n".repeat(500), tagline: 5 })));
    expect(b.name).toHaveLength(80);
    expect(b.tagline).toBeUndefined();
  });

  it("accepts only the literal theme for logo", () => {
    const one = (logo: unknown) => readBrandMeta(docWith(JSON.stringify({ name: "A", logo })));
    expect(one("theme").logo).toBe("theme");
    for (const bad of ["Theme", "https://x/l.svg", "", true, 1, null]) {
      expect(one(bad).logo).toBeUndefined();
    }
  });

  it("a non-https wordmark is kept as text for the renderer to show as text only", () => {
    const b = readBrandMeta(docWith(JSON.stringify({ name: "A", wordmark: "javascript:x" })));
    expect(b.wordmark).toBe("javascript:x");
  });
});
