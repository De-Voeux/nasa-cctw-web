# Handover: seagis-nasa-extractor

State on **2026-11-15**, branch `feat/data-pulling` (merged with `origin/main`).

## What this is

`seagis-extract` is a CLI that pulls **daily per-zone environmental statistics** for the candidate seaweed regions and loads them into Postgres/Supabase.

- **NASA MUR SST** (GHRSST L4, 0.01°): `analysed_sst` (°C) and `analysis_error`, via NASA Harmony subsetting.
- **Copernicus Marine** global analysis/forecast, surface level (0.494 m):
  - no3 and po4 (BGC_001_028, 0.25°)
  - pH (BGC_001_028, 0.25°)
  - salinity `so` (PHY_001_024, 1/12°)
  - ocean currents `uo`, `vo` (PHY_001_024, 1/12°), plus derived `current_speed`, `current_direction` (degrees from north, toward which the water flows) and `current_steadiness`. *Added 2026-11-15, not fetched yet.*
- **NASA GPM IMERG** Late daily V07 (GES DISC, 0.1°): `precipitation` (mm/day), via Harmony like MUR. *Added 2026-11-15, not fetched yet.*
- **NASA POWER** daily point (LaRC): T2M, RH2M, WS10M, WD10M (direction the wind comes from), ALLSKY_SFC_SW_DWN, ALLSKY_SFC_PAR_TOT and CLOUD_AMT, at one point inside each zone. No account. *Added 2026-11-15, not fetched yet.*

A zone (ROI) is a **5 km seaward buffer** of an administrative coastal unit. It is a **candidate area, not a farm extent**: no farm polygons were invented.

Every source, with links, DOIs and licences, is listed in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Current data

| | |
|---|---|
| Period | **2026-08-15 .. 2026-11-14** (narrowed from 2022-06-01, then from 2025-11-15, at the user's request) |
| Approved plan hash | `d5e5783e301c7ffde6628df6ead1a6103a534bfb4a95ac1b07ff582c9307511a` (renames PH-NE-BOHOL to PH-BOHOL; `4ebfe10c…` added currents, IMERG and POWER; `af7f572b…` added PH-S-LUZON) |
| Zones in plan | 48 zones; 19 regions, of which PH-NE-BOHOL has no zone yet. PH-S-LUZON resolved to Calatagan, Batangas |
| Bohol | The old `PH-NE-BOHOL/bohol` zone was the whole province, so it is now `PH-BOHOL/bohol` (Faisan et al. 2021). Local Parquet and the manifest were rewritten in place, with the same values and no re-fetch. `PH-NE-BOHOL` (Largo et al. 1995) waits for a named study coast. The DB rename is `sql/2026-11-15_rename_bohol.sql` |
| Fetched | **All 504 units**: every source for all 48 zones, 2026-08-15..2026-11-14 (MUR and IMERG to 11-13, not yet published for 11-14) |
| In Supabase | **82,932 daily rows, 48 zones, 19 regions** (export run `ff59a1d9`, 2026-11-15). Both extractor migrations applied; units are display labels |
| Central Sulawesi | Briefly excluded after Harmony connection resets on `tomini_tojo_una_una`, then re-fetched with `--region ID-CENT-SUL --concurrency 2` (23/23 ok) and restored to batch 2. Nothing is excluded now. |
| Missing date | MUR 2026-11-14, not yet published by NASA on 2026-11-15. Copernicus has that date. |

Batch 3 includes river-influenced zones: Nunukan salinity is 25-27, and Tarakan has salinity 28-30, pH 7.77-7.83 and no3 4.3-5.7. These are model values from coarse cells near the Kalimantan river mouths; they are plausible, but should be read as indicative.

Sanity ranges for batches 1 and 2 (daily zone means): SST 25.1-30.9 °C, no3 0.002-1.85 mmol m⁻³, po4 0.001-0.25 mmol m⁻³, pH 8.00-8.06, salinity 32.8-34.6. There are no NaN means and no duplicates.

## How to run

All commands run from `data/seagis-nasa-extractor/`. Credentials come from `.env` (gitignored, template `.env.example`) and are never printed.

```bash
# fetch what is left (one run at a time; a lock refuses a second one). Done units are skipped.
caffeinate -i .venv/bin/seagis-extract fetch --batch 6 --concurrency 8 --approve-plan d5e5783e301c7ffde6628df6ead1a6103a534bfb4a95ac1b07ff582c9307511a 2>&1 | tee -a outputs/fetch/batch6.log
#   then without --batch for everything (tee -a outputs/fetch/all.log, so `status` can give an ETA);
#   --source imerg|power|copernicus limits it to one source

# progress (read-only, safe while a fetch runs)
.venv/bin/seagis-extract status --batch 6

# load into the database
.venv/bin/seagis-extract export --dry-run --apply-migrations          # summary, no connection
.venv/bin/seagis-extract export --apply-migrations --confirm-host <db host>
```

### Fetch behaviour

- **Resumable.** A unit is one ROI × month for MUR and IMERG, one dataset × region for Copernicus (currents included), or one zone for POWER. Finished units are recorded in `outputs/fetch/fetch_manifest.jsonl` with the SHA-256 of the output, and are skipped on rerun. Failed units are retried by rerunning the same command.
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
- **Applying migrations.** `export --apply-migrations` applies only the extractor's own files, `20261115000000_seagis_environment.sql` and `20261115010000_seagis_more_sources.sql` (comments only), and records them in `seagis_schema_migrations`. It never applies the web application's RAG or `env` migrations. Alternatively use `supabase db push` after `supabase init && supabase link`; in that case, run `export` without `--apply-migrations` so the two trackers don't disagree.
- **Units.** `export` writes display labels to `units`: °C, mmol/m³, PSU, pH, m/s, ° and 0–1 (steadiness). The mapping is `export.DISPLAY_UNITS`. These are labels only, so no value changes: `1e-3` becomes PSU, and the `kelvin` of `analysis_error` (a temperature difference) becomes °C. Parquet keeps the source strings. An unknown unit stops the export, instead of passing through unlabelled.
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
| `imerg.py` | GPM IMERG grid, plan section, checks, aggregation |
| `power.py` | NASA POWER point plan section, client (plan URLs only), guard, rows |
| `fetch.py` | Harmony client: async jobs, manual redirects, token only to Earthdata hosts, retries, Copernicus toolbox wrapper |
| `backfill.py` | Units, runner, `status`, `RunLock` |
| `pilot.py` | Plan gate (`verify_plan`) and pilot run |
| `validate.py` | Response guards and checks |
| `process.py` | Weighted daily aggregation, derived current speed/direction/steadiness |
| `manifest.py` | Manifest |
| `export.py` | DB loader |
| `roi.py` | ROI builder |
| `auth.py` | `.env` loading |

Tests: `.venv/bin/python -m pytest -q` gives 88 passed and 1 skipped. Set `SEAGIS_TEST_DSN` to a scratch Postgres to run the DB round trip too, which removes the skip.

Install non-editable after code changes, because iCloud hides `.pth` files: `uv pip install -q --python .venv --reinstall-package seagis-nasa-extractor .`

### New sources: known issues (batch 6, 2026-11-15)

- **IMERG returned HTTP 403** from GES DISC OPeNDAP on every granule, so Harmony failed the job. The Earthdata account must authorize the **NASA GESDISC DATA ARCHIVE** application (Earthdata Login → Applications → Authorized Apps). Then rerun the same fetch: the failed units retry.
- **POWER latency.** ALLSKY_SFC_PAR_TOT and CLOUD_AMT are empty from 2026-08-31 onward, because they come from CERES, which runs about 2.5 months behind. ALLSKY_SFC_SW_DWN is empty for the last ~9 days, and T2M, RH2M and the wind variables for the last 3. The empty days are stored with `fill` in `qc_flags`.
- **Calatagan check** (first real run): currents 0.04-0.36 m/s, steadiness 0.28-1.0. POWER: T2M 26.8-29.8 °C, WS10M 0.9-8.5 m/s.

### New sources: how values are computed

- **Currents.** `current_speed` is the weighted mean of hypot(u, v) per cell. `current_direction` is atan2(ū, v̄) mod 360 of the weighted mean vector: 0 = flowing north, 90 = flowing east. Its min/max/std are empty, because direction is circular. `current_steadiness` is \|mean vector\| / mean speed; near 0, the direction is meaningless.
- **IMERG.** Weighted by overlap × cell area over the 0.1° cells touching the zone. No land mask is applied. The first IMERG unit is effectively the format check: wrong units, a wrong grid or bad values fail the unit, and the guard aborts the run.
- **POWER.** One value per day at the zone's representative point. `area_weighted` is false and `roi_pixel_count` is 1. Fill (-999) is stored as an empty mean with `qc_flags` containing `fill`.

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

1. **Done 2026-11-15:** all sources fetched and exported. Rerun `export` after any new fetch; upserts are incremental:
   `.venv/bin/seagis-extract export --apply-migrations --confirm-host aws-1-ap-southeast-2.pooler.supabase.com`
2. **Staging verification.** Confirm the Worker's `SUPABASE_URL` points to the approved extractor/staging project, then request `/api/environment` and verify a loaded region such as `PH-TAWI` and its latest date. Do not use the connected IoT project for this data.
3. **Web app access.** The Worker reads `seagis_daily_metrics`, `seagis_zones` and `seagis_regions` with its server-side service role. The polygons are not in the DB; serve `data/roi/roi_candidates_v1.geojson`, or a simplified copy, if the map needs them.
4. **ROI review still open:**
   - Samal sits in Davao del Norte.
   - Seram Barat islets.
   - Regions marked PROVISIONAL (whole provincial coast).
   - PH-S-LUZON resolved to Calatagan, Batangas (Alimin et al. 2026; Solis et al. 2010).
   - Lingayen Gulf BGC is intentionally empty (no model sea cell).
5. **CSV export** (TASK.md step 8) is not built; the output is Parquet and DB only.
7. **Commit.** Commit the code, tests, configs, and docs on `feat/live-seagis-data` after staging verification. `.env`, `data/processed`, `outputs/`, `dist/` and `.venv/` are gitignored.
8. **Docs.** `docs/PLAN_REVIEW.md` has dated notes for each period and hash change. `CATALOG_REVIEW.md` and `COPERNICUS_REVIEW.md` still quote the old 2022-2026 figures.
