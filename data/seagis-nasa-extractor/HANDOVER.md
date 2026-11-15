# Handover: seagis-nasa-extractor

State on **2026-11-15**, integrated on branch `feat/live-seagis-data` from `origin/main`.
The extractor work is committed in branch history (`e291201`, `85c0df4`, `7c99e5a`).

## What this is

`seagis-extract` is a CLI that pulls **daily per-zone environmental statistics** for the candidate seaweed regions and loads them into Postgres/Supabase.

- **NASA MUR SST** (GHRSST L4, 0.01°): `analysed_sst` (°C) and `analysis_error`, via NASA Harmony subsetting.
- **Copernicus Marine** global analysis/forecast, surface level (0.494 m):
  - no3 and po4 (BGC_001_028, 0.25°)
  - pH (BGC_001_028, 0.25°)
  - salinity `so` (PHY_001_024, 1/12°)

A zone (ROI) is a **5 km seaward buffer** of an administrative coastal unit. It is a **candidate area, not a farm extent**: no farm polygons were invented.

## Current data

| | |
|---|---|
| Period | **2026-08-15 .. 2026-11-14** (narrowed from 2022-06-01, then from 2025-11-15, at the user's request) |
| Approved plan hash | `3e55cf0ae7ddaaf9bc2cd619380ad1a8703ba769ff031f114e93f4ac6750b336` |
| Zones in plan | 47 in 17 regions; 42 after excluding Central Sulawesi |
| Fetched | Batch 1 (PH-TAWI, ID-SOUTH-SUL) and batch 2 (ID-SEA-SUL): **11 zones, 6,050 daily rows**, in `data/processed/` **and in Supabase** |
| Not fetched | Batches 3, 4 and 5 (31 zones, 163 units, ~350 MB, ~1-1.5 h) |
| Excluded | **ID-CENT-SUL** (Banggai, Morowali, Tomini). Harmony kept resetting connections on `tomini_tojo_una_una`, and the user chose to drop the region. Its outputs were deleted, and it is listed under `excluded:` in `config/fetch_batches.yaml`. It is still in the plan (see Known gaps). |
| Missing date | MUR 2026-11-14, not yet published by NASA on 2026-11-15. Copernicus has that date. |

Sanity ranges for batches 1 and 2 (daily zone means): SST 25.1-30.9 °C, no3 0.002-1.85 mmol m⁻³, po4 0.001-0.25 mmol m⁻³, pH 8.00-8.06, salinity 32.8-34.6. There are no NaN means and no duplicates.

## How to run

All commands run from `data/seagis-nasa-extractor/`. Credentials come from `.env` (gitignored, template `.env.example`) and are never printed.

```bash
# fetch the remaining batches, one at a time (a lock refuses a second concurrent run)
caffeinate -i .venv/bin/seagis-extract fetch --batch 3 --concurrency 4 --approve-plan 3e55cf0ae7ddaaf9bc2cd619380ad1a8703ba769ff031f114e93f4ac6750b336 2>&1 | tee -a outputs/fetch/batch3.log
#   batch 4 and 5: --concurrency 8 is fine (small zones)

# progress (read-only, safe while a fetch runs)
.venv/bin/seagis-extract status --batch 3

# load into the database
.venv/bin/seagis-extract export --dry-run --apply-migrations          # summary, no connection
.venv/bin/seagis-extract export --apply-migrations --confirm-host <db host>
```

### Fetch behaviour

- **Resumable.** A unit is one ROI × month for MUR, or one dataset × region for Copernicus. Finished units are recorded in `outputs/fetch/fetch_manifest.jsonl` with the SHA-256 of the output, and are skipped on rerun. Failed units are retried by rerunning the same command.
- **Guarded.**
  - Every MUR response must lie inside the approved grid cells, or the run aborts and the file is deleted.
  - Copernicus subsets are cropped to the plan's cells.
  - A byte budget applies (20 GB).
- **Raw files are discarded** after validation. Outputs are Parquet: `data/processed/<dataset>/<region>/<zone>/<YYYY-MM>.parquet` for MUR and `<zone>.parquet` for Copernicus.
- **Network resilience.** Each HTTP call retries 6 times with jittered backoff (resets, timeouts, 429, 5xx, honouring Retry-After). Each unit then retries 5 times.
- **Speed.** Harmony subsetting costs about 5 s per daily file, and that is the bottleneck, not bandwidth. `--concurrency` (1-16) changes only speed, not the plan hash. Use 4 for batch 3, whose zones need 2-5 tiles each, like the region that failed.
- **The plan hash gates everything.** It covers the plan content and its input files (catalog, ROI GeoJSON, extraction/products/roi_sources config, pilot report). Changing the period, zones or config needs `seagis-extract catalog && seagis-extract plan` and a new hash. `config/fetch_batches.yaml` is deliberately not hashed.

## Database

**Migration:** `supabase/migrations/20261115000000_seagis_environment.sql`, at the repo root. It is idempotent.

| Table | Key | Contents |
|---|---|---|
| `seagis_regions` | `region_id` | 18 regions from `config/regions.yaml`, `status`, `excluded` |
| `seagis_zones` | `(region_id, subregion_id, geometry_version)` | zone name, buffer, area, bbox, boundary source and its SHA-256. Polygons stay in `data/roi/roi_candidates_v1.geojson` (79 MB) |
| `seagis_daily_metrics` | `(region_id, subregion_id, geometry_version, dataset, variable, date)` | area-weighted mean/min/max/std, pixel counts, coverage, units, product version, QC flags, `plan_sha256`, `load_run_id` |
| `seagis_load_runs` | `run_id` | one row per export, for provenance |

- **Row level security** is on for all four tables. `anon` and `authenticated` can **read only**; writes need the DB owner or the service role. This was checked locally: an anon insert is rejected.
- **Applying migrations.** `export --apply-migrations` applies only `20261115000000_seagis_environment.sql` and records it in `seagis_schema_migrations`. It does not apply the web application's RAG or `env` migrations. Alternatively use `supabase db push` after `supabase init && supabase link`; in that case, run `export` without `--apply-migrations` so the two trackers don't disagree.
- **The export is one transaction.** It upserts on the keys above, so rerunning is safe and updates rows in place. It never deletes anything. It refuses unless `--confirm-host` equals the DSN host.
- **Connection.** Set `SEAGIS_DB_DSN` in `.env` to a `postgresql://` connection string; in Supabase, Connect → Session pooler. `SEAGIS_DB_URL` is the https project URL and cannot run SQL.
- **Historical status (2026-11-15): reported as pushed to Supabase.** The recorded target was pooler host `aws-1-ap-southeast-2.pooler.supabase.com`, project `aemqvswrqgkdefzfvnug`. This checkpoint did not re-query that project because the connected Supabase workspace exposed a different project. Treat the counts below as handover claims until the approved staging project is checked read-only.
  - The `public` schema was empty beforehand.
  - The migration was applied. All 5 `seagis_*` tables have RLS on, including `seagis_schema_migrations`, which has no policy.
  - Loaded 18 regions, 42 zones and **6,050 daily rows** (batches 1-2, 11 zones).
  - Checked live: anon can read all 6,050 rows, an anon insert is rejected, and anon sees nothing in the migrations table.
  - `seagis_load_runs` has 2 runs: the first load, plus a rerun that changed no rows and only enabled RLS on the migrations table.

## Code map

`src/seagis_extractor/`:

| File | Contents |
|---|---|
| `cli.py` | All subcommands |
| `estimate.py` | MUR grid, ROI membership, request tiling (edges inset ¼ cell), plan, hash |
| `copernicus.py` | Copernicus plan section and static sea masks |
| `fetch.py` | Harmony client: async jobs, manual redirects, token only to Earthdata hosts, retries, Copernicus toolbox wrapper |
| `backfill.py` | Units, runner, `status`, `RunLock` |
| `pilot.py` | Plan gate (`verify_plan`) and pilot run |
| `validate.py` | Response guards and checks |
| `process.py` | Weighted daily aggregation |
| `manifest.py` | Manifest |
| `export.py` | DB loader |
| `roi.py` | ROI builder |
| `auth.py` | `.env` loading |

Tests: `.venv/bin/python -m pytest -q` gives 81 passed and 1 skipped in the integrated branch. Set `SEAGIS_TEST_DSN` to a scratch Postgres to run the DB round trip too, which removes the skip.

Install non-editable after code changes, because iCloud hides `.pth` files: `uv pip install -q --python .venv --reinstall-package seagis-nasa-extractor .`

## Fixes made during the fetch (2026-11-15)

1. **Tile edges.** Request boxes whose edges lay on MUR cell boundaries made Harmony add a neighbouring row, and the guard aborted batch 2. Every edge is now at least ¼ cell inside its expected extent. The cells requested are unchanged, and so is the hash, which was bumped once for this change.
2. **Connection resets.** One reset used to fail a whole ROI-month. Calls now retry per request with backoff, and errors name the step and the URL (with the query stripped).
3. **Progress output.** Progress printed only when every MUR unit had finished. It now prints per unit.
4. **New commands and options.** `status` was added, and so was `fetch --concurrency`.

## Web integration on `feat/live-seagis-data`

- `GET /api/environment` reads `public.seagis_daily_metrics` through the Worker and keeps the service-role key server-side.
- It returns the latest 14 observed days for NASA MUR SST and Copernicus `so`, `no3`, `po4`, and `ph`, paging PostgREST responses and weighting subregions by valid pixel count.
- Dashboard locations carry explicit extractor `region_id` mappings.
- Mock levels are opt-in with `?demo=levels`; the default dashboard shows observed series where rows exist.
- Observed data remains `Insufficient Data` for biological classification until a species rule is reviewed and activated. It is not a disease diagnosis.
- Charts do not extend observations into a fabricated forecast or baseline.

The code path is covered by the Worker, frontend, extractor, and production-build checks. A read-only request against the approved staging project is still required before deployment.

## Known gaps / next steps

1. **Fetch batches 3-5**, then export again. Upserts are incremental:
   `.venv/bin/seagis-extract export --apply-migrations --confirm-host aws-1-ap-southeast-2.pooler.supabase.com`
2. **Staging verification.** Confirm the Worker's `SUPABASE_URL` points to the approved extractor/staging project, then request `/api/environment` and verify a loaded region such as `PH-TAWI` and its latest date. Do not use the connected IoT project for this data.
3. **Web app access.** The Worker reads `seagis_daily_metrics`, `seagis_zones` and `seagis_regions` with its server-side service role. The polygons are not in the DB; serve `data/roi/roi_candidates_v1.geojson`, or a simplified copy, if the map needs them.
3. **Remove ID-CENT-SUL from the plan properly**, if it stays excluded. Remove it from `config/regions.yaml` and `config/roi_sources.yaml`, then run `regions build`, `catalog` and `plan`; this gives a new hash. Until then, `status` without `--batch` counts its units, and `fetch --region ID-CENT-SUL` would still fetch it.
4. **ROI review still open:**
   - Samal sits in Davao del Norte.
   - Seram Barat islets.
   - Regions marked PROVISIONAL (whole provincial coast).
   - PH-S-LUZON is pending, because there is no admin unit for it.
   - Lingayen Gulf BGC is intentionally empty (no model sea cell).
5. **CSV export** (TASK.md step 8) is not built; the output is Parquet and DB only.
7. **Commit.** Commit the code, tests, configs, and docs on `feat/live-seagis-data` after staging verification. `.env`, `data/processed`, `outputs/`, `dist/` and `.venv/` are gitignored.
8. **Docs.** `docs/PLAN_REVIEW.md` has dated notes for each period and hash change. `CATALOG_REVIEW.md` and `COPERNICUS_REVIEW.md` still quote the old 2022-2026 figures.
