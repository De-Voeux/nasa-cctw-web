# Preflight plan — 2026-11-15

`seagis-extract plan` (metadata and local geometry only, **0 science bytes**). Outputs (gitignored, reproducible): `outputs/plan.json`, `outputs/estimate.csv` (one row per ROI × month, 511 rows), `outputs/plan_summary.txt`, and `outputs/membership/*.csv.gz` (grid-cell weight table per ROI).

**PLAN SHA256: `85f62d82722154f277094cf0b8fd330d6118eed5283d36c5018ff6a5746bdbc7`**

The hash covers the plan contents and the SHA-256 of every input (catalog, ROI GeoJSON, configs). Timestamps are excluded, so re-running `plan` on unchanged inputs gives the same hash. Any change to the ROIs, the period, or the limits gives a new hash.

> **Updated 2026-11-15:** all sources now start **2022-06-01**, the first day of daily Copernicus salinity. The plan also covers the Copernicus Marine datasets no3, po4, pH and salinity. Their transfer is exact, 129.4 MiB; see [COPERNICUS_REVIEW.md](COPERNICUS_REVIEW.md). Combined transfer is about 481 MiB. The tables below are the MUR part.
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

## 8. Approval

Preview the exact requests first. This sends nothing:

```bash
.venv/bin/seagis-extract pilot --dry-run
```

Run the pilot. Credentials are read from the gitignored `.env`, and values are never printed:

```bash
.venv/bin/seagis-extract pilot --approve-plan 85f62d82722154f277094cf0b8fd330d6118eed5283d36c5018ff6a5746bdbc7
```

Backfill (`fetch`) needs a **new** plan, re-generated after the pilot updates the calibration, and its own approval.
