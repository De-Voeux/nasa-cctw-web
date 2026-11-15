# 2026 challenge: verified brief

Status: verified against the official NASA Space Apps site on 2026-11-14 (Asia/Jakarta), by reading the rendered challenge page and its Resources tab. Everything below is either quoted or directly derived from that page. Items marked "not stated" are genuinely absent from the official text, not missing research.

This file replaces the open question "confirm the exact 2026 Space Apps challenge" in [DECISIONS.md](DECISIONS.md#open-decisions) with a verified answer. It does not by itself authorise product decisions.

## Event

| Item | Value |
| --- | --- |
| Event | 2026 NASA Space Apps Challenge |
| Dates | 14–15 November 2026 |
| Project submission opens | Saturday 14 November, 09:00 in the Local Event's time zone |
| Project submission closes | Sunday 15 November, 23:59 in the Local Event's time zone |
| Total challenges in 2026 | 14 |

Submission times are from the [Project Submission Guide](https://www.spaceappschallenge.org/resources/project-submission-guide/). Teams registered for the Universal Event use the Team Owner's local time instead. Local judging times can differ and are set by each Local Lead.

## Challenge identity

| Field | Value |
| --- | --- |
| Title | Be An Earth System Trend Detective! |
| Difficulty | Advanced |
| Subjects | Earth Science, Software |
| Page | https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/ |
| Resources tab | Same page, `?tab=resources` |

The title used in earlier planning documents, "Be an Earth Detective", is not a 2026 challenge title. The official title includes "System" and "Trend".

## What the challenge asks for

The core statement, quoted:

> Change is always occurring in the Earth's interconnected environmental system, and when it runs in a consistent direction – rising or falling, increasing or decreasing, thickening or thinning – measured variables reflect it. But a measured Earth science data variable can trend one way in one region and the opposite way in another, even when the same process drives both. The multitude of Earth science data variables makes it difficult to select variables that could indicate change, and to then perform an analysis on the selected variables. Your challenge is to create a tool that can select variables measured by Earth science missions or produced by Earth science models, visualize how they change over time, and determine what is changing, where it is changing, how much it is changing, and if these changes are what scientists call "significant."

The Objectives section names four elements a successful response should bring together:

1. Identify Earth science variables worth investigating for trends.
2. Acquire those variables for a particular region.
3. Generate and visualise a time series over a period long enough for statistical analysis.
4. Perform a basic statistical analysis of the rate of change and test significance using methods such as a t-test, the Mann-Kendall test, or confidence intervals.

The page adds that a response doing both visualisation and analysis meets the full scope, and that demonstration examples are "highly useful".

Named examples of data sources in the brief: MODIS, OMI, AIRS and GPM as instruments; MERRA-2 and GLDAS as models. These are examples, not a required list.

Explicitly optional: audience-specific framing, a guided question flow, demonstration examples, and the use of "SI" (the brief's own wording) to suggest variables. Suggested but not required: daily or monthly data, removal of the seasonal cycle, linear trends as a starting point.

## Official Resources tab

NASA data and resources:

| Resource | URL | What it is per the page |
| --- | --- | --- |
| Giovanni | https://giovanni.gsfc.nasa.gov/ | Menus of many data variables; time-series generation and download |
| Hydrology Time Series | https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Time%20Series | Time series with hydrological data |
| AppEEARS | https://appeears.earthdatacloud.nasa.gov/ | Access and transform geospatial data from federal archives; includes time-series generation |
| NOAA Climate Data Online | https://www.ncei.noaa.gov/cdo-web/ | Historical weather and climate archive with a mapping tool (non-NASA) |
| NTRS SeaWiFS chlorophyll paper | https://ntrs.nasa.gov/api/citations/20090042747/downloads/20090042747.pdf | Research article demonstrating time-series creation and significance testing |

Space agency partner resources (all non-NASA):

| Resource | URL | Provider |
| --- | --- | --- |
| KNMI Climate Explorer | https://climexp.knmi.nl/ | KNMI |
| Statistical test methods for trends | https://medium.com/@snp.kriss/statistical-test-methods-to-detect-trends-in-time-series-data-b361a0ec530b | Secondary, not peer reviewed |
| A Comprehensive Guide to Statistical Significance | https://www.statsig.com/perspectives/a-comprehensive-guide-to-statistical-significance | Secondary, vendor blog |
| RADARSAT Constellation Mission data | https://donnees-data.asc-csa.gc.ca/en/dataset/rcm | CSA |
| Geo.ca | http://geo.ca/ | CSA |
| SWOT mission information | https://www.asc-csa.gc.ca/eng/satellites/swot/ | CSA |
| Monitoring ecosystems from space | https://www.asc-csa.gc.ca/eng/satellites/everyday-lives/monitoring-and-protecting-our-ecosystems-from-space.asp | CSA |
| SAR Python tutorial | https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial | CSA |

The Resources tab carries a standard disclaimer that NASA does not endorse non-U.S. Government sites.

## Judging criteria

Five criteria, each scored 1–5, applied from Local Event judging through Executive Judging:

| Criterion | What judges look for |
| --- | --- |
| Impact | Significance of the problem addressed and reach of the effect |
| Creativity | Originality and inventiveness of the approach |
| Validity | Scientific soundness, technical feasibility, usability |
| Relevance | Direct response to the chosen challenge and meaningful integration of NASA data, not a superficial addition |
| Presentation | Clarity and structure of the story, demo included |

Source: https://www.spaceappschallenge.org/resources/judging-awards-guide/

Eligibility for global judging requires responding to one official challenge and every team member being registered under the same Local or Universal Event, with 1–6 members.

## What the brief does not say

These absences matter as much as the requirements, because they block claims we might otherwise be tempted to make.

- No required dataset, product, variable, region, or technology stack.
- No requirement that the tool cover oceans. Land, atmosphere and ocean are all allowed.
- No requirement to forecast anything. The challenge is about historical trend detection and significance.
- No requirement for a species model, a risk score, or a map. Visualisation is required, a map is not.
- No statement that the tool must produce a single verdict; showing that a trend is not significant is a valid, expected outcome.
- No deadline for a live demo beyond the submission close on 15 November.

## Fit with this repository

Observed, not yet agreed:

- The repository's current product framing is a coastal environmental risk atlas for seaweed aquaculture. That framing is not the challenge. The challenge is a trend-detection and significance-testing tool.
- The two are compatible only if the deliverable changes shape: variable selection, region selection, long time series, rate of change, and a stated significance test must be the primary surface. Species and environmental-stress context can remain as the motivating example, not as the output.
- Copernicus Marine and Open-Meteo are not challenge resources. They may remain supporting context, but they cannot carry the "meaningful NASA data integration" that Relevance is judged on.
- The 0.25° composite risk grid in [DECISIONS.md](DECISIONS.md) is not required by this challenge and competes for build time with the trend tool.
- The scaffold currently shows no computed trend, no statistics, and no NASA-derived series, so Relevance and Validity would score poorly as it stands.

These are assessments of fit, not decisions. Any change to the product framing belongs in [DECISIONS.md](DECISIONS.md) after the team agrees.

## References

- Challenge page: https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/
- 2026 challenge list: https://www.spaceappschallenge.org/2026/challenges/
- Project submission guide: https://www.spaceappschallenge.org/resources/project-submission-guide/
- Judging and awards guide: https://www.spaceappschallenge.org/resources/judging-awards-guide/
- Event home: https://www.spaceappschallenge.org/2026/
