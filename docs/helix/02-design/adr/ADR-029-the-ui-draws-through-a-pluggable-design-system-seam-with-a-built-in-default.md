---
ddx:
  id: ADR-029
  type: adr
  activity: design
  status: accepted
  owner: Erik LaBianca
  updated: 2026-10-21
  authoring:
    home: repo
  links:
    - id: ADR-021
      kind: informed_by
    - id: ADR-025
      kind: informed_by
    - id: ADR-027
      kind: informed_by
---

# ADR-029: The UI draws through a pluggable design-system seam with a built-in default

| Date | Status | Deciders | Related | Confidence |
|------|--------|----------|---------|------------|
| 2026-10-12 | Accepted | Erik LaBianca (architecture lead) | [ADR-021](ADR-021-operator-console-as-a-react-package-in-the-arras-repository.md), [ADR-025](ADR-025-one-shell-two-modes-and-operate-is-offered-by-the-host.md), [ADR-027](ADR-027-the-wheel-carries-the-ui-as-a-mountable-app-and-an-npm-tarball.md), [ADR-030](ADR-030-the-action-kit-and-its-import-rule.md) | Medium |

## Context

| Aspect | Description |
|--------|-------------|
| Problem | `arras-ui` is embedded in host applications whose pages have their own look. The console and the Graph Browser must look right with no host theme at all, follow a host's colours and appearance where it has them, and let a host draw the common controls with its own widgets. Hand-made buttons, fields and lists in every screen are each a place for layout and accessibility faults (an overlapping list and button row in the add-link popup). |
| Current State | The library's styles are scoped to `.arras-root` with their own tokens (`--bg`, `--surface`, `--fg`, `--accent`, ...) and light and dark values (ADR-027). The buttons, fields, dropdowns and notices are drawn through one set of widgets, imported from `src/ds`. |
| Requirements | The UI is complete and accessible (WCAG 2.1 AA) with no design-system package installed and no registry reached. A host can restyle it with CSS custom properties alone, or replace the widgets with its own. A host that does neither gets the built-in look. The library sets nothing on the host's document. |
| Decision Drivers | An open-source library has no private dependency to install; an embedding host can supply its own widgets; ADR-027's rule that the library's CSS reaches nothing outside its root; one copy of React and no second widget library in a host. |

## Decision

1. **A contract, not a package.** `src/ds/contract.ts` types the design system: six widgets, `Button`, `TextField`, `TextArea`, `Select`, `Notice` and `Mark` (the product's mark), each a React component with the props the screens use, and the role tokens as CSS custom properties (`ROLE_TOKENS`). The contract is exported from `arras-ui` (`DesignSystem`, `ButtonProps`, `NoticeProps`, ...). Nothing in `ui/` depends on a design-system package.
2. **A built-in default.** `src/ds/default.tsx` and `src/ds/default.css` implement every widget in plain React and CSS. A `Button` has `primary`, `secondary` and `text` variants and two sizes, takes its busy state as `aria-busy` with a spinner and ignores clicks while busy, and a visible focus ring. A `TextField`, `TextArea` or `Select` has a visible label tied to the control, a hint and an error tied by `aria-describedby`, and `aria-invalid` on an error. A `Notice` has a tone (`info`, `success`, `warning`, `error`), a role (`alert` for error and warning, `status` otherwise) and a glyph that does not rely on colour. The `Mark` is an inline SVG with no third-party artwork. The colours meet 4.5:1 for text and 3:1 for control borders and the focus ring in light and dark.
3. **Role tokens.** The stylesheet reads eighteen role tokens, each as `var(--arras-..., <built-in value>)` with a light and a dark built-in value, so a host sets only the ones it wants, on an ancestor of the interface or on its root: colour (`--arras-color-text`, `-text-muted`, `-surface`, `-surface-sunken`, `-ground`, `-border`, `-accent`, `-on-accent`), shape (`--arras-radius-control`, `--arras-radius-card`), type (`--arras-font-body`, `--arras-font-mono`, `--arras-font-size-small`, `--arras-font-size-heading`) and state (`--arras-state-live`, `-limited`, `-closed`, `-purchasing`). The library's own variables are derived from them: `--bg` is `--arras-color-ground`, `--surface` the surface, `--surface-2` the sunken surface, `--fg` the text, `--fg-muted` the muted text, `--line` the border, `--accent` and `--accent-fg` the accent and its on-colour; `--line-strong` and `--accent-soft` are mixed from those. A unit test (`src/test/design-system.test.tsx`) fails when the stylesheet reads a role token the contract does not list, or lacks a built-in value for one.
   The eight tones a view may name (CONTRACT-010) are drawn from the state colours, because a theme has one accent and four state colours and no eight-hue palette: `green` is `--arras-state-live`, `amber` `-limited`, `red` `-closed`, `blue` `-purchasing`, `slate` the muted text, `rose` the accent, `teal` a mix of live and purchasing, `violet` a mix of purchasing and the accent. A tone's ink and soft fill are mixed from its mark and the page's text and surface, so a node's border, icon tile and badge follow the tokens and the appearance. The status colours of the console (`--ok`, `--warn`, `--bad`) are the same live, limited and closed colours.
4. **The seam.** `src/ds/context.tsx` holds a React context whose default value is the built-in implementation, `DesignSystemProvider` (a host passes `designSystem`, complete or partial; a missing widget is the built-in one, an inner provider overrides an outer one) and `useDesignSystem()`. `src/ds/index.ts` re-exports the widgets as components that read the context, so a screen writes `import { Button, Notice } from "../ds"` and never names an implementation. `ArrasApp`, `ArrasConsole` and `GraphBrowser` install no provider of their own: they use the one above them, or the built-in default. `src/ds` is a leaf: it imports React and its own modules only (Biome override and `src/test/boundaries.test.ts`); the browser and the kit may import it (ADR-030).
5. **The host owns the theme.** No component installs a theme, takes an appearance prop, sets `color-scheme`, `data-theme`, `data-appearance` or a class on the host's document or elements, or stores a choice. The built-in dark values apply through the nearest ancestor that gives an appearance (`data-appearance="light" | "dark"`, or an inline `color-scheme` of exactly `light` or `dark`, alone or with `only`; `light dark` and `dark light` say none), then `prefers-color-scheme`. A host switching light, dark or auto at run time re-themes the components with no call into them. UMF's schema browser fixes its theme at mount, so the console reads the host's effective scheme (the same nearest ancestor, else the system's) with the tokens, watches the page's root element and every ancestor of its own root, for attributes only and never a subtree, for a change of `data-appearance`, `data-theme`, `class`, inline `style` or the system's preference (the ancestors are resolved again on every change and once after mount, so a host that writes its attribute after the console has mounted is seen, and an element that has stopped being an ancestor is no longer watched), and mounts the frame again when the scheme or the token values differ.
6. **Standalone pages.** The dev host (`src/main.tsx`) and the page `arras.ui` serves (`src/embed.tsx`) use the built-in design system, follow the system's preference, and load no theme or font file by default. A host may opt into CONTRACT-005's same-origin runtime theme manifest; executable widget replacement uses the compiled provider route.
7. **Where widgets stay ours.** Where a widget imposes a label that the page already states (the inline property editor), the native element carries the widget's field class (`arras-field__input`). Icon-sized controls, the lock and the dialogs stay ours (`gb-dialog`), drawn with the tokens. The action kit (`ui/src/kit/`, SD-013) is drawn with the widgets for both modes: `ActionFields`, `EffectsSummary` and `ReceiptSummary` use `Button`, `TextField`, `TextArea`, `Select` and `Notice`, and the kit renders no dialog or panel of its own.

### Downstream theme qualification

Publish reusable synthetic theme checks with the interface artifacts. A compiled
host may replace all six widgets and Mark without a private dependency entering
Arras; a prebuilt page may replace tokens, fonts and favicon through the inert
asset manifest. Neither route changes Arras layout, action behavior or focus
orchestration. The host remains responsible for replacement-widget semantics;
labels, descriptions, refs, busy/disabled/error and keyboard props are required.

Check the actual themed browser and console widgets, not only a probe calling the
provider hook. Run light/dark axe, applicable computed contrast/state pairs and
keyboard/focus checks, plus noncolor CSS token validation. Use separate reviewed
macOS visual baselines per theme and run nonvisual CI on Linux. The fixture uses
only public packed artifacts and neutral synthetic data. These checks qualify
that exact theme/browser cohort; token presence alone does not establish contrast
or accessibility. CONTRACT-005 owns the executable asset and acceptance boundary.

### The existing acceptance suite runs against a theme overlay

The packed token/axe/widget checker is useful but narrower than the existing
Playwright a11y/end-to-end suite. CONTRACT-005 therefore requires a shared public
testkit using the canonical specs/resources and a standard synthetic acceptance
host wrapped in the consumer's theme/provider. Parameterize only explicit fixture
origins, resource paths, expected Brand/surfaces and per-theme output/baselines;
retain assertions rather than inventing a selector/callback test language.
Production imports remain free of optional Playwright/Node tooling. Qualify the
actual packed overlay with all nonvisual projects and reviewed Darwin theme
baselines; Linux skips only visual comparison. No checkout-only or narrower-checker
result is counted as this portable full-suite proof.

## Alternatives

| Option | Pros | Cons | Evaluation |
|--------|------|------|------------|
| Depend on one design-system package as a peer | A host that uses it gets its look with no code | A hard dependency on one package and its registry for everyone who builds or embeds the UI; a host with another system cannot use the library | Rejected |
| Tokens only, no widget contract | Smallest surface; a host restyles with CSS | A host cannot give the controls its own markup or behaviour; the widgets still have to be ours | Rejected; tokens are half of the decision |
| Bundle a third-party widget library into the library | A rich widget set | A second copy of the widgets in every host; a dependency to audit and track | Rejected |
| A built-in default only, with no provider | Simplest | A host that wants its own buttons forks the screens | Rejected |

## Consequences

| Type | Impact |
|------|--------|
| Positive | The UI builds, tests and runs with the public registry only. A host restyles it with CSS custom properties, or replaces any widget, without forking a screen. The controls are accessible in one place. |
| Negative | The project keeps its own widgets and their accessibility; a host that replaces a widget owns that widget's accessibility and must honour the contract's props (`busy`, `error`, `hint`). |
| Neutral | A page with no host tokens looks as the built-in values draw it. A provider adds one context read per widget. |

## Risks

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| A host's widget ignores a contract prop (a label, a busy state) and loses an accessibility behaviour | M | M | The contract documents each prop (`ui/README.md`, "Theme and design system"); the built-in implementation is the reference and is tested per widget |
| A host's tokens give a pair under 4.5:1 | M | L | The built-in pairs are the reference; the axe suite runs against the built-in values |
| The contract grows a widget for every new screen | M | L | A widget is added when two screens need it; one-off markup stays in its screen |

## Validation

| Success Metric | Review Trigger |
|----------------|----------------|
| Every screen imports its widgets from `src/ds`; a host-supplied implementation is used by the console, the browser and the kit (`src/test/design-system.test.tsx`); no source installs a theme or writes to the host's document (`src/test/host-theme.test.tsx`); axe finds no WCAG 2.1 A/AA violation in light or dark | A host that needs a widget the contract lacks; a token a host cannot restyle with the eighteen |

## Concern Impact

- **Concerns used**: `frontend-framework` (React with TypeScript in `ui/`), `a11y-wcag-aa`.
- **Departures**: none.
