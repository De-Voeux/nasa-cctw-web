# Decisions and open questions

Source: user-provided `Seagis NASA.md`, last discussion update 14 November 2026. This file distinguishes agreed direction from proposals; it is not a claim that the research is complete.

| Topic | Status | Current direction |
| --- | --- | --- |
| Product | Agreed | Web-based, species-aware coastal environmental atlas |
| Data providers | Agreed | NASA, Copernicus Marine, Open-Meteo |
| IoT | Agreed | Excluded from hackathon version |
| Spatial view | Agreed | Country, island, and broad coastal region; no farm pins |
| Composite grid | Working decision | Deterministic 0.25° × 0.25° EPSG:4326 ocean cells |
| Source layers | Agreed | Preserve native resolution, time, and provenance |
| Stress labels | Proposed | Favorable, moderate, elevated, insufficient data |
| First species | Recommended | *Kappaphycus alvarezii* |
| First stressors | Proposed | Temperature, salinity disturbance, water movement |
| Technology | Recommended | Next.js/MapLibre, Python workers, PostGIS or equivalent |

## Open decisions

1. Confirm the exact 2026 Space Apps challenge, its resource list, rules, and deadline.
2. Review full scientific literature before activating species thresholds or disease associations.
3. Verify exact dataset IDs, versions, units, depth, grid, cadence, latency, licence, and quality fields.
4. Select source-verified cultivation regions and define coastal region geometry.
5. Test whether 0.25° cells adequately represent those coastal waters.
6. Define coverage thresholds, assessment windows, severity taxonomy, and composite logic from evidence.
7. Validate any future environmental alert against independent records.

Decisions should be dated and explained when updated.
