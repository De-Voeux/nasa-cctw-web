# MVP roadmap

## 0. Evidence and data discovery

- Confirm the challenge and at least one NASA resource from its official Resources tab.
- Follow the [research scope](RESEARCH_SCOPE.md): verify taxa, natural versus cultivated distribution, disease/syndrome records, environmental needs, cultivation impacts, and the historical data inventory.
- Check every entry in the [candidate host and region table](../research/evidence/CANDIDATE_HOST_REGIONS.md) against the original paper before using it in the product.
- Select a source-verified cultivated species and region.
- Review species/stressor literature and verify provider products at that region.
- Assess whether a prediction target has labelled data, a simple baseline, and held-out historical validation; otherwise keep it outside the MVP.

## 1. Data foundation

- Build provider adapters, unit/depth/time QA, provenance, and failure states.
- Build deterministic 0.25° ocean cells and coastal coverage tests.
- Keep source-native layers and composite grid distinct.

## 2. Initial atlas

- Replace this static shell with live country/island and species controls.
- Show real environmental layers and inspectable cells with time, quality, and citations.
- Report unavailable, stale, and unassessable states explicitly.

## 3. Reviewed assessment

- Activate only evidence-backed species rules.
- Produce reproducible stress levels with drivers and confidence.
- Keep disease context separate from environmental stress.

## 4. Challenge demo

- Add meaningful NASA historical trend/anomaly analysis if appropriate to the chosen challenge.
- Prepare a public demo and submission with resource and AI-use disclosure.

## Minimum acceptance checks

- Land never receives ocean risk; missing mandatory inputs never yield favorable.
- Each assessed cell has valid time, source lineage, rule version, and drivers.
- Native/coarse spatial support is not visually exaggerated.
- Species changes affect outcomes only through reviewed species-specific rules.
- Forecasts, analyses, and observations remain clearly labelled.
- No UI copy claims pathogen detection or unsupported disease probability.
