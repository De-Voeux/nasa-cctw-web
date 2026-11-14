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
- **Lighting** defaults to a camera-attached headlight so the visible hemisphere
  is always lit. Night lights therefore never show unless `lighting: "fixed"`.

## Textures

Textures are passed in by URL; none are bundled in the module.

`src/assets/earth/` in this repo:

| File | Source | Status |
|---|---|---|
| `albedo-5400.jpg` | NASA Blue Marble Next Generation, base map, January 2004, 5400x2700, unmodified | NASA |
| `albedo.jpg` | same file resized to 4096x2048 (`sips -z 2048 4096`) | NASA |
| `normal.jpg`, `ocean.jpg`, `clouds.png`, `lights.png` | three.js examples (`examples/textures/planets/`: `earth_normal_2048`, `earth_specular_2048`, `earth_clouds_1024`, `earth_lights_2048`) | **placeholder**, licence not checked |

Albedo origin: `https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/january/world.200401.3x5400x2700.jpg`
(page: https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map).
The page states no licence; NASA asks for the credit "NASA Earth Observatory"
(not confirmed on the official page). Credit it wherever the globe is shown.
Use the 4096 file by default; 5400 is for desktop (about 58 MB of GPU memory
uncompressed, and some older devices cap textures at 4096).

Do not use the "topography/bathymetry" Blue Marble variant as albedo: its relief
shading is baked in and would double up with a normal/bump map.

The other sources listed in `franky-adl/threejs-earth` (NASA Visible Earth / SVS,
ESA Gaia) could not be downloaded on 2026-11-14: `eoimages.gsfc.nasa.gov` timed
out and the Visible Earth pages now redirect. NASA cloud map: only an Internet
Archive copy of `cloud_combined_2048.jpg` was found (item `VE-IMG-2432`). No NASA
grayscale elevation map, ocean mask or city-lights file was located.
