# Globe texture sources

**Last checked:** 2026-11-14. Files are in [`earth-globe/src/assets/earth/`](../../earth-globe/src/assets/earth/).

## Files in the repository

| File | Origin | Bytes | SHA-256 | Status |
| --- | --- | --- | --- | --- |
| `albedo-5400.jpg` | NASA Blue Marble Next Generation, base map, January 2004, 5400×2700, unmodified | 1,884,678 | `99f5faad74efe985fbf1714c8be7296ca9999759a1215b65f99b7f1df278dde5` | NASA |
| `albedo.jpg` | Same file resized to 4096×2048 with `sips -z 2048 4096 -s format jpeg -s formatOptions 88` | 1,534,808 | `296416edd560df899f85666bd8d3b8963fcad4ed694966eb236643cd5036d940` | NASA (derived) |
| `normal.jpg` | three.js examples, `earth_normal_2048.jpg` | 336,774 | `3fc43e9639c34e8223c4a871e3bdf5b2d52ee79f7e89ce3f28cba45d4cac031a` | **placeholder**, licence not checked |
| `ocean.jpg` | three.js examples, `earth_specular_2048.jpg` | 223,421 | `2df48906732d7a458b2d0a7cdec51a829262307c6bdee4cfdf079a4dd7c71c69` | **placeholder**, licence not checked |
| `clouds.png` | three.js examples, `earth_clouds_1024.png` (cloud density in the alpha channel) | 226,113 | `5f9612e4f4040975a195dd0d14e89c9ba72bd6bdd22e1454db4fcefb92d37d38` | **placeholder**, licence not checked |
| `lights.png` | three.js examples, `earth_lights_2048.png` | 410,160 | `0564fa57f5fade2f65e56d3ad59b3c6bf5e32c44f60370a3e46fd367b0cabaee` | **placeholder**, licence not checked |

Placeholders were fetched from `https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/planets/`.

## NASA albedo (verified facts)

- Page: <https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map> (the old `visibleearth.nasa.gov` page returns a 301 redirect to it).
- File: `https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/january/world.200401.3x5400x2700.jpg`. An HTTP `HEAD` request returned 200 and `content-length: 1884678`; the downloaded file is a valid 5400×2700 JPEG of the same size.
- Pattern: `bmng-base/{month}/world.2004{MM}.3x{size}.jpg`, twelve months. Sizes listed on the page: 5400×2700, 21600×10800 (about 23.7 MB, checked by `HEAD`), and sixteen 21600×21600 tiles per month.
- The page shows **no credit or licence line**. NASA's requested credit "NASA Earth Observatory" came from a search summary; confirm it on an official page before relying on it.
- Do not use the "topography and bathymetry" variant as albedo: its relief shading is baked in and doubles up with a normal or bump map.
- The page does not say whether sea ice is included.

## Not found (do not assume these exist)

- The URLs in `franky-adl/threejs-earth`'s README no longer work: `eoimages.gsfc.nasa.gov` timed out, and Visible Earth image pages now redirect to generic Earth Observatory pages. `svs.gsfc.nasa.gov/vis/a000000/a003400/a003487/` returned 404.
- **Clouds:** only an Internet Archive copy of `cloud_combined_2048.jpg` was found ([item VE-IMG-2432](https://archive.org/details/VE-IMG-2432)). A cloud map at [shadedrelief.com](https://www.shadedrelief.com/natural3/pages/clouds.html) is derived from NASA data but is not NASA's; its page returned HTTP 403 to our fetch, so its licence is unread.
- **Elevation or bump map, ocean mask, city lights:** no working NASA download located. Wikimedia Commons has a 2160×1080 NASA-derived elevation PNG described as public domain; this has not been verified.
- ESA Gaia sky map (from the original article): not checked.
