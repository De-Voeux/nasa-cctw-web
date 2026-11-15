# Long-term data window (proposal, 2026-11-15)

**Status:** fetch plan written and three decisions made (2a). Nothing has been built or downloaded. A fetch still needs the code, a new plan and an approved hash.

## 1. How the extractor and `research/data-access/` line up

[`research/data-access/`](../../research/data-access/README.md) already holds a 2003–2024 trend analysis: Mann-Kendall + Sen's slope on annual means, 228 site–variable rows in `results/trends.csv`. The extractor holds three months of daily zone values. Both cover the same 19 regions. The differences:

| | `research/data-access` | extractor |
| --- | --- | --- |
| Spatial unit | 19 points, one grid cell each | 48 zones (5 km sea buffer of admin units), area-weighted over all cells in the zone |
| Period | 2003-01 .. 2024-12 | 2026-08-15 .. 2026-11-14 |
| SST | MUR via ERDDAP, one cell, every 30th day | MUR via Harmony, daily, all cells in the zone |
| Weather | POWER monthly: T2M (+max/min, dew), RH2M, QV2M, PS, **WS2M, WD2M**, **PRECTOTCORR**, ALLSKY_SFC_SW_DWN | POWER daily: T2M, RH2M, **WS10M, WD10M**, ALLSKY_SFC_SW_DWN, PAR, cloud |
| Rain | POWER PRECTOTCORR (MERRA-2) | GPM IMERG Late (satellite) |
| Ocean | none | Copernicus salinity, currents, nitrate, phosphate, pH |

**Sites that disagree:**

- **Southern Luzon.** The research site is Tayabas Bay (13.7, 121.6). The extractor uses Calatagan, Batangas, because the review's "Southern Luzon" source (Solis et al. 2010) sampled at Calatagan. Calatagan is also the research `batangas` site (13.8, 120.4), so the research `southern-luzon` series probably describes the wrong place. **Decision needed from the research owner.**
- **Northeastern Bohol.** The research site is offshore Candijay (9.9, 124.6). The extractor has no zone for it yet (Largo et al. 1995 coast not identified). The research notes already say that `bohol` and `ne-bohol` share one POWER cell.

These are noted here only; the research files and their checksums were not changed.

## 2. Proposed common window

**2003-01 .. 2024-12, monthly, the same 48 zones, the same aggregation.** No source goes further back than the others.

| Source (long-term product) | Available | Limits the window? |
| --- | --- | --- |
| MUR SST L4 | 2002-06 → present | **start**: first full year is 2003 |
| GPM IMERG **Final** (`GPM_3IMERGM`, monthly) | 1998-01 → 2025-09 | **end**: last full year is 2024 |
| Copernicus PHY multi-year (`cmems_mod_glo_phy_my_0.083deg_P1M-m`) | 1993-01 → 2026-08 | no |
| Copernicus BGC multi-year (`cmems_mod_glo_bgc_my_0.25deg_P1M-m`) | 1993-01 → 2026-08 | no |
| NASA POWER monthly (MERRA-2 / CERES) | 1981 / ~1984 → present | no |

The dates were read from CMR and Copernicus metadata on 2026-11-15. This window matches the one `research/data-access/` already uses, so its scripts and results stay comparable.

### Rules

- **Do not splice products.** The recent window uses IMERG Late and Copernicus ANFC. The long-term window uses IMERG Final and Copernicus multi-year, which are different datasets. Keep them as separate `dataset` names and never fit one trend across the join.
- **Currents:** a monthly mean of `uo`/`vo` gives the mean flow vector, but its magnitude underestimates the mean speed. Decided: mean vector only (see 2a).
- **MUR monthly:** use NOAA ERD's monthly mean of daily MUR (`jplMURSST41mday`, checked below). It is a NOAA-derived product: credit NASA JPL MUR and name NOAA ERD as distributor, as `research/data-access` already does. Two months are missing there (see 2a).
- **POWER:** use the same parameters as the daily run, from the monthly endpoint. Add `PRECTOTCORR` only as a cross-check against IMERG.
- **Storage:** `seagis_daily_metrics` is daily. Monthly values need a `seagis_monthly_metrics` table (or a period column), plus a new allowlisted migration.

## 2a. Fetch plan (metadata checked 2026-11-15, nothing downloaded)

Monthly values for 2003-01 .. 2024-12 (264 months), the same 48 zones and the same area weighting as the daily run.

| Source | Product | Access | Checked | Requests | Transfer (est.) | Time (est.) |
| --- | --- | --- | --- | --- | --- | --- |
| SST | NOAA ERD `jplMURSST41mday`: monthly mean of daily MUR, 0.01°, same grid as MUR | ERDDAP griddap subset (NetCDF), no account | 2002-06 → 2026-10; **291 of 293 months: 2023-06 and 2025-12 are missing** | ~50 boxes × 22 years | ~200 MB | 30–60 min |
| Rain | GPM IMERG Final monthly `GPM_3IMERGM` V07 (C2723754851) | Harmony subset, like daily IMERG | 264 of 264 granules | ~50 boxes | < 20 MB | 15–30 min |
| Salinity | Copernicus `cmems_mod_glo_phy_my_0.083deg_P1M-m_202311` (`so`) | ARCO Zarr, like today | 1993-01 → 2026-08 | 19 regions | < 100 MB | ~10 min |
| Currents | same product, `uo`, `vo`: monthly (P1M) or daily (P1D, `cmems_mod_glo_phy_my_0.083deg_P1D-m_202311`) | ARCO Zarr | both 1993 → 2026 | 19 regions | P1M small; P1D a few hundred MB | 10–40 min |
| Nutrients, pH | `cmems_mod_glo_bgc_my_0.25deg_P1M-m_202406` (`no3`, `po4`, `ph`) | ARCO Zarr | 1993-01 → 2026-08 | 19 regions | < 50 MB | ~5 min |
| Weather | POWER monthly point, same 7 parameters | POWER API | all 7 have MONTHLY | 48 | < 5 MB | ~2 min |

Static masks exist for both multi-year products (`..._static_202311--ext--bathy`, `..._static_202406--ext--mask`). Expected result: about 230,000 monthly rows.

Daily MUR through Harmony is ruled out: the 91-day run needed about 8,800 calls, so 22 years would need about 775,000 calls and ~37 GB.

### Code needed

1. A `cadence: monthly` setting. Plan, fetch and process key rows by month start, not by day.
2. An ERDDAP client: URL allowlist, the MUR 0.01° grid guard, no credentials. Same membership tables as MUR.
3. IMERG monthly. The units are expected to be mm/hr (to be confirmed in the plan); if so, store × 24 as mm/day and say so in `qc_flags`.
4. POWER monthly parser. It drops month "13" (the annual value).
5. New table `seagis_monthly_metrics` (allowlisted migration) and an export option for it.
6. Tests for each new part.

Then: `plan` → review and approve the hash → `fetch` → `export --confirm-host`. Afterwards, run `research/data-access/scripts/trend.py` on the zone series.

Rough total: 3–4 h code and tests, 1–2 h fetch, 1 h export and trends.

### Decided (user, 2026-11-15)

- **MUR 2023-06 and 2025-12:** keep the rows with an empty value and a `missing_at_source` flag. Do not compute them from daily MUR. (2025-12 is outside the window anyway.)
- **Currents:** monthly P1M `uo`, `vo`, so the long-term table holds only the mean flow vector. Store `uo`, `vo`, `current_direction` (of the mean vector) and `current_vector_speed` (|mean vector|). The monthly table has **no** `current_speed` or `current_steadiness`, because a monthly mean vector underestimates mean speed. The name `current_vector_speed` keeps it from being read as the daily `current_speed`. Transfer stays small (~10 min).
- **Storage:** new table `seagis_monthly_metrics` with its own allowlisted migration. Daily and monthly rows never share a table.

## 3. Statistics and forecast

- **Statistics already exist:** [`research/data-access/scripts/mk.py`](../../research/data-access/scripts/mk.py) and [`trend.py`](../../research/data-access/scripts/trend.py). No new method is needed. If the zone series are fetched, run the same scripts on them instead of writing new ones.
- **No forecast data exists.** The dashboard's three forecast pills have no data behind them. [CHALLENGE_2026.md](../CHALLENGE_2026.md) says a forecast is not required. If one is wanted later, Copernicus ANFC offers a 10-day ocean forecast. It must stay labelled as a forecast, apart from observations ([METHODOLOGY.md](../METHODOLOGY.md)).

## Decisions needed

1. Approve or change the window (2003–2024, monthly).
2. Southern Luzon: Tayabas Bay or Calatagan for the research site.
3. Whether to fetch at all before the submission deadline (2026-11-15 23:59), or to submit with the existing point-site trends plus the three-month zone data.
