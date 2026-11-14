# Globe → map hand-off (specification, not built)

**Status 2026-11-15:** a written specification only. No hand-off code exists. It tells whoever builds the flat map how to take over from the globe in [`earth-globe/`](../../earth-globe/) when the user zooms in, and back again when they zoom out. Everything marked *proposal* is untested and not agreed by the team; it is not in [DECISIONS.md](../DECISIONS.md).

## Idea

Zoomed out, the user sees the round Earth (three.js). Zoomed in, the view hands off to the flat map (MapLibre GL JS is the team's recommended map library in [DECISIONS.md](../DECISIONS.md), status *Recommended*). The two are separate canvases that cross-fade. The globe is presentation only: it never shows risk values or the 0.25° grid. Assessed cells, layers and the detail panel live on the map side, so the hand-off must not imply a result on the globe.

## What the globe already provides (verified in the code)

| Need | Globe API |
| --- | --- |
| Where the user is looking | `getView()` → `{ lat, lon, altitude }`, the point under the camera centre |
| Be told when it changes | `on("viewchange", fn)` |
| A clicked place | `on("select", ({ lat, lon }) => …)` (a click, not a drag) |
| Move the camera | `setView({ lat, lon, altitude })` (instant), `flyTo({ lat, lon, altitude, duration })` (returns a promise) |
| Stop the idle spin | `setAutoRotate(false)` (`flyTo` also turns it off) |
| Release GPU memory | `dispose()` |

Facts to design around:

- **Altitude** is in Earth radii above the surface, clamped to 0.15 … 8. The atmosphere is hidden below 0.25 and faded in up to about 0.9.
- The Earth mesh never rotates; the camera orbits. `lat`/`lon` from `getView()` are the point on the surface under the screen centre, and the pitch is whatever OrbitControls allows.
- The camera's vertical field of view is 45° in landscape and **wider in portrait** (the horizontal field is held fixed), so a portrait phone has a different scale at the same altitude.
- The sun is held 59° left of the view, so the focused region can be partly in darkness (see Risks).

## Mapping altitude to map zoom *(proposal; derived by me, not tested against a real map)*

Make the ground scale at the screen centre equal on both sides. On the globe, one pixel at the centre covers about `2 · R · altitude · tan(fov/2) / H` metres, where `R` is the Earth radius, `fov` the camera's vertical field of view and `H` the canvas height in pixels. On a Web Mercator map with 512-pixel tiles, one pixel covers `(40075016.686 / 512) · cos(lat) / 2^zoom` metres. Equating them:

```text
zoom = log2( (40075016.686 / 512) · cos(lat) · H / ( 2 · R · altitude · tan(fov/2) ) )
altitude = (40075016.686 / 512) · cos(lat) · H / ( 2 · R · tan(fov/2) · 2^zoom )
```

Computed with a script (`R` = 6,371,008.8 m, `H` = 800 px, `fov` = 45°). Numbers, not measurements:

| altitude | lat 0° | lat −6.2° (Jakarta) | lat 45° | lat 60° |
| --- | --- | --- | --- | --- |
| 0.15 | 6.31 | 6.30 | 5.81 | 5.31 |
| 0.30 | 5.31 | 5.30 | 4.81 | 4.31 |
| 0.50 | 4.57 | 4.56 | 4.07 | 3.57 |
| 0.75 | 3.98 | 3.98 | 3.48 | 2.98 |
| 1.00 | 3.57 | 3.56 | 3.07 | 2.57 |
| 2.00 | 2.57 | 2.56 | 2.07 | 1.57 |

Sensitivity: at altitude 0.5 and latitude 0 the result is zoom 4.15 for `H` = 600, 4.57 for 800 and 5.00 for 1080. A 587×810 portrait pane (fov about 59.5°) gives 4.12. So read `H` and `fov` from the live canvas and camera, never hard-code them.

Checked only for internal consistency: altitude 0.5 → zoom 4.56 → altitude 0.5000. **Not checked** against a rendered map. Known approximations: it matches the scale at the centre pixel only (perspective makes the edges differ); the globe uses the mean radius while Mercator uses the equatorial one (about 0.1%); and the tile-size convention (512 px) is my assumption about MapLibre, to be confirmed in its documentation.

## Sequence

**Globe → map** (the user zooms in, or clicks a place):

1. Stop the idle spin: `globe.setAutoRotate(false)`.
2. Read `{ lat, lon, altitude }`, canvas height and camera `fov`.
3. Compute the zoom from the formula; set the map to centre `[lon, lat]`, that zoom, bearing 0, pitch 0, **while it is still hidden**.
4. Wait until the map has loaded its tiles for that view (its idle event) before showing it, so the user never sees a blank map.
5. Cross-fade (map in, globe out), then pause or stop rendering the globe. Route pointer input to the map only.

**Map → globe** (the user zooms out): the inverse. Compute the altitude from the map's centre, zoom and the same `H` and `fov`, call `globe.setView(...)`, wait for a frame, cross-fade back, resume the globe.

**Stability:** use hysteresis. Enter the map below one threshold and return only well above it, so a zoom hovering at the boundary does not flicker.

## Proposals still to tune

- Enter the map at altitude ≈ 0.5 (about zoom 4.6 at 800 px and the equator) and return to the globe when the map is below about zoom 4.0. **Untested starting points.**
- Above roughly latitude 80° keep the globe: `cos(lat)` tends to 0 and Web Mercator ends near 85°. The exact limit is not decided.
- The cross-fade duration is not decided.
- Hand-off at 0.5 is already soft: the default albedo is 4096 px wide, so the globe is blurry well before 0.15, which argues for handing off earlier rather than later.

## Risks and open questions

1. **Dark side.** With the sun 59° left of the view, the focused region can be partly dark exactly when the map takes over. A candidate fix, not built: ease the sun toward the viewing direction as altitude drops (see proposal 5 in [README](README.md)).
2. **Visual jump.** The Blue Marble globe and a street or vector basemap look nothing alike. Options: a map style with a satellite-like raster at low zoom, or a longer cross-fade. Not decided.
3. **API gaps in the globe** that the hand-off would need, none built: a way to pause and resume rendering while hidden, a way to read the canvas size and `fov` without reaching into internals, and a sun-easing control.
4. **MapLibre's own globe projection** (from its documentation, not tested here) could replace the two-canvas design with one engine. It would give up the cloud layer, atmosphere and night lights. Not evaluated.
5. **Platform limits:** memory use of the globe on phones is unmeasured (see [README](README.md)); the hand-off should drop globe resources once the map is active if that proves necessary.

## How to check it once built

- Round trip: globe → map → globe returns the same centre within a tolerance **to be chosen**.
- Scale continuity: the distance between two known cities, measured in screen pixels on each side at the switch, should match within a tolerance **to be chosen**. Use at least one city pair at a high latitude.
- Both canvases have the same pixel size and are never interactive at the same time.
- No flicker with the zoom held at the threshold.
- Portrait and landscape both hand off at the same ground scale.
- No assessed cell, risk colour or grid appears on the globe.
