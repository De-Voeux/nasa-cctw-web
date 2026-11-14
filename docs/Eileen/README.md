# Eileen — collaborator context

**Collaborator:** eileenanindya

**Last updated:** 2026-11-15

## Responsibility and goal

**Frontend for the SEAGIS dashboard**: the page a user lands on. A full-screen 3D globe of Southeast Asia, with see-through "glass" panels floating on top (date pills, layer and zoom controls, a search/detail side panel, and an ask bar). The layout is modelled on Watch Duty's map-first dashboard.

The dashboard builds on Radit's [`EarthGlobe`](../../earth-globe/src/earth/README.md) and lives in the same Parcel subproject, [`earth-globe/`](../../earth-globe/). It is presentation only: it computes no environmental risk and shows no assessed cells.

## Work completed

### Glass dashboard (`earth-globe/src/index.html`)

| Area | Files | What it does |
| --- | --- | --- |
| Page shell | [`index.html`](../../earth-globe/src/index.html) | Globe container, HTML overlay layer, and the floating panels. |
| Design tokens | [`styles/tokens.css`](../../earth-globe/src/styles/tokens.css) | Colours, glass fill and border, radii, panel width, font (**Plus Jakarta Sans** via Google Fonts, system font fallback). |
| Layout and glass | [`styles/dashboard.css`](../../earth-globe/src/styles/dashboard.css) | `.glass` class (`backdrop-filter` blur + saturate, inner highlight), CSS star field, and a bottom-sheet layout below 860 px. |
| Wiring | [`dashboard/main.js`](../../earth-globe/src/dashboard/main.js) | Creates the globe with a transparent background, flies to Southeast Asia, and connects every component. |
| Globe overlay | [`dashboard/overlay.js`](../../earth-globe/src/dashboard/overlay.js) | Pins HTML elements (markers, labels) to lat/lon. Repositions them on each rendered frame and fades them out near the horizon and on the far side. |
| Date pills | [`dashboard/datePills.js`](../../earth-globe/src/dashboard/datePills.js) | Yesterday, today, and three forecast days, labelled history / today / forecast. |
| Side panel | [`dashboard/sidePanel.js`](../../earth-globe/src/dashboard/sidePanel.js) | Search, locations grouped by country, location detail (taxa, evidence status, environmental stress = insufficient data), and ask-bar answers. |
| Ask bar | [`dashboard/ask.js`](../../earth-globe/src/dashboard/ask.js) | **No AI backend.** Answers a few questions locally from the loaded data (for example "which area has the most ice-ice reports"), and says what it counted. |
| Marker data | [`data/reportedLocations.js`](../../earth-globe/src/data/reportedLocations.js) | 19 places and their taxa, from [CANDIDATE_HOST_REGIONS.md](../../research/evidence/CANDIDATE_HOST_REGIONS.md), plus country/sea label positions. |

Controls: the layers menu toggles markers, labels, and auto-rotate. The environmental data layers are listed but disabled. Zoom has +, −, and "back to Southeast Asia".

### Changes to shared code

- [`EarthGlobe.js`](../../earth-globe/src/earth/EarthGlobe.js): added `project(lat, lon, rect?, out?)`, which returns screen x/y, `facing` (cosine to the camera), and `visible`. Added a `"frame"` event, fired after every render, so HTML overlays never lag the globe. Existing behaviour is unchanged.
- **Radit's demo page moved:** `src/index.html` → `src/demo.html` and `src/index.js` → `src/demo.js`, now served at `/demo.html`. `npm start` and `npm run build` now bundle both pages. Radit's notes still use the old path.

### Prototype (reference only)

[`seagis-globe/index.html`](../../seagis-globe/index.html) is a single-file MapLibre GL v5 globe made while comparing approaches. It has a 0.25° coastal grid with an ocean mask computed in the browser, three.js beacons as a MapLibre custom layer, and live NASA GHRSST MUR SST layers from GIBS. **Its stress values are generated sample data.** It is kept as a reference for the grid, the NASA layers, and the globe → flat-map behaviour; it is not the product page.

## Current status and review steps

```bash
cd earth-globe
npm install
npm start      # dashboard: http://localhost:1235/   globe demo: http://localhost:1235/demo.html
npm test       # geo tests still pass
```

To view the MapLibre prototype, serve the repository root (`python3 -m http.server 5178`) and open `http://localhost:5178/seagis-globe/`.

**Verified 2026-11-15** (Chromium-based in-app browser at a 1440×900 desktop viewport):

- The globe loads and flies to Southeast Asia. Markers and labels follow it while rotating and flying, and hide on the far side.
- Clicking a marker flies to it, highlights it, and opens its detail in the panel. "All locations" returns to the list.
- Typing "Which area has the most ice-ice case?" answers Tawi-Tawi (4 taxa), with a note that this counts mentions, not cases.
- The layers menu, zoom buttons, and date pills work. There are no JavaScript errors.
- Plus Jakarta Sans loads and is applied.

**Not verified:** the mobile bottom-sheet layout at a real phone size, touch gestures, Safari and Firefox, and low-end GPUs. One HTTP 500 for an unidentified resource appears in the console; the page is unaffected.

## Assumptions, limitations, and blockers

### Verified facts

- Parcel's CSS minifier dropped the standard `backdrop-filter` when its value used `var()`, keeping only `-webkit-backdrop-filter`, so Chrome showed no blur. The blur values are now literal in `.glass`, and there is a comment explaining why.

### Working decisions (made in chat, 2026-11-14 to 15)

- The dashboard extends the three.js globe in `earth-globe/` (Parcel + plain JavaScript), not a new framework app.
- Scope is Southeast Asia, using the species and places in the candidate research leads.
- Markers and labels are HTML overlays, not three.js objects, so they stay crisp, accessible (buttons with labels), and easy to style.

### Proposals (not in [DECISIONS.md](../DECISIONS.md))

- The ask-bar placeholder says "ice-ice **reports**" rather than "cases", to stay within the brief's rule against case or outbreak claims.
- Swap the local ask-bar logic for a real assistant API later; `answer()` in `ask.js` is the single place to replace.

### Limitations

- **All 19 markers are unverified leads.** No citation is attached yet. Marker positions are approximate province/region anchors placed on nearby water, **not** farm or sampling coordinates. The UI says this in the list, the detail view, and the credit line.
- The date pills change only a status line. No environmental layer exists yet for any date.
- The globe has no flat-map hand-off yet, so zooming in stops at the globe's minimum altitude.

### Blockers and decisions needed

- Verified citations for the marker locations (see the checklist in [CANDIDATE_HOST_REGIONS.md](../../research/evidence/CANDIDATE_HOST_REGIONS.md)).
- Whether the product uses the three.js globe, the MapLibre globe, or both (globe zoomed out, MapLibre zoomed in).
- Which data feeds the date pills and the "Environmental data" layers.

## Next steps

1. Check the mobile layout at phone sizes and fix any overlap between the date bar, controls, and ask bar.
2. Attach citations to the marker data when the research rows are verified, and show them in the detail card.
3. Connect the first real layer (for example NASA MUR SST) to the layers menu and date pills.
4. Agree on the globe → flat-map hand-off with Radit, possibly reusing the MapLibre prototype for the zoomed-in view.
5. Replace the local ask-bar answers with a backend once one exists.

See [the collaborator context guide](../COLLABORATOR_CONTEXT.md) for shared guidance.
