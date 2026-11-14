# Catalog review — 2026-11-15

Source: `seagis-extract catalog` against NASA CMR, Harmony `/capabilities`, and one HEAD request (metadata only, **0 science bytes**). Raw results: `outputs/catalog.json` (gitignored; regenerate with the command). Period: 2020-11-15 .. 2026-11-14 (start moved from 2020-01-01 in `config/extraction.yaml` on 2026-11-15).

## Scope decision (2026-11-15)

**SST only.** Chlorophyll-a is out of scope for this extractor, by the user's decision after the first catalog review. The parts of [TASK.md](../TASK.md) about chlorophyll no longer apply. For the record, that review found no provider-side subsetting for OB.DAAC L3m daily chlorophyll, and about 41 GiB of global granules for NOAA-20 VIIRS alone.

## Verified facts — GHRSST MUR L4 v4.1

| Item | Value |
| --- | --- |
| Collection | `C1996881146-POCLOUD`, short name `MUR-JPL-L4-GLOB-v4.1`, version 4.1, DOI 10.5067/GHGMR-4FJ04 |
| Grid | 17999 lat × 36000 lon (0.01°), 1 time step per granule |
| `analysed_sst` | int16, **kelvin**, scale 0.001, offset 298.15, fill −32768. Convert K to °C after unpacking |
| Also kept | `analysis_error` (K, scale 0.01), `mask` (byte, values 1–31), `sea_ice_fraction` |
| Time | Granule named `YYYYMMDD090000`, valid 21:00 UTC previous day to 21:00 UTC; `time` = seconds since 1981-01-01 |
| Coverage | 2190 of 2191 days; **2026-11-14 not yet published** (latest 2026-11-13) |
| Full granule size | 456–797 MB each, about 1.48 TiB (1518 GiB) for the period, so whole-file download is not an option |
| Subset service | Harmony `sds/HOSS-geographic`: bbox, shape (GeoJSON), temporal, variable, dimension → NetCDF-4 |

## Endpoint / auth

- Data bucket `podaac-ops-cumulus-protected`. An anonymous HEAD returns 303 to a signed CloudFront URL, so HEAD cannot prove whether GET needs login.
- Earthdata OPeNDAP redirected an anonymous request to `/login/urs`, and Harmony requires an Earthdata Login token.
- **Credential needed for the pilot: a NASA Earthdata Login account**, via `~/.netrc` or `EARTHDATA_TOKEN` in `.env`. Not needed yet.

## Consequences for `plan`

- MUR goes through Harmony HOSS bbox/shape subsets. The local polygon mask is still applied.
- Subset response size cannot be predicted from metadata. The plan reports a shape-based range with low/`unknown` confidence until the pilot calibrates it.
- 2026-11-14 is unavailable today. The plan reports it as missing and does not fill it.
