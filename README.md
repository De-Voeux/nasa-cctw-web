# SEAGIS — NASA Space Apps web atlas

SEAGIS is a proposed species-aware coastal environmental risk atlas for seaweed aquaculture. It aims to combine NASA Earth observations, Copernicus Marine ocean products, and Open-Meteo weather data to explain regional water stress. The map must show source coverage, time, uncertainty, and evidence behind every assessed cell.

This repository is an **initial scaffold**, not a working environmental assessment. No live datasets, scientific thresholds, or disease predictions are shipped yet.

## Product scope

- Browser-based atlas for broad coastal regions and islands, without farm coordinates or accounts.
- Species-aware environmental layers and an explainable composite stress layer.
- Working MVP composite grid: 0.25° × 0.25° ocean cells. Native source resolution remains visible for individual layers.
- Separate historical observation, analysis/nowcast, and forecast time categories.
- NASA data must be ingested and used meaningfully for the Space Apps submission.
- No IoT, pathogen detection, disease diagnosis, or unsupported disease probabilities.

The first MVP candidate species is *Kappaphycus alvarezii*. A new [candidate host and region table](research/evidence/CANDIDATE_HOST_REGIONS.md) also lists *Eucheuma denticulatum*, *Gracilaria verrucosa*, *Kappaphycus* spp., and *Kappaphycus striatus* from user-provided research notes. Those records lack the paper citation and remain **unverified leads**, not approved map coverage or active disease rules. The target region, NASA challenge, exact dataset products, and citation-backed thresholds remain open decisions.

## Run the starter page

Open `index.html` in a browser, or serve this directory with any static HTTP server. The page is a product shell and deliberately displays **Insufficient data** rather than sample risk results.

## Repository map

- `index.html`, `styles.css`, `app.js`: accessible static UI starter.
- `docs/DECISIONS.md`: agreed direction, working choices, and open decisions.
- `docs/METHODOLOGY.md`: scientific and map semantics.
- `docs/DATA_CATALOG.md`: product verification template.
- `docs/ROADMAP.md`: implementation order and acceptance criteria.
- `docs/RESEARCH_SCOPE.md`: ten-part research checklist, from challenge fit to prediction feasibility.
- `research/evidence/CANDIDATE_HOST_REGIONS.md`: unverified species, location, and ice-ice leads awaiting source checks.
- `contracts/assessment.schema.json`: initial assessment output contract.
- `research/evidence/README.md`: literature review protocol and inactive rule guidance.

## Implementation path

1. Confirm the selected 2026 NASA Space Apps challenge, its research question, and its official resource list.
2. Verify taxon names, cultivation locations, ice-ice reports, and environmental evidence against the cited papers; follow the [research scope](docs/RESEARCH_SCOPE.md).
3. Verify one coastal region and exact NASA, Copernicus, and Open-Meteo products, including access and quality metadata.
4. Implement ingestion, source lineage, ocean masking, and deterministic 0.25° cells.
5. Render real environmental layers and inspectable cell details.
6. Activate only literature-reviewed species rules; report insufficient data when coverage or evidence is inadequate.
7. Add NASA-derived historical trend or anomaly analysis where the selected challenge requires it, and evaluate prediction feasibility before making predictive claims.

## Scientific boundary

Environmental conditions may indicate stress or documented susceptibility context. They cannot diagnose seaweed disease or establish a disease occurrence probability without biological validation data. A favorable cell does not identify a farm or certify cultivation suitability.

## Source brief

This scaffold follows the user-provided `Seagis NASA.md` brief dated 14 November 2026. Its proposed items are recorded as proposals here, rather than silently treated as requirements. External scientific, dataset, and challenge details need verification before use.
