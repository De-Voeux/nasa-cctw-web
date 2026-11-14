# Candidate ROI review — 2026-11-15 (geometry v1)

Built with `seagis-extract regions build` for the two pilot regions. All ROIs have `status: candidate`. They are coastal zones near administrative units and **do not show where seaweed is farmed**.

- GeoJSON: [`data/roi/roi_candidates_v1.geojson`](../data/roi/roi_candidates_v1.geojson), 6.2 MB, EPSG:4326
- QA maps and review sheet (gitignored, regenerate with the command): `outputs/qa/roi_PH-TAWI.png`, `outputs/qa/roi_ID-SOUTH-SUL.png`, `outputs/qa/roi_review_manifest.csv`

## Inputs

- Boundaries: geoBoundaries gbOpen PHL ADM3 (2020) and IDN ADM2 (2020), CC BY 3.0 IGO. URLs, commits and SHA-256 are in [`config/boundary_sources.yaml`](../config/boundary_sources.yaml). PHL ADM2 was also downloaded but is not used yet.
- Unit names: [`config/roi_sources.yaml`](../config/roi_sources.yaml). Each name matched exactly one feature.
- Buffer: 5 km seaward (agreed 2026-11-15), computed in UTM 50N or 50S.

## Method

1. Buffer each admin unit 5 km.
2. Subtract the land mask, which is the union of all admin polygons from the same file near the unit.
3. For the archipelagic regencies Pangkep and Selayar, keep only the polygon parts near the unit's largest landmass (agreed 2026-11-15). The distance limits sit in natural gaps measured on the source polygons. **Pangkep: 60 km.** The nearest 45 of 117 parts lie within 57.5 km, and the next one is at 118.7 km, so the Spermonde group is kept. **Selayar: 35 km.** The nearest 16 of 98 parts lie within 30.0 km, and the next one is at 45.8 km, so Takabonerate and the southern islands are dropped. Dropped islands still count as land and as neighbouring coast.
4. Split the sea by nearest coast among the selected units and their unselected admin neighbours. Sibling ROIs therefore never overlap, and no ROI takes water off a neighbouring unit's coast (for example, Takalar no longer extends into the waters off Makassar).

## Results

| Region | Subregion | Area km² | Before split | Parts | Note |
| --- | --- | ---: | ---: | ---: | --- |
| PH-TAWI | bongao | 277.9 | 330.0 | 1 | Proposed pilot unit |
| PH-TAWI | sitangkai | 656.6 | 742.6 | 3 | Western circles sit around tiny islets |
| PH-TAWI | sibutu | 375.2 | 462.2 | 1 | |
| ID-SOUTH-SUL | takalar | 654.0 | 699.0 | 1 | Proposed pilot unit; includes the Tanakeke islands |
| ID-SOUTH-SUL | jeneponto | 352.8 | 399.5 | 1 | |
| ID-SOUTH-SUL | pangkep | 1602.1 | 1674.8 | 4 | Spermonde group only; bbox 118.91–119.60°E, 5.00–4.44°S (was 117.0–119.6°E) |
| ID-SOUTH-SUL | selayar | 1496.6 | 1507.4 | 3 | Main island and nearby islets; bbox 120.22–120.61°E, 6.76–5.70°S (Takabonerate dropped) |

## Known limitations / to review

- Coastline accuracy comes from the admin polygons (NAMRIA/PSA, BPS). They have not been compared with an independent coastline such as OSM. The MUR `mask` will be compared during the pilot.
- Pangkep and Selayar are limited by distance from the main landmass, not by study evidence. If a paper places farms on the dropped islands (for example Takabonerate), raise the limit in `config/roi_sources.yaml`.
- Parent-level (province) ROIs are not built yet. The other 16 regions still need unit names, boundary files (MY, VN), and sources for the study-specific coasts.
- Reprojection leaves land/zone slivers of tens of m², far below one MUR cell (~1 km²).
- Visual review: fill in `review_status`, `reviewer` and `review_date` in the review sheet.
