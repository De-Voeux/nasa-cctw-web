#!/bin/sh
# Build the deployable bundle into dist/site:
#   /        the static shell (index.html, styles.css, app.js)
#   /globe/  the three.js globe demo (earth-globe, built with Parcel)
# docs/, research/ and contracts/ are deliberately NOT deployed: they are internal
# team notes. The site is also marked noindex while it is research-stage.
set -eu
cd "$(dirname "$0")/.."

OUT=dist/site
rm -rf "$OUT"
mkdir -p "$OUT/globe"

cp index.html styles.css app.js "$OUT/"

# Needs `npm install` once inside earth-globe/. --public-url ./ keeps asset paths
# relative so the demo works under /globe/.
(cd earth-globe && npx parcel build src/index.html --dist-dir "../$OUT/globe" --public-url ./ --no-source-maps --no-cache)

printf 'User-agent: *\nDisallow: /\n' > "$OUT/robots.txt"
printf '/*\n  X-Robots-Tag: noindex, nofollow\n' > "$OUT/_headers"

echo "Built $OUT"
du -sh "$OUT"
