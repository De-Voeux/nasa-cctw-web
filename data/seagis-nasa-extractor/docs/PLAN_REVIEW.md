# Preflight plan — 2026-11-15

`seagis-extract plan` (metadata and local geometry only, **0 science bytes**). Outputs (gitignored, reproducible): `outputs/plan.json`, `outputs/estimate.csv` (one row per ROI × month, 511 rows), `outputs/plan_summary.txt`, and `outputs/membership/*.csv.gz` (grid-cell weight table per ROI).

**PLAN SHA256: `5e8befeee46ed29752fa91ee1f883682213efbeb3c1037402e6158ab21084918`** (calibrated backfill plan; the pilot ran under `85f62d82…`)

The hash covers the plan contents and the SHA-256 of every input (catalog, ROI GeoJSON, configs). Timestamps are excluded, so re-running `plan` on unchanged inputs gives the same hash. Any change to the ROIs, the period, or the limits gives a new hash.

> **Updated 2026-11-15 (IMERG randomError dropped, current plan):** plan hash **`d5e5783e301c7ffde6628df6ead1a6103a534bfb4a95ac1b07ff582c9307511a`**. IMERG now requests `precipitation` only. Calatagan's daily `randomError` was 2.76 on dry days and 50-75× precipitation on wet days, so it is not an mm/day error on the same scale.

> **Updated 2026-11-15 (Bohol rename):** `PH-NE-BOHOL/bohol` was the whole-province coast, so it is now `PH-BOHOL/bohol`. `PH-NE-BOHOL` is kept as a region with no zone. Plan hash `8ad6a1e7…`. The zone, cells and requests are unchanged; only the IDs change, and local outputs were renamed in place.

> **Updated 2026-11-15 (more sources):** three sources added. Plan hash **`4ebfe10c9439485c786ac53eecbda8fb4fad3119437dd22d3c64bd2a2444aa37`** (48 zones; supersedes `af7f572b…`, which added PH-S-LUZON / Calatagan).
> - **Ocean currents.** `cmems_phy_cur`: uo and vo, PHY_001_024, 1/12°, surface, with the same static mask as salinity. Transfer 147 MiB per region. Derived per zone and day:
>   - `current_speed`: weighted mean of per-cell speed.
>   - `current_direction`: direction of the mean vector, in degrees clockwise from north, pointing where the water flows **to**.
>   - `current_steadiness`: \|mean vector\| / mean speed.
> - **Rainfall.** `gpm_imerg`: GPM_3IMERGDL V07 Late daily, 0.1°, via Harmony like MUR. Variables `precipitation` (mm/day). It has 48 boxes, the largest is 440 cells/day, and the transfer is ≤ 128 MiB. 2026-11-14 is not published yet.
> - **Weather.** `nasa_power`: POWER daily point at each zone's representative point (inside the zone). Parameters: T2M, RH2M, WS10M, WD10M (wind **from**), ALLSKY_SFC_SW_DWN, ALLSKY_SFC_PAR_TOT, CLOUD_AMT. 48 requests, no account.
> - **Earlier fetches are unaffected.** MUR and the first three Copernicus datasets keep their unit keys and files, so `fetch` skips them; 258 new units remain.

> **Updated 2026-11-15 (request edges):** every MUR request edge now sits at least a quarter cell inside its expected extent. Tile edges lay exactly on cell boundaries and Harmony returned one extra row there (lat -0.665, batch 2), which the guard rejected. 58 of 73 boxes moved inward; the cells requested are unchanged, so earlier outputs stay valid. New plan hash below.

> **Updated 2026-11-15 (three months):** the period is now **2026-08-15 .. 2026-11-14** for every source (supersedes the one-year note below). Transfer about **527 MiB** (MUR 357 / 396 / 495 MiB LOW / EXPECTED / HIGH, Copernicus 131 MiB per region). Approved plan hash: `3e55cf0ae7ddaaf9bc2cd619380ad1a8703ba769ff031f114e93f4ac6750b336`.

> **Superseded, one year:** the period is now **2025-11-15 .. 2026-11-14** for every source; the 2022-06-01 start below is superseded. Same 47 zones and 73 MUR boxes. Transfer: MUR 1.39 / **1.55** / 1.94 GiB (LOW / EXPECTED / HIGH), Copernicus 393 MiB per region (212 MiB with a shared chunk cache), about **1.9 GiB** in total. 2026-11-14 is not published yet and stays missing. Approved plan hash: `5e8befeee46ed29752fa91ee1f883682213efbeb3c1037402e6158ab21084918`. Data from the earlier partial fetch (2022-06..2024-02) was deleted; its manifest is in `outputs/archive_2022-2026/`.

> **Updated 2026-11-15:** all sources now start **2022-06-01**, the first day of daily Copernicus salinity. The plan also covers the Copernicus Marine datasets no3, po4, pH and salinity. Their transfer is exact, 129.4 MiB; see [COPERNICUS_REVIEW.md](COPERNICUS_REVIEW.md). Combined transfer is about 481 MiB. The tables below are the MUR part.
>
> **Updated 2026-11-15 (calibrated backfill plan):** this plan is re-generated from the pilot. MUR transfer comes from a fit of the pilot's 14 files: 58,790 bytes per file + 1.07 bytes per cell, with a maximum residual of 0.1%. LOW/HIGH are 0.9× and 1.25× of the fit.
>
> - **MUR** requests only `analysed_sst`, `analysis_error` and `mask`. `sea_ice_fraction` is dropped because it is always empty here.
> - **MUR transfer:** 6.23 / **6.92** / 8.65 GiB (LOW / EXPECTED / HIGH).
> - **Copernicus** is fetched per region: 1.46 GiB.
> - **Total about 8.4 GiB**, within the 20 GB limit.
> - **Work:** 2,589 units = 2,538 MUR ROI-months (3,942 Harmony jobs, 118,771 daily files) + 51 Copernicus dataset × region units.
> - **Final output:** 152,938 MUR daily rows in Parquet (~7 MiB) plus the Copernicus rows.
>
> **Updated 2026-11-15 (all regions):** the plan now covers **47 zones in 17 regions** (Southern Luzon pending: not an administrative unit). Totals for 2022-06-01 .. 2026-11-14: MUR 1.39 / **3.78** / 9.02 GiB (LOW / EXPECTED / HIGH), Copernicus **803 MiB** with a shared chunk cache (1.46 GiB if each region is fetched separately). Grand total about **4.6 GiB**, within the 20 GB download limit. Zones wider than 1° are split into tiles of at most 10,000 cells/day: **73 MUR boxes** for 47 zones, each tied to its zone, with tiles checked for full coverage and no overlap. Estimated API calls: about 146,000, mostly one download per daily file per box. The per-ROI tables below still describe the first 7 zones; the full list is in `outputs/estimate.csv` and `plan.json`.
>
> **Updated 2026-11-15 (sea check):** the Copernicus static land/sea masks (65 KB, public) confirm every zone has sea cells in every Copernicus dataset (3–7 for no3/po4/pH, 8–39 for salinity); see the table in COPERNICUS_REVIEW.md. The hash changed because the mask checksums and per-zone sea counts are now part of the plan. The MUR numbers did not change. MUR's own land mask can only be checked in the pilot.

## 1. Dataset and coverage

- GHRSST MUR L4 v4.1 (`C1996881146-POCLOUD`). Variables `analysed_sst`, `analysis_error`, `mask`, `sea_ice_fraction`. Access via Harmony HOSS bbox/temporal/variable subset.
- 2022-06-01 .. 2026-11-14: 1627 of 1628 days are published. **2026-11-14 is missing** (not yet released) and stays missing.
- 7 candidate subregions (geometry v1): PH-TAWI bongao, sitangkai, sibutu; ID-SOUTH-SUL takalar, jeneponto, pangkep, selayar.

## Download scope (guarded)

Only seven small boxes are ever requested, one per ROI, each the ROI's own bounding box rounded out to 0.0001°. Nothing global and nothing outside these regions is requested. Maps: `outputs/qa/requests_overview.png` and `requests_<region>.png`.

| ROI | Request W, S, E, N | Cells/day |
| --- | --- | ---: |
| PH-TAWI/bongao | 119.6911, 4.9602, 119.8976, 5.2040 | 550 |
| PH-TAWI/sitangkai | 118.9855, 4.5693, 119.4445, 4.9518 | 1794 |
| PH-TAWI/sibutu | 119.4196, 4.5421, 119.5521, 4.9591 | 602 |
| ID-SOUTH-SUL/takalar | 119.1448, −5.6526, 119.5130, −5.2141 | 1710 |
| ID-SOUTH-SUL/jeneponto | 119.4979, −5.7482, 119.9476, −5.5374 | 1012 |
| ID-SOUTH-SUL/pangkep | 118.9052, −5.0023, 119.5962, −4.4441 | 3990 |
| ID-SOUTH-SUL/selayar | 120.2243, −6.7620, 120.6133, −5.7039 | 4280 |

Enforced in code (`estimate.check_request`, tested):

- `plan` fails if a request does not cover its ROI, extends more than one grid cell (0.01°) beyond it, or needs more than `max_request_cells` (10,000 per day) cells.
- These requests are part of the hashed plan, so changing any box changes the hash and needs a new approval.

Rules that `fetch` must follow (recorded in `plan.json` `fetch_guards`, to be enforced when `fetch` is built): send only the listed requests; reject and delete any response whose coordinates fall outside the expected extent or whose cell count differs; use only pixels in the ROI membership table. The rest of each rectangle (33–64% of cells: land, or sea outside the 5 km zone) is discarded after masking.

## 2–5. Estimates

| | LOW | EXPECTED | HIGH |
| --- | ---: | ---: | ---: |
| Transfer, full period | 124 MiB | 352 MiB | 785 MiB |
| Peak disk | 15 MiB | 17 MiB | 24 MiB |

- Limits: `max_download_gb` 20 and `max_disk_gb` 30. HIGH is within both.
- Retained raw storage: `discard_after_validation` (default) 0; `archive_subsets` at most 785 MiB; `archive_all` (whole global granules) 1.10 TiB.
- Final aggregate: 34,167 rows (7 ROIs × 1627 days × 3 variables). Parquet about 1.5 MiB, CSV about 7.8 MiB.
- Uncompressed subset arrays: 134 MiB.
- Estimated API calls: 14,035 (one Harmony job per ROI-month plus about 6 status polls, plus one download per daily output file).

Per ROI (cells per day):

| ROI | bbox cells | ROI cells | efficiency |
| --- | ---: | ---: | ---: |
| PH-TAWI/bongao | 550 | 318 | 0.58 |
| PH-TAWI/sitangkai | 1794 | 667 | 0.37 |
| PH-TAWI/sibutu | 602 | 406 | 0.67 |
| ID-SOUTH-SUL/takalar | 1710 | 669 | 0.39 |
| ID-SOUTH-SUL/jeneponto | 1012 | 391 | 0.39 |
| ID-SOUTH-SUL/pangkep | 3990 | 1506 | 0.38 |
| ID-SOUTH-SUL/selayar | 4280 | 1532 | 0.36 |

Shared fetch: per-ROI bboxes overlap very little (PH 2946 → 2829 unique cells; ID 10992 → 10968). One bbox per region would cut jobs and files about 3.5×, but would fetch 6164 (PH) and 39843 (ID) cells per day. Both options are small in bytes. The choice affects the API call count, not the budget.

## 6. Uncertainty

- **Transfer is LOW confidence.** The subsets are tiny (550–4280 cells × 6 bytes per day), so the assumed per-file NetCDF overhead (10/30/60 KB) dominates the totals. HIGH assumes HOSS does not compress. The pilot will measure both.
- **Grid origin is assumed** (lat −89.99 + 0.01·i, lon −179.99 + 0.01·j). It matches the UMM-Var dimensions but is not stated in the metadata. Latitude order is unverified.
- **Final row sizes** come from a schema model with no calibration sample.
- Harmony rate limits and poll counts are unknown.
- ROI coastlines come from admin polygons and are not yet compared with the MUR `mask`.

## 7. Pilot (implemented, not run)

**Scope.** The pilot runs for 7 days (2022-06-01 .. 2022-06-07) on PH-TAWI/bongao and ID-SOUTH-SUL/takalar, for MUR and for the three Copernicus datasets. Estimated MUR transfer is 0.15 / 0.42 / 0.90 MiB. A hard budget of 5 MiB aborts the run if it is exceeded.

**What happens, in order:**

1. **Gate.** The pilot refuses to start unless all of these hold:
   - `--approve-plan` equals `plan_sha256`;
   - plan.json still hashes to that value, so it has not been edited;
   - every input file (catalog, ROI GeoJSON, configs) is unchanged;
   - no zone without sea cells is left unaccepted.
2. **MUR.** One Harmony job is sent per approved box. Only the boxes in `rois[].mur_requests` are allowed, and the time window selects exactly the granules dated 1–7 June. The Earthdata token is sent only to Earthdata/Harmony hosts and is stripped on redirects to S3.
   - Files that arrive with an unexpected date are not downloaded.
   - Any file whose cells fall outside the approved extent is **deleted**, and the run aborts with exit code 5.
3. **Copernicus.** The official toolbox (`copernicusmarine.open_dataset`) is used with the ROI box, the 7 days and the surface level only. A subset outside the box plus one cell aborts the run.
4. **Checks.** Each check is reported as PASS, WARN or FAIL:
   - MUR cell count vs plan
   - latitude order
   - grid origin and index range (the assumed grid)
   - timestamps
   - units
   - SST value range
   - fill fraction
   - days returned
   - zone cells that MUR's own mask calls land or lake (the coastline check)
   - transfer vs estimate
   - Copernicus cell count, dates, depth, and sea cells valid / land cells empty
5. **Outputs:**
   - `outputs/pilot/pilot_report.json`
   - `outputs/pilot/pilot_daily.csv` (`FINAL_SCHEMA`: area-weighted daily mean, min, max, std and coverage per zone and variable)
   - `outputs/pilot/pilot_summary.txt`
   - a resumable manifest, `pilot_manifest.jsonl`

   Raw pilot files are kept in `data/raw/pilot/` (gitignored) for inspection.

Exit codes: 0 PASS, 2 refused by the gate, 4 a check FAILED or an auth/HTTP error, 5 aborted by a download guard.

**Not yet verified live.** Two Harmony details are only covered by fakes in tests: the comma-separated `variable=` parameter, and the job/link format. The pilot is what verifies them.

## 7b. Pilot result (run 2026-11-15, plan 85f62d82…) — PASS

Run with the user's approval for 2022-06-01 .. 2022-06-07 on PH-TAWI/bongao and ID-SOUTH-SUL/takalar. Outputs are in `outputs/pilot/` (98 daily rows), and the raw files (~1 MB) are in `data/raw/pilot/`.

| Check | Result |
| --- | --- |
| MUR grid origin and order | **Confirmed.** Cells sit within 4e-6° of the assumed grid, latitude is ascending, and the index ranges equal the plan exactly. |
| MUR cell count, units, timestamps, value range | All PASS (kelvin, 09:00 UTC, 7/7 days for each zone). |
| MUR coastline vs mask | WARN, as expected. 54/318 Bongao cells and 72/669 Takalar cells are land/lake in MUR's own mask, and they are dropped. **MUR fills land with SST values** (fill fraction 0), so excluding land by mask, not by NaN, is required. |
| `sea_ice_fraction` | Always empty in these waters. Candidate to drop from the outputs. |
| Copernicus | All PASS after the fix: dates, surface depth 0.494 m, every sea cell valid, land cells empty. The toolbox returns one extra row/column around the box, which is now cropped to the plan's cells before saving. |

Pilot values for 1–7 June 2022:

| | Bongao | Takalar |
| --- | --- | --- |
| SST | 29.4–29.6 °C | 29.3–30.2 °C |
| pH | 8.03 | 8.02 |
| Salinity | 33.5–33.8 | 33.3–33.4 |
| no3 | 0.007–0.009 mmol m-3 | 0.010–0.013 mmol m-3 |
| po4 | 0.054–0.063 mmol m-3 | 0.112–0.119 mmol m-3 |

**Calibration.** MUR files are about 59 KB each, of which about 58.8 KB is fixed overhead per file plus about 1 byte per cell. The plan's EXPECTED estimate (439 KB for the pilot) was low; actual was 840 KB, within HIGH (939 KB). For the full backfill as planned (73 boxes × 1,627 days = 118,771 files), that gives **about 6.9 GiB of MUR**, against the plan's 3.78 EXPECTED and 9.02 HIGH. Because the cost is per file, not per cell, the number of boxes drives both size and API calls.

**Fixed during the pilot** (each failure stopped safely before or without keeping data):

- Harmony needs one `variable=` per variable.
- Async submits answer with `303 → /jobs/<id>`.
- The MUR extent guard compared float32 coordinates too strictly. It now compares grid indices; one extra column outside the box is still rejected (tested).

## 7c. Fetch (implemented, not run)

`seagis-extract fetch` uses the same gate as the pilot. It also refuses a plan that is not calibrated from a PASSing pilot.

**Units, all resumable** (`outputs/fetch/fetch_manifest.jsonl`):

- **MUR**, per ROI × month. Up to `concurrency` (4) Harmony jobs run in parallel. Every file is guarded and checked. Each day is aggregated over the ROI's MUR-mask sea cells. The month is written to `data/processed/mur_sst/<region>/<zone>/<YYYY-MM>.parquet`, and then the raw NetCDF is deleted.
- **Copernicus**, per dataset × region, whole period. Each zone is cropped to its plan cells and written to `data/processed/<dataset>/<region>/<zone>.parquet`.

**Order.** Pilot regions come first. A guard violation stops the run. Other unit errors are retried (`retries`), then recorded as failed while the run continues. A rerun skips finished units.

**Options:**

- `--dry-run` counts the work.
- `--max-units N` stops after N units, for example to measure speed.
- `--concurrency N` (1-16) runs N units at once instead of `execution.concurrency` (4). Speed only: the plan hash and the downloaded boxes do not change. The bottleneck is Harmony subsetting, about 5 s per daily file (a month takes ~150 s), not bandwidth. If Harmony returns 429 (too many requests), lower N; failed units retry and can be rerun.
- `seagis-extract status --batch N` is read-only: units done and remaining for the batch, whether a fetch holds the lock, elapsed time, and an ETA from the units finished in this run (start count read from `outputs/fetch/batchN.log`). Without `--batch` it counts every unit in the plan.
- `--region` (repeatable) limits the run to given regions.
- `--source mur|copernicus|imerg|power` limits the run to one source (`copernicus` includes currents).

## 8. Approval

Preview the exact requests first. This sends nothing:

```bash
.venv/bin/seagis-extract pilot --dry-run
```

Run the pilot. Credentials are read from the gitignored `.env`, and values are never printed:

```bash
.venv/bin/seagis-extract pilot --approve-plan 85f62d82722154f277094cf0b8fd330d6118eed5283d36c5018ff6a5746bdbc7
```

Backfill, after reviewing this calibrated plan:

```bash
.venv/bin/seagis-extract fetch --dry-run
```

```bash
.venv/bin/seagis-extract fetch --approve-plan 5e8befeee46ed29752fa91ee1f883682213efbeb3c1037402e6158ab21084918
```
