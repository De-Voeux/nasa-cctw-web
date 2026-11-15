# OpenCode handoff: activate real SEAmon environmental data

Updated: 2026-11-15 (Asia/Jakarta)

## Objective

Finish the work on a new branch until the SEAmon dashboard reads real NASA/Copernicus measurements, mock data is opt-in only, the data path is tested, and the extractor handover reflects the final verified state.

Do not invent biological thresholds, disease probabilities, or risk labels. Real measurements may be displayed immediately, but `favorable`, `moderate`, and `elevated` must remain inactive until a reviewed species rule with citations exists. Environmental observations do not diagnose ice-ice.

## Repository and branch

- Repository: `De-Voeux/nasa-cctw-web`
- Isolated worktree: `/Users/arieskakharzani/Documents/ChatGPT/NASA/live-seagis-data`
- Branch: `feat/live-seagis-data`
- Base: `origin/main` at `f867229`
- The user's older checkout at `/Users/arieskakharzani/Projects/NASA-Challenge/nasa-cctw-web` was left untouched.

The branch already contains these three commits cherry-picked from `origin/feat/data-pulling`:

1. `e291201` — extraction period and fetch batches
2. `85c0df4` — retries, status, concurrency, fetch fixes
3. `7c99e5a` — Postgres/Supabase exporter and `20261115000000_seagis_environment.sql`

They applied without conflicts. The branch is currently three commits ahead of `origin/main` and has not been pushed.

## Current uncommitted state

The following implementation started before this handoff was requested:

- `worker/environment.js` — new read-only `GET /api/environment` handler
- `worker/environment.test.mjs` — handler and aggregation tests
- `worker/index.js` — routes `/api/environment` to the handler

These files are uncommitted. The first implementation checkpoint is now complete: endpoint tests, frontend data transformation tests, globe tests, extractor tests, and the production build have passed. Review the files before committing; do not assume live staging data has been verified.

Frontend integration is now also present in `earth-globe/src/data/environment.js`, `earth-globe/src/data/reportedLocations.js`, `earth-globe/src/data/stress.js`, `earth-globe/src/dashboard/main.js`, `earth-globe/src/dashboard/sidePanel.js`, and `earth-globe/src/dashboard/trendChart.js`. No database migration has been applied in this branch. No data fetch, export, deployment, merge, or push has been performed.

Checkpoint verification:

- Worker/data-loader tests: 54 passed
- Globe tests: 22 passed
- Extractor tests: 81 passed, 1 skipped (optional scratch-DB round trip)
- Production build: passed
- Live staging request: pending; the connected Supabase project did not match the project recorded in the extractor handover

## Verified repository state

### Extractor data model

The extractor exports daily per-zone data to:

- `public.seagis_regions`
- `public.seagis_zones`
- `public.seagis_daily_metrics`
- `public.seagis_load_runs`

Variables currently supported:

- NASA MUR: `analysed_sst`, `analysis_error`
- Copernicus Marine: `so`, `no3`, `po4`, `ph`

The ROI is a 5 km seaward buffer of an administrative coastal unit. It is a candidate analysis zone, not a verified farm polygon.

### Existing app data model

The assistant's older numeric-data path uses:

- `env.sites`
- `env.daily`
- `public.env_list_sites(...)`
- `public.env_get_series(...)`

Do not silently copy the extractor data into this schema. The spatial support is different: extractor rows are zone aggregates while `env.daily` represents point-like research sites.

### Frontend state

- `earth-globe/src/data/stress.js` currently has `MOCK_DEFAULT = true`.
- `earth-globe/src/data/sampleDrivers.js` contains fabricated design values.
- `earth-globe/src/dashboard/sidePanel.js` always reads those fabricated drivers for non-insufficient levels.
- `earth-globe/src/dashboard/main.js` creates all assessments synchronously with `assess(loc)`.
- No real environmental endpoint is currently called by the dashboard.

### Scientific guardrail

The repository explicitly states that no species threshold or composite rule has been validated:

- `docs/METHODOLOGY.md`
- `docs/DECISIONS.md`
- `research/evidence/README.md`
- `docs/Eca/README.md`

Therefore the correct first release behavior is:

- show real observed series and provenance where available;
- keep `stress_level = insufficient` because the assessment rule is inactive;
- use a condition such as `Observed data available · species thresholds under review`;
- show `No stress level assigned` rather than treating missing rules as favorable conditions;
- keep `?demo=levels` as an explicit design-review mode only.

## Database finding that must not be ignored

The connected Supabase tool currently exposes project:

- project name: `seagis-model-database`
- project ID: `mdtmupiftllpglkfoaqy`

This is not the project recorded by the extractor handover:

- handover project ID: `aemqvswrqgkdefzfvnug`

The connected project contains the larger `seagis`, `seagis_app`, and IoT-style schema and must not receive this extractor migration without explicit confirmation. Repository documentation says to use the staging `nasa-seagis` project and not the IoT production project.

No database writes were made during this work. Before applying anything, confirm that the Worker's `SUPABASE_URL` points to the extractor/staging project containing `public.seagis_daily_metrics`.

## Migration conflict to fix

`data/seagis-nasa-extractor/src/seagis_extractor/export.py` currently selects every `*.sql` file in `supabase/migrations/` when `--apply-migrations` is used. After integration with current `main`, that directory also contains RAG and `env` migrations.

This can mix two migration trackers and can execute unrelated migration files inside the exporter's transaction.

Required fix:

- make the exporter apply only `20261115000000_seagis_environment.sql`, or preferably require an explicit migration file/directory dedicated to the extractor;
- keep normal project migrations owned by the Supabase migration system;
- update exporter tests so unrelated SQL files are ignored;
- update CLI help and documentation;
- do not run `export --apply-migrations` against a live project until this is fixed.

## Intended implementation

### 1. Read-only Worker endpoint

Use the existing Worker secrets server-side:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

`GET /api/environment` should:

- reject non-GET requests;
- query the latest date from `public.seagis_daily_metrics`;
- read the latest 14 observed days for `analysed_sst`, `so`, `no3`, `po4`, and `ph`;
- page PostgREST results so the 1,000-row default does not truncate regions;
- aggregate multiple subregions by `region_id`, date, and variable using `valid_pixel_count` as the weight;
- return values, units, product version, coverage, source, and dates;
- never return the service-role key or raw database errors;
- cache successful public-science responses briefly and return a safe 502/503 payload on failure.

The started `worker/environment.js` follows this shape but still needs review and tests.

### 2. Region mapping

Add an explicit extractor ID to each dashboard location instead of guessing from names:

| Dashboard location ID | Extractor region ID |
| --- | --- |
| `ph-pangasinan` | `PH-PANG` |
| `ph-batangas` | `PH-BATANGAS` |
| `ph-southern-luzon` | `PH-S-LUZON` |
| `ph-eastern-samar` | `PH-E-SAMAR` |
| `ph-palawan` | `PH-PALAWAN` |
| `ph-ne-bohol` | `PH-NE-BOHOL` |
| `ph-zamboanga` | `PH-ZAMBOANGA` |
| `ph-davao-norte` | `PH-DAVAO-N` |
| `ph-tawi-tawi` | `PH-TAWI` |
| `my-sabah` | `MY-SABAH` |
| `vn-khanh-hoa` | `VN-KHANH-HOA` |
| `id-n-kalimantan` | `ID-N-KAL` |
| `id-c-sulawesi` | `ID-CENT-SUL` (excluded from fetch) |
| `id-se-sulawesi` | `ID-SEA-SUL` |
| `id-s-sulawesi` | `ID-SOUTH-SUL` |
| `id-maluku` | `ID-MALUKU` |
| `id-n-java-sea` | `ID-N-JAVA-SEA` |
| `id-ntb` | `ID-NTB` |

`ph-bohol` has no direct extractor region and must remain unmapped unless a reviewed spatial mapping is added.

### 3. Frontend real-data state

Create a small data client, for example `earth-globe/src/data/environment.js`, with pure transformation functions and tests.

Expected behavior:

- default: mock disabled;
- explicit design mode: `?demo=levels` preserves sample cards;
- initial state: loading or insufficient, never a fabricated level;
- after `/api/environment` succeeds, mapped locations with measurements show the latest observed date and actual series;
- locations without returned measurements remain `Insufficient Data`;
- a failed endpoint degrades to the current safe insufficient-data state;
- all user-facing source labels state NASA MUR or Copernicus Marine and identify the values as daily zone means;
- the detail panel must say that no biological stress classification is assigned yet.

Do not call the observed series a forecast. The extractor handover only establishes observations/analysis through its approved period. A 10-day forecast needs a separately verified forecast issue time, valid time, and product lineage.

### 4. Charts and date controls

The existing chart assumes 14 observed days plus three fabricated forecast days and a fabricated baseline band.

For real observations:

- allow no baseline band;
- allow no forecast segment;
- select the closest available observation date rather than indexing from today's date;
- show the last observation date explicitly;
- do not extend a line into future date pills;
- retain the current demo behavior only under `?demo=levels`.

### 5. Documentation

Update at least:

- `data/seagis-nasa-extractor/HANDOVER.md`
- `data/seagis-nasa-extractor/README.md`
- `supabase/README.md`
- `docs/Radit/RAG_TEAM_HANDOFF.md` if it still says the dashboard is mock-only

The updated handover must distinguish:

- code verified locally;
- data confirmed in the staging database;
- historical observations available to the dashboard;
- regions still unfetched;
- no active species-risk rule;
- deployment status;
- exact branch and commit.

Never carry forward the old statement `None of this session's work is committed`; the extractor work is now committed.

## Data recovery and remaining fetches

The old handover claims 6,050 rows for batches 1–2 in staging Supabase, but the ignored local artifacts are absent from every checkout inspected:

- no Parquet outputs;
- no fetch manifest;
- no `outputs/plan.json`;
- no extractor `.env`;
- no virtual environment.

Do not claim those local files still exist. The database claim must be rechecked against project `aemqvswrqgkdefzfvnug` or the confirmed replacement staging project.

Batches 3–5 cannot safely resume until the exact approved plan, manifest, credentials, and destination project are recovered or regenerated. If the plan is regenerated, record the new hash and do not reuse the old approval hash silently.

## Verification checklist

Run these before committing:

1. Extractor tests:
   `cd data/seagis-nasa-extractor && python -m pytest -q`
2. Globe tests:
   `cd earth-globe && npm test`
3. Worker and loaders:
   `node --test worker/ask.test.mjs worker/environment.test.mjs scripts/rag/corpus.test.mjs scripts/env/parse.test.mjs`
4. Production bundle:
   `./scripts/build-site.sh`
5. Inspect the built bundle to ensure `MOCK_DEFAULT = true` is gone and `/api/environment` is referenced.
6. Test `/api/environment` with fixtures and then against the confirmed staging Worker/Supabase environment.
7. Confirm that a region with real rows displays actual values and provenance.
8. Confirm that a region without rows stays insufficient and does not display sample numbers.
9. Confirm `?demo=levels` is visibly demo-only.
10. Run Supabase security and performance advisors after any database change, then record only findings relevant to the new objects.

## Definition of done

- Work is on `feat/live-seagis-data`.
- No mock environmental value appears by default.
- Real measurements load through a tested, read-only endpoint.
- Secrets remain server-side.
- Measurements and risk classification are clearly separated.
- No unreviewed threshold is activated.
- Exporter cannot apply unrelated migrations.
- All relevant tests and the production build pass.
- The correct staging database is confirmed and queried successfully.
- HANDOVER.md states the final verified branch, commit, data counts, coverage dates, limitations, and deployment state.
- The branch is committed and pushed only after the above checks pass.

## Immediate next action

Review the three uncommitted Worker files, finish the endpoint tests, then implement the frontend data client and mock-off behavior. Before any live database write, resolve the project-ID mismatch and verify the staging project read-only.
