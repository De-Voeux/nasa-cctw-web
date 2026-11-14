# Deployment (Cloudflare Worker)

**First deployed 2026-11-15**, as a new Cloudflare Worker, `seagis-atlas`, serving static assets. The custom domain `nasa.seagis.app` was attached the same day.

| | |
| --- | --- |
| Address | <https://nasa.seagis.app> |
| Globe demo | <https://nasa.seagis.app/globe/> |
| `workers.dev` address | **disabled** (see below) |
| Current version ID | `d606caa5-c27b-4159-9de4-07b2fa06d87a` (first deploy was `f2fef4e9-4a68-41db-9917-5c8a53cb3164`) |
| Account | the personal Cloudflare account of the repository owner (not the "Cendana" account that is also on that login) |
| Config | [`wrangler.jsonc`](../../wrangler.jsonc) |
| Build | [`scripts/build-site.sh`](../../scripts/build-site.sh) |
| CI/CD | [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) (written, **never run yet**) |

## What is deployed

- `/` — the static shell (`index.html`, `styles.css`, `app.js`).
- `/globe/` — the globe demo, built from `earth-globe/` with Parcel.
- `/robots.txt` (disallow all) and an `X-Robots-Tag: noindex, nofollow` header on every response, because the site is research-stage and some texture licences are unresolved.

**Not deployed on purpose:** `docs/`, `research/`, `contracts/`. They are internal team notes, including unverified research leads. The root page does not link to `/globe/` yet (that would edit a shared page).

## Custom domain

- `seagis.app` uses Cloudflare nameservers (`aisha.ns.cloudflare.com`, `ethan.ns.cloudflare.com`, from a DNS lookup), and the zone is in the same account as the Worker: the deploy was accepted. A lookup before the deploy showed no existing records for `nasa.seagis.app`, so nothing was overwritten.
- `wrangler.jsonc` has `routes: [{ "pattern": "nasa.seagis.app", "custom_domain": true }]`. On deploy, Cloudflare created the DNS records itself.
- **`workers.dev` is now off.** Wrangler disables the `*.workers.dev` address and preview URLs by default once `routes` is set, and printed a warning to that effect. The old address, `seagis-atlas.radityaaydin.workers.dev`, returned 404 afterwards. `workers_dev` and `preview_urls` are now written out as `false` in `wrangler.jsonc` so no deploy changes them silently. Set `"workers_dev": true` to bring the address back.

Verified on 2026-11-15 after the deploy:

- `https://nasa.seagis.app/` and `/globe/` return 200 with a valid certificate; `/robots.txt` returns 200; `/docs/Radit/README.md` returns 404; the noindex header is present; the response comes from Cloudflare.
- DNS returns A and AAAA records for `nasa.seagis.app` (Cloudflare addresses, as expected for a proxied hostname).
- In Chrome on `https://nasa.seagis.app/globe/` the page loaded over HTTPS, the globe reported `ready` with the NASA surface (4096×2048), the 7680×4320 sky, the day/night side, and a credit footer whose two links point to the Unsplash photographer and photo. The console showed one error, `Could not establish connection. Receiving end does not exist`, whose wording is typical of a browser-extension messaging failure rather than the page's own code; that is my guess and I did not confirm it. The same check on the first address had shown no console errors.

## Deploy by hand

```bash
cd earth-globe && npm install && cd ..   # once
./scripts/build-site.sh                  # writes dist/site
npx wrangler deploy                      # from the repository root
```

On the owner's machine use the wrapper that pins the right account (`wrangler-radityaaydin`) instead of plain `npx wrangler`: plain `npx wrangler` there uses a different Cloudflare account. On any other machine, log in to the account that should own the Worker, or set `CLOUDFLARE_ACCOUNT_ID`, first. `npx wrangler deploy --dry-run` validates the config without uploading. Standard wrangler commands, not exercised here: `npx wrangler deployments list`, `npx wrangler rollback`.

## CI/CD (GitHub Actions)

[`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml). **Written 2026-11-15, validated only by parsing the YAML; it has never run on GitHub.**

- **Triggers:** a push to `main` **or `master`**; a pull request; a manual run. Only changes to the site files (`index.html`, `styles.css`, `app.js`, `earth-globe/**`, `scripts/**`, `wrangler.jsonc`, the workflow itself) trigger it, so a docs-only push does not deploy.
- **Branches:** the repository's branch is `main`. There is **no `master` branch** on the remote (checked with `git ls-remote`); the workflow lists it only so it also works if one is created.
- **Steps:** install the globe dependencies with `npm ci`, run `npm test`, run `scripts/build-site.sh`, then deploy with `cloudflare/wrangler-action`. Pull requests stop after the build and never deploy. Only a push (or manual run) on `main` or `master` deploys. One deploy runs at a time and a running deploy is not cancelled.
- **Pinning:** Node 22; wrangler `4.162.0` (the version used for the manual deploys); the three actions are pinned by major tag (`@v4`, `@v4`, `@v3`), not by commit hash.

### Secrets the workflow needs (not set yet)

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

So the template alone may be too little for the custom-domain step, and I do not know which extra permission it needs. The docs I read name none, so this table is partly inference. Do not trust it over a real run.

**How to find out without guessing:** create the token (scoped to the one account and the `seagis.app` zone only, not all zones), then deploy once from your own terminal with it before relying on CI. Redeploying the same assets and the same domain should be harmless. Run it with the token in your shell environment (not typed into a chat or a file), as `CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… npx wrangler deploy` from the repository root. A missing permission shows up as an error naming the failing call; add that permission and repeat. Only then put the token in the GitHub secret. Until both secrets exist, the deploy step fails (build and test still run).

## Not done

- **CI/CD has never run**, and the secrets are not set. The first run on GitHub may reveal problems that parsing the file cannot (for example the token's permissions, or a dependency install difference between npm 11 locally and npm 10 on the runner).
- **Access control.** The site is public to anyone who has the address; `noindex` only keeps it out of search engines.
- **Licences and credits.** The article textures' terms and the sky photo's licence are still unconfirmed (see [TEXTURE_SOURCES.md](TEXTURE_SOURCES.md)). They are publicly reachable at this address.
- **Phones.** The deployed page was not tested on a phone, and the globe's memory use there is unmeasured.
- **Image re-encoding.** Parcel's production build re-encodes images (the sky went from 1.25 MB to 0.84 MB); the output was inspected visually only, not compared pixel by pixel with the originals.
- One reading I cannot explain: `renderer.info.memory.textures` was 0 on the live page (6 locally), although every texture rendered.
