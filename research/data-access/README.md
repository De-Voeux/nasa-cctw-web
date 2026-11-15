# Data access — verified catalogue

Status: access tested on 2026-11-15 from a Mac in Jakarta against live endpoints. Every row marked "works" below returned real values in this session; nothing here is copied from documentation alone.

Point series for nineteen Southeast Asian coastal cells were pulled and analysed. The raw downloads, the tidied tables and the trend results are all stored in this folder, about 16 MB in total, so the work can be reviewed without re-downloading anything. The scripts that produce them are in [`scripts/`](scripts/).

The nineteen sites are the ice-ice regions recorded in [`research/evidence/`](../evidence/), reduced to one regional cell each. That evidence table is still unverified against the primary papers, so treat the site list as a working set, not a confirmed distribution map.

Note on repository size: the daily tidy table is derived from the raw files and nothing reads it, so `tidy.py` skips it by default. Passing `--with-daily` builds it, which takes about 98 MB and roughly two minutes.

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
- After the nineteen-site pull, the POWER monthly file and the full MUR series for maluku were re-downloaded from scratch and compared: zero differing lines in both.
- SHA-256 checksums for all 60 data files are in [`checksums.txt`](checksums.txt). Verify with `shasum -a 256 -c checksums.txt`.

Each raw file also carries its own provenance internally. POWER writes the source, the requested coordinates, the date range, the time standard, the missing-value sentinel, and the full parameter list with units into its header block. MUR writes the time standard and units as its second row.

What is our choice rather than a source:

- The nineteen coordinates. They are regional grid-cell centroids chosen to sit near cultivation areas named in the literature. No official farm registry was consulted, and no claim of farm-level location is made. Each candidate was probed once against the MUR endpoint first; two points that returned `NaN` because the cell was land were moved offshore.
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

Nineteen sites, three products, 57 raw files, about 12 MB.

| Product | Files | Volume | Period |
| --- | --- | --- | --- |
| NASA POWER monthly | `power/monthly/<site>.csv` | 22 KB each | 2003–2024 |
| NASA POWER daily | `power/daily/<site>.csv` | 590 KB each | 2003–2024 |
| MUR SST, sampled every 30 days | `mur/<site>.csv` | 10 KB each | 2003–2024 |

Tidied long-format tables add `data/power_monthly.csv` (55,176 rows: 19 sites × 11 variables × 264 months) and `data/mur_sst.csv` (5,092 rows: 19 sites × 268 timesteps). `data/power_daily.csv` is not stored; build it with `python3 scripts/tidy.py --with-daily` if you need it.

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

The nineteen sites are the ice-ice regions listed in [`research/evidence/`](../evidence/) for *Kappaphycus* and *Eucheuma*, one regional cell each, across the four countries the research scope covers. The literature rows themselves are still marked unverified; this folder only guarantees the NASA numbers at these coordinates.

Every row is a regional grid-cell centroid chosen for comparison, not a farm coordinate. Each coordinate was probed against the MUR endpoint before the pull. Two candidates returned `NaN` because the cell was land and were moved offshore: Palawan from 9.8, 118.7 to 9.8, 118.3, and Zamboanga City from 6.9, 122.1 to 6.8, 122.0.

| Site | Region | Country | Latitude | Longitude |
| --- | --- | --- | --- | --- |
| se-sulawesi | Southeast Sulawesi, Konawe coast | Indonesia | -4.0 | 123.0 |
| s-sulawesi | South Sulawesi, Takalar coast | Indonesia | -5.6 | 119.2 |
| c-sulawesi | Central Sulawesi, Banggai coast | Indonesia | -1.0 | 122.8 |
| n-kalimantan | North Kalimantan, Tarakan coast | Indonesia | 3.3 | 117.7 |
| maluku | Maluku, Kei Islands | Indonesia | -5.6 | 132.7 |
| n-java-sea | North Java Sea, Jepara offshore | Indonesia | -5.8 | 110.5 |
| wnt | West Nusa Tenggara, East Lombok | Indonesia | -8.9 | 116.5 |
| sabah | Sabah, Semporna coast | Malaysia | 4.5 | 118.8 |
| tawi-tawi | Tawi-Tawi, Bongao coast | Philippines | 5.0 | 119.9 |
| bohol | Bohol Sea | Philippines | 10.0 | 124.5 |
| ne-bohol | Northeastern Bohol, Candijay offshore | Philippines | 9.9 | 124.6 |
| zamboanga | Zamboanga City, Basilan Strait | Philippines | 6.8 | 122.0 |
| davao-del-norte | Davao del Norte, Davao Gulf | Philippines | 7.2 | 125.7 |
| pangasinan | Pangasinan, Lingayen Gulf | Philippines | 16.4 | 119.8 |
| batangas | Batangas, Calatagan coast | Philippines | 13.8 | 120.4 |
| southern-luzon | Southern Luzon, Tayabas Bay | Philippines | 13.7 | 121.6 |
| eastern-samar | Eastern Samar, Borongan coast | Philippines | 11.6 | 125.6 |
| palawan | Palawan, Sulu Sea | Philippines | 9.8 | 118.3 |
| khanh-hoa | Khanh Hoa coast | Vietnam | 12.2 | 109.3 |

Two of these sites are not independent samples. `bohol` and `ne-bohol` fall in the same MERRA-2 cell, so ten of the eleven POWER variables are byte-identical between them; only `ALLSKY_SFC_SW_DWN` differs, because CERES uses a different grid. Their MUR series do differ. Any count of "19 sites" must therefore be read as 19 coordinate points, not 19 independent atmospheric samples. This was checked by hashing each variable series across all sites; no other pair shares values.

## File schemas

```
data/power_monthly.csv   site_id, country, lat, lon, variable, unit, year, month, date, value
data/mur_sst.csv         site_id, country, lat, lon, variable, unit, date, value
data/power_daily.csv     site_id, country, lat, lon, variable, unit, date, value
                         (only written with --with-daily)
results/trends.csv       site_id, country, lat, lon, variable, unit,
                         n_years, n_months, annual_sens_slope_per_year,
                         annual_mk_z, annual_mk_p,
                         monthly_anom_sens_slope_per_month, monthly_anom_mk_p
```

## Method

Trend headline is computed on annual means, n = 22, using the Mann-Kendall test for significance and Sen's slope for magnitude. Annual means are used rather than monthly values because monthly series are heavily autocorrelated and inflate false positives.

The monthly-anomaly column removes the monthly climatology and is reported for direction only. Its p-value is optimistic and should not be quoted as the headline result.

Missing values are dropped, never filled with zero, so gaps are invisible in the tidy tables unless rows per period are counted.

### What the nineteen-site run produced

228 site–variable combinations in `results/trends.csv`, 114 significant at p < 0.05. Per variable, out of 19 sites:

| Variable | Significant | Share |
| --- | --- | --- |
| QV2M, T2MDEW | 18 | 95% |
| T2M | 17 | 89% |
| MUR SST | 16 | 84% |
| T2M_MIN | 16 | 84% |
| WS2M | 11 | 58% |
| T2M_MAX | 9 | 47% |
| RH2M | 5 | 26% |
| PRECTOTCORR | 4 | 21% |
| PS, WD2M, ALLSKY_SFC_SW_DWN | 0 | 0% |

Sea surface temperature rises in every site; the slope ranges from +0.023 °C/yr at wnt and c-sulawesi to +0.047 °C/yr at n-kalimantan and maluku, and it is not significant at three sites (wnt, s-sulawesi, c-sulawesi).

Precipitation is the variable that justifies the site list rather than a global average: it is significant and negative at tawi-tawi (−0.077 mm/day/yr, p = 0.032) while being significant and positive at se-sulawesi (+0.132, p = 0.007), khanh-hoa (+0.116, p = 0.037) and maluku (+0.081, p = 0.015). The other fifteen sites show no significant rainfall trend. That is the challenge's own point about one process trending in opposite directions, and it holds across the wider set as well.

The 228 rows must be read against multiplicity: testing 228 combinations at α = 0.05 will flag about 11 purely by chance. No correction is applied. Treat each p-value as a description of one series, not as a validated discovery.

## Caveats that must travel with any claim

- POWER is reanalysis model output on a ~55 × 69 km cell, not a station measurement.
- `bohol` and `ne-bohol` share one POWER cell, so their atmospheric numbers are the same series counted twice.
- MUR here is a single 0.01° cell with no spatial averaging, sampled every 30 days: about 268 values across 22 years, not 8,000 daily values.
- POWER timestamps are local solar time; MUR timestamps are UTC.
- Chlorophyll coverage at coastal cells is poor and highly variable by product.
- Nineteen p-values per variable, 228 in total, with no multiplicity correction. Roughly 11 false positives are expected at α = 0.05.
- Environmental conditions can indicate stress or documented susceptibility. They cannot diagnose disease.

## Reproducing

```bash
cd research/data-access
python3 scripts/fetch.py         # needs curl; system Python may lack a CA bundle
python3 scripts/tidy.py          # add --with-daily for the 98 MB daily table
python3 scripts/trend.py
```

`fetch.py` shells out to `curl` because this machine's Python has no CA certificates and `urllib` fails TLS verification. Running it again re-downloads about 12 MB of raw files and rewrites the tidy tables. It also rewrites `sites.json`, which is the input `tidy.py` reads.

ERDDAP returns HTTP 503 when requests arrive back to back, so `fetch.py` pauses three seconds between sites and retries up to four times. A full nineteen-site run takes about ten minutes, almost all of it MUR.

## Attribution

NASA data is public. POWER values are MERRA-2 and CERES. MUR is NASA JPL. Both are redistributed as CSV by NOAA CoastWatch ERDDAP, so credit NASA and name the distributor. Do not describe the ERDDAP download as a NASA-hosted API.
