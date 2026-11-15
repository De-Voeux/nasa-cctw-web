# Calzy — collaborator context

**Collaborator:** camellion

**Last updated:** 2026-11-15

## Responsibility and goal

**Environmental data for the candidate seaweed zones.** I own [`data/seagis-nasa-extractor/`](../../data/seagis-nasa-extractor/), a Python CLI (`seagis-extract`). It pulls daily per-zone statistics from NASA and Copernicus products for the 19 candidate regions, then loads them into the team's Supabase project (`seagis_*` tables). The assistant reads these tables through `seagis_coverage` and `seagis_zone_series`, and the dashboard can use them later.

Goal: real, traceable values with source, version, units and quality flags. No synthetic, gap-filled or proxy values. The extractor computes no risk score and makes no disease claim.

## Work completed

### Zones

| Item | Where | Notes |
| --- | --- | --- |
| 48 zones in 19 regions | [`config/regions.yaml`](../../data/seagis-nasa-extractor/config/regions.yaml), [`data/roi/roi_candidates_v1.geojson`](../../data/seagis-nasa-extractor/data/roi/roi_candidates_v1.geojson) | Each zone is a **5 km seaward buffer of an administrative coastal unit**. It is a candidate area, not a farm extent. |
| Source of each zone | [`config/roi_sources.yaml`](../../data/seagis-nasa-extractor/config/roi_sources.yaml), [`docs/ROI_REVIEW.md`](../../data/seagis-nasa-extractor/docs/ROI_REVIEW.md) | The admin unit and the paper behind each region. |
| Southern Luzon | same | Resolved to **Calatagan, Batangas** (region `PH-S-LUZON`). |
| Bohol split | [`sql/2026-11-15_rename_bohol.sql`](../../data/seagis-nasa-extractor/sql/2026-11-15_rename_bohol.sql) | The old `PH-NE-BOHOL` zone was the whole province, so it became `PH-BOHOL` (Faisan et al. 2021). `PH-NE-BOHOL` stays as a region with **no zone** until the northeastern study coast (Largo et al. 1995) is identified. The SQL was run on the DB on 2026-11-15. |

### Sources (all daily, per zone)

Full list with links, DOIs and licences: [`docs/DATA_SOURCES.md`](../../data/seagis-nasa-extractor/docs/DATA_SOURCES.md).

| Source | Variables (display units) | Grid | Access |
| --- | --- | --- | --- |
| NASA MUR SST L4 | SST (°C), analysis error | 0.01° | Harmony subset, Earthdata Login |
| Copernicus BGC_001_028 | nitrate, phosphate (mmol/m³), pH | 0.25° | Copernicus Marine toolbox |
| Copernicus PHY_001_024 | salinity (PSU); currents `uo`, `vo` (m/s) | 1/12° | Copernicus Marine toolbox |
| derived from `uo`, `vo` | current speed (m/s), direction (°, where the water flows **to**), steadiness (0–1) | 1/12° | computed per zone |
| NASA GPM IMERG Late V07 | precipitation (mm/day) | 0.1° | Harmony subset, Earthdata Login + GES DISC EULA |
| NASA POWER (AG) | air temp, RH, wind 10 m speed and direction (where it blows **from**), solar, PAR, cloud | ~0.5–1° | point API, no account |

### Pipeline

- `plan` reads **metadata only** and writes a plan with a SHA-256 hash (content + inputs). `fetch` refuses to run unless that exact hash was approved. Every request is checked against the approved boxes and grid cells, and raw files are discarded after aggregation. Review notes for each hash: [`docs/PLAN_REVIEW.md`](../../data/seagis-nasa-extractor/docs/PLAN_REVIEW.md).
- `fetch` runs in resumable units recorded in a manifest; finished units are skipped.
- `export` writes to Postgres only with `--confirm-host`. It applies only the extractor's own migrations (an allowlist), never the RAG/env ones.
- Units are relabelled for display at export (`degree_C` → °C, `mmol m-3` → mmol/m³, `1e-3` → PSU, …). Values are unchanged.
- Tests: `pytest` → 88 passed, 1 skipped.

### Data loaded

Supabase project `nasa-seagis`: **82,932 daily rows, 48 zones, 19 regions**, period **2026-08-15 .. 2026-11-14**. Export run `ff59a1d9`, 2026-11-15. Migrations [`20261115000000_seagis_environment.sql`](../../supabase/migrations/20261115000000_seagis_environment.sql) and [`20261115010000_seagis_more_sources.sql`](../../supabase/migrations/20261115010000_seagis_more_sources.sql) are applied.

## Current status and review steps

```bash
cd data/seagis-nasa-extractor
python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest                                   # 88 passed, 1 skipped
seagis-extract plan                      # metadata only; prints the plan hash
seagis-extract fetch --dry-run           # what is still to do, per source
seagis-extract status                    # last full run
```

Credentials (Earthdata, Copernicus, DB DSN) go in `.env` only; see [`HANDOVER.md`](../../data/seagis-nasa-extractor/HANDOVER.md). A download needs the plan hash approved, and a DB write needs `--confirm-host`.

To check the DB, run in the Supabase SQL editor:

```sql
select dataset, variable, units, count(*) from public.seagis_daily_metrics group by 1, 2, 3 order by 1, 2;
```

## Assumptions, limitations, and blockers

### Verified facts

- MUR, Copernicus, IMERG and POWER all returned data for every zone. **504 of 504 units ok**, 0 failed. Sanity ranges: precipitation 0–150 mm/day, current speed up to 1.22 m/s, air temperature 20.5–30.5 °C.
- MUR and IMERG for 2026-11-14 were not yet published on 2026-11-15.
- POWER publishes recent days late. PAR and cloud (from CERES) are empty from 2026-08-31 on. These are stored as rows with an empty mean and the `fill` flag (169 of 644 per zone).
- Some zones have **no sea cell** in the Copernicus mask. Their values are left empty and flagged; there is no proxy or gap filling (decided 2026-11-15).
- IMERG needs each Earthdata account to accept the GES DISC EULA once. Without it, Harmony fails with "75 percent maximum errors exceeded".

### Working decisions (made in chat, 2026-11-15)

- **Period narrowed** to the last three months, all sources (was 2022-06-01, then 2025-11-15), so the full run fits in the challenge time.
- **IMERG `randomError` dropped.** Its values (14,212..68,567, and 2.76 on dry days) did not match the documented mm/day, so only `precipitation` is stored.
- **POWER uses one point per zone** (the polygon's representative point, inside the zone). The values describe a 50–100 km cell, not the zone.
- **Currents direction conventions differ.** Copernicus direction is where the water flows to; POWER wind direction is where the wind comes from. Both are noted in the column comments.
- Copernicus **analysis/forecast (ANFC)** products are used for the recent window. They reach back only to 2019 (PHY) and 2021-10 (BGC).

### Proposals

- **Long-term common window (2003–2024, monthly)** for trend work. See [LONG_TERM_DATA.md](LONG_TERM_DATA.md).
- **Pulau Tidung baseline** for the Seagis iOS app: [`docs/TIDUNG_CONTEXT.md`](../../data/seagis-nasa-extractor/docs/TIDUNG_CONTEXT.md). Nothing has been built or fetched.

### Limitations

- Only MUR (0.01°) is close to zone scale. The other sources are coarse regional context: model or satellite values, never field observations.
- Zones are admin-unit buffers, not farms. The candidate regions are unverified leads ([CANDIDATE_HOST_REGIONS.md](../../research/evidence/CANDIDATE_HOST_REGIONS.md)).
- Three months is too short for trends. The statistical trend work is in [`research/data-access/`](../../research/data-access/README.md) (19 point sites, 2003–2024).
- **No forecast data is stored.** The dashboard's forecast pills have no backing data. The challenge does not require a forecast ([CHALLENGE_2026.md](../CHALLENGE_2026.md)).

## Next steps

- Agree with the research owners whether the zone polygons replace the point sites in `research/data-access/`. The sites differ for Southern Luzon (Tayabas Bay vs Calatagan) and northeastern Bohol.
- If the long-term window is approved: add the monthly products, plan, approve the hash, fetch, and export (needs a new DB table or dataset name).
- Find the northeastern Bohol study coast, then add its zone.
- Re-run `fetch` later to fill MUR/IMERG 2026-11-14 and the POWER fill days.

See [the collaborator context guide](../COLLABORATOR_CONTEXT.md) for shared guidance.
