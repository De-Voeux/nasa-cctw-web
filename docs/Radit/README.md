# Radit — collaborator context

**Collaborator:** Raditya Aydin

**Last updated:** 2026-11-14

## Responsibility and goal

The 3D **globe overview** for the SEAGIS atlas: when a user zooms out they see a round Earth, and when they zoom in the view should hand off to the flat map. This is presentation only. It does not compute, store or display environmental risk, and it is not part of the assessment pipeline.

Code: [`earth-globe/`](../../earth-globe/) (a self-contained subproject; nothing at the repository root was changed). Module notes: [`earth-globe/src/earth/README.md`](../../earth-globe/src/earth/README.md). Texture provenance: [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md).

## Work completed

- **`EarthGlobe` module** (three.js 0.156.1, plain JavaScript, no framework): albedo, normal/bump, ocean reflection, drifting clouds with cloud shadows, atmosphere rim, optional night lights. Technique adapted from Franky Hung's [Make Your Own Earth in Three.js](https://franky-arkon-digital.medium.com/make-your-own-earth-in-three-js-8b875e281b1e) (code repository [`franky-adl/threejs-earth`](https://github.com/franky-adl/threejs-earth), MIT).
- **Camera behaviour:** auto-rotate on by default; stops on any user interaction; resumes after 5 s idle (configurable, or never). `flyTo` / `setView` / `getView`; `viewchange` and `select` (click returns lat/lon) events; `dispose()`.
- **Coordinate math** in [`geo.mjs`](../../earth-globe/src/earth/geo.mjs) with [8 tests](../../earth-globe/src/earth/geo.test.mjs), including a check against every vertex of `THREE.SphereGeometry`.
- **Demo page** (`earth-globe/src/index.html`, `index.js`) with fly-to buttons, a lat/lon/altitude readout and click-to-coordinate.
- **NASA surface texture:** Blue Marble Next Generation base map (January 2004), 5400×2700, downloaded and checksummed. See [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md).
- Portrait screens: the horizontal field of view is held fixed so the globe is not cropped on phones.

## Current status and review steps

```bash
cd earth-globe
npm install
npm test          # 8 tests, node:test, no browser needed
npm start         # http://localhost:1235
```

**Verified on 2026-11-14** (Chromium-based in-app browser, desktop, narrow and wide panes):

- `npm test`: 8/8 pass. `parcel build` succeeds. No console errors from the library.
- Surface texture loads at 4096×2048; the page credits NASA Earth Observatory.
- `flyTo` to Jakarta (−6.2, 106.8) arrives exactly at the target in about 1.2 s. A click at the exact screen centre returns (−6.2, 106.8).
- Auto-rotate stops on interaction, resumes after about 5 s, and stays off when disabled explicitly. This was exercised by dispatching the controls' own `start`/`end` events, not with real mouse drags.
- `dispose()` takes geometries 3→0, textures 4→0, canvases 1→0, and is safe to call twice.
- Orientation was checked visually (India right of Africa, Australia south of Indonesia).

**Not tested:** touch devices, low-end GPUs, Safari and Firefox, real drag gestures, and any integration with the root `index.html`.

## Assumptions, limitations, and blockers

### Working decisions (made in chat, 2026-11-14)

- Use three.js for the globe, rather than MapLibre's built-in globe projection.
- Keep the starter's toolchain (Parcel + JavaScript) rather than Vite + TypeScript.
- The Earth mesh never rotates or tilts; the camera orbits. Lat/lon ↔ world conversion is therefore time-invariant.

### Proposals (not in [DECISIONS.md](../DECISIONS.md); the team has not agreed to these)

1. Adopt the globe as the zoom-out view, with a hand-off to the flat map. The library already hides the atmosphere shell below altitude 0.25 Earth radii, which is a natural hand-off point. The hand-off itself is **not built**.
2. Auto-rotate resuming after 5 s idle is a default I chose; it was not specified.
3. MapLibre GL JS 5+ has a built-in globe projection (from search results, not tested by us). It remains the fallback if a single-engine globe-to-map transition is preferred.
4. Serve large Blue Marble resolutions as tiles rather than one huge texture. Untested.

### Limitations

- **Four of the five textures are placeholders** (normal, ocean, clouds, city lights) from the three.js examples. Their licence has not been checked; do not publish them as they are.
- The albedo is a static monthly composite. It is a background image, **not** a NASA data product used by SEAGIS. It does not satisfy the "use NASA data meaningfully" requirement in [README](../../README.md) and [ROADMAP](../ROADMAP.md).
- The 0.25° assessment grid is not drawn on the globe, and the globe shows no risk values.
- A 5400×2700 texture is about 58 MB of GPU memory before mipmaps, and some older devices cap textures at 4096. The 4096 version is the default.

### Blockers and decisions needed

- Which Space Apps challenge, and whether Blue Marble is on its official Resources tab (open decision 1 in [DECISIONS.md](../DECISIONS.md)). Do not claim it as a challenge resource until confirmed.
- Credit and licence wording for NASA imagery. The NASA download page states no licence; NASA's requested credit "NASA Earth Observatory" came from a search summary and is not yet confirmed on an official page.
- NASA sources for the cloud map, an elevation/bump map, an ocean mask and city lights were not found at working URLs (details in [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md)).
- How the bundle is shipped into the static root site, which currently has no build step.

## Next steps

1. Decide whether the globe belongs in the product (proposal 1) and record it in [DECISIONS.md](../DECISIONS.md) if so.
2. Build the globe → flat-map hand-off (altitude and centre → map zoom and centre), as a pure, tested function.
3. Replace or drop the placeholder textures; confirm NASA credit wording.
4. Decide how the root static site loads the built globe bundle.
5. Test on touch devices and a low-end GPU before relying on the 4096 default.

See [the collaborator context guide](../COLLABORATOR_CONTEXT.md) for shared guidance.
