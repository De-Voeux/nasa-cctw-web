# Preflight plan — 2026-11-15

`seagis-extract plan` (metadata and local geometry only, **0 science bytes**). Outputs (gitignored, reproducible): `outputs/plan.json`, `outputs/estimate.csv` (one row per ROI × month, 511 rows), `outputs/plan_summary.txt`, and `outputs/membership/*.csv.gz` (grid-cell weight table per ROI).

**PLAN SHA256: `9d4122370cd8713e1a605106552e53e1b3a03e7bf0e775f9c53887da310e50fd`**

The hash covers the plan contents and the SHA-256 of every input (catalog, ROI GeoJSON, configs). Timestamps are excluded, so re-running `plan` on unchanged inputs gives the same hash. Any change to the ROIs, the period, or the limits gives a new hash.

## 1. Dataset and coverage

- GHRSST MUR L4 v4.1 (`C1996881146-POCLOUD`). Variables `analysed_sst`, `analysis_error`, `mask`, `sea_ice_fraction`. Access via Harmony HOSS bbox/temporal/variable subset.
- 2020-11-15 .. 2026-11-14: 2190 of 2191 days are published. **2026-11-14 is missing** (not yet released) and stays missing.
- 7 candidate subregions (geometry v1): PH-TAWI bongao, sitangkai, sibutu; ID-SOUTH-SUL takalar, jeneponto, pangkep, selayar.

## 2–5. Estimates

| | LOW | EXPECTED | HIGH |
| --- | ---: | ---: | ---: |
| Transfer, full period | 167 MiB | 473 MiB | 1.03 GiB |
| Peak disk | 18 MiB | 21 MiB | 27 MiB |

- Limits: `max_download_gb` 20 and `max_disk_gb` 30. HIGH is within both.
- Retained raw storage: `discard_after_validation` (default) 0; `archive_subsets` at most 1.03 GiB; `archive_all` (whole global granules) 1.48 TiB.
- Final aggregate: 45,990 rows (7 ROIs × 2190 days × 3 variables). Parquet about 2 MiB, CSV about 10.5 MiB.
- Uncompressed subset arrays: 180 MiB.
- Estimated API calls: 18,907 (one Harmony job per ROI-month plus about 6 status polls, plus one download per daily output file).

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

## 7. Pilot (not run)

7 days (2020-11-15 .. 2020-11-21) for PH-TAWI/bongao and ID-SOUTH-SUL/takalar. Estimated transfer 0.15 / 0.42 / 0.90 MiB and 28 API calls. The pilot checks units, timestamps, latitude order, grid origin, the coastline versus the MUR mask, nulls, actual file size against the estimate, and the outputs. **The `pilot` command is not implemented yet. It needs an Earthdata Login account.**

## 8. Approval

After the pilot is built and run, the command will be:

```bash
.venv/bin/seagis-extract pilot --plan outputs/plan.json --approve-plan 9d4122370cd8713e1a605106552e53e1b3a03e7bf0e775f9c53887da310e50fd
```

Backfill (`fetch`) needs a **new** plan, re-generated after the pilot updates the calibration, and its own approval.
