# Long-term data window (proposal, 2026-11-15)

**Status:** proposal. Nothing has been planned or fetched. A fetch needs a new plan, an approved hash and a DB schema decision.

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
- **Currents:** a monthly mean of `uo`/`vo` gives the mean flow vector, but its magnitude underestimates the mean speed. Either use the daily (P1D) multi-year product for speed and steadiness, or store only the mean vector monthly. Decide this before planning.
- **MUR monthly:** compute monthly means from daily files (all cells in the zone). This is 8,000 days × 48 zones through Harmony, the largest part of the job. A NOAA ERDDAP monthly MUR product may be cheaper; its existence and terms are **not verified**.
- **POWER:** use the same parameters as the daily run, from the monthly endpoint. Add `PRECTOTCORR` only as a cross-check against IMERG.
- **Storage:** `seagis_daily_metrics` is daily. Monthly values need a `seagis_monthly_metrics` table (or a period column), plus a new allowlisted migration.

## 3. Statistics and forecast

- **Statistics already exist:** [`research/data-access/scripts/mk.py`](../../research/data-access/scripts/mk.py) and [`trend.py`](../../research/data-access/scripts/trend.py). No new method is needed. If the zone series are fetched, run the same scripts on them instead of writing new ones.
- **No forecast data exists.** The dashboard's three forecast pills have no data behind them. [CHALLENGE_2026.md](../CHALLENGE_2026.md) says a forecast is not required. If one is wanted later, Copernicus ANFC offers a 10-day ocean forecast. It must stay labelled as a forecast, apart from observations ([METHODOLOGY.md](../METHODOLOGY.md)).

## Decisions needed

1. Approve or change the window (2003–2024, monthly).
2. Southern Luzon: Tayabas Bay or Calatagan for the research site.
3. Currents at monthly scale: daily product or mean vector only.
4. Whether to fetch at all before the submission deadline (2026-11-15 23:59), or to submit with the existing point-site trends plus the three-month zone data.
