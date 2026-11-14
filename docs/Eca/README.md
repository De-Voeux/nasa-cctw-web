# Eca — collaborator context

**Collaborator:** Arieska Kharzani

**Last updated:** 2026-11-15

This page is the context handoff for my part of SEAGIS. It records what is verified, what is built, what is only a proposal, and what is still blocked. Everything below was produced and checked on 2026-11-14 and 2026-11-15.

## Responsibility and goal

Research and data foundation for SEAGIS: which seaweed species and cultivation regions have real evidence behind them, which NASA products can actually be read at those regions, and what analysis the 2026 challenge asks for.

I own the trail from paper to dataset to any claim shown on the site. I do not own the visual design, the globe, or deployment.

## Scope decisions

Set by the product owner on 2026-11-15. These change the product framing for everyone and still need to be mirrored into [DECISIONS.md](../DECISIONS.md).

| Decision | Status |
| --- | --- |
| The website is the product output for the NASA challenge, replacing the earlier research-only scope | agreed |
| NASA stays the primary data source; third-party products may be combined only if NASA remains the main source, not decoration | agreed |
| Product shape: risk atlas, trend detective, or something between | open |

The third row is the blocker. The repository currently frames the product as a coastal environmental risk atlas, while the challenge asks for a trend-detection and significance-testing tool. The data work below is compatible with either, but the interface work is not.

## What I have done

### 1. Challenge verification

The selected challenge is **Be An Earth System Trend Detective!** (Advanced; Earth Science, Software). It asks for a tool that selects Earth science variables, acquires them for a region, plots a long time series, and reports the rate of change with a significance test. Submission closes Sunday 15 November, 23:59 in the Local Event time zone.

Full record, including the official Resources tab and the five judging criteria: [docs/CHALLENGE_2026.md](../CHALLENGE_2026.md).

### 2. Literature and evidence

Starting point is the systematic review of reported seaweed diseases in aquaculture (Alimin et al. 2026, https://doi.org/10.1007/s10499-026-02486-2), followed by the primary studies it cites.

Findings that constrain what we may claim:

- Tahiluddin & Terzi (2024, https://doi.org/10.3390/plants13152157) monitored *Kappaphycus alvarezii* and *K. striatus* farms in Sibutu, Tawi-Tawi, January–December 2023. Temperature, salinity, pH, currents and wind showed no significant correlation with the ice-ice indicators tested. Rainfall correlated positively with lesion length; ammonium correlated negatively with an intensity indicator.
- Absence of correlation in one study is not evidence that a factor never matters. It does mean no temperature threshold can be presented as validated.
- Organisms isolated from diseased tissue are not automatically proven causes.
- Vairappan et al. (2008, https://doi.org/10.1007/s10811-007-9299-8) concerns epiphytes. The review links it to ice-ice, so the classification needs checking before use as a disease label.
- Nitrate, ammonium, chlorophyll and total nitrogen are different variables and are not interchangeable.

Species and location records collected so far remain unverified leads transcribed in [research/evidence/CANDIDATE_HOST_REGIONS.md](../../research/evidence/CANDIDATE_HOST_REGIONS.md). They are location mentions in the literature, not a verified cultivation map.

### 3. Data access test

I tested access to live endpoints rather than deciding from documentation. Results, variable definitions, units, schemas and failures: [research/data-access/README.md](../../research/data-access/README.md).

What works with no account:

| Source | Content | Format | Speed |
| --- | --- | --- | --- |
| NASA POWER (MERRA-2, plus CERES radiation) | 11 atmospheric variables | CSV, JSON | 1–2 seconds |
| MUR SST v4.1 via NOAA CoastWatch ERDDAP | sea surface temperature | CSV | 2–75 seconds |
| MODIS ocean colour via the same ERDDAP | chlorophyll, Kd490 | CSV | ~10 seconds |

What does not work without an Earthdata account: GPM IMERG through GES DISC (HTTP 302 to login) and the DAAC archives (PO.DAAC, OB.DAAC), which timed out from this network.

### 4. Data pulled

Six Southeast Asian coastal cells, 2003–2024, 18 raw files, three tidied tables and one results table. All of it is committed in [research/data-access/](../../research/data-access/), about 35 MB. Every value came from a live request on 2026-11-15 and was re-downloaded once to confirm it matched; [`research/data-access/checksums.txt`](../../research/data-access/checksums.txt) records SHA-256 hashes for all 23 data files.

The six sites are not a sample of Southeast Asia. They are the specific regions the literature names for *Kappaphycus* and *Eucheuma* cultivation or ice-ice reports, reduced to one regional cell each. Other areas were not tested, and no site is a farm location.

| Site | Country | Latitude | Longitude |
| --- | --- | --- | --- |
| se-sulawesi | Indonesia | −4.0 | 123.0 |
| s-sulawesi | Indonesia | −5.6 | 119.2 |
| sabah | Malaysia | 4.5 | 118.8 |
| tawi-tawi | Philippines | 5.0 | 119.9 |
| bohol | Philippines | 10.0 | 124.5 |
| khanh-hoa | Vietnam | 12.2 | 109.3 |

Every point is a regional grid-cell centroid chosen for comparison, not a farm coordinate. That distinction must survive into the product.

### 5. First trend results

Mann-Kendall for significance and Sen's slope for magnitude, computed on annual means (n = 22) because monthly series are heavily autocorrelated. 72 combinations of site and variable, 39 significant at p < 0.05. Full table: [research/data-access/results/trends.csv](../../research/data-access/results/trends.csv).

Sea surface temperature, °C per year:

| Site | Sen's slope | p |
| --- | --- | --- |
| sabah | +0.043 | <0.001 |
| khanh-hoa | +0.043 | 0.013 |
| tawi-tawi | +0.035 | <0.001 |
| se-sulawesi | +0.028 | 0.024 |
| bohol | +0.027 | 0.002 |
| s-sulawesi | +0.029 | 0.071 |

Precipitation, mm/day per year, is the clearest illustration of the challenge's own point that the same process can trend in opposite directions in different regions:

| Site | Sen's slope | p |
| --- | --- | --- |
| se-sulawesi | +0.132 | 0.007 |
| khanh-hoa | +0.116 | 0.037 |
| tawi-tawi | −0.077 | 0.032 |
| bohol, s-sulawesi, sabah | not significant | 0.06–0.59 |

Air temperature at 2 m is significant and positive at five of six sites; wind speed is significant and negative at three.

Two cautions attached to these numbers. POWER is reanalysis model output on a ~55 × 69 km cell, so it describes regional air, not water at a farm. MUR here is a single 0.01° cell sampled every 30 days, with no spatial averaging.

### 6. Why 22 years and not 5

Cutting the record to 2020–2024 was considered for size. The arithmetic does not support it: 22 years of daily point data is about 550 KB per site, and 5 years is 124 KB. The saving is negligible while the statistical cost is severe. Using the same series and the same test, precipitation at se-sulawesi is +0.148 mm/day per year with p = 0.0068 over 2003–2024, but −0.664 with p = 0.086 over 2020–2024. Five years cannot separate a trend from one La Niña phase.

## Current status

Verified:

- Challenge brief, Resources tab, submission window, judging criteria.
- Live access and real values from POWER, MUR and MODIS ocean colour.
- Trend statistics for 72 site and variable combinations, reproducible from the committed scripts.

Not done, and not to be claimed:

- No prediction model, no training, no baseline, no skill score. Nothing predictive has been built.
- Salinity, currents and nutrients are absent. SMAP and OSCAR need Earthdata Login.
- Chlorophyll coverage at coastal cells is poor: 78 valid months out of 230 at the cell tested.
- No biological threshold or composite weight is validated.
- No pilot region or farm boundary is final.
- Several primary publications have not been read directly.

How to review: open [research/data-access/README.md](../../research/data-access/README.md), check the numbers in [research/data-access/results/trends.csv](../../research/data-access/results/trends.csv), and reread the scripts in `research/data-access/scripts/`. They are plain Python with no third-party packages, so they run anywhere.

## Assumptions, limitations, and blockers

- No threshold, weight, or disease probability enters the product without a citation. Hard constraint.
- Environmental drivers may indicate stress or documented susceptibility. They cannot diagnose disease.
- Forecast, analysis and observation stay distinguishable, with issue time recorded separately from valid time.
- Grid size is not biological precision. The 0.25° composite grid in DECISIONS.md is a working decision this challenge does not require.
- Copernicus and Open-Meteo are not challenge resources and cannot carry the Relevance score.
- MERRA-2 is a model, not a station. Two sites inside one cell return identical values.
- Blocker: the product-shape decision, because the interface cannot be built twice in the remaining hours.

## Next steps

1. Settle the product shape, then update [DECISIONS.md](../DECISIONS.md) and [README.md](../../README.md) in one pass so the repository stops contradicting itself.
2. Build the smallest honest trend view: variable list, region, time series, Sen's slope, p-value, sample size, source and coverage, with the non-significant cases shown rather than hidden.
3. Add one prediction baseline only after the trend view works: climatology first, then a simple model, evaluated on held-out years and reported against the baseline. Label it experimental.
4. If an Earthdata account exists, add SMAP salinity, which the literature cares about more than air temperature.
5. Verify the candidate species table against the source papers, marking each row verified or rejected with a page citation.

See [the collaborator context guide](../COLLABORATOR_CONTEXT.md) for shared guidance.
