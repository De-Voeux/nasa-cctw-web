# EarthGlobe

A framework-free three.js Earth (albedo, normal/bump, ocean reflection, drifting
clouds with shadows, atmosphere rim, optional night lights). Built from the
technique in Franky Hung's ["Make Your Own Earth in Three.js"](https://franky-arkon-digital.medium.com/make-your-own-earth-in-three-js-8b875e281b1e)
(MIT code, `franky-adl/threejs-earth`), adapted for a map/atlas use case.

```js
import { EarthGlobe } from "./earth/EarthGlobe.js"

const globe = new EarthGlobe(containerEl, {
  textures: { albedo, normal, ocean, clouds /* , lights, sky, bump */ },
  cloudsFormat: "alpha", // "luminance" for NASA Blue Marble cloud maps
})
globe.on("viewchange", ({ lat, lon, altitude }) => {})
globe.on("select", ({ lat, lon }) => {})        // click, not drag
await globe.flyTo({ lat: -6.2, lon: 106.8, altitude: 0.6 })
globe.setAutoRotate(false)
globe.dispose()
```

## Conventions

- **Altitude** is in Earth radii above the surface (`0` = surface, `1` = one
  radius up). Clamped to `minAltitude`..`maxAltitude` (default 0.15..8).
- **The Earth mesh never rotates or tilts.** Auto-rotate and dragging move the
  camera, so lat/lon <-> world conversion (`geo.mjs`) is time-invariant.
  `npm test` checks it against every vertex of `THREE.SphereGeometry`.
- **Auto-rotate** is on by default, stops on any interaction, and resumes after
  5 s idle (`autoRotate.resumeAfterMs`, `null` = never). `flyTo` turns it off.
  `prefers-reduced-motion` disables it and the cloud drift.
- **Atmosphere** fades out below altitude ~0.9 and is hidden below 0.25
  (the camera would otherwise sit inside the glow shell). This is also roughly
  where a hand-off to a flat map should happen.
- **Lighting** reproduces the article's demo: the sun is a fixed angle (59° to the
  left, `sunAzimuth`) from the viewing direction, so the globe always shows a day
  side and a night side with city lights, however the user rotates. `ambient` is 0,
  so the night side is black apart from lights and the atmosphere. `lighting:
  "fixed"` pins the sun in world space instead. `terminatorSoftness` (default 0.3)
  widens the dusk band: stock three.js clamps N·L to 0 exactly at the terminator,
  which gave a hard edge to pure black ("two different Earths"). It uses wrap
  lighting, N·L → (N·L + w) / (1 + w), on the ground and the cloud shell, and
  city lights fade in across the dusk band. 0 restores the hard edge. Try
  `?softness=0.15` or `?ambient=0.03` on the demo page. The focused region can end up on
  the dark side, which matters for a map hand-off (see `docs/Radit/README.md`).

## Textures

Textures are passed in by URL; none are bundled in the module.

`src/assets/earth/` in this repo:

| File | Source | Status |
|---|---|---|
| `albedo-5400.jpg` | NASA Blue Marble Next Generation, base map, January 2004, 5400x2700, unmodified | NASA |
| `albedo.jpg` | same file resized to 4096x2048 (`sips -z 2048 4096`) | NASA |
| `bump.jpg`, `clouds.jpg`, `ocean.png`, `lights.png` | the article author's processed copies (`franky-adl/threejs-earth`, `src/assets`), resized | NASA via the article |
| `sky.jpg` | 7680×4320 (16:9) star field, used as is | Photo by Logan Voss on Unsplash (credit supplied by the project owner; match and licence not verified) |

Albedo origin: `https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/january/world.200401.3x5400x2700.jpg`
(page: https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map).
The page states no licence; NASA asks for the credit "NASA Earth Observatory"
(not confirmed on the official page). Credit it wherever the globe is shown.
Use the 4096 file by default; 5400 is for desktop (about 58 MB of GPU memory
uncompressed, and some older devices cap textures at 4096).

Do not use the "topography/bathymetry" Blue Marble variant as albedo: its relief
shading is baked in and would double up with a normal/bump map.

The original NASA and ESA pages behind those files could not be reached on
2026-11-14 (`eoimages.gsfc.nasa.gov` timed out, Visible Earth pages redirect), so
pristine originals are not in this repo. Full provenance, checksums and licence
notes: `docs/Radit/TEXTURE_SOURCES.md` in the repository root.

These cloud maps store density as brightness: pass `cloudsFormat: "luminance"`.
`bumpScale` is 0.003, the article's 0.03 scaled for a radius-1 sphere.
`nightLightsIntensity` is 3 because the lights map was shrunk to 4096×2048 (the
article's is 16384×8192) and its points of light dim; use 1 with the full map.

`sky` keeps its own proportions. A 2:1 image is wrapped around the viewer as an
equirectangular map; any other ratio (the current 16:9 one) is a flat backdrop that
covers the canvas, cropped evenly and never stretched. It loads after `ready`.
7680×4320 is about 133 MB decoded (estimate); three.js shrinks images larger than the
GPU's texture limit.
