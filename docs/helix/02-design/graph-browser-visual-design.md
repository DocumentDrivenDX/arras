---
ddx:
  id: DESIGN-GB
  type: design-system
  activity: design
  status: draft
  owner: Erik LaBianca
  updated: 2026-10-12
  authoring:
    home: repo
  links:
    - id: FEAT-011
      kind: informed_by
    - id: SD-011
      kind: informed_by
    - id: CONTRACT-010
      kind: informed_by
    - id: ADR-022
      kind: informed_by
---

# DESIGN.md — Graph Browser

This is the interface system of the Graph Browser (FEAT-011): the concrete layout, hierarchy, states, tokens and picture geometry it commits to. It is the Graph Browser's instance of the interface guidelines; the Operator Console keeps its own denser system (`ui/src/styles.css`), whose tokens the browser reuses. The reference rendering is the mockup in [`graph-browser-mockup/`](graph-browser-mockup/index.html), with a screenshot of each screen beside it:

The mockup is `graph-browser-mockup/index.html`, open in a browser: screens for entry and results, the node page in light and dark, the narrow window with tones, and the states. The mockup is the design; the real component is checked against it.

## Navigation and Active State

The browser has one level of navigation inside a module and no sidebar. The top bar holds the module name (a menu when the viewer may read more than one module), the search box (from slice 3), the **mode switch** (operators only), and the freshness line. The mode switch is a two-option segmented control, `Explore` and `Operate`, at the right of the top bar before the freshness line; it is **absent from the page** for a viewer who is not an operator (not disabled, not greyed, not mentioned). In Operate the same top bar frames the Operator Console, whose own area tabs sit beneath it. Below it the page is either the **Entry** (the type choice and hits) or a **Node page**. A breadcrumb on a node page has three crumbs: the root (`Explore`, or `Search: lumen alert` when the reader came from a search), the type's **plural label** (`Solutions`), and the current entity's key. The root links to the module's entry and the type crumb to the type's list (`#/explore/<module>/<type>`), both real links that a keyboard reaches and that show the focus ring; the last crumb is plain text. A type is named by its plural label wherever it names a collection (the type crumb, a type card, a type chip, the list's heading) and by its singular label where one entity is meant (the card's eyebrow, a relationship row's `Type · key`, a picture node, a hit row's type label).

**Active-state convention (required):** an active control shows a visible active state **and** carries the matching ARIA state, and the visible style is derived from that state, never set separately.

| Surface | Component | Active cue (visible) | Semantic |
|---------|-----------|----------------------|----------|
| Type chips (single choice: `All`, then one per type; exactly one selected) | `Chip` | `--accent-soft` fill, a 2 px `--accent` border (border plus inset ring), bold label and a trailing check mark (not colour alone) | a `radiogroup` of `role="radio"` chips, `aria-checked="true"` on the selected one, a roving tabindex and the arrow keys (Home, End) moving the selection |
| Mode switch (Explore, Operate) | `Seg` | `--accent` fill with `--accent-fg` text and a check mark glyph | `aria-pressed="true"` |
| Breadcrumb | `Crumbs` | The earlier crumbs are links in `--accent` (underlined on hover and focus, with the 2 px focus ring); the current page is plain text, not a link | `aria-current="page"` on the last crumb |
| The centre node of the picture | `PictureNode` | 3 px outline instead of 2, bold label, "this page" caption | none: the centre is drawn text inside the labelled group, and the page heading names the same entity |
| Relationship links | `RelLink` | Hover and keyboard focus show a `--surface-2` row and a trailing arrow | none (links) |

The shell landmarks are `banner` (top bar), `search` (the search box's form), `main` (the page), `complementary` (the side column: picture and relationships, labelled "Relationships"), and the card's `footer` element (attribution and freshness; not a landmark, because axe requires a `contentinfo` landmark to be top level and the card sits inside `main`).

## Visual Hierarchy

The browser is a reading interface: larger type, more space and less density than the Operator Console, and one dominant object per screen.

- **Layout**: the page is capped at 1200 px and centred. A node page has two columns: the node card (flexible, at least 560 px) and a side column of 400 px holding the picture above the relationship groups. Slice 1 has no search box; the Entry's first element is then the module title and the type cards. At 1024 px and below the side column drops under the card; under 420 px the picture is behind a "Show neighbourhood picture" button and the relationship list is the only view of the links. The Entry is a single column of at most 880 px.
- **Where the eye lands first**: on a node page the card header (the tone-coloured top rule, the icon tile and the 26 px title); on the Entry the search box, then the first hit.
- **Type scale** (base 15 px, the console's 13 px is for dense tables and is not used here): 26/32 title (700), 20/28 state heading (600), 16/24 hit title and summary (600 and 400), 15/22 body, 13/18 secondary and metadata, 12/16 labels and eyebrows (600, uppercase, +0.06em tracking). Numbers use tabular figures.
- **Weight and emphasis**: primary is the title and the hit title; secondary is the summary and excerpts in `--fg-muted`; tertiary is the eyebrow, type label, attribution and freshness at 12 to 13 px. Matched text in a hit is `mark` with a 25% `--warn` wash behind it and `--fg` text (the excerpt line is muted, and muted text on the wash fails 4.5:1 in dark), so it is not conveyed by colour alone (it has a background shape and the text is the same weight).
- **Spacing rhythm**: an 8 px base. Cards pad 24 px horizontally; sections pad 16 px vertically with a 1 px `--line` divider; rows in a list are 40 px high minimum; groups in the side column are 16 px apart; the page's outer gutter is 24 px (16 px under 760 px).
- **Elevation**: cards use `--shadow` (a 1 px and a 4 px blur at 6% in light, 40% and 35% in dark) and a 12 px radius; hit rows a 10 px radius with the shadow on hover only; the picture panel is a card.

## Screens

### 1. Entry and results

```text
+--------------------------------------------------------------------------------+
| Product catalog        [ search: lumen alert                     / ]  ● Truss · current · LATEST     |
|  catalog · 6 types                                                              |
+--------------------------------------------------------------------------------+
| (All 4 ✓) (Solutions 3) (Products 1) (Findings 0) (Use cases  not searched)  chips, wrap |
| ⚠ UseCase was not searched. Its backend (ashlar) is unavailable.   banner       |
| 4 results for lumen alert · ranked                                              |
| +----------------------------------------------------------------------------+ |
| | [▣] SOLUTION                                                   (Embedded)  | |
| |     Lumen alert correlation (S-017)                                         | |
| |     …uses Lumen for alert correlation…                                     | |
| +----------------------------------------------------------------------------+ |
| | [▣] PRODUCT ...                                                            | |
+--------------------------------------------------------------------------------+
```

- With no text the Entry shows the module title and description (from the module's view), then one **type card** per readable type: tone icon tile, plural label, entity count where served, and the first three hits' titles; activating a card lists that type.
- A hit row is a single link: a 40 px tone icon tile, the type label (12 px uppercase), the title, an excerpt with matches marked, and and, on the right, a type badge. The whole row is the target (minimum 44 px high).
- The chips sit under the search box and are a single choice: `All` first and selected by default, then one chip per type, exactly one selected; choosing the selected chip changes nothing and `All` is the way back (there is no clear control). With text, `All` searches every type and shows the total, and a type chip searches only that type; with no text `All` shows the type cards and a type chip lists that type. A chip for a type that was not searched is dashed with "not searched". Notices (a backend unavailable, truncation) appear in one banner above the results, never inside the list.
- The status line under the banner states the count, that results are ranked, and, when truncated, how to refine ("showing the best 50 of each type").

### 2. Node page

```text
Search: lumen alert › Solution › S-017
+------------------------------------------------------+  +----------------------------+
|▔▔▔▔ tone rule ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔|  | NEIGHBOURHOOD   (1 hop|2) |
| [icon tile 56]  SOLUTION                             |  |   picture (see Picture)    |
|                 Lumen alert correlation (S-017)       |  | 7 of 7 shown               |
|                 Summary line…                        |  +----------------------------+
|                 (Embedded)                           |  | ADDRESSES USE CASES      4 |
+------------------------------------------------------+  | ▢ Alert review      →      |
| DELIVERY                                             |  | ▢ Runbook check     →      |
|  Audience     Platform engineers                     |  | ▢ Not available            |
|  Launch       https://…  (link)                      |  +----------------------------+
|  Caveat       Not set                                |  | PROVIDED BY              1 |
| ▾ HOW IT WORKS (prose, collapsible)                  |  | ▢ Lumen             →      |
| ▸ MORE                                               |  +----------------------------+
+------------------------------------------------------+
| Last changed by alice · 9 Oct 2026, 14:12   Truss · current as of 09:30 · LATEST ▾ |
+------------------------------------------------------+
```

- **Header**: a 4 px rule in the type's tone mark colour across the top of the card; a 56 px tile in the tone's soft colour holding the icon in the tone's ink colour; the header reads in this order: the eyebrow (type label) in the tone's ink, the title (26 px), the key (13 px, muted, monospace), then the links (for an operator **Open in Operate**, as a text button). In edit mode the card's top right holds the **entity menu**, a `⋯` button beside the edit lock, whose items are **Retire** and then each declared action that takes the entity and no inline control claims, each with its description as secondary text (there is no separate Actions button); the summary (16 px, muted); up to two badges from the declared view (the first two `badge` properties that have a value). A property shown as a header badge is not repeated in the sections: its row is left out, and a section left with no rows is not drawn.
- **Sections** follow the resolved view's order. A section heading is a 13 px uppercase label; a collapsed section is a `details` element whose summary is that heading. Properties are a definition list: a 160 px label column (muted) and a value column that wraps anywhere. A property with no value shows *Not set* in italic muted text unless `hideWhenEmpty`.
- **Formats**: `badge` is a pill in the tone for the value (a value not mapped is `slate`); `link` is an underlined link in `--accent` that opens in the same window for the module's own locations and with `rel="noopener noreferrer"` in a new tab for others, showing the host name when long; `prose` keeps line breaks and has a 68-character measure; `code` is monospace on `--surface-2`; `date` and `datetime` show a local, readable value, and a small "exact" control shows the stored RFC 3339 value in a popover; `json` is a collapsed tree; `tags` are slate pills.
- **Footer** (the card's `footer` element): the last change (who and when, where the backend supplies it) and the freshness line (backend, current or behind, time, consistency). The first release reads `LATEST` only, so there is no consistency menu.

### 3. Side column: relationships and the picture

- Each relationship is a card with a 13 px uppercase title (the declared label, or the inverse label on the target), the count right-aligned, and a list of rows: a 28 px tone tile with the type's icon, the related entity's title, and "Type · key" in muted 12 px; the trailing arrow appears on hover and focus. A row is a link to that entity's node page. An entity that is hidden or absent is a non-link row with a lock icon and "Not available", the same for both cases. A group with more than 100 members shows the first page and "Show more". A group with none shows "None" (unless `hideWhenEmpty`).
- Groups are in the declared order, then by label.
- The picture sits above the groups in the same column, in a card of its own (see Picture geometry). A group lists 20 neighbours and a "Show more" control labels the next 20 (and, beyond the 100 keys a read returns, reads one page of the other type's list through the inverse relationship when there is one, marked when it is truncated).

### 4. Narrow window

At 390 px the page is one column (the four screens of instance work, New, Retire, Actions and History, are checked at 390 px too, Screens 6 to 9): a top bar of two rows (the module name with the mode switch and the host's toolbar, then the search with the freshness line), the card, then the relationship groups, then a full-width "Show neighbourhood picture" button that expands the picture in place (the picture is scaled to the width and is the same component). Hit rows keep their 44 px height; badges wrap under the title.

### 5. States

| State | Appearance |
|-------|------------|
| Loading | Skeleton blocks of the final shape (title bar, three lines, a card), shimmering only when `prefers-reduced-motion: no-preference`; the region has `aria-busy="true"` and the status text "Loading" for screen readers |
| No results | A circle with a search icon, "No results for “…”", what was searched and what was not, and a "Clear type filters" primary button when any are on |
| Not available | A circle with a lock icon, "Not available", the sentence "This page does not exist or you cannot read it", and one button; the heading and sentence are identical for a missing, hidden, malformed or unreadable location. The button reads "Back to <module title>" and leads to the module's entry when the location names a module the viewer can read, and reads "Back to search" and leads to the start otherwise. The document title is the brand alone and never carries a key |
| Backend down | A circle with a warning icon, "The catalog did not answer", the backend's name, and a "Retry" primary button; where other backends answered, the page shows their results and the banner of Screen 1 instead of this state |
| Session expired | The host's state; the browser keeps the location and the typed text |
| Truncated | The status line of Screen 1; on a node page, "Show more" on the group |

### 6. New form

Where the host offers edits, a type's list shows the edit-mode lock beside the list's heading (the same lock as on a node page), and, while edit mode is on, **New <type>** (a secondary `Button` with a plus glyph) before it. It opens a dialog in the `gb-dialog` style (`role="dialog"`, `aria-modal`, a focus trap, focus starting in the first field and returned to the button on Cancel or Escape).

```text
+----------------------------------------------+
| New Solution                              [x] |
|----------------------------------------------|
| Create with [ AddSolution         v ]  (only when several fit) |
| code *   [ S-018                      ]       |
| name *   [                            ]       |
| useCase *[ Filter or search use cases ]       |   the picker as the ref field:
|          [ Choose…                  v ]       |   a filter above a dropdown
| notes    [                            ]       |
| ⚠ conflict (exists)                           |   a refusal, in the dialog
|              [ Cancel ] [ Validate ] [ Create ] |
+----------------------------------------------+
```

- One field per input of the action: a text field, a text area for a list input (one value per line) or a record input (JSON), a `Select` for a boolean, and the picker for a `ref` input (a filter above a dropdown of the referenced type's entities, the key field where the type cannot be listed). A required field is marked with text, not colour alone, and its error is associated with it. The server's violations that name an input show beside that field by path; a refusal that names none (a key already used, a failed precondition) shows in a notice above the buttons, and the values are kept. **Validate** lists the effects as text; **Create** is disabled until the validation has passed.
- At 1280 px the dialog is 520 px wide, centred. At 390 px it is full width and full height, the actions pinned to the bottom, fields in one column.
- On success the dialog closes and the created entity's page opens (a new history entry, so Back returns to the list), with focus on its title.

### 7. Retire confirmation

In edit mode a node page offers **Retire** as an item of the entity menu in the card's header (`aria-haspopup="menu"`, a `role="menu"`; arrow keys move, Enter chooses, Escape closes and returns focus to the button). It opens a confirmation dialog, which returns focus to the menu button when it closes.

```text
+----------------------------------------------+
| Retire Lumen alert correlation (S-017)?     [x] |
|----------------------------------------------|
| This removes the Solution. It has these links:  |
|   Addresses use cases   4                        |
|   Provided by           1                        |
| The key S-017 cannot be used again. The interface |
| has no undo.                                      |
|                        [ Cancel ] [ Retire ]      |
+----------------------------------------------+
```

- The links are the page's own relationship groups with their counts, from the read already on screen; where a count is "100 or more" it says so. The confirm button is the primary style of the design system and is not focused first: focus starts on Cancel. A refusal shows inside the dialog and applies nothing.
- At 390 px the dialog fills the width. After the retire the type's list opens in place of the entity's history entry, so Back does not return to the retired page, and focus is placed on the list's heading.

### 8. Actions menu and dialog

In edit mode a node page offers **Actions**, a menu button (`aria-haspopup="menu"`) opening a `role="menu"` of the declared actions that take this entity, each with its description as secondary text. Arrow keys move, Enter chooses, Escape closes and returns focus to the button. A choice opens the action's dialog.

```text
[ Actions v ]                    +--------------------------------------------+
 +--------------------------+    | CorrectStatus                           [x] |
 | CorrectStatus            |    | Corrects a Solution's lifecycle status.     |
 |   Corrects a status      |    |---------------------------------------------|
 | AddCoverage              |    | Solution *  S-017  (prefilled)              |
 |   Links a use case…      |    | Status *    [ Embedded           v ]        |
 +--------------------------+    |---------------------------------------------|
                                 | Effects: updates Solution S-017 (status).   |
                                 |            [ Cancel ] [ Validate ] [ Apply ] |
                                 +--------------------------------------------+
```

- The dialog repeats the New form's field conventions, with the entity's input prefilled and read-only. **Validate** shows a text summary of the effects (one line each: creates, updates, deletes, links, unlinks) and any violation; **Apply** invokes. The receipt replaces the form: what changed, with a link to each entity touched, and the focus is placed on it.
- At 1280 px the menu is 320 px wide under its button and the dialog 560 px. At 390 px the menu is a full-width sheet at the bottom and the dialog full screen.

### 9. History panel

An operator's node page shows a **History** button above the card, at the right of the breadcrumb row. It opens a panel in the page (the address ends in `/history`, so the panel is bookmarkable; Back closes it): full width between the breadcrumb and the card at 1280 px, and at 390 px the only pane, with **Back to** the entity's title as the way back. The panel's heading is History.

```text
+----------------------------------------------+
| History                 [ Back to Log extractor ] |
|----------------------------------------------|
| alice · 9 Oct 2026, 14:12                      |
|   CorrectStatus                               |
|   Solution S-017 · Product Lumen              |
| bob · 8 Oct 2026, 09:40                       |
|   AddCoverage                                 |
|   Solution S-017 · Use case Not available     |
|                              [ Show more ] |
+----------------------------------------------+
```

- Newest first, 20 a page, then a **Show more** button. A change shows who and when (an exact UTC time), the action's name and the entities it touched as links; a touched entity the viewer cannot read is "Not available" with no key. A change's group links to Operate's receipt view where Operate is offered.
- Where the journal is not granted (403) or the backend keeps none (501) the panel is one sentence in a `Notice`, never an error panel.

### Screens as built


## Picture geometry

The picture is a pure function `layoutGroups(centre, groups) → {nodes, edges, captions, size}` (SD-011, Layout of the picture); it has no animation and no randomness, so the same input always draws the same picture and the layout is testable as coordinates.

- **Canvas**: a 440 × 340 `viewBox` scaled to the card's width (400 px at full size, so type renders at about 11 to 12 px); the height follows the number of rows.
- **Centre**: a 120 × 48 px rounded rectangle at the middle, a 3 px border in the type's tone mark, a 36 px tile with the icon, the title clipped to 11 characters with an ellipsis, and "this page" beneath it.
- **Neighbours**: a 36 px-high pill, width 134 for a left column and 120 for a right, with a 28 px tile holding the type's icon, a 2 px border in the type's tone mark and the title clipped to 15 characters with an ellipsis (the full title is in the accessible name and in the hover card). Pills never overlap: each group is a column or a row, and the layout adds rows rather than shrinking.
- **Groups**: a relationship's neighbours form one group, laid out on a side: group 0 a column on the left, group 1 a column on the right, group 2 a row along the bottom, group 3 a row along the top, and group *n* ≥ 4 on side *n* mod 4 after the groups already there. Each group has a 10 px uppercase caption at its start (the relationship's label, with `· +N more` when members are left out, and `· +N or more` when the relationship returned its 100-key limit, so the count is a lower bound), which replaces labels on edges so that edges never carry text. Groups are ordered by the declared `order`, then label; members by title, then key.
- **Edges**: a 1.5 px `--line-strong` cubic curve from the centre's edge to the neighbour's edge, each leaving the centre at the side nearest its group. A block of members (see Big groups) has one bundled edge instead: a straight vertical line between the centre and the block's nearest edge. A self-link is a small loop on the centre. An edge to a neighbour that appears in two groups is drawn to its first.
- **Bound**: at most 40 nodes, taken round-robin one member per group so every group is represented. The left-out count is shown in each group's caption (`+N more`) and the footer says "32 of 120 neighbours shown"; the list is always complete. A "+N more" is not a node. Two hops are a later addition.
- **Interaction**: the picture's container is a `fieldset` (the group role) named by a visually hidden `legend` (not an image, so its links stay exposed); each node is an SVG `a` link (an anchor, so Enter activates it natively) with an accessible name "Type, title, relationship"; the nodes are **one Tab stop** with a roving tabindex: the arrow keys move between nodes group by group, Home and End go to the first and last, Enter opens. Hover and focus raise the node with a `--soft` fill and show a card with the full title, the type and the relationship, in the side of the node that has room; the card is also the focus state, so it needs no hover. Selecting a node navigates and re-centres; `prefers-reduced-motion` removes the 160 ms cross-fade.
- **Big groups**: a group with more than 8 drawn members is a block of rows of three 134 px pills instead of a column, so a hub does not run the card's height. A block goes to whichever of the top and bottom bands is shorter so far (the top on a tie), so two blocks sit one above and one below the centre, and the centre stays in the middle band. A block is joined to the centre by one bundled edge, not one curve per pill: forty curves fanning into a 120 px centre read as a hatch, not as links. The list beside the picture is the complete view. The caption says `+N or more` and the group's "Show more" control says "Show more (20 of 80+)" when the relationship returned its 100-key limit; the footer says "40 of 100+ neighbours shown" when a relationship returned its 100-key limit.
- **Fallback**: under 420 px the picture is hidden behind a button; with fewer than one neighbour it is a compact card "No relationships".

## Interaction States

States are stated only where they exist for the element.

| State | Applies to | Convention |
|-------|------------|------------|
| Hover and `:focus-visible` | Hit rows, chips, links, relationship rows, picture nodes, buttons | Hover: `--surface-2` fill or the shadow of a hit row. Focus: a 2 px `--accent` outline with 2 px offset (inset on rows so it is not clipped), always visible on keyboard focus; no focus style is removed anywhere. A chip's focus ring is its own: a 2 px `--fg` outline with 3 px offset, outside the selected chip's border, so a focused chip beside the selected one never reads as a second selection |
| Pressed | The mode switch | `aria-pressed` with the visible cue in Navigation (an inline check glyph rendered from the pressed state, `aria-hidden`, so it is not read twice) |
| Selected | The type chips | `aria-checked` on a radio with the visible cue in Navigation (the same inline check glyph, from the checked state) |
| Disabled | "Show more" while loading | `disabled` attribute and 50% opacity with a title that says why; never colour alone |
| Loading | Search, node page, "Show more", the picture | Skeleton or inline spinner with `aria-busy`; the previous answer stays visible (dimmed) while a new search runs so the page does not flash; a double activation is ignored |
| Empty | No results, empty group, empty type | An icon, a sentence naming what was searched, and a next step |
| Error | Backend down, search failed, location unreadable | A sentence that names the backend or says "not available"; a Retry or Back action; no raw error codes, stack traces or backend messages |
| Stale | An answer from a replica behind its feed | The freshness line turns `--warn` with the lag and is announced politely (`role="status"`); never an error |
| Selected text | Matches in hits | `mark` as above |

Focus order is the reading order: the top bar, the chips, the notices, the hits; on a node page the card, the side column's picture (nodes group by group), then the relationship groups. The search box is focused on entry and by the `/` key anywhere outside a text field; Escape clears it. The picture is a convenience: everything in it is reachable and equivalent in the relationship list; the container's name says the list has the same links.

## Tokens

Concrete values; the neutrals, accent and semantic colours are the Operator Console's (`ui/src/styles.css`, WCAG 2.1 AA pairs), reused so the two interfaces sit together in the embedding host. The browser adds the eight tones and the reading scale.

### Color

| Token | Light | Dark | Use |
|-------|-------|------|-----|
| `--bg` | `#f6f7f9` | `#0f131a` | Page |
| `--surface` | `#ffffff` | `#161b24` | Cards, search, hits |
| `--surface-2` | `#eef0f4` | `#1e2531` | Hover rows, footers, code |
| `--fg` / `--fg-muted` | `#151a23` / `#4a5365` | `#e8ebf1` / `#a8b0c0` | Text |
| `--line` / `--line-strong` | `#d5d9e1` / `#aab1bf` | `#2d3545` / `#4a5469` | Dividers / control borders |
| `--accent` / `--accent-soft` | `#1f4fd8` / `#e4ebfd` | `#7aa2ff` / `#1e2b4d` | Links, focus, pressed |
| `--ok`, `--warn`, `--bad` | `#0b6b3a`, `#8a4b00`, `#a31523` | `#6fdc9f`, `#f2b864`, `#ff8a95` | Freshness current, stale, error |

**Tones** (the closed set of CONTRACT-010). For each tone: `ink` for text and glyphs on `soft`, `soft` for tiles and badges, `mark` for borders, rules and node outlines. Contrast was computed from these values: `ink` on `soft` is at least 6.2:1 in light and 7.8:1 in dark; `mark` on the surface is at least 4.2:1 in light and 5.3:1 in dark (3:1 is the requirement for a border and a glyph).

| Tone | Light ink / soft / mark | Dark ink / soft / mark |
|------|-------------------------|------------------------|
| slate | `#3b4659` / `#eceff4` / `#64708a` | `#c3cada` / `#252c3a` / `#8c97ae` |
| blue | `#1b46b8` / `#e4ebfd` / `#2f62e0` | `#a9c1ff` / `#1e2b4d` / `#6f98ff` |
| teal | `#0b5f66` / `#dcf3f4` / `#117d86` | `#7fdbe2` / `#0f3338` / `#3fb6c0` |
| green | `#0b5f33` / `#dff5e8` / `#1a8a50` | `#7fe0aa` / `#12301f` / `#3fb978` |
| amber | `#7a4300` / `#fdf0d9` / `#b36a00` | `#f5c26f` / `#3a2a0f` / `#d9962b` |
| red | `#9a1424` / `#fde6e8` / `#c9263a` | `#ffa3ad` / `#3d1419` / `#f0606f` |
| violet | `#5b32b0` / `#ece6fb` / `#7a4fd6` | `#c9b4ff` / `#2c2150` / `#9c7bf0` |
| rose | `#9c1f64` / `#fbe4ef` / `#c42b83` | `#ffa6d1` / `#3e1630` / `#ee5fa8` |

A tone never carries meaning alone: it always accompanies an icon, a label or a position (a badge has its text; a node has its type icon and label).

### Spacing

4 / 8 / 12 / 16 / 24 / 32 / 48 px. Radii: 6 (segment control), 8 (inputs, buttons, rows), 10 (hit rows, picture pills), 12 (cards), 14 (56 px tile), 16 (chips), full (badges, state icon).

### Type

Family: the console's `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`; monospace `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`. Scale (size/line-height, weight): 26/32 700 title; 20/28 600 state heading; 16/24 600 hit title, 400 summary; 15/22 400 body; 13/18 400 secondary; 12/16 600 label, eyebrow, badge (uppercase with 0.06em tracking for labels and eyebrows). Tabular figures on.

### Motion

160 ms cross-fade on re-centring the picture and 120 ms on hover fills; none under `prefers-reduced-motion`; the skeleton shimmer only under `no-preference`.

### Icons

The 24 names of CONTRACT-010 drawn on a 24 px grid with a 1.8 px stroke, round caps and joins, `currentColor`, rendered at 14 to 30 px; each is also given in a table in the code with its accessible name (the type's label; the glyph itself is `aria-hidden`).

## Review

The design is reviewed against the real component by screenshots, not by reading code, at these points; each is a Playwright test in the whole-stack suite that stores its screenshots as test artifacts and fails on a pixel diff against a reviewed baseline above a 0.5% threshold:

1. Each screen above, in light and dark, at 1280 × 900 and 390 × 844 (Entry with results, Entry empty, Node page, Node page with a hub, Not available, no results, backend down).
2. The picture with 0, 1, 7, 40 and 120 neighbours, and with 3, 5 and 6 groups.
3. The top bar as an operator (with the mode switch) and as a reader (without it, with no trace of Operate).
4. Keyboard focus visible on every interactive element class.
5. `axe-core` clean on each screen in both schemes.
6. A human review of the screenshots against the mockup at the end of each slice (Review checklist in SD-011), with differences either fixed or recorded here.

Baselines are macOS only (`-darwin`; ui/README.md, Visual baselines). Differences from the mockup that are deliberate:

- A hub's picture is a block of pills with one bundled edge to the centre, not the mockup's fan of curves, and the centre sits at the foot of a single block (two blocks put it between them): the mockup has no group of more than 8.
- The mockup's results column is 880 px (the Entry's maximum); at 1280 px the right of the page is empty.
- The type list has an `h2` heading with the type's plural label above its count line, which the mockup does not draw; chips, cards and the type crumb read in the plural (`Use cases`), a hit row's type label and a relationship row's `Type · key` in the singular.
- The mockup's chips are a radio group with `All` first, a double border for the selected chip and a separate `--fg` focus ring, as the component draws them.
- The component's screenshots use the catalog example: a coverage assertion is titled by its code (`lumen.search-application-logs`) with its level as the header badge and no row for it below, a finding by its code with the statement as its summary, a product version by `label (code)`; the mockup's sample entities differ.
- At 390 px the top bar is two rows (module name and freshness line, then the search and the host's toolbar); the mockup shows one row without a host toolbar.

## Non-Goals

This document is the **interface system only**. It deliberately does NOT cover:

- **Runtime architecture**, data flow and module structure → SD-011.
- **Component implementation internals**: props, hooks, file layout → technical designs.
- **Architecture-significant decisions**: the vocabulary, search and location → ADR-022, ADR-023, ADR-024.
- **The Operator Console's screens**, which keep their own denser system (FEAT-010), and the whole-module graph.
- **Custom themes per module.** A module chooses an icon, a tone and formats from the closed sets (CONTRACT-010); it does not choose colours, fonts or layout.
