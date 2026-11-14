# Methodology guardrails

## What an assessment means

An assessed cell describes regional environmental conditions for a selected seaweed species under reviewed rules. It does not identify a farm, diagnose infection, certify safety, or establish legal or commercial suitability.

## Spatial support

The working composite grid is 0.25° latitude × 0.25° longitude, aligned from −180° longitude and −90° latitude in EPSG:4326. Cell IDs must be deterministic. Land has no ocean risk value. Mixed coastal cells require documented valid-water and source coverage tests; inadequate cells are unassessable. Individual source layers retain native resolution and their original semantics.

## Time and lineage

Keep historical observation, analysis/nowcast, and forecast separate. Each value needs valid time, issue time where applicable, ingestion time, source product and version, units, depth, spatial support, and quality/coverage. Do not blend providers by variable name or count related products as independent corroboration without checking lineage.

## Severity and confidence

Store stress level separately from evidence confidence. An assessed result must include risk drivers, missing factors, rule version, and citations. Missing mandatory inputs or inactive rules cannot produce a favorable cell. Never invent weights, thresholds, or disease probabilities.

## Disease context

Literature-linked disease or syndrome concerns are explanatory context only. If evidence is insufficient, show “disease susceptibility not assessable.” Satellite and model signals cannot establish pathogen presence.
