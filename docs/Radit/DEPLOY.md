# Deployment (Cloudflare Worker)

**First deployed 2026-11-15**, as a new Cloudflare Worker, `seagis-atlas`, serving static assets. The custom domain `nasa.seagis.app` was attached the same day, and later that day it was replaced by `seamon.seagis.app` (see "Domain change").

| | |
| --- | --- |
| Address | <https://seamon.seagis.app> |
| Globe demo | <https://seamon.seagis.app/demo> (the address `/demo.html` redirects here) |
| Previous addresses | `nasa.seagis.app` (replaced the same day; no DNS record any more), `seagis-atlas.radityaaydin.workers.dev` (disabled) |
| `workers.dev` address | **disabled** (see below) |
| Current version ID | `e40b07c9-b7f8-4c8f-8dd6-61a1f773d71c` (deployed by CI, 2026-11-15 18:10 UTC). Earlier: `d606caa5-c27b-4159-9de4-07b2fa06d87a` (manual, custom domain added), `f2fef4e9-4a68-41db-9917-5c8a53cb3164` (first, manual) |
| Account | the personal Cloudflare account of the repository owner (not the "Cendana" account that is also on that login) |
| Config | [`wrangler.jsonc`](../../wrangler.jsonc) |
| Build | [`scripts/build-site.sh`](../../scripts/build-site.sh) |
| CI/CD | [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) (working since the third attempt of the first run, 2026-11-15; see "CI/CD") |

## Domain change (2026-11-15)

- Radit changed the custom domain from `nasa.seagis.app` to **`seamon.seagis.app`** (the product is called SEAmon). I did not make that change and was not told how it was done (the Cloudflare dashboard or something else).
- Observed afterwards: Cloudflare's own nameservers answer `NXDOMAIN` for `nasa.seagis.app`, so the old address is gone. `seamon.seagis.app` resolves to Cloudflare addresses and returns 200 with the Worker's `X-Robots-Tag: noindex, nofollow`, the root page and the dashboard at `/globe/`.
- That live copy still had the old `robots.txt` (disallow everything) and no Open Graph tags, because the Open Graph change had not been deployed when it was checked.
- `wrangler.jsonc` on `main` still said `nasa.seagis.app` when this was found, so the next CI deploy would have tried to attach that name again. It now says `seamon.seagis.app`; the hostnames in the Open Graph tags, `scripts/build-site.sh` and the workflow comment were changed to match. This was a local change at the time of writing, not yet pushed. Where later sections record what was checked on `nasa.seagis.app`, that is history and is left as it was.

## What is deployed

- `/` — **the dashboard on the globe** (`earth-globe/src/index.html`; Eileen's pull request #1). It used to be at `/globe/`; the old static starter page that was at `/` (`index.html`, `styles.css`, `app.js` in the repository root) is **no longer deployed**. Those three files are still in the repository, untouched by the move; editing them no longer changes the site.
- `/demo` — the plain globe demo (`earth-globe/src/demo.html`).
- `/globe/`, `/globe`, `/globe/demo` and `/globe/demo.html` redirect (301) to `/` or `/demo` through a `_redirects` file written by the build, so links made while the dashboard lived at `/globe/` keep working. Not yet verified live; Cloudflare's static-assets redirect support is from its documentation, not from a test here.
- Both pages are built from `earth-globe/` with Parcel (the dashboard was merged and first deployed by CI on 2026-11-15). The dashboard pins 19 places from `research/evidence/CANDIDATE_HOST_REGIONS.md` ("unverified leads"), compiled into the public JavaScript bundle (`earth-globe/src/data/reportedLocations.js`). The page labels them unverified, but they are no longer kept out of the public site the way `research/` is. The built dashboard page was checked locally to load 19 pins and no cloud layer; the live bundle was not re-checked for the pin data.
- `/robots.txt` (disallow all) and an `X-Robots-Tag: noindex, nofollow` header on every response, because the site is research-stage and some texture licences are unresolved.

**Not deployed on purpose:** `docs/`, `research/`, `contracts/`. They are internal team notes, including unverified research leads. Nothing links to the demo from the dashboard yet.

## Custom domain

- `seagis.app` uses Cloudflare nameservers (`aisha.ns.cloudflare.com`, `ethan.ns.cloudflare.com`, from a DNS lookup), and the zone is in the same account as the Worker: the deploy was accepted. A lookup before the deploy showed no existing records for `nasa.seagis.app`, so nothing was overwritten.
- `wrangler.jsonc` now has `routes: [{ "pattern": "seamon.seagis.app", "custom_domain": true }]` (it said `nasa.seagis.app` until the domain change; see below). On the first deploy with `nasa.seagis.app`, Cloudflare created the DNS records itself.
- **`workers.dev` is now off.** Wrangler disables the `*.workers.dev` address and preview URLs by default once `routes` is set, and printed a warning to that effect. The old address, `seagis-atlas.radityaaydin.workers.dev`, returned 404 afterwards. `workers_dev` and `preview_urls` are now written out as `false` in `wrangler.jsonc` so no deploy changes them silently. Set `"workers_dev": true` to bring the address back.

Verified on 2026-11-15 after the deploy:

- `https://nasa.seagis.app/` and `/globe/` return 200 with a valid certificate; `/robots.txt` returns 200; `/docs/Radit/README.md` returns 404; the noindex header is present; the response comes from Cloudflare.
- DNS returns A and AAAA records for `nasa.seagis.app` (Cloudflare addresses, as expected for a proxied hostname).
- In Chrome on `https://nasa.seagis.app/globe/` the page loaded over HTTPS, the globe reported `ready` with the NASA surface (4096×2048), the 7680×4320 sky, the day/night side, and a credit footer whose two links point to the Unsplash photographer and photo. The console showed one error, `Could not establish connection. Receiving end does not exist`, whose wording is typical of a browser-extension messaging failure rather than the page's own code; that is my guess and I did not confirm it. The same check on the first address had shown no console errors.

## Link previews (Open Graph image)

Added 2026-11-15, **built and checked locally, not yet deployed**.

- The asset is `earth-globe/src/assets/earth/ogimage.png` (supplied by Radit, replaced on 2026-11-15 by a new version that reads "SEAmon · Created for the 2026 NASA Space Apps Challenge" over the globe): 1200×457 px, PNG, 430,791 bytes. `scripts/build-site.sh` copies it, byte for byte, to `/og-image.png` (a fixed address, because Parcel would hash the name).
- The tags live in the dashboard page, `earth-globe/src/index.html`, which is now the site root: 10 `og:*` tags and 5 `twitter:*` tags (card type `summary_large_image`), plus the page title and a description. They were first on the old static root page and were moved here when the dashboard became `/`. The image address is absolute, `https://seamon.seagis.app/og-image.png`, as the protocol requires (it was `nasa.seagis.app` until the domain change). The demo page has no tags.
- **`robots.txt` changed.** It used to disallow every robot, which would also stop link-preview crawlers from reading the page and the image. It now allows Twitterbot, facebookexternalhit, LinkedInBot, Slackbot, Discordbot, WhatsApp and TelegramBot, and still disallows everything else (checked with Python's robots parser: those seven may fetch the page and the image; Googlebot, bingbot and an unknown bot may not). The crawler names come from general knowledge, not from testing against each platform. The `noindex` header is unchanged.

Things to know about the image itself:

- **Its shape is 2.63:1, not the usual 1.91:1** (1200×630) for large preview cards. From general knowledge, not tested here, some platforms crop the middle of a wider image to roughly 2:1 or 1.91:1. That would cut about 140 to 165 px off each side of this one, and the "SEAmon" text starts about 38 px from the left edge, so it may be clipped. A 1200×630 version with the text inside the central area would avoid that.
- **The name is SEAmon** (Radit, 2026-11-15). The image says "SEAmon", and since the rename the page title, the tags and the visible text say it too, so the preview title and the picture agree.
- The origin and licence of the seaweed illustration are not recorded.
- Platforms cache previews. Replacing the image later usually needs a new file name or a refresh in each platform's debugger.
- Nothing here has been seen as an actual preview card on any platform.

## Deploy by hand

```bash
cd earth-globe && npm install && cd ..   # once
./scripts/build-site.sh                  # writes dist/site
npx wrangler deploy                      # from the repository root
```

On the owner's machine use the wrapper that pins the right account (`wrangler-radityaaydin`) instead of plain `npx wrangler`: plain `npx wrangler` there uses a different Cloudflare account. On any other machine, log in to the account that should own the Worker, or set `CLOUDFLARE_ACCOUNT_ID`, first. `npx wrangler deploy --dry-run` validates the config without uploading. Standard wrangler commands, not exercised here: `npx wrangler deployments list`, `npx wrangler rollback`.

## CI/CD (GitHub Actions)

[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml). **First run 2026-11-15 (push `35c595b`, run 43623964279): `npm ci`, `npm test` and the site build passed on the GitHub runner (so npm 10 there was fine); the deploy step failed.** The log shows `A request to the Cloudflare API (/accounts/***/workers/services/seagis-atlas) failed. Authentication error [code: 10000]`, from wrangler's first call, a read of the existing Worker. Nothing was deployed and the live site was unaffected (it still returned 200 afterwards). The log does not say which permission is missing; see the checklist under "Token permissions". GitHub also warned that the three actions run on a newer Node than they target, which is only a warning for now. Re-run (attempt 2, 18:06 UTC), after both secrets were set again at 18:03 UTC: the same `Authentication error [code: 10000]` on the same first call, so the new token value was rejected too.

**Attempt 3 (18:10 UTC) succeeded end to end.** Nothing was changed in the repository or in the GitHub secrets between attempts 2 and 3 (their update times were still 18:03 UTC), so the fix was made on the Cloudflare side to the token the secret already holds; I was not told what was changed. The deploy log shows 5 assets uploaded (10 already present), `Deployed seagis-atlas triggers`, `nasa.seagis.app (custom domain)` and a new version, `e40b07c9-b7f8-4c8f-8dd6-61a1f773d71c`. Afterwards `/` and `/globe/` returned 200, `/docs/…` 404, and the noindex header was present. In Chrome the live globe (now the CI-built bundle, with different file hashes from the local build) reported `ready`, loaded the 4096×2048 surface and the 7680×4320 sky, and logged no console errors. The CI build is not bit-identical to the local one; that was expected and is why 5 assets differed.

- **Triggers:** a push to `main` **or `master`**; a pull request; a manual run. Only changes to the site files (`earth-globe/**`, `scripts/**`, `wrangler.jsonc`, the workflow itself) trigger it (the root `index.html`, `styles.css` and `app.js` were removed from the list when they stopped being deployed), so a docs-only push does not deploy. Example: commit `751ac61` (Eca's NASA data access, which touches only `docs/Eca/` and `docs/CHALLENGE_2026.md`) matched none of those paths and GitHub recorded no run for it, as intended. If a data or docs change should ever trigger a deploy, add its path to both `paths` lists in the workflow.
- **Branches:** the repository's branch is `main`. There is **no `master` branch** on the remote (checked with `git ls-remote`); the workflow lists it only so it also works if one is created.
- **Steps:** install the globe dependencies with `npm ci`, run `npm test`, run `scripts/build-site.sh`, then deploy with `cloudflare/wrangler-action`. Pull requests stop after the build and never deploy. Only a push (or manual run) on `main` or `master` deploys. One deploy runs at a time and a running deploy is not cancelled.
- **Pinning:** Node 22; wrangler `4.162.0` (the version used for the manual deploys); the three actions are pinned by major tag (`@v4`, `@v4`, `@v3`), not by commit hash.

### Secrets the workflow needs (both set 2026-11-15)

Both are repository secrets (GitHub → Settings → Secrets and variables → Actions):

| Secret | What it is |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | A Cloudflare API token that can deploy Workers on the owner's account. Create it in the Cloudflare dashboard (My Profile → API Tokens), starting from the "Edit Cloudflare Workers" template and limiting it to the account and the `seagis.app` zone. |
| `CLOUDFLARE_ACCOUNT_ID` | The ID of the account that owns the Worker. |

Set them without putting the values in a file or in shell history:

```bash
gh secret set CLOUDFLARE_API_TOKEN --repo De-Voeux/nasa-cctw-web
gh secret set CLOUDFLARE_ACCOUNT_ID --repo De-Voeux/nasa-cctw-web
```

### Token permissions: what is known and what is not (checked 2026-11-15)

| Permission | Why | Status |
| --- | --- | --- |
| Account → Workers Scripts: Edit | upload the Worker and its static assets | The [GitHub Actions page](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/) says to use "Edit Cloudflare Workers" under Custom. Cloudflare's template reference (seen only in search snippets and mirrors) lists Workers Scripts and Workers Routes write access. |
| Zone (`seagis.app`) → Workers Routes: Edit | the template includes it | In the template; not shown to be required for a Custom Domain. |
| Zone (`seagis.app`) → DNS: Edit | attaching a Custom Domain makes Cloudflare create a DNS record | **Unverified.** The [Custom Domains page](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/) says Cloudflare creates the record but names no token permission. Nothing I found says the Workers template includes DNS. |
| Zone (`seagis.app`) → SSL and Certificates: Edit | the same page says a Custom Domain generates an Advanced Certificate on the zone | **Unverified guess.** No permission is named for it either. |

So the template alone may be too little for the custom-domain step, and I do not know which extra permission it needs. The docs I read name none, so this table is partly inference. Do not trust it over a real run. A real run has now succeeded with the token's present permissions (which I have not seen), and its deploy step printed `nasa.seagis.app (custom domain)`. Because that domain already existed, the step may not have exercised the DNS or certificate permissions, so this table still does not say which of them are required.

**How to find out without guessing:** create the token (scoped to the one account and the `seagis.app` zone only, not all zones), then deploy once from your own terminal with it before relying on CI. Redeploying the same assets and the same domain should be harmless. Run it with the token in your shell environment (not typed into a chat or a file), as `CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… npx wrangler deploy` from the repository root. A missing permission shows up as an error naming the failing call; add that permission and repeat. Only then put the token in the GitHub secret.

**Checklist after the `10000` failure** (resolved on attempt 3; I was not told which item was the cause. I could not see the token or its settings, so these were likely causes, never a diagnosis):

1. The token must have **Account → Workers Scripts: Edit** with Account Resources set to the account that owns the Worker. The same Cloudflare login also has the "Cendana" account; a token scoped to that one, or to zone permissions only, produces exactly this error.
2. `CLOUDFLARE_ACCOUNT_ID` must be the ID of that same account.
3. The token value pasted into the secret must be complete, with no stray spaces or line breaks. Re-run `gh secret set` for both if in doubt.
4. Check that the token is active: for a user token, `curl -s -H "Authorization: Bearer $TOKEN" https://api.cloudflare.com/client/v4/user/tokens/verify`; for an account-owned token, the same path under `/accounts/<ACCOUNT_ID>/tokens/verify`. Keep the token in an environment variable, not in a file or in a chat.
5. Re-run only the failed job with `gh run rerun 43623964279 --failed --repo De-Voeux/nasa-cctw-web` (or push a change to a site file). The run id is the first run; a later run has a new id.

## Not done

- **CI has deployed once** (attempt 3 of the first run). It has not yet been tried on an ordinary new push, on a pull request, or on a branch named `master` (none exists). The token's exact permissions are unrecorded, and whether a first-time domain attach would work with them is untested.
- **Access control.** The site is public to anyone who has the address; `noindex` only keeps it out of search engines.
- **Licences and credits.** The article textures' terms and the sky photo's licence are still unconfirmed (see [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md)). They are publicly reachable at this address.
- **Phones.** The deployed page was not tested on a phone, and the globe's memory use there is unmeasured.
- **Image re-encoding.** Parcel's production build re-encodes images (the sky went from 1.25 MB to 0.84 MB); the output was inspected visually only, not compared pixel by pixel with the originals.
- One reading I cannot explain: `renderer.info.memory.textures` was 0 on the live page (6 locally), although every texture rendered.
