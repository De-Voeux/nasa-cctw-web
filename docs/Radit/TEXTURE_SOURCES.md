# Globe texture sources

**Last checked:** 2026-11-14. Files are in [`earth-globe/src/assets/earth/`](../../earth-globe/src/assets/earth/).

The globe follows Franky Hung's article [Make Your Own Earth in Three.js](https://franky-arkon-digital.medium.com/make-your-own-earth-in-three-js-8b875e281b1e). Except for the albedo and the sky, the textures are the article author's **processed copies**, taken from his repository, not pristine NASA files. `sky.jpg` was first the article's ESA Gaia map (resized by us), then replaced by a photo supplied by Radit (credited below); the Gaia version is no longer in the repository.

## Files in the repository

| File | Origin | Processing | SHA-256 of the file as stored |
| --- | --- | --- | --- |
| `albedo-5400.jpg` | NASA Blue Marble Next Generation, base map, January 2004, 5400×2700 | none | `99f5faad74efe985fbf1714c8be7296ca9999759a1215b65f99b7f1df278dde5` |
| `albedo.jpg` | same NASA file | resized to 4096×2048, JPEG q88 (`sips`) | `296416edd560df899f85666bd8d3b8963fcad4ed694966eb236643cd5036d940` |
| `bump.jpg` | `Bump.jpg` (10800×5400 grayscale JPEG, 2,322,957 B) | resized to 2048×1024, JPEG q90 | `beb2512e85f334e7ed19d2bcd251fbcad35cec4d74de9735d18d0a51139fc478` |
| `clouds.jpg` | `Clouds.png` (4096×2048 RGB PNG, 8,151,461 B; density stored as brightness) | converted to JPEG q90 (lossy) | `a4f0526702c4cc71cdd0f37915af82e4e65c134f3ccaee593413f78b672ff967` |
| `ocean.png` | `Ocean.png` (4096×2048 RGBA PNG, 688,779 B; white = ocean, black = land) | none | `6077b48f263abf05eefb4bbcc4cc7ea283f2e7b85d130d8b83760246672da65f` |
| `lights.png` | `night_lights_modified.png` (16384×8192 grayscale PNG, 1,422,842 B) | resized to 4096×2048 | `62d15219756a9c9cf5abd40c515a0ce6a80d7a7fa15c4046601717db3a8be0df` |
| `sky.jpg` | **Supplied by Radit**: replaced the file at 23:42 on 2026-11-14; 7680×4320 JPEG, 1,250,737 B, 16:9. Photo by Logan Voss on Unsplash (credit below). | used as is, drawn as a flat backdrop at its own ratio | `dfa51427e2ae10bafb88970a572d99e400b1bd58652082583abf8add0a084bb9` |

Originals were downloaded from `https://raw.githubusercontent.com/franky-adl/threejs-earth/main/src/assets/<name>` (repository default branch `main`, licence MIT per the GitHub API, last push 2023-10-08). Sizes match the GitHub API listing, so these are real files, not Git LFS pointers. SHA-256 of the downloaded originals:

```text
f7ec42f918103153db25e73625a26cb91ded40c2f377c73be3c61fc9a9122d76  Bump.jpg
a56549cce821ca0beb541cc92a83d26dadc3444f91545eb1c7d934daa942bbc6  Clouds.png
6077b48f263abf05eefb4bbcc4cc7ea283f2e7b85d130d8b83760246672da65f  Ocean.png
352560d87304b3e4482f8857c5e27cbd7b96ebf603c90c3bd56bf184309def9b  night_lights_modified.png
60773f3a608cf12a44d00256542f023179e593a893099a1da73ccc134ab70531  Gaia_EDR3_darkened.png
```

The originals were resized before use because browsers decode images to about 4 bytes per pixel: a 16384×8192 texture would take roughly 512 MB, and many GPUs cap textures at 8192 or 4096.

## Provenance and licence

**Verified**

- The NASA albedo: page <https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map>; file `https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/january/world.200401.3x5400x2700.jpg`. An HTTP `HEAD` returned 200 and `content-length: 1884678`, matching the download. The old `visibleearth.nasa.gov` page returns a 301 redirect to it.
- The page shows **no credit or licence line**. The credit "NASA Earth Observatory" came from a search summary and is not yet confirmed on an official page.
- Pattern `bmng-base/{month}/world.2004{MM}.3x{size}.jpg`; the 21600×10800 version is about 23.7 MB (checked by `HEAD`).
- Do not use the "topography and bathymetry" variant as albedo: its relief shading is baked in and doubles up with a bump map.
- Channel semantics were checked on previews: ocean white over water; clouds grayscale; bump grayscale; lights grayscale on black.

**Reported by the article's repository README, not verified by us:** the images come from NASA Visible Earth and NASA SVS (visualization 3487 for the ocean map) and ESA Gaia; the README says they "may require attribution" and points to the original pages. The article says they are "mostly from NASA and ESA" and tells readers to check the licences.

**Sky credit (supplied by Radit, 2026-11-14):** Photo by [Logan Voss](https://unsplash.com/@loganvoss?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText) on [Unsplash](https://unsplash.com/photos/a-dark-sky-filled-with-countless-tiny-stars-sOvC2p6seUc?utm_source=unsplash&utm_medium=referral&utm_content=creditCopyText). The demo page shows this credit, with these links.

**Not checked:** that the file in the repository is that photo (the credit text came from Radit; I did not compare images), the terms of the Unsplash licence (not read in this session), and whether the article author's "darkened" and "modified" edits change the terms of the other textures. Credit NASA, the article's repository and the sky photo wherever the globe is shown, and resolve the licences before publishing.

## Could not be reached

- The original NASA pages and URLs listed in that README: `eoimages.gsfc.nasa.gov` timed out, Visible Earth image pages redirect to generic pages, and `svs.gsfc.nasa.gov/vis/a000000/a003400/a003487/` returned 404. Pristine NASA originals for clouds, elevation, ocean and city lights are therefore not in this repository.
- `shadedrelief.com` (Natural Earth cloud and land/water masks): the site shows a bot-verification page, so it was not read or used.
- An Internet Archive copy of NASA's `cloud_combined_2048.jpg` exists ([item VE-IMG-2432](https://archive.org/details/VE-IMG-2432)); it was not downloaded.
