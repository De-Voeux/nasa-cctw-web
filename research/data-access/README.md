# Data access — verified catalogue

Status: access tested on 2026-11-15 from a Mac in Jakarta against live endpoints. Every row marked "works" below returned real values in this session; nothing here is copied from documentation alone.

Point series for six Southeast Asian coastal cells were pulled and analysed. The raw downloads, the tidied tables and the trend results are all stored in this folder, about 35 MB in total, so the work can be reviewed without re-downloading anything. The scripts that produce them are in [`scripts/`](scripts/).

Note on repository size: the daily tidy table alone is 31 MB and is fully derived from the raw files. Keeping it here costs clone time; dropping it costs nothing except one command to regenerate.

## Where every value comes from

Every number in this folder was returned by a live request on 2026-11-15. Nothing was typed in, estimated, interpolated or filled by us. Missing values were dropped, never replaced.

The three endpoints, with the exact parameters used:

| Data | Endpoint and parameters |
| --- | --- |
| POWER monthly | `https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M,T2M_MAX,T2M_MIN,T2MDEW,RH2M,QV2M,PS,WS2M,WD2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN&community=AG&longitude=<lon>&latitude=<lat>&start=2003&end=2024&format=CSV` |
| POWER daily | same path under `temporal/daily/point`, `start=20030101&end=20241231` |
| MUR SST | `https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv?analysed_sst[(2003-01-01T09:00:00Z):30:(2024-12-31T09:00:00Z)][(<lat>):1:(<lat>)][(<lon>):1:(<lon>)]` |

Verification performed on 2026-11-15:

- The POWER monthly file for se-sulawesi was re-downloaded and compared with the stored copy: zero differing lines, byte-identical.
- The MUR series for the same site was re-downloaded for January to June 2003 and matched value for value, including repeating decimals such as `30.173000000000002`.
- SHA-256 checksums for all 23 data files are in [`checksums.txt`](checksums.txt). Verify with `shasum -a 256 -c checksums.txt`.

Each raw file also carries its own provenance internally. POWER writes the source, the requested coordinates, the date range, the time standard, the missing-value sentinel, and the full parameter list with units into its header block. MUR writes the time standard and units as its second row.

What is our choice rather than a source:

- The six coordinates. They are regional grid-cell centroids chosen to sit near cultivation areas named in the literature. No official farm registry was consulted, and no claim of farm-level location is made.
- The 30-day sampling of MUR, used to keep 22 years inside one request.
- The aggregation to annual means, and the 0.05 significance threshold. These are methodological decisions, not properties of the data.

## How NASA data arrives

NASA publishes in three very different shapes. Which one you use decides how long the work takes.

| Route | Example | Format | Login | Speed |
| --- | --- | --- | --- | --- |
| Tabular API | NASA POWER | CSV, JSON | none | about 1–2 seconds |
| Subsetting service | Giovanni, AppEEARS, Harmony | CSV, NetCDF | usually Earthdata | minutes |
| Native DAAC archive | GES DISC, PO.DAAC, OB.DAAC | NetCDF-4, HDF5 | Earthdata | hours to days, and very large |

The size people quote for "NASA data" is the native global archive. A full global daily field at 0.01° is hundreds of millions of cells per day. Requesting one grid cell instead of the whole planet is a reduction of roughly eight orders of magnitude, which is why 22 years of a single point is under one megabyte.

## What is downloaded

Six sites, three products, 18 raw files, about 3.7 MB.

| Product | Files | Volume | Period |
| --- | --- | --- | --- |
| NASA POWER monthly | `power/monthly/<site>.csv` | 22 KB each | 2003–2024 |
| NASA POWER daily | `power/daily/<site>.csv` | 590 KB each | 2003–2024 |
| MUR SST, sampled every 30 days | `mur/<site>.csv` | 10 KB each | 2003–2024 |

Tidied long-format tables add `data/power_monthly.csv` (17,424 rows), `data/power_daily.csv` (530,376 rows) and `data/mur_sst.csv` (1,608 rows).

## The datasets, explained

### MUR SST — sea surface temperature

Multi-scale Ultra-high Resolution Sea Surface Temperature, from NASA JPL. One number per point per day: how warm the top of the ocean is. Resolution 0.01°, about 1 km, daily since June 2002.

The variable name is `analysed_sst`. "Analysed" means it is not a raw pixel from one satellite: several satellites are blended with in-situ measurements and gaps under cloud are filled. That makes it complete but still not a measurement at a farm.

Units come back as `degree_C` from the ERDDAP distribution. The native MUR files on PO.DAAC use Kelvin, so never convert twice — check the unit in the file you actually loaded.

This is the most relevant variable for seaweed, because seaweed lives in water, not in air.

### NASA POWER — packaged atmosphere and land surface

POWER is not a satellite. It is a service that packages NASA model output as a time series for a point, in CSV or JSON, with no authentication.

Most variables come from MERRA-2, a NASA reanalysis: a physics model run back across history while ingesting satellite and surface observations. The result is a complete, consistent record with no gaps, but it is model output rather than a thermometer at the site.

One exception: `ALLSKY_SFC_SW_DWN` comes from CERES, not MERRA-2.

POWER serves a MERRA-2 grid cell of 0.5° × 0.625°, roughly 55 × 69 km. Any point inside that cell returns identical numbers, so it cannot separate two farms 10 km apart.

The eleven variables downloaded:

| Code | Meaning | Unit |
| --- | --- | --- |
| T2M | air temperature at 2 m | °C |
| T2M_MAX | daily maximum air temperature | °C |
| T2M_MIN | daily minimum air temperature | °C |
| T2MDEW | dew point | °C |
| RH2M | relative humidity at 2 m | % |
| QV2M | specific humidity at 2 m | g/kg |
| PS | surface pressure | kPa |
| WS2M | wind speed at 2 m | m/s |
| WD2M | wind direction at 2 m | degrees |
| PRECTOTCORR | corrected total precipitation | mm/day |
| ALLSKY_SFC_SW_DWN | all-sky surface shortwave irradiance | MJ/m²/day |

`T2M` is air temperature, not water temperature. That distinction is easy to lose and it matters: air at 28 °C and water at 30 °C are both ordinary, and seaweed responds to the second.

POWER also offers soil wetness, evaporation and other land variables. They were not downloaded because they are not relevant to open water.

### MODIS ocean colour — chlorophyll, Kd490, PAR

Chlorophyll indicates phytoplankton, not seaweed biomass. It is useful as nutrient and water-clarity context and must never be presented as a seaweed measurement. Kd490 describes how quickly light fades with depth, which is closer to the light actually available to a culture line.

Tested through NOAA CoastWatch ERDDAP as CSV without authentication. The monthly chlorophyll product `erdMH1chlamday` runs from January 2003 only to March 2022.

Coverage is the real problem. At the coastal cell -4.0, 123.0 only 78 of 230 months were valid. The rest were masked. Reporting a trend without reporting that coverage would misrepresent the data.

### What was tested and failed

| Product | Result |
| --- | --- |
| GPM IMERG daily (GES DISC) | HTTP 302 redirect to Earthdata Login; blocked without an account |
| PO.DAAC and OB.DAAC direct | request timed out from this network; Earthdata Login required |
| Chlorophyll by OB.DAAC | not attempted further, same authentication barrier |

### What is relevant but not included

| Product | What it measures | Why it is missing |
| --- | --- | --- |
| SMAP salinity | sea surface salinity | 0.25° grid, effective ~60 km, 8-day running mean, Earthdata Login |
| OSCAR | upper-ocean currents, ~30 m average | 0.25°, Earthdata Login |
| GLDAS | soil moisture, runoff, evapotranspiration | NetCDF, Earthdata Login; links rainfall to coastal salinity |
| VIIRS ocean colour | chlorophyll from 2012 | not needed yet; available from the same ERDDAP |
| SWOT | water surface elevation from 2022 | too short a record for trend work |

Salinity is the costliest omission. Lower salinity after heavy rain is the most frequently discussed stress trigger in the seaweed literature, and we cannot currently show it.

### Imagery is not measurement

Blue Marble, MODIS true colour and similar products are visual backgrounds. They cannot count as meaningful NASA data integration in judging, however good they look.

## Sites

Six sites were chosen because they are the regions the literature actually names for *Kappaphycus* and *Eucheuma* cultivation or ice-ice reports, across the four countries the research scope covers. They are not a sample of all Southeast Asian waters, and no other region was tested.

Every row is a regional grid-cell centroid chosen for comparison, not a farm coordinate.

| Site | Country | Latitude | Longitude |
| --- | --- | --- | --- |
| se-sulawesi | Indonesia | -4.0 | 123.0 |
| s-sulawesi | Indonesia | -5.6 | 119.2 |
| sabah | Malaysia | 4.5 | 118.8 |
| tawi-tawi | Philippines | 5.0 | 119.9 |
| bohol | Philippines | 10.0 | 124.5 |
| khanh-hoa | Vietnam | 12.2 | 109.3 |

## File schemas

```
data/power_monthly.csv   site_id, country, lat, lon, variable, unit, year, month, date, value
data/power_daily.csv     site_id, country, lat, lon, variable, unit, date, value
data/mur_sst.csv         site_id, country, lat, lon, variable, unit, date, value
results/trends.csv       site_id, country, lat, lon, variable, unit,
                         n_years, n_months, annual_sens_slope_per_year,
                         annual_mk_z, annual_mk_p,
                         monthly_anom_sens_slope_per_month, monthly_anom_mk_p
```

## Method

Trend headline is computed on annual means, n = 22, using the Mann-Kendall test for significance and Sen's slope for magnitude. Annual means are used rather than monthly values because monthly series are heavily autocorrelated and inflate false positives.

The monthly-anomaly column removes the monthly climatology and is reported for direction only. Its p-value is optimistic and should not be quoted as the headline result.

Missing values are dropped, never filled with zero, so gaps are invisible in the tidy tables unless rows per period are counted.

## Caveats that must travel with any claim

- POWER is reanalysis model output on a ~55 × 69 km cell, not a station measurement.
- MUR here is a single 0.01° cell with no spatial averaging, sampled every 30 days: about 268 values across 22 years, not 8,000 daily values.
- POWER timestamps are local solar time; MUR timestamps are UTC.
- Chlorophyll coverage at coastal cells is poor and highly variable by product.
- Environmental conditions can indicate stress or documented susceptibility. They cannot diagnose disease.

## Reproducing

```bash
cd research/data-access
python3 scripts/fetch.py         # needs curl; system Python may lack a CA bundle
python3 scripts/tidy.py
python3 scripts/trend.py
```

`fetch.py` shells out to `curl` because this machine's Python has no CA certificates and `urllib` fails TLS verification. Running it again re-downloads about 3.7 MB of raw files and rewrites the tidy tables.

## Attribution

NASA data is public. POWER values are MERRA-2 and CERES. MUR is NASA JPL. Both are redistributed as CSV by NOAA CoastWatch ERDDAP, so credit NASA and name the distributor. Do not describe the ERDDAP download as a NASA-hosted API.
