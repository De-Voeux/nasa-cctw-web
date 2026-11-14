# Radit — collaborator context

**Collaborator:** Raditya Aydin

**Last updated:** 2026-11-15

## Responsibility and goal

The 3D **globe overview** for the SEAGIS atlas: when a user zooms out they see a round Earth, and when they zoom in the view should hand off to the flat map. This is presentation only. It does not compute, store or display environmental risk, and it is not part of the assessment pipeline.

Code: [`earth-globe/`](../../earth-globe/) (a self-contained subproject; nothing at the repository root was changed). Module notes: [`earth-globe/src/earth/README.md`](../../earth-globe/src/earth/README.md). Texture provenance: [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md).

## Work completed

- **`EarthGlobe` module** (three.js 0.156.1, plain JavaScript, no framework): albedo, normal/bump, ocean reflection, drifting clouds with cloud shadows, atmosphere rim, optional night lights. Technique adapted from Franky Hung's [Make Your Own Earth in Three.js](https://franky-arkon-digital.medium.com/make-your-own-earth-in-three-js-8b875e281b1e) (code repository [`franky-adl/threejs-earth`](https://github.com/franky-adl/threejs-earth), MIT).
- **Camera behaviour:** auto-rotate on by default; stops on any user interaction; resumes after 5 s idle (configurable, or never). `flyTo` / `setView` / `getView`; `viewchange` and `select` (click returns lat/lon) events; `dispose()`.
- **Coordinate math** in [`geo.mjs`](../../earth-globe/src/earth/geo.mjs) with [8 tests](../../earth-globe/src/earth/geo.test.mjs), including a check against every vertex of `THREE.SphereGeometry`.
- **Demo page** (`earth-globe/src/index.html`, `index.js`) with fly-to buttons, a lat/lon/altitude readout and click-to-coordinate.
- **NASA surface texture:** Blue Marble Next Generation base map (January 2004), 5400×2700, downloaded and checksummed.
- **All eight steps of the article are in place:** albedo, bump map, clouds with cloud shadows, ocean reflection, night lights, atmospheric fresnel, atmosphere shell, and a space background. Bump, clouds, ocean and lights are the article author's processed copies, resized. The background is a 16:9 star-field photo by Logan Voss on Unsplash (credit text supplied by Radit), drawn flat at its own ratio instead of the article's equirectangular Gaia map. Provenance, processing and checksums: [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md).
- **Day and night like the article's demo:** the sun is held 59° to the left of the viewing direction (the article's light at (−50, 0, 30) for a camera at (0, 0, 30)), ambient light is 0, and city lights are on by default with `emissiveIntensity` 3 to make up for the shrunken lights map. The sun follows the camera's orientation, so the globe always shows both a lit side and a dark side however it is rotated.
- **Soft terminator:** the first version had a hard edge to pure black, which looked like two different Earths. `terminatorSoftness` (default 0.3) applies wrap lighting, N·L → (N·L + w)/(1 + w), to the ground and the cloud shell, and city lights now fade in across the dusk band. The side effect is a narrower dark side, because light now reaches about 17° past the old terminator. Set `?softness=0.15` on the demo page for a stronger night.
- `bumpScale` is 0.003: the article's 0.03 was written for a sphere of radius 10, and ours has radius 1.
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
- With the article textures installed: the page reports `ready` with 6 textures loaded, the cloud layer renders, and a production build succeeds. Draw calls: 4, about 55,000 triangles (measured earlier with the Gaia sky).
- Day/night: a terminator is visible with the dark side on the right, and city lights appear on the dark side (Europe, the Middle East, India). Setting `emissiveIntensity` to 3 visibly strengthened them compared with 1; that comparison was by eye on small crops. Sun angle and brightness were not compared numerically against the article's demo.
- Terminator: with `?softness=0` the page reproduces the hard edge reported on 2026-11-15; with 0.3 and 0.15 the edge is gradual (compared on full-size screenshots at the same view, with the Pacific and North America in frame). An attempt to measure edge sharpness from the canvas pixels returned invalid zero readings and was discarded, so this is a visual judgement only. Which value looks best is a taste call; 0.3 is the current default.
- Sky: the 16:9 image is drawn as a flat background (`UVMapping`); with a 1.752 canvas the cover fit crops about 0.7% per side. Only a landscape pane was checked; portrait cropping was computed but not viewed.
- Close-up (altitude 0.4 over the Andes): coastline, albedo, clouds and ocean map line up. The relief shading from the bump map is subtle there and was **not** judged beyond "active".
- `flyTo` to Jakarta (−6.2, 106.8) arrives exactly at the target in about 1.2 s. A click at the exact screen centre returns (−6.2, 106.8).
- Auto-rotate stops on interaction, resumes after about 5 s, and stays off when disabled explicitly. Checked two ways: by dispatching the controls' own `start`/`end` events, and with a real drag and a real wheel scroll in the in-app browser (drag stopped the rotation and did not fire `select`; rotation resumed after about 7 s idle; scrolling zoomed in and also stopped the rotation). The size of the rotation per drag was **not** verified: a 100-pixel drag moved the longitude by only 11°, which I could not explain.
- `dispose()` takes geometries 3→0, textures 4→0, canvases 1→0, and is safe to call twice.
- Orientation was checked visually (India right of Africa, Australia south of Indonesia).

**Not tested:** touch devices and pinch, low-end GPUs and memory use on phones, Safari and Firefox, and any integration with the root `index.html`.

## Assumptions, limitations, and blockers

### Working decisions (made in chat, 2026-11-14)

- Use three.js for the globe, rather than MapLibre's built-in globe projection.
- Keep the starter's toolchain (Parcel + JavaScript) rather than Vite + TypeScript.
- The Earth mesh never rotates or tilts; the camera orbits. Lat/lon ↔ world conversion is therefore time-invariant.
- 2026-11-15: kept the orbiting camera with the sun locked to the camera and an upright axis. Considered and not done: rotating the Earth with a fixed camera (looks identical while the sun is camera-locked), a world-fixed sun like the article's demo (day and night change as you orbit, and the focused region can end up dark, which hurts a map hand-off), and a 23.5° axial tilt.

### Proposals (not in [DECISIONS.md](../DECISIONS.md); the team has not agreed to these)

1. Adopt the globe as the zoom-out view, with a hand-off to the flat map. The library already hides the atmosphere shell below altitude 0.25 Earth radii, which is a natural hand-off point. The hand-off itself is **not built**.
2. Auto-rotate resuming after 5 s idle is a default I chose; it was not specified.
3. MapLibre GL JS 5+ has a built-in globe projection (from search results, not tested by us). It remains the fallback if a single-engine globe-to-map transition is preferred.
4. Serve large Blue Marble resolutions as tiles rather than one huge texture. Untested.
5. Because the sun is fixed relative to the camera at 59°, the region the user focuses on can sit partly in darkness. That reads well for an overview but is a problem at the map hand-off. A possible fix is to ease the sun toward the viewing direction as altitude drops. Not built.

### Limitations

- **Only the albedo is a pristine NASA file.** The other textures are the article author's edited copies (e.g. "darkened", "modified"), resized by us. The README of his repository attributes them to NASA and ESA and says they may require attribution. The sky photo is credited to Logan Voss on Unsplash (credit text supplied by Radit); I did not check that the file matches that photo or read the Unsplash licence. Do not publish before the licences are resolved and the credits are in place (the demo page already shows the NASA, article and sky credits).
- **Git history:** the first commit of this folder (`16c8a1a`, 2026-11-14) contains the three.js example textures used as placeholders (`normal.jpg`, `ocean.jpg`, `clouds.png`, `lights.png`; licence never checked). They were replaced in the next commit but remain in the history; removing them would mean rewriting shared history, which is a team decision.
- The albedo is a static monthly composite. It is a background image, **not** a NASA data product used by SEAGIS. It does not satisfy the "use NASA data meaningfully" requirement in [README](../../README.md) and [ROADMAP](../ROADMAP.md).
- The 0.25° assessment grid is not drawn on the globe, and the globe shows no risk values.
- A 5400×2700 texture is about 58 MB of GPU memory before mipmaps, and some older devices cap textures at 4096. The 4096 version is the default.
- The default configuration loads albedo, ocean mask, clouds and city lights at 4096×2048, bump at 2048×1024, and the 7680×4320 sky. My estimate (4 bytes per pixel, not measured) is about 275 MB of GPU memory, about 320 MB with mipmaps, and the sky alone is about 133 MB of that. That is likely too much for low-end phones, and there is no reduced-quality mode yet. Downscaling the sky (a star field tolerates it well, but I have not tried) to 3840×2160 would cut it to roughly a quarter. The sky loads after the globe is ready, so it does not delay first render.

### Blockers and decisions needed

- Which Space Apps challenge, and whether Blue Marble is on its official Resources tab (open decision 1 in [DECISIONS.md](../DECISIONS.md)). Do not claim it as a challenge resource until confirmed.
- Credit and licence wording for NASA imagery. The NASA download page states no licence; NASA's requested credit "NASA Earth Observatory" came from a search summary and is not yet confirmed on an official page.
- Pristine NASA originals for clouds, elevation, the ocean mask and city lights could not be reached (details in [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md)); we use the article author's copies instead.
- How the bundle is shipped into the static root site, which currently has no build step.

## Next steps

1. Decide whether the globe belongs in the product (proposal 1) and record it in [DECISIONS.md](../DECISIONS.md) if so.
2. Build the globe → flat-map hand-off (altitude and centre → map zoom and centre), as a pure, tested function.
3. Confirm credit and licence wording for NASA and ESA/Gaia, and add a reduced-quality mode (skip clouds and sky, smaller textures) for phones.
4. Decide how the root static site loads the built globe bundle.
5. Test on touch devices and a low-end GPU before relying on the 4096 default.

See [the collaborator context guide](../COLLABORATOR_CONTEXT.md) for shared guidance.
