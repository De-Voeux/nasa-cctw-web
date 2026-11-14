#!/bin/sh
# Build the deployable bundle into dist/site:
#   /       the SEAmon dashboard on the three.js globe (earth-globe/src/index.html)
#   /demo   the plain globe demo (earth-globe/src/demo.html)
# Both are built with Parcel from earth-globe. The old static starter page in the
# repository root (index.html, styles.css, app.js) is NOT deployed any more.
# docs/, research/ and contracts/ are deliberately NOT deployed: they are internal
# team notes. The site is also marked noindex while it is research-stage.
set -eu
cd "$(dirname "$0")/.."

OUT=dist/site
rm -rf "$OUT"
mkdir -p "$OUT"

# Needs `npm install` once inside earth-globe/. --public-url ./ keeps asset paths relative.
(cd earth-globe && npx parcel build src/index.html src/demo.html --dist-dir "../$OUT" --public-url ./ --no-source-maps --no-cache)

# Link-preview image at a fixed, unhashed URL: https://seamon.seagis.app/og-image.png
# (the og:image tag in earth-globe/src/index.html points here). Parcel would hash the
# name, so copy it after the build.
cp earth-globe/src/assets/earth/ogimage-nasa.png "$OUT/og-image.png"

# The dashboard used to live at /globe/. Send the old addresses to their new homes.
# Rules are matched top to bottom, so the specific ones come first.
cat > "$OUT/_redirects" <<'REDIRECTS'
/globe/demo.html /demo 301
/globe/demo /demo 301
/globe/ / 301
/globe / 301
REDIRECTS

# Search engines are kept out, but link-preview crawlers must be allowed to read the page
# and og:image, or no preview card appears. The crawler names below are from general
# knowledge and have not been tested against each platform.
cat > "$OUT/robots.txt" <<'ROBOTS'
User-agent: Twitterbot
User-agent: facebookexternalhit
User-agent: LinkedInBot
User-agent: Slackbot
User-agent: Discordbot
User-agent: WhatsApp
User-agent: TelegramBot
Allow: /

User-agent: *
Disallow: /
ROBOTS
printf '/*\n  X-Robots-Tag: noindex, nofollow\n' > "$OUT/_headers"

echo "Built $OUT"
du -sh "$OUT"
